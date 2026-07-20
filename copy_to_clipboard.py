from __future__ import annotations

import sys
from pathlib import Path


project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

from clipanywhere.clipboard_windows import copy_files_to_clipboard


def main() -> None:
    paths = [Path(arg) for arg in sys.argv[1:]]
    if not paths:
        print("Usage: python copy_to_clipboard.py <file-or-folder> [more-files-or-folders]")
        raise SystemExit(2)
    missing = [path for path in paths if not path.exists()]
    if missing:
        print("Missing paths:")
        for path in missing:
            print(path)
        raise SystemExit(1)
    copy_files_to_clipboard(paths)
    print("Copied to Windows file clipboard:")
    for path in paths:
        print(path.resolve())


if __name__ == "__main__":
    main()

