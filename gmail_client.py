import base64
import re
from pathlib import Path
from email.utils import parsedate_to_datetime
from googleapiclient.discovery import build


class GmailClient:
    def __init__(self, credentials):
        self.service = build('gmail', 'v1', credentials=credentials)

    def list_labels(self):
        result = self.service.users().labels().list(userId='me').execute()
        all_labels = result.get('labels', [])

        system_order = {'INBOX': 'Inbox', 'SENT': 'Sent', 'DRAFT': 'Drafts',
                        'SPAM': 'Spam', 'TRASH': 'Trash'}
        system_skip  = {'UNREAD', 'STARRED', 'IMPORTANT', 'CHAT',
                        'CATEGORY_PERSONAL', 'CATEGORY_SOCIAL', 'CATEGORY_PROMOTIONS',
                        'CATEGORY_UPDATES', 'CATEGORY_FORUMS'}

        labels = [{'id': '', 'name': 'All Mail'}]
        for sys_id, sys_name in system_order.items():
            if any(l['id'] == sys_id for l in all_labels):
                labels.append({'id': sys_id, 'name': sys_name})

        user_labels = sorted(
            [l for l in all_labels if l.get('type') == 'user' and l['id'] not in system_skip],
            key=lambda l: l['name'].lower(),
        )
        labels.extend({'id': l['id'], 'name': l['name']} for l in user_labels)
        return labels

    def list_large_messages(self, min_size_bytes, label_id=None):
        min_mb = max(1, int(min_size_bytes / (1024 * 1024)))
        query = f'larger:{min_mb}m has:attachment'
        messages = []
        page_token = None
        while True:
            kwargs = {'userId': 'me', 'q': query, 'maxResults': 500}
            if label_id:
                kwargs['labelIds'] = [label_id]
            if page_token:
                kwargs['pageToken'] = page_token
            result = self.service.users().messages().list(**kwargs).execute()
            messages.extend(result.get('messages', []))
            page_token = result.get('nextPageToken')
            if not page_token:
                break
        return [m['id'] for m in messages]

    def get_message_summary(self, msg_id):
        msg = self.service.users().messages().get(
            userId='me', id=msg_id, format='full'
        ).execute()
        return self._parse_message(msg)

    def get_thread(self, thread_id):
        thread = self.service.users().threads().get(
            userId='me', id=thread_id, format='full'
        ).execute()
        return [self._parse_message(m) for m in thread.get('messages', [])]

    def _parse_message(self, msg):
        headers = {h['name'].lower(): h['value'] for h in msg['payload'].get('headers', [])}
        body = {'text': '', 'html': ''}
        attachments = []
        self._extract_parts(msg['payload'], attachments, body, set())
        return {
            'id': msg['id'],
            'thread_id': msg['threadId'],
            'size': msg.get('sizeEstimate', 0),
            'subject': headers.get('subject', '(no subject)'),
            'from': headers.get('from', ''),
            'to': headers.get('to', ''),
            'cc': headers.get('cc', ''),
            'date': headers.get('date', ''),
            'snippet': msg.get('snippet', ''),
            'body_text': body['text'][:3000] or body['html'][:3000],
            'attachments': attachments,
        }

    def _extract_parts(self, payload, attachments, body, seen_att_ids):
        mime = payload.get('mimeType', '')
        raw = payload.get('body', {}).get('data', '')
        att_id = payload.get('body', {}).get('attachmentId')
        filename = payload.get('filename', '')

        if att_id and filename and att_id not in seen_att_ids:
            seen_att_ids.add(att_id)
            attachments.append({
                'id': att_id,
                'filename': filename,
                'mime_type': mime,
                'size': payload.get('body', {}).get('size', 0),
            })
        elif mime == 'text/plain' and raw and not body['text']:
            body['text'] = base64.urlsafe_b64decode(raw).decode('utf-8', errors='replace')
        elif mime == 'text/html' and raw and not body['html']:
            body['html'] = base64.urlsafe_b64decode(raw).decode('utf-8', errors='replace')

        for part in payload.get('parts', []):
            self._extract_parts(part, attachments, body, seen_att_ids)

    def get_attachment_data(self, msg_id, att_id):
        result = self.service.users().messages().attachments().get(
            userId='me', messageId=msg_id, id=att_id
        ).execute()
        return base64.urlsafe_b64decode(result['data'])

    def download_attachment(self, msg_id, att_id, filename, sender, date_str,
                            dry_run=False, base_path='downloads', sort_by='sender_date',
                            mime_type='', subject=''):
        sender_name  = _safe_path(_extract_sender_name(sender))[:40] or 'unknown'
        date         = _parse_date(date_str)
        year         = date[:4] if len(date) >= 4 else 'unknown'
        month        = date[5:7] if len(date) >= 7 else 'unknown'
        ftype        = _file_type(filename, mime_type)
        safe_subject = _safe_path(subject)[:60] or 'no subject'

        if sort_by == 'year_sender':
            parts = (year, sender_name)
        elif sort_by == 'sender':
            parts = (sender_name,)
        elif sort_by == 'year_month_sender':
            parts = (year, month, sender_name)
        elif sort_by == 'type_sender':
            parts = (ftype, sender_name)
        elif sort_by == 'sender_subject':
            parts = (sender_name, safe_subject)
        else:  # sender_date (default)
            parts = (sender_name, date)

        dest_dir = Path(base_path).joinpath(*parts)
        dest_path = _unique_path(dest_dir / filename)

        if dry_run:
            return str(dest_path)

        data = self.get_attachment_data(msg_id, att_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(data)
        return str(dest_path)

    def delete_message(self, msg_id, dry_run=False):
        if not dry_run:
            self.service.users().messages().trash(userId='me', id=msg_id).execute()
        return {'msg_id': msg_id, 'dry_run': dry_run}

    def delete_thread(self, thread_id, dry_run=False):
        if not dry_run:
            self.service.users().threads().trash(userId='me', id=thread_id).execute()
        # Get count for the confirmation message
        thread = self.service.users().threads().get(
            userId='me', id=thread_id, format='minimal'
        ).execute()
        count = len(thread.get('messages', []))
        return {'thread_id': thread_id, 'count': count, 'dry_run': dry_run}

    def detach_attachments(self, msg_id, dry_run=False, keep_original=False):
        import email as _email_lib

        raw_result = self.service.users().messages().get(
            userId='me', id=msg_id, format='raw'
        ).execute()

        thread_id = raw_result['threadId']
        label_ids = raw_result.get('labelIds', [])
        raw_bytes = base64.urlsafe_b64decode(raw_result['raw'])

        msg = _email_lib.message_from_bytes(raw_bytes)
        removed = _strip_attachments(msg)

        if removed == 0:
            return {'removed': 0, 'dry_run': dry_run, 'keep_original': keep_original}

        if dry_run:
            return {'removed': removed, 'dry_run': True, 'keep_original': keep_original}

        new_raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        self.service.users().messages().insert(
            userId='me',
            internalDateSource='dateHeader',
            body={'raw': new_raw, 'labelIds': label_ids, 'threadId': thread_id},
        ).execute()

        if not keep_original:
            self.service.users().messages().trash(userId='me', id=msg_id).execute()

        return {'removed': removed, 'dry_run': False, 'keep_original': keep_original}


def _strip_attachments(msg):
    import re

    inline_map = {}  # cid → filename
    att_names  = []  # regular attachment filenames (no CID)
    _collect_parts(msg, inline_map, att_names)
    if not inline_map and not att_names:
        return 0

    # Build CID lookup: full CID and local part before @ for fuzzy matching
    cid_lookup = {}
    for cid, name in inline_map.items():
        cid_lookup[cid] = name
        local = cid.split('@')[0]
        if local:
            cid_lookup[local] = name

    # Pass 1 — replace <img src="cid:..."> with text badges, track which names were replaced
    replaced_names = set()

    def img_badge(m):
        tag   = m.group(0)
        src_m = re.search(r'src=["\']cid:([^"\']+)["\']', tag, re.IGNORECASE)
        if src_m:
            val  = src_m.group(1).strip()
            name = cid_lookup.get(val) or cid_lookup.get(val.split('@')[0]) or val.split('@')[0] or 'image'
            replaced_names.add(name)
        else:
            name = 'image'
        return (
            '<span style="display:inline-block;border:1px solid #ccc;border-radius:3px;'
            'padding:1px 6px;background:#f5f5f5;color:#555;font-family:monospace;font-size:12px;">'
            f'&#128247;&nbsp;{name}</span>'
        )

    _replace_cid_images(msg, img_badge)

    # Pass 2 — build footer: regular attachments + any CID items not found in HTML (e.g. PDFs with Content-ID)
    unreplaced = [n for n in inline_map.values() if n not in replaced_names]
    footer_names = att_names + unreplaced
    if footer_names:
        _add_att_footer(msg, footer_names)

    return _remove_parts(msg)


def _collect_parts(payload, inline_map, att_names):
    # TODO: duplicate inline images — the same image (e.g. a signature logo) can appear
    # in multiple messages within a thread, AND possibly multiple times within a single
    # message's MIME structure. Not yet clear which case the user is hitting.
    # Options: deduplicate by (filename + size) within a message, across a thread, or both.
    # Need to reproduce and confirm before implementing. See conversation around this point.
    if payload.is_multipart():
        for part in payload.get_payload():
            _collect_parts(part, inline_map, att_names)
        return
    filename = payload.get_filename()
    if not filename:
        return
    cid = payload.get('Content-ID', '').strip().strip('<>')
    if cid:
        inline_map[cid] = filename
    else:
        att_names.append(filename)


def _replace_cid_images(msg, img_badge):
    import re
    if msg.is_multipart():
        for part in msg.get_payload():
            _replace_cid_images(part, img_badge)
        return
    if msg.get_content_type() != 'text/html':
        return
    charset = msg.get_content_charset() or 'utf-8'
    raw = msg.get_payload(decode=True)
    if not raw:
        return
    body = raw.decode(charset, errors='replace')
    new_body = re.sub(r'<img\b[^>]*?src=["\']cid:[^"\']+["\'][^>]*?/?>', img_badge, body,
                      flags=re.IGNORECASE | re.DOTALL)
    if new_body != body:
        _replace_payload(msg, new_body.encode(charset, errors='replace'))


def _add_att_footer(msg, att_names):
    import re
    if msg.is_multipart():
        for part in msg.get_payload():
            _add_att_footer(part, att_names)
        return
    mime    = msg.get_content_type()
    charset = msg.get_content_charset() or 'utf-8'
    raw     = msg.get_payload(decode=True)
    if not raw:
        return
    if mime == 'text/html':
        body   = raw.decode(charset, errors='replace')
        footer = (
            '<div style="margin-top:12px;padding-top:8px;border-top:1px solid #e0e0e0;">'
            + ''.join(
                f'<p style="font-family:monospace;color:#888;font-size:12px;margin:2px 0;">'
                f'[Attachment removed: {n}]</p>'
                for n in att_names
            )
            + '</div>'
        )
        if re.search(r'</body\s*>', body, re.IGNORECASE):
            body = re.sub(r'</body\s*>', footer + '</body>', body, flags=re.IGNORECASE)
        else:
            body += footer
        _replace_payload(msg, body.encode(charset, errors='replace'))
    elif mime == 'text/plain':
        body = raw.decode(charset, errors='replace')
        body += '\n\n' + '\n'.join(f'[Attachment removed: {n}]' for n in att_names)
        _replace_payload(msg, body.encode(charset, errors='replace'))


def _replace_payload(msg, new_bytes):
    import base64 as _b64
    if 'Content-Transfer-Encoding' in msg:
        del msg['Content-Transfer-Encoding']
    msg.set_payload(_b64.b64encode(new_bytes).decode('ascii'))
    msg['Content-Transfer-Encoding'] = 'base64'


def _remove_parts(msg):
    removed = 0
    if msg.is_multipart():
        new_payload = []
        for part in msg.get_payload():
            if part.get_filename():
                removed += 1
            else:
                removed += _remove_parts(part)
                new_payload.append(part)
        msg.set_payload(new_payload)
    return removed


def _extract_sender_name(from_header):
    match = re.match(r'^(.+?)\s*<', from_header)
    if match:
        return match.group(1).strip().strip('"')
    return from_header.split('@')[0] if '@' in from_header else from_header


def _parse_date(date_str):
    try:
        return parsedate_to_datetime(date_str).strftime('%Y-%m-%d')
    except Exception:
        return date_str[:10] if date_str else 'unknown'


def _file_type(filename, mime_type=''):
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    if mime_type.startswith('image/') or ext in ('jpg','jpeg','png','gif','webp','bmp','tiff','heic','heif','svg'):
        return 'images'
    if mime_type.startswith('video/') or ext in ('mp4','mov','avi','mkv','wmv','m4v','flv'):
        return 'videos'
    if mime_type.startswith('audio/') or ext in ('mp3','wav','flac','aac','m4a','ogg','opus'):
        return 'audio'
    if ext == 'pdf' or mime_type == 'application/pdf':
        return 'documents'
    if ext in ('doc','docx','xls','xlsx','ppt','pptx','odt','ods','odp','pages','numbers','key','txt','rtf','csv'):
        return 'documents'
    if ext in ('zip','rar','7z','tar','gz','bz2','xz'):
        return 'archives'
    return 'other'


def _safe_path(s):
    return re.sub(r'[^\w\s\-.]', '', s).strip()


def _unique_path(path):
    path = Path(path)
    if not path.exists():
        return path
    stem, suffix, i = path.stem, path.suffix, 1
    while True:
        candidate = path.parent / f'{stem}_{i}{suffix}'
        if not candidate.exists():
            return candidate
        i += 1
