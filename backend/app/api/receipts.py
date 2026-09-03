from __future__ import annotations

import json
import uuid
import asyncio
import hashlib
import sqlite3
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path
from functools import lru_cache

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from backend.app.api.deps import assert_desktop_auth
from backend.app.services.receipt_extractor import LocalReceiptExtractor, build_payment_rows, clean_columns, create_reimbursement_workbook, extract_invoice_fields, is_invoice, reimbursement_workbook_title

router = APIRouter(prefix="/receipts", tags=["receipts"], dependencies=[Depends(assert_desktop_auth)])
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
MAX_FILES = 200

@dataclass
class ReceiptJob:
    total: int
    files: list[tuple[str, bytes]]
    id: str = ""
    status: str = "queued"
    completed: int = 0
    current_file: str = ""
    error: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[dict[str, str]] = field(default_factory=list)
    payment_images: dict[str, bytes] = field(default_factory=dict)
    invoice_images: dict[str, bytes] = field(default_factory=dict)
    invoices: list[dict[str, str]] = field(default_factory=list)
    worker_count: int = 2
    duplicate_count: int = 0
    duplicate_files: list[str] = field(default_factory=list)


jobs: dict[str, ReceiptJob] = {}

def _dedupe_saved(data: dict[str, object]) -> dict[str, object]:
    columns = [str(x) for x in data.get('columns', [])]
    rows = data.get('rows', [])
    unique = []
    seen = set()
    for row in rows if isinstance(rows, list) else []:
        key = tuple(str(row.get(c, '')).strip() for c in columns)
        if not any(key) or key in seen:
            continue
        seen.add(key); unique.append(row)
    data['rows'] = unique
    return data

def _history_db() -> Path:
    root = Path(__import__('os').getenv('CORE_GATEWAY_DATA_DIR', '/data'))
    root.mkdir(parents=True, exist_ok=True)
    path = root / 'receipt_history.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE IF NOT EXISTS receipt_batches (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, total INTEGER NOT NULL, rows_json TEXT NOT NULL, title TEXT NOT NULL DEFAULT \'\')')
        columns = {row[1] for row in db.execute('PRAGMA table_info(receipt_batches)')}
        if 'title' not in columns:
            db.execute("ALTER TABLE receipt_batches ADD COLUMN title TEXT NOT NULL DEFAULT ''")
        db.execute('CREATE TABLE IF NOT EXISTS receipt_image_hashes (digest TEXT PRIMARY KEY, batch_id TEXT NOT NULL)')
    return path

def _history_dir(job_id: str) -> Path:
    path = _history_db().parent / 'receipt-history' / job_id
    path.mkdir(parents=True, exist_ok=True)
    return path


@lru_cache(maxsize=1)
def get_extractor() -> LocalReceiptExtractor:
    return LocalReceiptExtractor()


def parse_columns(raw_columns: str) -> list[str]:
    try:
        value = json.loads(raw_columns)
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=422, detail="列名格式无效。") from error
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise HTTPException(status_code=422, detail="列名必须是文本列表。")
    try:
        return clean_columns(value)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/process")
async def process_receipts(
    columns: str = Form(...),
    worker_count: int = Form(2),
    force_reprocess: bool = Form(False),
    files: list[UploadFile] = File(...),
) -> dict[str, object]:
    requested_columns = parse_columns(columns)
    if not files:
        raise HTTPException(status_code=422, detail="请至少选择一张图片。")
    if len(files) > MAX_FILES:
        raise HTTPException(status_code=422, detail=f"单次最多处理 {MAX_FILES} 张图片。")
    if worker_count < 1 or worker_count > 4:
        raise HTTPException(status_code=422, detail="线程数必须是 1 到 4。")

    uploaded_images: list[tuple[str, bytes]] = []
    source_images: dict[str, bytes] = {}
    seen_hashes: set[str] = set()
    duplicate_files: list[str] = []
    with sqlite3.connect(_history_db()) as db:
        historical_hashes = {row[0] for row in db.execute('SELECT digest FROM receipt_image_hashes')}
    for image in files:
        if image.content_type not in ALLOWED_IMAGE_TYPES and Path(image.filename or "").suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".pdf"}:
            raise HTTPException(status_code=422, detail=f"{image.filename} 不是支持的图片或 PDF 格式。")
        try:
            content = await image.read(); name = image.filename or "未命名图片"
            digest = hashlib.sha256(content).hexdigest()
            if digest in seen_hashes or (digest in historical_hashes and not force_reprocess):
                duplicate_files.append(name)
                continue
            seen_hashes.add(digest)
            source_images[name] = content
            uploaded_images.append((name, content))
        except Exception as error:
            raise HTTPException(status_code=422, detail=f"无法识别 {image.filename}：{error}") from error

    get_extractor()
    job_id = str(uuid.uuid4())
    job = ReceiptJob(total=len(uploaded_images), files=uploaded_images, id=job_id, duplicate_count=len(duplicate_files), duplicate_files=duplicate_files, payment_images=source_images, invoice_images=source_images, worker_count=worker_count)
    if uploaded_images:
        job.current_file = uploaded_images[0][0]
    jobs[job_id] = job
    asyncio.create_task(run_receipt_job(job, requested_columns))
    return {"job_id": job_id, "status": job.status, "total": job.total, "completed": job.completed, "duplicate_count": job.duplicate_count, "duplicate_files": job.duplicate_files}


def run_receipt_job_sync(job: ReceiptJob, requested_columns: list[str]) -> None:
    extractor = get_extractor()

    def on_progress(completed: int, _total: int, index: int) -> None:
        job.completed = completed
        job.current_file = job.files[index][0]

    contents = [content for _, content in job.files]
    read_many = getattr(extractor, "read_many", None)
    ocr_results = read_many(contents, on_progress, worker_count=job.worker_count) if read_many else [extractor.read(content) for content in contents]
    documents = [(name, lines) for (name, _), lines in zip(job.files, ocr_results, strict=True)]
    job.invoices = [{**extract_invoice_fields(lines), "_source": name} for name, lines in documents if is_invoice(lines)]
    job.columns, job.rows = build_payment_rows(requested_columns, documents)
    # OCR can produce duplicate rows when the same screenshot was recompressed
    # or renamed.  Deduplicate on extracted payment fields, not raw file bytes.
    unique_rows: list[dict[str, str]] = []
    seen_rows: set[tuple[str, ...]] = set()
    for row in job.rows:
        key = tuple((row.get(column) or "").strip() for column in job.columns)
        if not any(key) or key in seen_rows:
            continue
        seen_rows.add(key)
        unique_rows.append(row)
    job.rows = unique_rows
    image_dir = _history_dir(job.id)
    for name, content in job.payment_images.items():
        safe_name = hashlib.sha256(name.encode('utf-8')).hexdigest() + Path(name).suffix.lower()
        (image_dir / safe_name).write_bytes(content)
    with sqlite3.connect(_history_db()) as db:
        db.execute('INSERT OR REPLACE INTO receipt_batches (id, created_at, total, rows_json, title) VALUES (?, ?, ?, ?, ?)', (job.id, datetime.now(timezone.utc).isoformat(), job.total, json.dumps({'columns': job.columns, 'rows': job.rows, 'files': list(job.payment_images)}, ensure_ascii=False), ''))
        for content in job.payment_images.values():
            db.execute('INSERT OR IGNORE INTO receipt_image_hashes VALUES (?, ?)', (hashlib.sha256(content).hexdigest(), job.id))


async def run_receipt_job(job: ReceiptJob, requested_columns: list[str]) -> None:
    job.status = "processing"
    try:
        await asyncio.to_thread(run_receipt_job_sync, job, requested_columns)
        job.completed = job.total
        job.status = "completed"
    except Exception as error:
        job.error = str(error)
        job.status = "failed"


@router.get("/status/{job_id}")
async def receipt_status(job_id: str) -> dict[str, object]:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="该识别任务已失效，请重新上传。")
    response: dict[str, object] = {
        "job_id": job_id,
        "status": job.status,
        "total": job.total,
        "completed": job.completed,
        "current_file": job.current_file,
        "duplicate_count": job.duplicate_count,
        "duplicate_files": job.duplicate_files,
    }
    if job.status == "completed":
        response.update({"columns": job.columns, "rows": job.rows})
    if job.status == "failed":
        response["error"] = job.error or "本地 OCR 识别失败。"
    return response

@router.get("/history")
async def receipt_history() -> list[dict[str, object]]:
    with sqlite3.connect(_history_db()) as db:
        rows = db.execute('SELECT id, created_at, total, rows_json, title FROM receipt_batches ORDER BY created_at DESC').fetchall()
    return [{'job_id': row[0], 'created_at': row[1], 'title': row[4] or row[1], 'total': row[2], **_dedupe_saved(json.loads(row[3]))} for row in rows]

@router.patch("/history/{job_id}")
async def rename_receipt_history(job_id: str, payload: dict[str, object]) -> dict[str, str]:
    title = str(payload.get('title', '')).strip()[:120]
    if not title:
        raise HTTPException(status_code=422, detail='名称不能为空。')
    with sqlite3.connect(_history_db()) as db:
        result = db.execute('UPDATE receipt_batches SET title=? WHERE id=?', (title, job_id))
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail='找不到该历史批次。')
    return {'job_id': job_id, 'title': title}

@router.delete("/history/{job_id}")
async def delete_receipt_history(job_id: str) -> dict[str, bool]:
    with sqlite3.connect(_history_db()) as db:
        db.execute('DELETE FROM receipt_batches WHERE id=?', (job_id,))
        db.execute('DELETE FROM receipt_image_hashes WHERE batch_id=?', (job_id,))
    import shutil
    shutil.rmtree(_history_dir(job_id), ignore_errors=True)
    jobs.pop(job_id, None)
    return {"deleted": True}


@router.post("/export")
async def export_receipts(payload: dict[str, object]) -> Response:
    job_id = payload.get("job_id")
    if not isinstance(job_id, str):
        raise HTTPException(status_code=422, detail="批次编号无效。")
    job = jobs.get(job_id)
    if job is None:
        with sqlite3.connect(_history_db()) as db:
            saved = db.execute('SELECT rows_json FROM receipt_batches WHERE id=?', (job_id,)).fetchone()
        if not saved:
            raise HTTPException(status_code=422, detail="找不到该历史批次。")
        data = _dedupe_saved(json.loads(saved[0]))
        files = []
        image_dir = _history_dir(job_id)
        for name in data.get('files', []):
            safe_name = hashlib.sha256(name.encode('utf-8')).hexdigest() + Path(name).suffix.lower()
            image_path = image_dir / safe_name
            if image_path.exists():
                files.append((name, image_path.read_bytes()))
        job = ReceiptJob(total=len(files), files=files, id=job_id, status='completed', columns=data.get('columns', []), rows=data.get('rows', []), payment_images=dict(files), invoice_images=dict(files))
    if job.status != "completed":
        raise HTTPException(status_code=422, detail="图片仍在识别中，请等待处理完成。")
    content = create_reimbursement_workbook(job.rows, job.payment_images, job.invoice_images, job.invoices)
    import re
    from urllib.parse import quote
    title = re.sub(r'[\\/:*?"<>|\r\n]+', "_", reimbursement_workbook_title(job.rows)).strip(" .") or "费用报销单"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(title)}.xlsx"},
    )
