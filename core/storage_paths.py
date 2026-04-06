import os
import json
import shutil


RENDER_DISK_DIR = '/kultura'
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_DATA_DIR = os.path.join(BASE_DIR, 'data')


def get_local_data_path(filename: str) -> str:
    """Absolute path to a repo-local data file."""
    return os.path.join(LOCAL_DATA_DIR, filename)


def _merge_json_plans(local_path: str, disk_path: str) -> bool:
    """
    Синхронизировать периоды из repo-файла в файл на Render Disk.

    Локальные периоды (из repo) перезаписывают значения на disk.
    Периоды, которых нет в repo, сохраняются (не удаляются).
    Returns: True если были изменения.
    """
    if not os.path.exists(local_path) or not os.path.exists(disk_path):
        if os.path.exists(local_path) and not os.path.exists(disk_path):
            shutil.copy2(local_path, disk_path)
            print(f"[DATA] Создан файл на Render Disk из repo: {disk_path}")
            return True
        return False

    try:
        with open(local_path, 'r', encoding='utf-8') as f:
            local_data = json.load(f)
        with open(disk_path, 'r', encoding='utf-8') as f:
            disk_data = json.load(f)
    except Exception as e:
        print(f"[DATA] Ошибка чтения при merge: {e}")
        return False

    local_plans = local_data.get('plans', {}) if isinstance(local_data, dict) else {}
    disk_plans = disk_data.get('plans', {}) if isinstance(disk_data, dict) else {}

    changed = False
    local_keys = set(local_plans.keys())
    disk_keys = set(disk_plans.keys())

    # Новые периоды из repo → добавляем
    for key in local_keys - disk_keys:
        disk_plans[key] = local_plans[key].copy()
        changed = True

    # Изменённые периоды из repo → обновляем
    for key in local_keys & disk_keys:
        if disk_plans[key] != local_plans[key]:
            disk_plans[key] = local_plans[key].copy()
            changed = True

    # Периоды которых нет в repo сохраняются (не трогаем)

    if changed:
        disk_data['plans'] = disk_plans
        with open(disk_path + '.tmp', 'w', encoding='utf-8') as f:
            json.dump(disk_data, f, indent=2, ensure_ascii=False)
        os.replace(disk_path + '.tmp', disk_path)
        new_count = len(local_keys - disk_keys)
        updated_count = len(local_keys & disk_keys) - len(set(local_keys - disk_keys))
        print(f"[DATA] Синхронизирован {os.path.basename(disk_path)}: "
              f"+{new_count} новых, обновлено существующих")

    return changed


def get_data_path(filename: str, seed_from_local: bool = False) -> str:
    """
    Resolve a data file path.

    On Render, prefer the mounted disk at /kultura.
    Если seed_from_local=True — периоды из repo-копии добавляются в файл
    на Render Disk и перезаписывают существующие. Периоды без repo сохраняются.
    """
    local_path = get_local_data_path(filename)

    if os.path.exists(RENDER_DISK_DIR):
        disk_path = os.path.join(RENDER_DISK_DIR, filename)

        if seed_from_local and os.path.exists(local_path):
            _merge_json_plans(local_path, disk_path)

        return disk_path

    return local_path
