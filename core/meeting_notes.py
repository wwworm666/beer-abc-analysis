"""
Менеджер заметок с собраний.
Хранит заметки привязанные к бару + периоду.
Данные сохраняются на Render Disk (/kultura) или локально (data/).
"""

import json
import os
import threading
from datetime import datetime


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
        self._data = self._load()

    def _load(self):
        """Загрузить заметки из файла."""
        if not os.path.exists(self.data_file):
            return {}
        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[ERROR] Ошибка загрузки заметок: {e}")
            return {}

    def _save(self):
        """Сохранить заметки в файл. Вызывать только под self._lock."""
        try:
            os.makedirs(os.path.dirname(self.data_file) or '.', exist_ok=True)
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[ERROR] Ошибка сохранения заметок: {e}")

    @staticmethod
    def _make_key(venue, date_from, date_to):
        """Ключ заметки: venue::date_from::date_to"""
        return f"{venue}::{date_from}::{date_to}"

    def get(self, venue, date_from, date_to):
        """Получить заметку для бара и периода."""
        key = self._make_key(venue, date_from, date_to)
        with self._lock:
            entry = self._data.get(key)
        return entry

    def save(self, venue, date_from, date_to, text):
        """Сохранить заметку."""
        key = self._make_key(venue, date_from, date_to)
        with self._lock:
            self._data[key] = {
                'text': text,
                'venue': venue,
                'date_from': date_from,
                'date_to': date_to,
                'updated_at': datetime.now().isoformat()
            }
            self._save()

    def list_by_venue(self, venue, limit=10):
        """Все заметки для бара, отсортированные по дате (новые первые)."""
        with self._lock:
            entries = [
                v for v in self._data.values()
                if v.get('venue') == venue and v.get('text', '').strip()
            ]
        entries.sort(key=lambda x: x.get('date_to', ''), reverse=True)
        return entries[:limit]

    def delete(self, venue, date_from, date_to):
        """Удалить заметку."""
        key = self._make_key(venue, date_from, date_to)
        with self._lock:
            if key in self._data:
                del self._data[key]
                self._save()
