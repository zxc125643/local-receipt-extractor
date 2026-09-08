from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response

from .services.receipt_extractor import (
    LocalReceiptExtractor,
    build_invoice_record,
    build_payment_rows,
    clean_columns,
    create_reimbursement_workbook,
    enrich_expense_classifications,
    is_invoice,
    reimbursement_workbook_title,
)

ALLOWED = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
MAX_FILES = 200


@dataclass
class ReceiptJob:
    id: str
    files: list[tuple[str, bytes]]
    total: int
    status: str = "queued"
    completed: int = 0
    current_file: str = ""
    error: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[dict[str, str]] = field(default_factory=list)
    invoices: list[dict[str, str]] = field(default_factory=list)
    worker_count: int = 2
    duplicate_count: int = 0
    duplicate_files: list[str] = field(default_factory=list)
    title: str = ""
    manual_entries: list[dict[str, str]] = field(default_factory=list)
    manual_draft: str = ""


app = FastAPI(title="Local Receipt Extractor", version="2.0.0")
jobs: dict[str, ReceiptJob] = {}


def _data_root() -> Path:
    root = Path(os.getenv("RECEIPT_DATA_DIR", "/data"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _history_db() -> Path:
    path = _data_root() / "receipt_history.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE IF NOT EXISTS receipt_batches (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, total INTEGER NOT NULL, rows_json TEXT NOT NULL, title TEXT NOT NULL DEFAULT '')")
        db.execute("CREATE TABLE IF NOT EXISTS receipt_image_hashes (digest TEXT PRIMARY KEY, batch_id TEXT NOT NULL)")
    return path


def _history_dir(job_id: str, create: bool = True) -> Path:
    path = _data_root() / "receipt-history" / job_id
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def _assert_auth(x_receipt_token: str = Header("", alias="X-Receipt-Token")) -> None:
    expected = os.getenv("RECEIPT_ACCESS_TOKEN", "").strip()
    if expected and x_receipt_token != expected:
        raise HTTPException(status_code=401, detail="访问口令错误。")


@lru_cache(maxsize=1)
def get_extractor() -> LocalReceiptExtractor:
    return LocalReceiptExtractor()


def _parse_columns(raw: str) -> list[str]:
    try:
        value = json.loads(raw)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError("列名必须是文本列表。")
        return clean_columns(value)
    except (json.JSONDecodeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


def _dedupe_saved(data: dict[str, object]) -> dict[str, object]:
    columns = [str(value) for value in data.get("columns", [])]
    source_rows = data.get("rows", [])
    rows = source_rows if isinstance(source_rows, list) else []
    unique: list[dict[str, str]] = []
    seen: set[tuple[str, ...]] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = tuple(str(row.get(column, "")).strip() for column in columns)
        if not any(key) or key in seen:
            continue
        seen.add(key)
        unique.append(row)
    columns, unique = enrich_expense_classifications(columns, unique)
    data["columns"] = columns
    data["rows"] = unique
    return data


def _persist_job(job: ReceiptJob) -> None:
    image_dir = _history_dir(job.id)
    for name, content in job.files:
        safe_name = hashlib.sha256(name.encode("utf-8")).hexdigest() + Path(name).suffix.lower()
        (image_dir / safe_name).write_bytes(content)
    payload = {
        "columns": job.columns,
        "rows": job.rows,
        "invoices": job.invoices,
        "files": [name for name, _ in job.files],
        "manual_entries": job.manual_entries,
        "manual_draft": job.manual_draft,
    }
    with sqlite3.connect(_history_db()) as db:
        db.execute("INSERT OR REPLACE INTO receipt_batches (id, created_at, total, rows_json, title) VALUES (?, ?, ?, ?, ?)", (job.id, datetime.now(timezone.utc).isoformat(), job.total, json.dumps(payload, ensure_ascii=False), job.title))
        for _, content in job.files:
            db.execute("INSERT OR IGNORE INTO receipt_image_hashes (digest, batch_id) VALUES (?, ?)", (hashlib.sha256(content).hexdigest(), job.id))


def _load_saved(job_id: str) -> tuple[dict[str, object], str] | None:
    with sqlite3.connect(_history_db()) as db:
        saved = db.execute("SELECT rows_json, title FROM receipt_batches WHERE id=?", (job_id,)).fetchone()
    return (_dedupe_saved(json.loads(saved[0])), str(saved[1] or "")) if saved else None


def _load_images(job_id: str, names: list[str]) -> list[tuple[str, bytes]]:
    image_dir = _history_dir(job_id, create=False)
    files: list[tuple[str, bytes]] = []
    for name in names:
        safe_name = hashlib.sha256(name.encode("utf-8")).hexdigest() + Path(name).suffix.lower()
        image_path = image_dir / safe_name
        if image_path.exists():
            files.append((name, image_path.read_bytes()))
    return files


def _run_job_sync(job: ReceiptJob, requested_columns: list[str]) -> None:
    extractor = get_extractor()

    def progress(completed: int, _total: int, index: int) -> None:
        job.completed = completed
        job.current_file = job.files[index][0]

    contents = [content for _, content in job.files]
    read_many = getattr(extractor, "read_many", None)
    results = read_many(contents, progress, worker_count=job.worker_count) if read_many else [extractor.read(content) for content in contents]
    documents = [(name, lines) for (name, _), lines in zip(job.files, results, strict=True)]
    job.invoices = [build_invoice_record(name, lines) for name, lines in documents if is_invoice(lines)]
    job.columns, job.rows = build_payment_rows(requested_columns, documents)
    unique_rows: list[dict[str, str]] = []
    seen_rows: set[tuple[str, ...]] = set()
    for row in job.rows:
        key = tuple(str(row.get(column, "")).strip() for column in job.columns)
        if not any(key) or key in seen_rows:
            continue
        seen_rows.add(key)
        unique_rows.append(row)
    job.rows = unique_rows
    _persist_job(job)


async def _run_job(job: ReceiptJob, requested_columns: list[str]) -> None:
    job.status = "processing"
    try:
        await asyncio.to_thread(_run_job_sync, job, requested_columns)
        job.completed = job.total
        job.status = "completed"
    except Exception as error:
        job.error = str(error)
        job.status = "failed"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(Path(__file__).resolve().parents[2] / "static" / "index.html")


@app.post("/api/process", dependencies=[Depends(_assert_auth)])
async def process(columns: str = Form(...), worker_count: int = Form(2), force_reprocess: bool = Form(False), title: str = Form(""), files: list[UploadFile] = File(...)) -> dict[str, object]:
    requested = _parse_columns(columns)
    if not 1 <= worker_count <= 4:
        raise HTTPException(status_code=422, detail="线程数必须是 1 到 4。")
    if not files or len(files) > MAX_FILES:
        raise HTTPException(status_code=422, detail=f"请上传 1 到 {MAX_FILES} 个文件。")
    with sqlite3.connect(_history_db()) as db:
        historical_hashes = {row[0] for row in db.execute("SELECT digest FROM receipt_image_hashes")}
    uploaded: list[tuple[str, bytes]] = []
    duplicate_files: list[str] = []
    seen_hashes: set[str] = set()
    for file in files:
        name = file.filename or "未命名图片"
        if file.content_type not in ALLOWED and Path(name).suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".pdf"}:
            raise HTTPException(status_code=422, detail=f"不支持的文件：{name}")
        content = await file.read()
        digest = hashlib.sha256(content).hexdigest()
        if digest in seen_hashes or (digest in historical_hashes and not force_reprocess):
            duplicate_files.append(name)
            continue
        seen_hashes.add(digest)
        uploaded.append((name, content))
    job_id = str(uuid.uuid4())
    job = ReceiptJob(id=job_id, files=uploaded, total=len(uploaded), worker_count=worker_count, duplicate_count=len(duplicate_files), duplicate_files=duplicate_files, title=title.strip()[:120], current_file=uploaded[0][0] if uploaded else "")
    jobs[job_id] = job
    asyncio.create_task(_run_job(job, requested))
    return {"job_id": job_id, "status": job.status, "total": job.total, "completed": 0, "duplicate_count": job.duplicate_count, "duplicate_files": job.duplicate_files}


@app.get("/api/status/{job_id}", dependencies=[Depends(_assert_auth)])
def status(job_id: str) -> dict[str, object]:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在或已过期。")
    result: dict[str, object] = {"job_id": job.id, "status": job.status, "total": job.total, "completed": job.completed, "current_file": job.current_file, "duplicate_count": job.duplicate_count, "duplicate_files": job.duplicate_files}
    if job.status == "completed":
        result.update(columns=job.columns, rows=job.rows)
    if job.error:
        result["error"] = job.error
    return result


@app.get("/api/history", dependencies=[Depends(_assert_auth)])
def history() -> list[dict[str, object]]:
    with sqlite3.connect(_history_db()) as db:
        saved_rows = db.execute("SELECT id, created_at, total, rows_json, title FROM receipt_batches ORDER BY created_at DESC").fetchall()
    return [{"job_id": row[0], "created_at": row[1], "total": row[2], "title": row[4] or row[1], **_dedupe_saved(json.loads(row[3]))} for row in saved_rows]


@app.patch("/api/history/{job_id}", dependencies=[Depends(_assert_auth)])
def rename_history(job_id: str, payload: dict[str, object]) -> dict[str, str]:
    title = str(payload.get("title", "")).strip()[:120]
    if not title:
        raise HTTPException(status_code=422, detail="名称不能为空。")
    with sqlite3.connect(_history_db()) as db:
        result = db.execute("UPDATE receipt_batches SET title=? WHERE id=?", (title, job_id))
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="找不到该历史批次。")
    if job_id in jobs:
        jobs[job_id].title = title
    return {"job_id": job_id, "title": title}


@app.put("/api/history/{job_id}/manual", dependencies=[Depends(_assert_auth)])
def save_manual(job_id: str, payload: dict[str, object]) -> dict[str, object]:
    entries = payload.get("manual_entries", [])
    draft = payload.get("manual_draft", "")
    if not isinstance(entries, list) or not all(isinstance(item, dict) for item in entries) or not isinstance(draft, str):
        raise HTTPException(status_code=422, detail="补录格式无效。")
    job = jobs.get(job_id)
    if job:
        job.manual_entries = entries
        job.manual_draft = draft
    with sqlite3.connect(_history_db()) as db:
        saved = db.execute("SELECT rows_json FROM receipt_batches WHERE id=?", (job_id,)).fetchone()
        if saved:
            data = json.loads(saved[0]); data.update(manual_entries=entries, manual_draft=draft)
            db.execute("UPDATE receipt_batches SET rows_json=? WHERE id=?", (json.dumps(data, ensure_ascii=False), job_id))
        elif not job:
            raise HTTPException(status_code=404, detail="找不到该历史批次。")
    return {"job_id": job_id, "saved": True}


@app.delete("/api/history/{job_id}", dependencies=[Depends(_assert_auth)])
def delete_history(job_id: str) -> dict[str, bool]:
    with sqlite3.connect(_history_db()) as db:
        db.execute("DELETE FROM receipt_batches WHERE id=?", (job_id,)); db.execute("DELETE FROM receipt_image_hashes WHERE batch_id=?", (job_id,))
    shutil.rmtree(_history_dir(job_id, create=False), ignore_errors=True)
    jobs.pop(job_id, None)
    return {"deleted": True}


@app.post("/api/export", dependencies=[Depends(_assert_auth)])
def export(payload: dict[str, object]) -> Response:
    job_id = str(payload.get("job_id", "")); saved = _load_saved(job_id); job = jobs.get(job_id)
    if job is None:
        if saved is None:
            raise HTTPException(status_code=422, detail="找不到该历史批次。")
        data, saved_title = saved
        names = [str(name) for name in data.get("files", [])]; files = _load_images(job_id, names)
        job = ReceiptJob(id=job_id, files=files, total=len(files), status="completed", columns=[str(value) for value in data.get("columns", [])], rows=data.get("rows", []), invoices=data.get("invoices", []), title=saved_title, manual_entries=data.get("manual_entries", []), manual_draft=str(data.get("manual_draft", "")))
    if job.status != "completed":
        raise HTTPException(status_code=422, detail="图片仍在识别中，请等待处理完成。")
    requested_title = str(payload.get("title", "")).strip()[:120] or job.title
    manual_entries = payload.get("manual_entries", job.manual_entries)
    if not isinstance(manual_entries, list) or not all(isinstance(item, dict) for item in manual_entries):
        raise HTTPException(status_code=422, detail="手工补录格式无效。")
    images = dict(job.files)
    content = create_reimbursement_workbook(job.rows, images, images, job.invoices, requested_title, manual_entries)
    title = re.sub(r'[\\/:*?"<>|\r\n]+', "_", reimbursement_workbook_title(job.rows, requested_title, manual_entries)).strip(" .") or "费用报销单"
    return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(title)}.xlsx"})
