from __future__ import annotations

import json
import uuid
import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from functools import lru_cache

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from backend.app.api.deps import assert_desktop_auth
from backend.app.services.receipt_extractor import LocalReceiptExtractor, build_payment_rows, clean_columns, create_reimbursement_workbook

router = APIRouter(prefix="/receipts", tags=["receipts"], dependencies=[Depends(assert_desktop_auth)])
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
MAX_FILES = 200

@dataclass
class ReceiptJob:
    total: int
    files: list[tuple[str, bytes]]
    status: str = "queued"
    completed: int = 0
    current_file: str = ""
    error: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[dict[str, str]] = field(default_factory=list)
    payment_images: dict[str, bytes] = field(default_factory=dict)
    invoice_images: dict[str, bytes] = field(default_factory=dict)


jobs: dict[str, ReceiptJob] = {}


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
    files: list[UploadFile] = File(...),
) -> dict[str, object]:
    requested_columns = parse_columns(columns)
    if not files:
        raise HTTPException(status_code=422, detail="请至少选择一张图片。")
    if len(files) > MAX_FILES:
        raise HTTPException(status_code=422, detail=f"单次最多处理 {MAX_FILES} 张图片。")

    uploaded_images: list[tuple[str, bytes]] = []
    source_images: dict[str, bytes] = {}
    for image in files:
        if image.content_type not in ALLOWED_IMAGE_TYPES and Path(image.filename or "").suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".pdf"}:
            raise HTTPException(status_code=422, detail=f"{image.filename} 不是支持的图片或 PDF 格式。")
        try:
            content = await image.read(); name = image.filename or "未命名图片"
            source_images[name] = content
            uploaded_images.append((name, content))
        except Exception as error:
            raise HTTPException(status_code=422, detail=f"无法识别 {image.filename}：{error}") from error

    job_id = str(uuid.uuid4())
    job = ReceiptJob(total=len(uploaded_images), files=uploaded_images, payment_images=source_images, invoice_images=source_images)
    jobs[job_id] = job
    asyncio.create_task(run_receipt_job(job, requested_columns))
    return {"job_id": job_id, "status": job.status, "total": job.total, "completed": job.completed}


def run_receipt_job_sync(job: ReceiptJob, requested_columns: list[str]) -> None:
    extractor = get_extractor()

    def on_progress(completed: int, _total: int, index: int) -> None:
        job.completed = completed
        job.current_file = job.files[index][0]

    contents = [content for _, content in job.files]
    read_many = getattr(extractor, "read_many", None)
    ocr_results = read_many(contents, on_progress) if read_many else [extractor.read(content) for content in contents]
    documents = [(name, lines) for (name, _), lines in zip(job.files, ocr_results, strict=True)]
    job.columns, job.rows = build_payment_rows(requested_columns, documents)


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
    }
    if job.status == "completed":
        response.update({"columns": job.columns, "rows": job.rows})
    if job.status == "failed":
        response["error"] = job.error or "本地 OCR 识别失败。"
    return response


@router.post("/export")
async def export_receipts(payload: dict[str, object]) -> Response:
    job_id = payload.get("job_id")
    if not isinstance(job_id, str) or job_id not in jobs:
        raise HTTPException(status_code=422, detail="该批次已失效，请重新识别后导出。")
    job = jobs[job_id]
    if job.status != "completed":
        raise HTTPException(status_code=422, detail="图片仍在识别中，请等待处理完成。")
    content = create_reimbursement_workbook(job.rows, job.payment_images, job.invoice_images)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=receipt-extraction.xlsx"},
    )
