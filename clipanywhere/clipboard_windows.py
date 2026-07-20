from __future__ import annotations

import shutil
import tempfile
import time
import zipfile
import ctypes
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


GMEM_MOVEABLE = 0x0002
DROPEFFECT_COPY = 1


def open_clipboard_with_retry(retries: int = 40, delay_seconds: float = 0.05) -> None:
    ensure_available()
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            win32clipboard.OpenClipboard()
            return
        except Exception as exc:
            last_error = exc
            time.sleep(min(delay_seconds * (attempt + 1), 0.5))
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
                    zf.writestr(f"{path.name}/", "")
                    for child in path.rglob("*"):
                        archive_name = Path(path.name) / child.relative_to(path)
                        if child.is_dir():
                            zf.writestr(str(archive_name).replace("\\", "/") + "/", "")
                        if child.is_file():
                            zf.write(child, arcname=str(archive_name))
                elif path.is_file():
                    zf.write(path, arcname=path.name)
        return zip_name, zip_path.read_bytes()


def extract_zip_to_downloads(zip_bytes: bytes, download_dir: Path) -> list[Path]:
    download_dir.mkdir(parents=True, exist_ok=True)
    target = download_dir / time.strftime("clipboard-files-%Y%m%d-%H%M%S")
    target.mkdir()
    zip_path = target / "clipboard-files.zip"
    zip_path.write_bytes(zip_bytes)
    top_level_names: set[str] = set()
    with zipfile.ZipFile(zip_path) as zf:
        target_root = target.resolve()
        for member in zf.infolist():
            member_target = (target / member.filename).resolve()
            if target_root not in (member_target, *member_target.parents):
                raise ValueError(f"unsafe zip member path: {member.filename}")
            top_level = Path(member.filename).parts[0] if Path(member.filename).parts else ""
            if top_level:
                top_level_names.add(top_level)
        zf.extractall(target)
    zip_path.unlink(missing_ok=True)
    extracted_paths = [target / name for name in sorted(top_level_names)]
    return [path for path in extracted_paths if path.exists()] or [target]


def copy_files_to_clipboard(paths: list[Path]) -> None:
    opened = False
    fallback_text: str | None = None
    try:
        open_clipboard_with_retry()
        opened = True
        win32clipboard.EmptyClipboard()
        set_file_drop_data(paths)
        set_preferred_drop_effect()
    except Exception:
        fallback_text = "\r\n".join(str(p) for p in paths)
    finally:
        if opened:
            win32clipboard.CloseClipboard()
    if fallback_text is not None:
        set_text(fallback_text)


def set_file_drop_data(paths: list[Path]) -> None:
    file_list = "\0".join(str(p.resolve()) for p in paths) + "\0\0"
    encoded_files = file_list.encode("utf-16le")

    # DROPFILES: DWORD pFiles, POINT pt, BOOL fNC, BOOL fWide.
    dropfiles_header = (
        (20).to_bytes(4, "little")
        + (0).to_bytes(4, "little")
        + (0).to_bytes(4, "little")
        + (0).to_bytes(4, "little")
        + (1).to_bytes(4, "little")
    )
    set_clipboard_hglobal(win32con.CF_HDROP, dropfiles_header + encoded_files)


def set_preferred_drop_effect() -> None:
    format_id = win32clipboard.RegisterClipboardFormat("Preferred DropEffect")
    set_clipboard_hglobal(format_id, DROPEFFECT_COPY.to_bytes(4, "little"))


def set_clipboard_hglobal(format_id: int, data: bytes) -> None:
    kernel32 = ctypes.windll.kernel32
    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.restype = ctypes.c_int
    kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
    kernel32.GlobalFree.restype = ctypes.c_void_p

    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    if not handle:
        raise OSError("GlobalAlloc failed")
    locked = kernel32.GlobalLock(handle)
    if not locked:
        kernel32.GlobalFree(handle)
        raise OSError("GlobalLock failed")
    try:
        ctypes.memmove(locked, data, len(data))
    finally:
        kernel32.GlobalUnlock(handle)
    try:
        win32clipboard.SetClipboardData(format_id, handle)
    except Exception:
        kernel32.GlobalFree(handle)
        raise
