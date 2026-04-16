import os
import shutil


RENDER_DISK_DIR = '/kultura'
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_DATA_DIR = os.path.join(BASE_DIR, 'data')


def get_local_data_path(filename: str) -> str:
    """Absolute path to a repo-local data file."""
    return os.path.join(LOCAL_DATA_DIR, filename)


def get_data_path(filename: str, seed_from_local: bool = False) -> str:
    """
    Resolve a data file path.

    На Render: используется постоянный диск /kultura. Если файла на диске нет,
    а в repo (data/<filename>) есть и передан seed_from_local=True — копируем один
    раз как начальное заполнение, после чего repo-копия больше ни на что не влияет.

    Если файл на диске уже существует — НИКОГДА не перезаписываем его значениями из
    repo. Диск является единственным источником правды; все изменения делаются через
    дашборд и сохраняются напрямую в /kultura.

    В dev-окружении (/kultura не существует) возвращается путь к repo-копии.
    """
    local_path = get_local_data_path(filename)

    if os.path.exists(RENDER_DISK_DIR):
        disk_path = os.path.join(RENDER_DISK_DIR, filename)

        if seed_from_local and not os.path.exists(disk_path) and os.path.exists(local_path):
            shutil.copy2(local_path, disk_path)
            print(f"[DATA] Seed: {filename} скопирован из repo на Render Disk (диск был пуст)")

        return disk_path

    return local_path
