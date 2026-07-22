from __future__ import annotations

import os
import subprocess
import sys
import threading
import traceback
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
PYTHONW = Path(r"C:\python\pythonw.exe")
PYTHON = Path(r"C:\python\python.exe")
LOG_PATH = PROJECT_ROOT / "clipanywhere_client.log"
TRAY_LOG_PATH = PROJECT_ROOT / "clipanywhere_tray.log"
CONFIG_PATH = PROJECT_ROOT / "client_config.json"
ICON_PATH = PROJECT_ROOT / "assets" / "clipanywhere.ico"


def log_tray(message: str) -> None:
    with TRAY_LOG_PATH.open("a", encoding="utf-8") as log:
        log.write(message + "\n")
        log.flush()


try:
    import win32api
    import win32con
    import win32gui
except Exception:
    log_tray("Failed to import pywin32 tray modules:")
    log_tray(traceback.format_exc())
    raise


WM_TRAY = win32con.WM_USER + 20
MENU_OPEN_LOG = 1001
MENU_EXIT = 1002
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010
LR_DEFAULTSIZE = 0x0040
NIF_INFO = 0x00000010
NIIF_INFO = 0x00000001


class TrayApp:
    def __init__(self) -> None:
        self.process: subprocess.Popen[str] | None = None
        self.window_class = "ClipAnywhereTrayWindow"
        self.hwnd: int | None = None
        self.icon: int | None = None
        self.pending_download_source = ""

    def run(self) -> None:
        log_tray("ClipAnywhere tray launcher starting")
        self.start_client()
        self.create_window()
        self.add_tray_icon()
        log_tray("Tray icon added. If you cannot see it, check the hidden tray icons arrow (^).")
        win32gui.PumpMessages()

    def start_client(self) -> None:
        python_exe = PYTHONW if PYTHONW.exists() else PYTHON
        command = [
            str(python_exe),
            str(PROJECT_ROOT / "start_client.py"),
            "--config",
            str(CONFIG_PATH),
        ]
        log_tray("Starting client process:")
        log_tray(" ".join(command))
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.process = subprocess.Popen(
            command,
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        log_tray(f"Client process started, pid={self.process.pid}")
        threading.Thread(target=self.watch_client_output, daemon=True).start()

    def watch_client_output(self) -> None:
        if not self.process or not self.process.stdout:
            return
        with LOG_PATH.open("a", encoding="utf-8") as log:
            for line in self.process.stdout:
                log.write(line)
                log.flush()
                self.handle_client_status(line.strip())

    def handle_client_status(self, line: str) -> None:
        if not line:
            return
        if "Text being sync: downloading from " in line:
            self.pending_download_source = line.rsplit(" from ", 1)[-1]
        elif "Files/Folder being sync: downloading from " in line:
            self.pending_download_source = line.rsplit(" from ", 1)[-1]
        elif "Text sync uploaded" in line:
            self.show_notification("ClipAnywhere sent", "Text clipboard sent to other PCs.")
        elif "Files/Folder sync uploaded" in line:
            self.show_notification("ClipAnywhere sent", "Files/folders sent to other PCs.")
        elif "Text placed on clipboard:" in line:
            source = self.pending_download_source or "another PC"
            self.pending_download_source = ""
            self.show_notification("ClipAnywhere received", f"Text received from {source}.")
        elif "Files/Folder placed on clipboard" in line:
            source = self.pending_download_source or "another PC"
            self.pending_download_source = ""
            self.show_notification("ClipAnywhere received", f"Files/folders received from {source}. Ready for Ctrl+V.")

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
            win32con.WS_OVERLAPPED,
            -32000,
            -32000,
            1,
            1,
            0,
            0,
            wc.hInstance,
            None,
        )
        win32gui.ShowWindow(self.hwnd, win32con.SW_HIDE)
        log_tray(f"Tray window created, hwnd={self.hwnd}")

    def add_tray_icon(self) -> None:
        self.icon = self.load_tray_icon()
        nid = (
            self.hwnd,
            0,
            win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP,
            WM_TRAY,
            self.icon,
            "ClipAnywhere - Ctrl+Alt+C to sync",
        )
        win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, nid)

    def show_notification(self, title: str, message: str) -> None:
        if not self.hwnd:
            return
        try:
            nid = (
                self.hwnd,
                0,
                win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP | NIF_INFO,
                WM_TRAY,
                self.icon or self.load_tray_icon(),
                "ClipAnywhere - Ctrl+Alt+C to sync",
                message[:255],
                5000,
                title[:63],
                NIIF_INFO,
            )
            win32gui.Shell_NotifyIcon(win32gui.NIM_MODIFY, nid)
            log_tray(f"Tray notification shown: {title} - {message}")
        except Exception:
            log_tray("Tray notification failed:")
            log_tray(traceback.format_exc())

    def load_tray_icon(self) -> int:
        if ICON_PATH.exists():
            try:
                icon = win32gui.LoadImage(
                    0,
                    str(ICON_PATH),
                    IMAGE_ICON,
                    0,
                    0,
                    LR_LOADFROMFILE | LR_DEFAULTSIZE,
                )
                log_tray(f"Loaded tray icon: {ICON_PATH}")
                return icon
            except Exception:
                log_tray("Failed to load custom tray icon:")
                log_tray(traceback.format_exc())
        return win32gui.LoadIcon(0, win32con.IDI_APPLICATION)

    def remove_tray_icon(self) -> None:
        if self.hwnd:
            win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, (self.hwnd, 0))

    def on_tray(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        try:
            if lparam in (
                win32con.WM_RBUTTONUP,
                win32con.WM_CONTEXTMENU,
                win32con.WM_LBUTTONDBLCLK,
            ):
                log_tray(f"Tray menu requested, lparam={lparam}")
                self.show_menu()
        except Exception:
            log_tray("Tray callback failed:")
            log_tray(traceback.format_exc())
        return 0

    def show_menu(self) -> None:
        log_tray("Creating tray menu")
        menu = win32gui.CreatePopupMenu()
        log_tray(f"Popup menu handle={menu}")
        win32gui.AppendMenu(menu, win32con.MF_STRING, MENU_OPEN_LOG, "Open log")
        log_tray("Added Open log menu item")
        win32gui.AppendMenu(menu, win32con.MF_SEPARATOR, 0, "")
        log_tray("Added menu separator")
        win32gui.AppendMenu(menu, win32con.MF_STRING, MENU_EXIT, "Exit ClipAnywhere")
        log_tray("Added Exit ClipAnywhere menu item")
        pos = win32gui.GetCursorPos()
        log_tray(f"Showing tray menu at {pos[0]},{pos[1]}")
        win32gui.SetForegroundWindow(self.hwnd)
        command = win32gui.TrackPopupMenu(
            menu,
            win32con.TPM_LEFTALIGN | win32con.TPM_RIGHTBUTTON | win32con.TPM_RETURNCMD,
            pos[0],
            pos[1],
            0,
            self.hwnd,
            None,
        )
        log_tray(f"Tray menu command returned: {command}")
        win32gui.PostMessage(self.hwnd, win32con.WM_NULL, 0, 0)
        win32gui.DestroyMenu(menu)
        if command:
            self.handle_menu_command(command)

    def on_command(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        self.handle_menu_command(win32api.LOWORD(wparam))
        return 0

    def handle_menu_command(self, command: int) -> None:
        if command == MENU_OPEN_LOG:
            if not LOG_PATH.exists():
                LOG_PATH.write_text("", encoding="utf-8")
            os.startfile(LOG_PATH)
        elif command == MENU_EXIT:
            self.exit()

    def on_destroy(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        log_tray("Tray window destroying")
        self.remove_tray_icon()
        self.stop_client()
        win32gui.PostQuitMessage(0)
        return 0

    def exit(self) -> None:
        win32gui.DestroyWindow(self.hwnd)

    def stop_client(self) -> None:
        if self.process and self.process.poll() is None:
            log_tray(f"Stopping client process, pid={self.process.pid}")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                log_tray("Client process killed after timeout")


if __name__ == "__main__":
    try:
        if sys.platform != "win32":
            raise SystemExit("Tray launcher is Windows-only")
        TrayApp().run()
    except Exception:
        log_tray("Tray launcher crashed:")
        log_tray(traceback.format_exc())
        raise
