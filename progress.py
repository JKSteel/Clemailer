import json
import re
from datetime import datetime, timezone
from pathlib import Path


class ProgressManager:
    def __init__(self, email):
        self.email = email
        self.path = Path(f'progress_{_safe(email)}.json')
        self._data = self._load()

    def _load(self):
        if self.path.exists():
            return json.loads(self.path.read_text())
        return {
            'email': self.email,
            'threshold_mb': 5.0,
            'dry_run': False,
            'message_ids': None,
            'current_index': 0,
            'decisions': {},
            'fetched_at': None,
        }

    def _save(self):
        self.path.write_text(json.dumps(self._data, indent=2))

    @property
    def threshold_mb(self):
        return float(self._data.get('threshold_mb', 5.0))

    @property
    def dry_run(self):
        return bool(self._data.get('dry_run', False))

    @property
    def current_index(self):
        return int(self._data.get('current_index', 0))

    @property
    def message_ids(self):
        return self._data.get('message_ids') or []

    def has_email_list(self):
        return self._data.get('message_ids') is not None

    def set_message_ids(self, ids):
        self._data['message_ids'] = ids
        self._data['current_index'] = 0
        self._data['fetched_at'] = datetime.now(timezone.utc).isoformat()
        self._save()

    def update_settings(self, threshold_mb=None, dry_run=None):
        if threshold_mb is not None:
            self._data['threshold_mb'] = float(threshold_mb)
        if dry_run is not None:
            self._data['dry_run'] = bool(dry_run)
        self._save()

    def record_decision(self, msg_id, decision):
        self._data['decisions'][msg_id] = {
            'action': decision,
            'at': datetime.now(timezone.utc).isoformat(),
        }
        self._save()

    def get_decision(self, msg_id):
        return self._data['decisions'].get(msg_id, {}).get('action')

    def set_index(self, idx):
        total = len(self.message_ids)
        if total:
            self._data['current_index'] = max(0, min(idx, total - 1))
            self._save()

    def advance(self):
        self.set_index(self.current_index + 1)

    def retreat(self):
        self.set_index(self.current_index - 1)

    def get_summary(self):
        decisions = self._data.get('decisions', {})
        return {
            'email': self.email,
            'total': len(self.message_ids),
            'reviewed': len(decisions),
            'current_index': self.current_index,
            'fetched_at': self._data.get('fetched_at'),
            'dry_run': self.dry_run,
            'threshold_mb': self.threshold_mb,
            'decision_counts': _count_decisions(decisions),
        }

    # TODO: confirm reset behavior — two options implemented:
    # reset_all: wipe everything and re-fetch from scratch
    # reset_skipped: re-queue only skipped items, preserve deletions/downloads
    def reset_all(self):
        self._data['message_ids'] = None
        self._data['current_index'] = 0
        self._data['decisions'] = {}
        self._data['fetched_at'] = None
        self._save()

    def reset_skipped(self):
        self._data['decisions'] = {
            k: v for k, v in self._data.get('decisions', {}).items()
            if v.get('action') != 'skipped'
        }
        self._save()


def _count_decisions(decisions):
    counts = {}
    for v in decisions.values():
        action = v.get('action', 'unknown')
        counts[action] = counts.get(action, 0) + 1
    return counts


def _safe(s):
    return re.sub(r'[^\w]', '_', s)
