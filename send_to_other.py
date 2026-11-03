"""Send Explorer selections directly, without changing the local clipboard."""
from __future__ import annotations

import argparse
import contextlib
import sqlite3
import time
import traceback
from pathlib import Path

from clipanywhere.archive import zip_paths
from clipanywhere.client import Client, describe_paths
from clipanywhere.common import load_json


ROOT = Path(__file__).resolve().parent
QUEUE_DIR = ROOT / ".clipanywhere_sender"
LOG_PATH = ROOT / "clipanywhere_send.log"


def collect_selection(paths: list[Path], config_path: Path, queue_path: Path) -> list[Path]:
    """Combine Explorer's separate per-item invocations into one upload."""
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    config = str(config_path.resolve())
    with contextlib.closing(sqlite3.connect(queue_path, timeout=30)) as db, db:
        db.execute("CREATE TABLE IF NOT EXISTS selection (path TEXT, config TEXT, added REAL)")
        db.executemany("INSERT INTO selection VALUES (?, ?, ?)",
                       [(str(p.resolve()), config, time.time()) for p in paths])
    while True:
        time.sleep(0.2)
        with contextlib.closing(sqlite3.connect(queue_path, timeout=30)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute("SELECT path, added FROM selection WHERE config = ? ORDER BY rowid", (config,)).fetchall()
            if not rows:
                return []
            if time.time() - max(row[1] for row in rows) < 2:
                continue
            db.execute("DELETE FROM selection WHERE config = ?", (config,))
        return list(dict.fromkeys(Path(row[0]) for row in rows))


def send_paths(paths: list[Path], config_path: Path) -> None:
    if not paths:
        raise ValueError("Select a file or folder to send.")
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(f"File or folder no longer exists: {path}")
    client = Client(load_json(config_path))
    client.log(f"Explorer send: uploading {describe_paths(paths)}")
    name, body = zip_paths(paths)
    client.post_bytes(
        "push/files",
        body,
        {
            "Content-Type": "application/zip",
            "X-ClipAnywhere-Filename": name,
            "X-ClipAnywhere-Device": client.device_name,
        },
    )
    client.log("Files/Folder sync uploaded")


def main() -> int:
    parser = argparse.ArgumentParser(description="Send files/folders through ClipAnywhere")
    parser.add_argument("--config", type=Path, default=ROOT / "client_config.json")
    parser.add_argument("--explorer", action="store_true")
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    with LOG_PATH.open("a", encoding="utf-8") as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
        try:
            paths = collect_selection(args.paths, args.config, QUEUE_DIR / "selection.sqlite3") if args.explorer else args.paths
            if paths:
                send_paths(paths, args.config)
        except Exception:
            print(time.strftime("[%Y-%m-%d %H:%M:%S] Explorer send failed"), flush=True)
            traceback.print_exc()
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
