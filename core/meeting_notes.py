"""
Менеджер заметок с собраний.
Хранит заметки привязанные к бару + периоду.
Данные сохраняются на Render Disk (/kultura) или локально (data/).
"""

import json
import os
import threading
from datetime import datetime

from core.json_store import atomic_write_json, file_lock


class MeetingNotesManager:
    def __init__(self, data_file=None):
        if data_file:
            self.data_file = data_file
        elif os.path.exists('/kultura'):
            self.data_file = '/kultura/meeting_notes.json'
        else:
            self.data_file = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), 'data', 'meeting_notes.json'
            )
        self._lock = threading.Lock()
        self._lock_path = self.data_file + '.lock'

    def _load(self):
        """Загрузить заметки из файла (свежее чтение с диска)."""
        if not os.path.exists(self.data_file):
            return {}
        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[ERROR] Ошибка загрузки заметок: {e}")
            return {}

    @staticmethod
    def _make_key(venue, date_from, date_to):
        """Ключ заметки: venue::date_from::date_to"""
        return f"{venue}::{date_from}::{date_to}"

    def get(self, venue, date_from, date_to):
        """Получить заметку для бара и периода (свежее чтение)."""
        key = self._make_key(venue, date_from, date_to)
        return self._load().get(key)

    def save(self, venue, date_from, date_to, text):
        """Сохранить заметку (cross-worker safe read-modify-write)."""
        key = self._make_key(venue, date_from, date_to)
        with self._lock, file_lock(self._lock_path):
            data = self._load()  # перечитываем внутри лока — не теряем правки другого воркера
            data[key] = {
                'text': text,
                'venue': venue,
                'date_from': date_from,
                'date_to': date_to,
                'updated_at': datetime.now().isoformat()
            }
            atomic_write_json(self.data_file, data)

    def list_by_venue(self, venue, limit=10):
        """Все заметки для бара, отсортированные по дате (новые первые)."""
        entries = [
            v for v in self._load().values()
            if v.get('venue') == venue and v.get('text', '').strip()
        ]
        entries.sort(key=lambda x: x.get('date_to', ''), reverse=True)
        return entries[:limit]

    def delete(self, venue, date_from, date_to):
        """Удалить заметку (cross-worker safe)."""
        key = self._make_key(venue, date_from, date_to)
        with self._lock, file_lock(self._lock_path):
            data = self._load()
            if key in data:
                del data[key]
                atomic_write_json(self.data_file, data)
