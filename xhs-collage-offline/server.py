"""方格志离线草稿服务：只使用 Python 标准库和本地 SQLite。"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "drafts.db"
HOST = "0.0.0.0"
PORT = 8766


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
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
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
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
        return self.send_json(404, {"error": "接口不存在"})

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path.rstrip("/") != "/api/drafts":
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
