from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import win32api
import win32con
import win32gui


PROJECT_ROOT = Path(__file__).resolve().parent
PYTHONW = Path(r"C:\python\pythonw.exe")
PYTHON = Path(r"C:\python\python.exe")
LOG_PATH = PROJECT_ROOT / "clipanywhere_client.log"
CONFIG_PATH = PROJECT_ROOT / "client_config.json"
WM_TRAY = win32con.WM_USER + 20
MENU_OPEN_LOG = 1001
MENU_EXIT = 1002


class TrayApp:
    def __init__(self) -> None:
        self.process: subprocess.Popen[bytes] | None = None
        self.window_class = "ClipAnywhereTrayWindow"
        self.hwnd: int | None = None

    def run(self) -> None:
        self.start_client()
        self.create_window()
        self.add_tray_icon()
        win32gui.PumpMessages()

    def start_client(self) -> None:
        python_exe = PYTHONW if PYTHONW.exists() else PYTHON
        command = [
            str(python_exe),
            str(PROJECT_ROOT / "start_client.py"),
            "--config",
            str(CONFIG_PATH),
        ]
        log = LOG_PATH.open("a", encoding="utf-8")
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.process = subprocess.Popen(
            command,
            cwd=str(PROJECT_ROOT),
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
        )

    def create_window(self) -> None:
        message_map = {
            WM_TRAY: self.on_tray,
            win32con.WM_DESTROY: self.on_destroy,
            win32con.WM_COMMAND: self.on_command,
        }
        wc = win32gui.WNDCLASS()
        wc.lpfnWndProc = message_map
        wc.lpszClassName = self.window_class
        wc.hInstance = win32api.GetModuleHandle(None)
        win32gui.RegisterClass(wc)
        self.hwnd = win32gui.CreateWindow(
            self.window_class,
            "ClipAnywhere",
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            wc.hInstance,
            None,
        )

    def add_tray_icon(self) -> None:
        icon = win32gui.LoadIcon(0, win32con.IDI_APPLICATION)
        nid = (
            self.hwnd,
            0,
            win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP,
            WM_TRAY,
            icon,
            "ClipAnywhere - Ctrl+Alt+C to sync",
        )
        win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, nid)

    def remove_tray_icon(self) -> None:
        if self.hwnd:
            win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, (self.hwnd, 0))

    def on_tray(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        if lparam in (win32con.WM_RBUTTONUP, win32con.WM_LBUTTONDBLCLK):
            self.show_menu()
        return 0

    def show_menu(self) -> None:
        menu = win32gui.CreatePopupMenu()
        win32gui.AppendMenu(menu, win32con.MF_STRING, MENU_OPEN_LOG, "Open log")
        win32gui.AppendMenu(menu, win32con.MF_SEPARATOR, 0, None)
        win32gui.AppendMenu(menu, win32con.MF_STRING, MENU_EXIT, "Exit ClipAnywhere")
        pos = win32gui.GetCursorPos()
        win32gui.SetForegroundWindow(self.hwnd)
        win32gui.TrackPopupMenu(menu, win32con.TPM_LEFTALIGN, pos[0], pos[1], 0, self.hwnd, None)
        win32gui.PostMessage(self.hwnd, win32con.WM_NULL, 0, 0)

    def on_command(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        command = win32api.LOWORD(wparam)
        if command == MENU_OPEN_LOG:
            if not LOG_PATH.exists():
                LOG_PATH.write_text("", encoding="utf-8")
            os.startfile(LOG_PATH)
        elif command == MENU_EXIT:
            self.exit()
        return 0

    def on_destroy(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        self.remove_tray_icon()
        self.stop_client()
        win32gui.PostQuitMessage(0)
        return 0

    def exit(self) -> None:
        win32gui.DestroyWindow(self.hwnd)

    def stop_client(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()


if __name__ == "__main__":
    if sys.platform != "win32":
        raise SystemExit("Tray launcher is Windows-only")
    TrayApp().run()

