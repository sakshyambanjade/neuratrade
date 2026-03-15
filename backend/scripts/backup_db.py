"""
Simple SQLite backup with 7-day retention.
Usage: python scripts/backup_db.py
"""
import os
import shutil
import time
from pathlib import Path
from config import DB_PATH

BACKUP_DIR = Path("backups")
RETENTION_DAYS = 7


def backup():
    BACKUP_DIR.mkdir(exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    target = BACKUP_DIR / f"{Path(DB_PATH).stem}-{ts}.db"
    shutil.copy2(DB_PATH, target)
    prune()
    print(f"Backup written to {target}")


def prune():
    cutoff = time.time() - RETENTION_DAYS * 86400
    for file in BACKUP_DIR.glob("*.db"):
        if file.stat().st_mtime < cutoff:
            file.unlink()


if __name__ == "__main__":
    if not Path(DB_PATH).exists():
        raise SystemExit(f"{DB_PATH} not found")
    backup()
