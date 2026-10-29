"""Install the current user's Explorer menu; no administrator rights required."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VERB = "ClipAnywhereSend"


def update_menu(remove: bool = False) -> None:
    import winreg

    for kind in ("*", "Directory"):
        key_path = rf"Software\Classes\{kind}\shell\{VERB}"
        if remove:
            for suffix in (r"\command", ""):
                try:
                    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path + suffix)
                except FileNotFoundError:
                    pass
            continue
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "Send to other...")
            winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, str(ROOT / "assets" / "clipanywhere.ico"))
            # One invocation avoids separate uploads replacing each other in /latest.
            winreg.SetValueEx(key, "MultiSelectModel", 0, winreg.REG_SZ, "Single")
        command = subprocess.list2cmdline([
            sys.executable, str(ROOT / "send_to_other.py"),
            "--config", str(ROOT / "client_config.json"), "--",
        ]) + ' "%1"'
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path + r"\command") as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remove", action="store_true")
    args = parser.parse_args()
    if sys.platform != "win32":
        raise SystemExit("Explorer integration is Windows-only")
    update_menu(args.remove)
    print("ClipAnywhere Explorer menu " + ("removed." if args.remove else "installed."))
