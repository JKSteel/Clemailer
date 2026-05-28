import base64
import re
from pathlib import Path
from email.utils import parsedate_to_datetime
from googleapiclient.discovery import build


class GmailClient:
    def __init__(self, credentials):
        self.service = build('gmail', 'v1', credentials=credentials)

    def list_large_messages(self, min_size_bytes):
        min_mb = max(1, int(min_size_bytes / (1024 * 1024)))
        query = f'larger:{min_mb}m has:attachment'
        messages = []
        page_token = None
        while True:
            kwargs = {'userId': 'me', 'q': query, 'maxResults': 500}
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
        self._extract_parts(msg['payload'], attachments, body)
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

    def _extract_parts(self, payload, attachments, body):
        mime = payload.get('mimeType', '')
        raw = payload.get('body', {}).get('data', '')
        att_id = payload.get('body', {}).get('attachmentId')
        filename = payload.get('filename', '')

        if att_id and filename:
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
            self._extract_parts(part, attachments, body)

    def get_attachment_data(self, msg_id, att_id):
        result = self.service.users().messages().attachments().get(
            userId='me', messageId=msg_id, id=att_id
        ).execute()
        return base64.urlsafe_b64decode(result['data'])

    def download_attachment(self, msg_id, att_id, filename, sender, date_str, dry_run=False):
        sender_name = _extract_sender_name(sender)
        safe_sender = _safe_path(sender_name)[:40] or 'unknown'
        safe_date = _safe_path(_parse_date(date_str))
        dest_dir = Path('downloads') / safe_sender / safe_date
        dest_path = _unique_path(dest_dir / filename)

        if dry_run:
            return str(dest_path)

        data = self.get_attachment_data(msg_id, att_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(data)
        return str(dest_path)

    def delete_message(self, msg_id, dry_run=False):
        if not dry_run:
            self.service.users().messages().delete(userId='me', id=msg_id).execute()
        return {'msg_id': msg_id, 'dry_run': dry_run}

    def delete_thread(self, thread_id, dry_run=False):
        thread = self.service.users().threads().get(
            userId='me', id=thread_id, format='minimal'
        ).execute()
        msg_ids = [m['id'] for m in thread.get('messages', [])]
        if not dry_run:
            for mid in msg_ids:
                self.service.users().messages().delete(userId='me', id=mid).execute()
        return {'thread_id': thread_id, 'count': len(msg_ids), 'dry_run': dry_run}


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
