import os
import re

# Must be set before any oauth library code runs
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

from pathlib import Path
from functools import wraps
from flask import (Flask, render_template, redirect, url_for, session,
                   request, jsonify, Response)
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request

from gmail_client import GmailClient
from progress import ProgressManager

app = Flask(__name__)

_key_file = Path('.secret_key')
if not _key_file.exists():
    _key_file.write_bytes(os.urandom(24))
app.secret_key = _key_file.read_bytes()

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
CREDENTIALS_FILE = 'credentials.json'


@app.template_filter('filesize')
def filesize_filter(n):
    n = float(n or 0)
    for unit in ['B', 'KB', 'MB', 'GB']:
        if n < 1024:
            return f'{n:.1f} {unit}'
        n /= 1024
    return f'{n:.1f} TB'


@app.template_test('previewable_mime')
def previewable_mime_test(mime_type):
    return mime_type.startswith('image/') or mime_type == 'application/pdf'


def _token_path(email):
    safe = re.sub(r'[^\w]', '_', email)
    return Path(f'token_{safe}.json')


def get_credentials(email):
    path = _token_path(email)
    if not path.exists():
        return None
    creds = Credentials.from_authorized_user_file(str(path), SCOPES)
    if not creds.valid and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            path.write_text(creds.to_json())
        except Exception:
            return None
    return creds if creds.valid else None


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        email = session.get('email')
        if not email or not get_credentials(email):
            session.clear()
            return redirect(url_for('auth'))
        return f(*args, **kwargs)
    return decorated


def get_client():
    return GmailClient(get_credentials(session['email']))


def get_progress():
    return ProgressManager(session['email'])


# ── Auth routes ──────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return redirect(url_for('triage') if session.get('email') else url_for('auth'))


@app.route('/auth')
def auth():
    return render_template('auth.html')


@app.route('/auth/start')
def auth_start():
    flow = Flow.from_client_secrets_file(
        CREDENTIALS_FILE, scopes=SCOPES,
        redirect_uri=url_for('oauth_callback', _external=True)
    )
    auth_url, state = flow.authorization_url(
        access_type='offline', prompt='consent', code_challenge_method='S256'
    )
    session['oauth_state'] = state
    session['code_verifier'] = flow.code_verifier
    return redirect(auth_url)


@app.route('/oauth/callback')
def oauth_callback():
    if 'error' in request.args:
        return redirect(url_for('auth'))

    flow = Flow.from_client_secrets_file(
        CREDENTIALS_FILE, scopes=SCOPES,
        state=session.get('oauth_state'),
        redirect_uri=url_for('oauth_callback', _external=True)
    )
    flow.fetch_token(authorization_response=request.url,
                     code_verifier=session.get('code_verifier'))
    creds = flow.credentials

    from googleapiclient.discovery import build
    svc = build('gmail', 'v1', credentials=creds)
    email = svc.users().getProfile(userId='me').execute()['emailAddress']

    _token_path(email).write_text(creds.to_json())
    session['email'] = email
    return redirect(url_for('triage'))


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth'))


# ── Triage ───────────────────────────────────────────────────────────────────

@app.route('/triage')
@require_auth
def triage():
    p = get_progress()
    summary = p.get_summary()

    if not p.has_email_list():
        return render_template('triage.html', state='no_list', summary=summary)

    ids = p.message_ids
    if not ids:
        return render_template('triage.html', state='empty', summary=summary)

    idx = p.current_index
    msg_id = ids[idx]
    decision = p.get_decision(msg_id)

    try:
        c = get_client()
        msg = c.get_message_summary(msg_id)
        thread = c.get_thread(msg['thread_id'])
    except Exception as e:
        return render_template('triage.html', state='error', error=str(e), summary=summary)

    return render_template('triage.html',
        state='card',
        msg=msg,
        thread=thread,
        idx=idx,
        total=len(ids),
        decision=decision,
        summary=summary,
    )


@app.route('/navigate', methods=['POST'])
@require_auth
def navigate():
    p = get_progress()
    direction = request.form.get('direction')
    jump_to = request.form.get('jump_to', '').strip()

    if jump_to.isdigit():
        p.set_index(int(jump_to) - 1)
    elif direction == 'next':
        p.advance()
    elif direction == 'prev':
        p.retreat()

    return redirect(url_for('triage'))


# ── Fetch ────────────────────────────────────────────────────────────────────

@app.route('/fetch', methods=['POST'])
@require_auth
def fetch():
    p = get_progress()
    threshold_mb = request.form.get('threshold_mb', '').strip()
    if threshold_mb:
        try:
            p.update_settings(threshold_mb=float(threshold_mb))
        except ValueError:
            pass

    c = get_client()
    ids = c.list_large_messages(int(p.threshold_mb * 1024 * 1024), label_id=p.label_id or None)
    p.set_message_ids(ids)
    return redirect(url_for('triage'))


# ── Settings ─────────────────────────────────────────────────────────────────

@app.route('/settings', methods=['GET', 'POST'])
@require_auth
def settings():
    p = get_progress()
    if request.method == 'POST':
        threshold = request.form.get('threshold_mb', '5').strip()
        try:
            threshold = float(threshold)
        except ValueError:
            threshold = 5.0
        p.update_settings(
            threshold_mb=threshold,
            dry_run='dry_run' in request.form,
            download_path=request.form.get('download_path', 'downloads'),
            download_sort=request.form.get('download_sort', 'sender_date'),
            label_id=request.form.get('label_id', ''),
            label_name=request.form.get('label_name', 'All Mail'),
        )
        return redirect(url_for('settings'))
    try:
        labels = get_client().list_labels()
    except Exception:
        labels = [{'id': '', 'name': 'All Mail'}]
    return render_template('settings.html', summary=p.get_summary(), labels=labels)


@app.route('/next-undecided', methods=['POST'])
@require_auth
def next_undecided():
    p = get_progress()
    idx = p.next_undecided()
    if idx is not None:
        p.set_index(idx)
    return redirect(url_for('triage'))


@app.route('/reset', methods=['POST'])
@require_auth
def reset():
    p = get_progress()
    if request.form.get('mode') == 'skipped':
        p.reset_skipped()
    else:
        p.reset_all()
    return redirect(url_for('triage'))


# ── Preview & actions ────────────────────────────────────────────────────────

@app.route('/preview/<msg_id>/<att_id>')
@require_auth
def preview(msg_id, att_id):
    mime = request.args.get('mime', 'application/octet-stream')
    data = get_client().get_attachment_data(msg_id, att_id)
    return Response(data, mimetype=mime)


@app.route('/action', methods=['POST'])
@require_auth
def action():
    data = request.get_json()
    action_type = data.get('action')
    msg_id = data.get('msg_id')
    p = get_progress()
    c = get_client()
    dry_run = p.dry_run

    try:
        if action_type == 'download':
            paths = []
            for att in data.get('attachments', []):
                path = c.download_attachment(
                    msg_id, att['id'], att['filename'],
                    data.get('sender', ''), data.get('date', ''),
                    dry_run=dry_run,
                    base_path=p.download_path,
                    sort_by=p.download_sort,
                    mime_type=att.get('mime_type', ''),
                    subject=data.get('subject', ''),
                )
                paths.append(path)
            p.record_decision(msg_id, 'downloaded')
            if data.get('advance', False):
                p.advance()
            return jsonify(ok=True, paths=paths, dry_run=dry_run)

        elif action_type == 'delete_message':
            result = c.delete_message(msg_id, dry_run=dry_run)
            p.record_decision(msg_id, 'deleted_message')
            p.advance()
            return jsonify(ok=True, **result)

        elif action_type == 'delete_thread':
            result = c.delete_thread(data.get('thread_id'), dry_run=dry_run)
            p.record_decision(msg_id, 'deleted_thread')
            p.advance()
            return jsonify(ok=True, **result)

        elif action_type == 'detach':
            keep_original = data.get('keep_original', False)
            result = c.detach_attachments(msg_id, dry_run=dry_run, keep_original=keep_original)
            p.record_decision(msg_id, 'detached')
            p.advance()
            return jsonify(ok=True, **result)

        elif action_type == 'skip':
            p.record_decision(msg_id, 'skipped')
            p.advance()
            return jsonify(ok=True)

        return jsonify(ok=False, error='unknown action'), 400

    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500


@app.route('/batch/step', methods=['POST'])
@require_auth
def batch_step():
    data = request.get_json()
    idx = data.get('idx', 0)
    p = get_progress()
    ids = p.message_ids

    if idx >= len(ids):
        return jsonify(done=True)

    msg_id = ids[idx]

    if p.get_decision(msg_id):
        return jsonify(skipped=True)

    c = get_client()
    dry_run = p.dry_run

    try:
        msg = c.get_message_summary(msg_id)
        paths = []
        for att in msg.get('attachments', []):
            path = c.download_attachment(
                msg_id, att['id'], att['filename'],
                msg.get('from', ''), msg.get('date', ''),
                dry_run=dry_run,
                base_path=p.download_path,
                sort_by=p.download_sort,
                mime_type=att.get('mime_type', ''),
                subject=msg.get('subject', ''),
            )
            paths.append(path)

        strip_result = c.detach_attachments(msg_id, dry_run=dry_run, keep_original=False)
        p.record_decision(msg_id, 'batch_processed')

        return jsonify(
            ok=True,
            subject=msg.get('subject', '(no subject)'),
            sender=msg.get('from', ''),
            paths=paths,
            stripped=strip_result.get('removed', 0),
            dry_run=dry_run,
        )
    except Exception as e:
        return jsonify(ok=False, error=str(e), subject='unknown')


@app.route('/browse-folder')
@require_auth
def browse_folder():
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.wm_attributes('-topmost', 1)
        folder = filedialog.askdirectory(title='Select download folder')
        root.destroy()
        return jsonify(path=folder.replace('/', '\\') if folder else '')
    except Exception as e:
        return jsonify(path='', error=str(e))


if __name__ == '__main__':
    import threading
    import webbrowser
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        threading.Timer(1.0, lambda: webbrowser.open('http://localhost:5000')).start()
    app.run(debug=True, port=5000)
