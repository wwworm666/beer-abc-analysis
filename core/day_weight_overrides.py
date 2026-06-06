"""
Менеджер переопределений веса дня (day weight overrides).

Хранит ИСКЛЮЧЕНИЯ веса дня по (заведение, дата) — например, праздник = 5.0 или
закрытый день = 0.0. Обычные дни (будни = 1, пт/сб = 2) в файле не хранятся:
их вес даёт core/day_weights.default_day_weight().

Источник правды для дневного плана = месячные планы (plansdashboard.json) +
эти override. Файл data/daily_plans.json — лишь производный кэш, который
пересобирается после любого изменения override (см. регенерацию ниже).

Файл: data/day_weight_overrides.json (на проде — /kultura/day_weight_overrides.json).
Структура:
{
  "overrides": {
    "bolshoy":   {"2025-11-04": 5.0, "2025-11-10": 0.0},
    "ligovskiy": {"2025-12-31": 0.0}
  },
  "metadata": {...}
}
"""

import json
import os
import shutil
import threading
from contextlib import contextmanager
from datetime import datetime, date
from typing import Dict, Optional

import portalocker

from core.storage_paths import get_data_path
from core.day_weights import default_day_weight


# Реальные заведения (для агрегата 'all' и валидации). 'all' здесь не хранится.
REAL_VENUES = ['bolshoy', 'ligovskiy', 'kremenchugskaya', 'varshavskaya']


class DayWeightOverridesManager:
    """Чтение/запись override весов дней. Атомарная запись + блокировки как в PlansManager."""

    def __init__(self, data_file: str = None):
        if data_file:
            self.data_file = data_file
        else:
            self.data_file = get_data_path('day_weight_overrides.json', seed_from_local=True)
            print(f"[DAY_OVERRIDES] Файл override: {self.data_file}")

        self._lock = threading.Lock()
        self._lock_path = self.data_file + '.lock'
        self._initialize_file()

    @contextmanager
    def _file_lock(self, timeout: int = 10):
        """Cross-worker advisory lock на отдельном lock-файле."""
        with portalocker.Lock(self._lock_path, mode='a', timeout=timeout):
            yield

    def _initialize_file(self):
        directory = os.path.dirname(self.data_file)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)

        if not os.path.exists(self.data_file):
            empty = {
                'overrides': {},
                'metadata': {
                    'version': '1.0',
                    'notes': 'absolute day weight per (venue, date); default weekday=1, Fri/Sat=2; closed day=0',
                    'lastUpdate': datetime.now().isoformat(),
                }
            }
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(empty, f, indent=2, ensure_ascii=False)
            print(f"[DAY_OVERRIDES] Создан новый файл: {self.data_file}")

    def _read_file(self) -> Dict:
        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            self._initialize_file()
            with open(self.data_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            # Пытаемся восстановить из backup, иначе — не затираем, поднимаем ошибку
            backup = self.data_file + '.backup'
            if os.path.exists(backup):
                shutil.copy2(backup, self.data_file)
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            raise RuntimeError(
                f"Файл override {self.data_file} повреждён, backup отсутствует. "
                "Автосоздание пустой структуры отключено во избежание потери данных."
            ) from e

    def _write_file(self, data: Dict):
        """Атомарная запись (backup -> tmp -> os.replace), как PlansManager._write_file."""
        if os.path.exists(self.data_file):
            try:
                shutil.copy2(self.data_file, self.data_file + '.backup')
            except Exception as e:
                print(f"[DAY_OVERRIDES WARNING] backup не создан: {e}")

        if 'metadata' not in data:
            data['metadata'] = {}
        data['metadata']['lastUpdate'] = datetime.now().isoformat()
        data['metadata']['version'] = '1.0'

        temp_file = self.data_file + '.tmp'
        try:
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass
            os.replace(temp_file, self.data_file)
        except Exception:
            if os.path.exists(temp_file):
                os.remove(temp_file)
            raise

    # ------------------------------------------------------------------ чтение

    def get_all(self) -> Dict[str, Dict[str, float]]:
        """Все override: {venue: {date: weight}}."""
        with self._lock:
            data = self._read_file()
            return data.get('overrides', {})

    def get_for_venue_month(self, venue_key: str, year: int, month: int) -> Dict[str, float]:
        """Override одного заведения за месяц: {"YYYY-MM-DD": weight}."""
        prefix = f"{year}-{month:02d}-"
        all_overrides = self.get_all()
        venue_overrides = all_overrides.get(venue_key, {})
        return {d: w for d, w in venue_overrides.items() if d.startswith(prefix)}

    # ------------------------------------------------------------------ запись

    @staticmethod
    def _parse_date(date_str: str) -> date:
        return datetime.strptime(date_str, '%Y-%m-%d').date()

    def set_override(self, venue_key: str, date_str: str, weight: float) -> Dict:
        """Установить override веса дня для заведения.

        Если weight равен весу по умолчанию для этого дня — ключ удаляется
        (no-op cleanup), чтобы в файле не копились избыточные записи.

        После записи пересобирает daily_plans.json для этого заведения+месяца
        и агрегат 'all' за месяц.

        Returns:
            dict с результатом {venue, date, weight, stored: bool}.
        """
        if venue_key == 'all':
            raise ValueError("Агрегат 'all' не редактируется: задавайте override по конкретному заведению")

        d = self._parse_date(date_str)  # бросит ValueError при некорректной дате
        weight = float(weight)
        if weight < 0:
            raise ValueError(f"Вес дня не может быть отрицательным: {weight}")

        is_default = (weight == default_day_weight(d))

        with self._lock, self._file_lock():
            data = self._read_file()
            overrides = data.setdefault('overrides', {})
            venue_overrides = overrides.setdefault(venue_key, {})

            if is_default:
                stored = False
                venue_overrides.pop(date_str, None)
            else:
                stored = True
                venue_overrides[date_str] = weight

            if not venue_overrides:
                overrides.pop(venue_key, None)

            self._write_file(data)

        self._regenerate(venue_key, d.year, d.month)
        return {'venue': venue_key, 'date': date_str, 'weight': weight, 'stored': stored}

    def delete_override(self, venue_key: str, date_str: str) -> Dict:
        """Удалить override (вернуть день к весу по умолчанию). Идемпотентно."""
        if venue_key == 'all':
            raise ValueError("Агрегат 'all' не редактируется")

        d = self._parse_date(date_str)

        with self._lock, self._file_lock():
            data = self._read_file()
            overrides = data.get('overrides', {})
            venue_overrides = overrides.get(venue_key, {})
            removed = venue_overrides.pop(date_str, None) is not None
            if venue_key in overrides and not venue_overrides:
                overrides.pop(venue_key, None)
            if removed:
                self._write_file(data)

        self._regenerate(venue_key, d.year, d.month)
        return {'venue': venue_key, 'date': date_str, 'removed': removed}

    def delete_venue_month(self, venue_key: str, year: int, month: int) -> int:
        """Удалить все override заведения за месяц (при удалении месячного плана).

        Returns:
            Количество удалённых записей.
        """
        if venue_key == 'all':
            return 0

        prefix = f"{year}-{month:02d}-"
        with self._lock, self._file_lock():
            data = self._read_file()
            overrides = data.get('overrides', {})
            venue_overrides = overrides.get(venue_key, {})
            to_remove = [d for d in venue_overrides if d.startswith(prefix)]
            for d in to_remove:
                venue_overrides.pop(d, None)
            if venue_key in overrides and not venue_overrides:
                overrides.pop(venue_key, None)
            if to_remove:
                self._write_file(data)
        return len(to_remove)

    # --------------------------------------------------------------- регенерация

    def _regenerate(self, venue_key: str, year: int, month: int):
        """Пересобрать daily_plans.json для заведения+месяца и агрегат 'all'."""
        try:
            from core.daily_plans_generator import (
                regenerate_daily_plan_for_venue_month,
                regenerate_all_aggregate_for_month,
            )
            regenerate_daily_plan_for_venue_month(venue_key, year, month)
            regenerate_all_aggregate_for_month(year, month)
        except Exception as e:
            print(f"[DAY_OVERRIDES WARN] Не удалось пересобрать daily_plans: {e}")


# Самотестирование
if __name__ == "__main__":
    import tempfile

    print("=" * 60)
    print("ТЕСТ DayWeightOverridesManager")
    print("=" * 60)

    tmp = os.path.join(tempfile.gettempdir(), 'test_day_weight_overrides.json')
    for ext in ('', '.backup', '.tmp', '.lock'):
        if os.path.exists(tmp + ext):
            os.remove(tmp + ext)

    mgr = DayWeightOverridesManager(data_file=tmp)

    # set + get round-trip (регенерация упадёт мягко — daily_plans тут не настроен)
    mgr.set_override('bolshoy', '2025-11-04', 5.0)
    got = mgr.get_for_venue_month('bolshoy', 2025, 11)
    print(f"\n1. set 04=5.0 -> get = {got}")
    assert got == {'2025-11-04': 5.0}

    # no-op cleanup: вес по умолчанию для вторника (1.0) не хранится
    mgr.set_override('bolshoy', '2025-11-11', 1.0)  # 2025-11-11 — вторник
    got = mgr.get_for_venue_month('bolshoy', 2025, 11)
    print(f"2. set 11=1.0 (дефолт вт) -> не хранится, get = {got}")
    assert '2025-11-11' not in got

    # delete
    mgr.delete_override('bolshoy', '2025-11-04')
    got = mgr.get_for_venue_month('bolshoy', 2025, 11)
    print(f"3. delete 04 -> get = {got}")
    assert got == {}

    # all не редактируется
    try:
        mgr.set_override('all', '2025-11-04', 5.0)
        assert False, "ожидался ValueError для all"
    except ValueError:
        print("4. set_override('all', ...) корректно отклонён")

    # backup создаётся
    assert os.path.exists(tmp + '.backup')
    print("5. backup-файл создан")

    for ext in ('', '.backup', '.tmp', '.lock'):
        if os.path.exists(tmp + ext):
            os.remove(tmp + ext)
    print("\n" + "=" * 60)
    print("OK")
