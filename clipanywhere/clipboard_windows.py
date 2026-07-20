from __future__ import annotations

import shutil
import tempfile
import time
import zipfile
from pathlib import Path

try:
    import win32clipboard
    import win32con
except ImportError as exc:  # pragma: no cover - platform dependency
    win32clipboard = None
    win32con = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


class ClipboardUnavailable(RuntimeError):
    pass


def open_clipboard_with_retry(retries: int = 8, delay_seconds: float = 0.05) -> None:
    ensure_available()
    last_error: Exception | None = None
    for _ in range(retries):
        try:
            win32clipboard.OpenClipboard()
            return
        except Exception as exc:
            last_error = exc
            time.sleep(delay_seconds)
    raise ClipboardUnavailable("Windows clipboard is busy") from last_error


def ensure_available() -> None:
    if IMPORT_ERROR is not None:
        raise ClipboardUnavailable(
            "Windows clipboard file support requires pywin32. Run: pip install pywin32"
        ) from IMPORT_ERROR


def get_text() -> str | None:
    opened = False
    try:
        open_clipboard_with_retry()
        opened = True
        if not win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
            return None
        return win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
    finally:
        if opened:
            win32clipboard.CloseClipboard()


def set_text(text: str) -> None:
    opened = False
    try:
        open_clipboard_with_retry()
        opened = True
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
    finally:
        if opened:
            win32clipboard.CloseClipboard()


def get_file_paths() -> list[Path]:
    opened = False
    try:
        open_clipboard_with_retry()
        opened = True
        if not win32clipboard.IsClipboardFormatAvailable(win32con.CF_HDROP):
            return []
        return [Path(p) for p in win32clipboard.GetClipboardData(win32con.CF_HDROP)]
    finally:
        if opened:
            win32clipboard.CloseClipboard()


def zip_paths(paths: list[Path]) -> tuple[str, bytes]:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    zip_name = f"clipboard-files-{stamp}.zip"
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / zip_name
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in paths:
                if path.is_dir():
                    for child in path.rglob("*"):
                        if child.is_file():
                            zf.write(child, arcname=str(Path(path.name) / child.relative_to(path)))
                elif path.is_file():
                    zf.write(path, arcname=path.name)
        return zip_name, zip_path.read_bytes()


def extract_zip_to_downloads(zip_bytes: bytes, download_dir: Path) -> Path:
    download_dir.mkdir(parents=True, exist_ok=True)
    target = download_dir / time.strftime("clipboard-files-%Y%m%d-%H%M%S")
    target.mkdir()
    zip_path = target / "clipboard-files.zip"
    zip_path.write_bytes(zip_bytes)
    with zipfile.ZipFile(zip_path) as zf:
        target_root = target.resolve()
        for member in zf.infolist():
            member_target = (target / member.filename).resolve()
            if target_root not in (member_target, *member_target.parents):
                raise ValueError(f"unsafe zip member path: {member.filename}")
        zf.extractall(target)
    zip_path.unlink(missing_ok=True)
    return target


def copy_files_to_clipboard(paths: list[Path]) -> None:
    opened = False
    fallback_text: str | None = None
    try:
        open_clipboard_with_retry()
        opened = True
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(
            win32con.CF_HDROP,
            tuple(str(p.resolve()) for p in paths),
        )
    except Exception:
        fallback_text = "\r\n".join(str(p) for p in paths)
    finally:
        if opened:
            win32clipboard.CloseClipboard()
    if fallback_text is not None:
        set_text(fallback_text)
