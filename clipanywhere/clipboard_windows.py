from __future__ import annotations

import time
import ctypes
from ctypes import wintypes
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
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
CLIPANYWHERE_HOTKEY_ID = 0xCA10
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
PM_REMOVE = 0x0001
VK_C = 0x43
VK_CONTROL = 0x11
VK_MENU = 0x12
KEYEVENTF_KEYUP = 0x0002
WM_HOTKEY = 0x0312
_HOTKEY_REGISTERED = False


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


def hotkey_description() -> str:
    return "Ctrl+Alt+C"


def register_sync_hotkey() -> None:
    global _HOTKEY_REGISTERED
    if _HOTKEY_REGISTERED:
        return
    user32 = ctypes.windll.user32
    user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
    user32.RegisterHotKey.restype = wintypes.BOOL
    if not user32.RegisterHotKey(None, CLIPANYWHERE_HOTKEY_ID, MOD_CONTROL | MOD_ALT, VK_C):
        raise ClipboardUnavailable("Cannot register Ctrl+Alt+C hotkey. Another app may already use it.")
    _HOTKEY_REGISTERED = True


def unregister_sync_hotkey() -> None:
    global _HOTKEY_REGISTERED
    if not _HOTKEY_REGISTERED:
        return
    user32 = ctypes.windll.user32
    user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.UnregisterHotKey.restype = wintypes.BOOL
    user32.UnregisterHotKey(None, CLIPANYWHERE_HOTKEY_ID)
    _HOTKEY_REGISTERED = False


def sync_hotkey_pressed() -> bool:
    user32 = ctypes.windll.user32
    msg = wintypes.MSG()
    user32.PeekMessageW.argtypes = [
        ctypes.POINTER(wintypes.MSG),
        wintypes.HWND,
        wintypes.UINT,
        wintypes.UINT,
        wintypes.UINT,
    ]
    user32.PeekMessageW.restype = wintypes.BOOL
    while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
        if msg.message == WM_HOTKEY and msg.wParam == CLIPANYWHERE_HOTKEY_ID:
            return True
    return False


def prepare_clipanywhere_copy() -> None:
    wait_for_hotkey_release()
    user32 = ctypes.windll.user32
    user32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, wintypes.ULONG]
    user32.keybd_event.restype = None
    user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.05)
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    user32.keybd_event(VK_C, 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(VK_C, 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.5)


def wait_for_hotkey_release(timeout_seconds: float = 1.0) -> None:
    user32 = ctypes.windll.user32
    user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    user32.GetAsyncKeyState.restype = ctypes.c_short
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        alt_down = bool(user32.GetAsyncKeyState(VK_MENU) & 0x8000)
        control_down = bool(user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)
        c_down = bool(user32.GetAsyncKeyState(VK_C) & 0x8000)
        if not alt_down and not control_down and not c_down:
            return
        time.sleep(0.02)


def get_clipboard_lock_owner() -> str:
    try:
        user32 = ctypes.windll.user32
        user32.GetOpenClipboardWindow.restype = wintypes.HWND
        owner_window = user32.GetOpenClipboardWindow()
        if not owner_window:
            return "unknown process"

        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.GetWindowThreadProcessId(owner_window, ctypes.byref(process_id))
        if not process_id.value:
            return f"window handle {owner_window}"

        process_path = query_process_path(process_id.value)
        if process_path:
            return f"{Path(process_path).name} (pid {process_id.value})"
        return f"pid {process_id.value}"
    except Exception:
        return "unknown process"


def query_process_path(process_id: int) -> str:
    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, process_id)
    if not handle:
        return ""
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(buffer))
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return buffer.value
        return ""
    finally:
        kernel32.CloseHandle(handle)


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
