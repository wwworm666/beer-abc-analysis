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

    On Render, prefer the mounted disk at /kultura.
    Optionally seed the disk file from the repo copy on first use.
    """
    local_path = get_local_data_path(filename)

    if os.path.exists(RENDER_DISK_DIR):
        disk_path = os.path.join(RENDER_DISK_DIR, filename)

        if seed_from_local and not os.path.exists(disk_path) and os.path.exists(local_path):
            try:
                shutil.copy2(local_path, disk_path)
                print(f"[DATA] Seeded {filename} to Render Disk: {disk_path}")
            except Exception as e:
                print(f"[DATA] Failed to seed {filename} to Render Disk: {e}")

        return disk_path

    return local_path
