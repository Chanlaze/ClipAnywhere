from __future__ import annotations

import subprocess
from pathlib import Path


class ClipboardUnavailable(RuntimeError):
    pass


def get_clipboard_lock_owner() -> str:
    return "macOS pasteboard"


def get_text() -> str | None:
    result = run_command(["pbpaste"])
    text = result.stdout
    return text if text else None


def set_text(text: str) -> None:
    run_command(["pbcopy"], input_text=text)


def get_file_paths() -> list[Path]:
    script = """
set outputText to ""
try
    set clipboardItems to the clipboard as list
    repeat with clipboardItem in clipboardItems
        try
            set outputText to outputText & POSIX path of clipboardItem & linefeed
        end try
    end repeat
end try
return outputText
"""
    result = run_command(["osascript", "-e", script])
    return [Path(line) for line in result.stdout.splitlines() if line.strip()]


def copy_files_to_clipboard(paths: list[Path]) -> None:
    if not paths:
        return
    lines = ["set clipboardItems to {}"]
    for path in paths:
        lines.append(f"set end of clipboardItems to POSIX file {quote_applescript(str(path.resolve()))}")
    lines.append("set the clipboard to clipboardItems")
    run_command(["osascript", "-e", "\n".join(lines)])


def quote_applescript(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def run_command(command: list[str], input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            input=input_text,
            text=True,
            capture_output=True,
            check=True,
        )
    except FileNotFoundError as exc:
        raise ClipboardUnavailable(f"Missing macOS clipboard command: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        raise ClipboardUnavailable(detail) from exc

