from __future__ import annotations

import platform

if platform.system() == "Darwin":
    from .clipboard_macos import (
        ClipboardUnavailable,
        copy_files_to_clipboard,
        get_clipboard_lock_owner,
        get_file_paths,
        get_text,
        hotkey_description,
        prepare_clipanywhere_copy,
        register_sync_hotkey,
        set_text,
        sync_hotkey_pressed,
        unregister_sync_hotkey,
    )
elif platform.system() == "Windows":
    from .clipboard_windows import (
        ClipboardUnavailable,
        copy_files_to_clipboard,
        get_clipboard_lock_owner,
        get_file_paths,
        get_text,
        hotkey_description,
        prepare_clipanywhere_copy,
        register_sync_hotkey,
        set_text,
        sync_hotkey_pressed,
        unregister_sync_hotkey,
    )
else:
    raise RuntimeError("ClipAnywhere client supports Windows and macOS")
