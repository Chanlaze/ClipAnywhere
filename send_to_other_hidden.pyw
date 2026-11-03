"""Launch the sender without a console; keep pythonw free of native extensions."""
import subprocess
import sys
import traceback
from pathlib import Path

root = Path(__file__).resolve().parent
try:
    python = Path(sys.executable).with_name("python.exe")
    with (root / "clipanywhere_send.log").open("a", encoding="utf-8") as log:
        subprocess.Popen(
            [str(python), str(root / "send_to_other.py"), *sys.argv[1:]],
            cwd=root,
            stdout=log,
            stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
except Exception:
    with (root / "clipanywhere_send.log").open("a", encoding="utf-8") as log:
        traceback.print_exc(file=log)
