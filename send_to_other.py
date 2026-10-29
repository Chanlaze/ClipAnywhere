"""Send Explorer selections directly, without changing the local clipboard."""
from __future__ import annotations

import argparse
import ctypes
import sys
from pathlib import Path

from clipanywhere.archive import zip_paths
from clipanywhere.client import Client, describe_paths
from clipanywhere.common import load_json


ROOT = Path(__file__).resolve().parent


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
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    try:
        send_paths(args.paths, args.config)
    except Exception as exc:
        message = f"Could not send files/folders:\n{exc}"
        print(message, flush=True)
        if sys.platform == "win32":
            ctypes.windll.user32.MessageBoxW(0, message, "ClipAnywhere", 0x10)
        return 1
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(
            0,
            "Files/folders uploaded. Other connected PCs will receive them automatically.",
            "ClipAnywhere sent",
            0x40,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
