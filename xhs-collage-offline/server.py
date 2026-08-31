"""方格志离线草稿服务：只使用 Python 标准库和本地 SQLite。"""

from __future__ import annotations

import json
import hashlib
import mimetypes
import os
import sqlite3
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("XHS_DATA_DIR", ROOT)).resolve()
DB_PATH = DATA_DIR / "drafts.db"
ASSET_DIR = DATA_DIR / "assets"
HOST = "0.0.0.0"
PORT = int(os.environ.get("XHS_API_PORT", "8766"))
MAX_ASSET_BYTES = 50 * 1024 * 1024


def safe_image_extension(filename: str, content_type: str) -> str:
    if not content_type.lower().startswith("image/"):
        raise ValueError("只允许上传图片")
    known = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/avif": ".avif",
        "image/heic": ".heic",
        "image/heif": ".heif",
    }
    return known.get(content_type.lower()) or Path(filename).suffix.lower() or ".img"


def store_asset(data: bytes, filename: str, content_type: str, directory: Path = ASSET_DIR) -> dict[str, str]:
    if not data:
        raise ValueError("图片内容为空")
    if len(data) > MAX_ASSET_BYTES:
        raise ValueError("单张图片不能超过 50MB")
    extension = safe_image_extension(filename, content_type)
    asset_id = hashlib.sha256(data).hexdigest()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{asset_id}{extension}"
    if not target.exists():
        temporary = target.with_suffix(f"{target.suffix}.tmp")
        temporary.write_bytes(data)
        temporary.replace(target)
    return {
        "id": asset_id,
        "name": filename or target.name,
        "src": f"/assets/{target.name}",
        "mimeType": content_type,
    }


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_name TEXT NOT NULL,
            payload TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    return connection


class Handler(BaseHTTPRequestHandler):
    server_version = "XHSCollageOffline/1.0"

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Filename")
        if not urlparse(self.path).path.startswith("/assets/"):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_json(self, status: int, payload: object) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path == "/health":
            return self.send_json(200, {"ok": True, "database": str(DB_PATH)})
        if path == "/api/drafts":
            with connect() as database:
                rows = database.execute(
                    "SELECT id, project_name, updated_at, payload FROM drafts ORDER BY updated_at DESC"
                ).fetchall()
            items = []
            for row in rows:
                data = json.loads(row["payload"])
                items.append(
                    {
                        "id": row["id"],
                        "project_name": row["project_name"],
                        "page_count": data.get("page_count", len(data.get("pages", [])) or 1),
                        "asset_count": data.get("asset_count", len(data.get("assets", []))),
                        "updated_at": row["updated_at"],
                    }
                )
            return self.send_json(200, {"drafts": items})
        prefix = "/api/drafts/"
        if path.startswith(prefix):
            try:
                draft_id = int(unquote(path[len(prefix) :]))
            except ValueError:
                return self.send_json(400, {"error": "项目编号无效"})
            with connect() as database:
                row = database.execute("SELECT payload FROM drafts WHERE id = ?", (draft_id,)).fetchone()
            if not row:
                return self.send_json(404, {"error": "项目不存在"})
            payload = json.loads(row["payload"])
            payload["id"] = draft_id
            return self.send_json(200, payload)
        asset_prefix = "/assets/"
        if path.startswith(asset_prefix):
            filename = Path(unquote(path[len(asset_prefix) :])).name
            target = ASSET_DIR / filename
            if not filename or not target.is_file():
                return self.send_json(404, {"error": "素材不存在"})
            body = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            self.end_headers()
            self.wfile.write(body)
            return
        return self.send_json(404, {"error": "接口不存在"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path.rstrip("/")
        if path == "/api/assets":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length > MAX_ASSET_BYTES:
                    return self.send_json(413, {"error": "单张图片不能超过 50MB"})
                filename = unquote(self.headers.get("X-Filename", "image"))[:255]
                asset = store_asset(
                    self.rfile.read(length),
                    filename,
                    self.headers.get("Content-Type", "application/octet-stream").split(";", 1)[0],
                )
            except (ValueError, OSError) as error:
                return self.send_json(400, {"error": str(error)})
            return self.send_json(201, asset)
        if path != "/api/drafts":
            return self.send_json(404, {"error": "接口不存在"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self.send_json(400, {"error": "项目数据格式无效"})
        name = str(payload.get("project_name") or payload.get("name") or "未命名项目").strip()[:100]
        updated_at = datetime.now(timezone.utc).isoformat()
        payload["project_name"] = name
        payload["updated_at"] = updated_at
        draft_id = payload.get("id")
        with connect() as database:
            if draft_id:
                exists = database.execute("SELECT 1 FROM drafts WHERE id = ?", (draft_id,)).fetchone()
            else:
                exists = None
            serialized = json.dumps(payload, ensure_ascii=False)
            if exists:
                database.execute(
                    "UPDATE drafts SET project_name = ?, payload = ?, updated_at = ? WHERE id = ?",
                    (name, serialized, updated_at, draft_id),
                )
            else:
                cursor = database.execute(
                    "INSERT INTO drafts(project_name, payload, updated_at) VALUES (?, ?, ?)",
                    (name, serialized, updated_at),
                )
                draft_id = cursor.lastrowid
            database.commit()
        return self.send_json(200, {"id": draft_id, "project_name": name, "updated_at": updated_at})

    def do_DELETE(self) -> None:  # noqa: N802
        path = urlparse(self.path).path.rstrip("/")
        prefix = "/api/drafts/"
        if not path.startswith(prefix):
            return self.send_json(404, {"error": "接口不存在"})
        try:
            draft_id = int(unquote(path[len(prefix) :]))
        except ValueError:
            return self.send_json(400, {"error": "项目编号无效"})
        with connect() as database:
            cursor = database.execute("DELETE FROM drafts WHERE id = ?", (draft_id,))
            database.commit()
        if cursor.rowcount == 0:
            return self.send_json(404, {"error": "项目不存在"})
        return self.send_json(200, {"ok": True, "id": draft_id})

    def log_message(self, format: str, *args: object) -> None:
        print(f"[{self.log_date_time_string()}] {format % args}")


if __name__ == "__main__":
    with ThreadingHTTPServer((HOST, PORT), Handler) as server:
        print(f"方格志离线草稿服务：http://127.0.0.1:{PORT}")
        server.serve_forever()
