from __future__ import annotations

import argparse
import base64
import hashlib
import json
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

from .clipboard_windows import (
    ClipboardUnavailable,
    copy_files_to_clipboard,
    extract_zip_to_downloads,
    get_file_paths,
    get_text,
    set_text,
    zip_paths,
)
from .common import load_json, sha256_bytes


class Client:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.server_url = config["server_url"].rstrip("/") + "/"
        self.device_name = config["device_name"]
        self.poll_seconds = float(config.get("poll_seconds", 2))
        self.download_dir = Path(config.get("download_dir", "ClipAnywhereDownloads"))
        self.last_seen_id = 0
        self.last_local_digest = ""
        self.proxy_authorization = ""
        self.install_proxy()

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

    def push_local_clipboard(self) -> None:
        paths = get_file_paths()
        if paths:
            existing_paths = [p for p in paths if p.exists()]
            digest = digest_paths(existing_paths)
            if existing_paths and digest != self.last_local_digest:
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
            return

        text = get_text()
        if text is None:
            return
        digest = sha256_bytes(text.encode("utf-8"))
        if digest != self.last_local_digest:
            result = self.request_json(
                "POST",
                "push/text",
                {"source_device": self.device_name, "text": text},
            )
            self.mark_seen(result.get("item"))
            self.last_local_digest = digest

    def pull_remote_clipboard(self) -> None:
        item = self.request_json("GET", "latest").get("item")
        if not item:
            return
        if item["id"] <= self.last_seen_id or item["source_device"] == self.device_name:
            self.mark_seen(item)
            return
        if item["kind"] == "text":
            set_text(item["text"])
            self.last_local_digest = sha256_bytes(item["text"].encode("utf-8"))
        elif item["kind"] == "files":
            body = self.request_bytes(item["download_url"])
            targets = extract_zip_to_downloads(body, self.download_dir)
            copy_files_to_clipboard(targets)
            self.last_local_digest = item["sha256"]
        self.mark_seen(item)

    def mark_seen(self, item: dict[str, Any] | None) -> None:
        if item:
            self.last_seen_id = max(self.last_seen_id, int(item["id"]))

    def run(self) -> None:
        print(f"ClipAnywhere client running as {self.device_name}")
        while True:
            try:
                self.pull_remote_clipboard()
                self.push_local_clipboard()
            except HTTPError as exc:
                print(f"HTTP error: {exc.code} {exc.reason}")
            except ClipboardUnavailable as exc:
                print(f"Clipboard busy, retrying: {exc}")
            except Exception as exc:
                print(f"Sync error: {exc}")
            time.sleep(self.poll_seconds)


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="client_config.json")
    args = parser.parse_args()
    Client(load_json(args.config)).run()


if __name__ == "__main__":
    main()
