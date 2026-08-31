from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shutil
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.request import (
    HTTPBasicAuthHandler,
    ProxyBasicAuthHandler,
    ProxyHandler,
    Request,
    build_opener,
    install_opener,
    urlopen,
)

from .archive import extract_zip_to_downloads, zip_paths
from .clipboard import (
    ClipboardUnavailable,
    copy_files_to_clipboard,
    get_file_paths,
    get_clipboard_lock_owner,
    get_text,
    hotkey_description,
    prepare_clipanywhere_copy,
    register_sync_hotkey,
    set_text,
    sync_hotkey_pressed,
    unregister_sync_hotkey,
)
from .common import load_json, sha256_bytes


class Client:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.server_url = config["server_url"].rstrip("/") + "/"
        self.device_name = config["device_name"]
        self.poll_seconds = float(config.get("poll_seconds", 2))
        self.download_dir = Path(config.get("download_dir", "ClipAnywhereDownloads"))
        self.cleanup_downloads_enabled = bool(config.get("cleanup_downloads_enabled", True))
        self.download_retention_days = float(config.get("download_retention_days", 7))
        self.download_max_items = int(config.get("download_max_items", 20))
        self.last_seen_id = 0
        self.last_local_digest = ""
        self.last_clipboard_busy_log = 0.0
        self.clipboard_busy_log_seconds = float(config.get("clipboard_busy_log_seconds", 30))
        self.proxy_authorization = ""
        self.install_proxy()

    def log(self, message: str) -> None:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{stamp}] {message}", flush=True)

    def install_proxy(self) -> None:
        proxy = self.config.get("proxy", {})
        if not proxy.get("enabled"):
            return
        proxy_url = proxy["url"]
        handlers: list[Any] = [ProxyHandler({"http": proxy_url, "https": proxy_url})]
        username = proxy.get("username")
        password = proxy.get("password")
        if username and password:
            raw_credentials = f"{username}:{password}".encode("utf-8")
            encoded_credentials = base64.b64encode(raw_credentials).decode("ascii")
            self.proxy_authorization = f"Basic {encoded_credentials}"
            proxy_auth = ProxyBasicAuthHandler()
            proxy_auth.add_password(None, proxy_url, username, password)
            handlers.append(proxy_auth)
            basic_auth = HTTPBasicAuthHandler()
            basic_auth.add_password(None, proxy_url, username, password)
            handlers.append(basic_auth)
        install_opener(build_opener(*handlers))

    def headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.config['token']}"}
        if self.proxy_authorization:
            headers["Proxy-Authorization"] = self.proxy_authorization
        if extra:
            headers.update(extra)
        return headers

    def request_json(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = self.headers({"Content-Type": "application/json"})
        req = Request(urljoin(self.server_url, path), data=body, headers=headers, method=method)
        with urlopen(req, timeout=30) as res:
            return json.loads(res.read().decode("utf-8"))

    def request_bytes(self, path: str) -> bytes:
        req = Request(urljoin(self.server_url, path.lstrip("/")), headers=self.headers(), method="GET")
        with urlopen(req, timeout=120) as res:
            return res.read()

    def post_bytes(self, path: str, body: bytes, headers: dict[str, str]) -> dict[str, Any]:
        req = Request(
            urljoin(self.server_url, path),
            data=body,
            headers=self.headers(headers),
            method="POST",
        )
        with urlopen(req, timeout=180) as res:
            return json.loads(res.read().decode("utf-8"))

    def push_local_clipboard(self, *, force_log: bool = False) -> None:
        paths = get_file_paths()
        if paths:
            existing_paths = [p for p in paths if p.exists()]
            digest = digest_paths(existing_paths)
            if existing_paths and digest != self.last_local_digest:
                self.log(f"Files/Folder being sync: uploading {describe_paths(existing_paths)}")
                name, body = zip_paths(existing_paths)
                result = self.post_bytes(
                    "push/files",
                    body,
                    {
                        "Content-Type": "application/zip",
                        "X-ClipAnywhere-Filename": name,
                        "X-ClipAnywhere-Device": self.device_name,
                    },
                )
                self.mark_seen(result.get("item"))
                self.last_local_digest = digest
                self.log("Files/Folder sync uploaded")
            elif force_log:
                self.log("Files/Folder clipboard unchanged, upload skipped")
            return

        text = get_text()
        if text is None:
            if force_log:
                self.log("Clipboard has no text/files to sync")
            return
        digest = sha256_bytes(text.encode("utf-8"))
        if digest != self.last_local_digest:
            self.log(f"Text being sync: uploading {len(text)} characters")
            result = self.request_json(
                "POST",
                "push/text",
                {"source_device": self.device_name, "text": text},
            )
            self.mark_seen(result.get("item"))
            self.last_local_digest = digest
            self.log("Text sync uploaded")
        elif force_log:
            self.log("Text clipboard unchanged, upload skipped")

    def pull_remote_clipboard(self) -> None:
        item = self.request_json("GET", "latest").get("item")
        if not item:
            return
        if item["id"] <= self.last_seen_id or item["source_device"] == self.device_name:
            self.mark_seen(item)
            return
        if item["kind"] == "text":
            self.log(f"Text being sync: downloading from {item['source_device']}")
            set_text(item["text"])
            self.last_local_digest = sha256_bytes(item["text"].encode("utf-8"))
            self.log(f"Text placed on clipboard: {len(item['text'])} characters")
        elif item["kind"] == "files":
            self.log(f"Files/Folder being sync: downloading from {item['source_device']}")
            body = self.request_bytes(item["download_url"])
            targets = extract_zip_to_downloads(body, self.download_dir)
            self.log(f"Files/Folder downloaded: {describe_paths(targets)}")
            copy_files_to_clipboard(targets)
            self.last_local_digest = digest_paths(targets)
            self.log("Files/Folder placed on clipboard, ready for Ctrl+V")
            self.cleanup_downloads(keep_paths=targets)
        self.mark_seen(item)

    def mark_seen(self, item: dict[str, Any] | None) -> None:
        if item:
            self.last_seen_id = max(self.last_seen_id, int(item["id"]))

    def cleanup_downloads(self, *, keep_paths: list[Path]) -> None:
        if not self.cleanup_downloads_enabled or not self.download_dir.exists():
            return

        keep_roots = {download_batch_root(path, self.download_dir) for path in keep_paths}
        keep_roots = {path.resolve() for path in keep_roots if path is not None}
        now = time.time()
        max_age_seconds = self.download_retention_days * 24 * 60 * 60
        candidates = [
            path
            for path in self.download_dir.iterdir()
            if path.name.startswith("clipboard-files-") and path.resolve() not in keep_roots
        ]
        candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)

        removed = 0
        for index, path in enumerate(candidates):
            too_old = self.download_retention_days >= 0 and now - path.stat().st_mtime > max_age_seconds
            too_many = self.download_max_items >= 0 and index >= self.download_max_items
            if too_old or too_many:
                try:
                    remove_path(path)
                except OSError as exc:
                    self.log(f"Download cleanup skipped {path.name}: {exc}")
                else:
                    removed += 1
        if removed:
            self.log(f"Download cleanup removed {removed} old sync item(s)")

    def run(self) -> None:
        self.log(f"ClipAnywhere client running as {self.device_name}")
        self.log(f"Server: {self.server_url.rstrip('/')}")
        hotkey_enabled = True
        try:
            register_sync_hotkey()
        except ClipboardUnavailable as exc:
            hotkey_enabled = False
            self.log(f"Hotkey unavailable: {exc}")
            self.log("Receiving clipboard sync still works. Close the other ClipAnywhere copy, then restart this client.")
        else:
            self.log(f"Status: press {hotkey_description()} to ClipAnywhere-copy and sync")

        try:
            while True:
                try:
                    self.pull_remote_clipboard()
                    if hotkey_enabled and sync_hotkey_pressed():
                        self.log(f"{hotkey_description()} pressed: ClipAnywhere copy started")
                        prepare_clipanywhere_copy()
                        self.push_local_clipboard(force_log=True)
                except HTTPError as exc:
                    self.log(f"HTTP error: {exc.code} {exc.reason}")
                except ClipboardUnavailable as exc:
                    now = time.time()
                    if now - self.last_clipboard_busy_log >= self.clipboard_busy_log_seconds:
                        owner = get_clipboard_lock_owner()
                        self.log(f"Clipboard busy, retrying: {exc}; locked by {owner}")
                        self.last_clipboard_busy_log = now
                except Exception as exc:
                    self.log(f"Sync error: {exc}")
                time.sleep(self.poll_seconds)
        finally:
            unregister_sync_hotkey()


def digest_paths(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for path in sorted(paths, key=lambda p: str(p).lower()):
        if path.is_dir():
            add_directory_to_digest(h, path.relative_to(path.parent))
            for child in sorted(path.rglob("*"), key=lambda p: str(p).lower()):
                if child.is_dir():
                    add_directory_to_digest(h, child.relative_to(path.parent))
                if child.is_file():
                    add_file_to_digest(h, child, child.relative_to(path.parent))
        elif path.is_file():
            add_file_to_digest(h, path, Path(path.name))
    return h.hexdigest()


def add_file_to_digest(h: Any, path: Path, archive_name: Path) -> None:
    stat = path.stat()
    h.update(str(archive_name).replace("\\", "/").encode("utf-8"))
    h.update(b"\0")
    h.update(str(stat.st_size).encode("ascii"))
    h.update(b"\0")
    h.update(str(stat.st_mtime_ns).encode("ascii"))
    h.update(b"\0")


def add_directory_to_digest(h: Any, archive_name: Path) -> None:
    h.update(b"dir")
    h.update(b"\0")
    h.update(str(archive_name).replace("\\", "/").encode("utf-8"))
    h.update(b"\0")


def describe_paths(paths: list[Path]) -> str:
    if not paths:
        return "0 items"
    if len(paths) == 1:
        path = paths[0]
        kind = "folder" if path.is_dir() else "file"
        return f"1 {kind} ({path.name})"
    file_count = sum(1 for path in paths if path.is_file())
    folder_count = sum(1 for path in paths if path.is_dir())
    parts = []
    if file_count:
        parts.append(f"{file_count} files")
    if folder_count:
        parts.append(f"{folder_count} folders")
    return ", ".join(parts)


def download_batch_root(path: Path, download_dir: Path) -> Path | None:
    try:
        relative = path.resolve().relative_to(download_dir.resolve())
    except ValueError:
        return None
    if not relative.parts:
        return path
    return download_dir / relative.parts[0]


def remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="client_config.json")
    args = parser.parse_args()
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Config file not found: {config_path}", flush=True)
        print("Copy one of these example files to client_config.json, then edit server_url, token, and device_name:", flush=True)
        print("  client_config.example.json        office PC with proxy", flush=True)
        print("  client_config.direct.example.json PC without proxy", flush=True)
        print("  client_config.macos.example.json  macOS", flush=True)
        raise SystemExit(2)
    Client(load_json(config_path)).run()


if __name__ == "__main__":
    main()
