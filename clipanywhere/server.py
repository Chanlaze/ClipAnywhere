from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import time
from contextlib import closing
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .common import load_json, sha256_bytes


SCHEMA = """
CREATE TABLE IF NOT EXISTS clipboard_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    source_device TEXT NOT NULL,
    created_at REAL NOT NULL,
    text TEXT,
    file_name TEXT,
    file_path TEXT,
    sha256 TEXT NOT NULL
);
"""


class Store:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.files_dir = data_dir / "files"
        self.db_path = data_dir / "clipanywhere.sqlite3"
        self.files_dir.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db:
            with db:
                db.executescript(SCHEMA)

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row
        return db

    def latest(self) -> dict[str, Any] | None:
        with closing(self.connect()) as db:
            row = db.execute(
                "SELECT * FROM clipboard_items ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def get(self, item_id: int) -> dict[str, Any] | None:
        with closing(self.connect()) as db:
            row = db.execute(
                "SELECT * FROM clipboard_items WHERE id = ?", (item_id,)
            ).fetchone()
        return dict(row) if row else None

    def add_text(self, source_device: str, text: str) -> dict[str, Any]:
        digest = sha256_bytes(text.encode("utf-8"))
        with closing(self.connect()) as db:
            with db:
                cur = db.execute(
                    """
                    INSERT INTO clipboard_items
                    (kind, source_device, created_at, text, sha256)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    ("text", source_device, time.time(), text, digest),
                )
                item_id = int(cur.lastrowid)
        return self.get(item_id) or {}

    def add_files(self, source_device: str, file_name: str, body: bytes) -> dict[str, Any]:
        digest = sha256_bytes(body)
        stored_name = f"{int(time.time())}-{digest[:16]}.zip"
        file_path = self.files_dir / stored_name
        file_path.write_bytes(body)
        with closing(self.connect()) as db:
            with db:
                cur = db.execute(
                    """
                    INSERT INTO clipboard_items
                    (kind, source_device, created_at, file_name, file_path, sha256)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    ("files", source_device, time.time(), file_name, str(file_path), digest),
                )
                item_id = int(cur.lastrowid)
        return self.get(item_id) or {}


class ClipHandler(BaseHTTPRequestHandler):
    server_version = "ClipAnywhere/0.1"

    def do_GET(self) -> None:
        if not self.authorized():
            self.reply_error(HTTPStatus.UNAUTHORIZED, "unauthorized")
            return
        parsed = urlparse(self.path)
        path = self.normalized_path(parsed.path)
        if path == "/health":
            self.reply_json({"ok": True})
            return
        if path == "/latest":
            item = self.store.latest()
            self.reply_json({"item": self.public_item(item) if item else None})
            return
        if path.startswith("/files/"):
            self.serve_file(path.removeprefix("/files/"))
            return
        self.reply_error(HTTPStatus.NOT_FOUND, "not found")

    def do_POST(self) -> None:
        if not self.authorized():
            self.reply_error(HTTPStatus.UNAUTHORIZED, "unauthorized")
            return
        parsed = urlparse(self.path)
        path = self.normalized_path(parsed.path)
        if path == "/push/text":
            payload = self.read_json()
            item = self.store.add_text(
                source_device=str(payload.get("source_device", "unknown")),
                text=str(payload.get("text", "")),
            )
            self.reply_json({"item": self.public_item(item)})
            return
        if path == "/push/files":
            length = self.content_length()
            max_bytes = int(self.config["max_upload_mb"]) * 1024 * 1024
            if length > max_bytes:
                self.reply_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "upload too large")
                return
            body = self.rfile.read(length)
            file_name = self.headers.get("X-ClipAnywhere-Filename", "clipboard-files.zip")
            source_device = self.headers.get("X-ClipAnywhere-Device", "unknown")
            item = self.store.add_files(source_device, file_name, body)
            self.reply_json({"item": self.public_item(item)})
            return
        self.reply_error(HTTPStatus.NOT_FOUND, "not found")

    @property
    def store(self) -> Store:
        return self.server.store  # type: ignore[attr-defined]

    @property
    def config(self) -> dict[str, Any]:
        return self.server.config  # type: ignore[attr-defined]

    def normalized_path(self, path: str) -> str:
        base_path = str(self.config.get("base_path", "")).rstrip("/")
        if base_path and path.startswith(base_path + "/"):
            return path.removeprefix(base_path)
        if base_path and path == base_path:
            return "/"
        return path

    def authorized(self) -> bool:
        expected = f"Bearer {self.config['token']}"
        return self.headers.get("Authorization") == expected

    def content_length(self) -> int:
        return int(self.headers.get("Content-Length", "0"))

    def read_json(self) -> dict[str, Any]:
        raw = self.rfile.read(self.content_length())
        return json.loads(raw.decode("utf-8"))

    def public_item(self, item: dict[str, Any] | None) -> dict[str, Any] | None:
        if item is None:
            return None
        public = {
            "id": item["id"],
            "kind": item["kind"],
            "source_device": item["source_device"],
            "created_at": item["created_at"],
            "sha256": item["sha256"],
        }
        if item["kind"] == "text":
            public["text"] = item["text"]
        if item["kind"] == "files":
            public["file_name"] = item["file_name"]
            public["download_url"] = f"/files/{item['id']}"
        return public

    def serve_file(self, raw_id: str) -> None:
        try:
            item_id = int(raw_id)
        except ValueError:
            self.reply_error(HTTPStatus.BAD_REQUEST, "invalid file id")
            return
        item = self.store.get(item_id)
        if not item or item["kind"] != "files":
            self.reply_error(HTTPStatus.NOT_FOUND, "file not found")
            return
        path = Path(item["file_path"])
        if not path.exists():
            self.reply_error(HTTPStatus.GONE, "file missing on server")
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", f'attachment; filename="{item["file_name"]}"')
        self.send_header("Content-Length", str(path.stat().st_size))
        self.end_headers()
        with path.open("rb") as f:
            shutil.copyfileobj(f, self.wfile)

    def reply_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def reply_error(self, status: HTTPStatus, message: str) -> None:
        self.reply_json({"error": message}, status)

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        if self.is_successful_healthcheck(code):
            return
        super().log_request(code, size)

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.address_string()} - {fmt % args}")

    def is_successful_healthcheck(self, code: int | str) -> bool:
        return self.normalized_path(urlparse(self.path).path) == "/health" and str(code) == "200"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="server_config.json")
    args = parser.parse_args()
    config = load_json(args.config)
    store = Store(Path(config.get("data_dir", "clipanywhere_data")))
    server = ThreadingHTTPServer((config["host"], int(config["port"])), ClipHandler)
    server.config = config  # type: ignore[attr-defined]
    server.store = store  # type: ignore[attr-defined]
    print(f"ClipAnywhere server listening on {config['host']}:{config['port']}")
    server.serve_forever()


if __name__ == "__main__":
    main()
