from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response

from .services.receipt_extractor import LocalReceiptExtractor, build_payment_rows, clean_columns, create_reimbursement_workbook, extract_invoice_fields, is_invoice

app = FastAPI(title="Local Receipt Extractor")
extractor = LocalReceiptExtractor()
jobs: dict[str, dict] = {}
ALLOWED = {"image/jpeg", "image/png", "image/webp", "application/pdf"}

@app.get("/")
def index() -> FileResponse:
    return FileResponse(Path(__file__).resolve().parents[3] / "static" / "index.html")

@app.post("/api/process")
async def process(columns: str = Form(...), worker_count: int = Form(2), files: list[UploadFile] = File(...)):
    if not 1 <= worker_count <= 4:
        raise HTTPException(422, "线程数必须是 1 到 4。")
    try:
        requested = clean_columns(json.loads(columns))
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    if not files or len(files) > 200:
        raise HTTPException(422, "请上传 1 到 200 个文件。")
    uploaded = []
    for file in files:
        if file.content_type not in ALLOWED and Path(file.filename or "").suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".pdf"}:
            raise HTTPException(422, f"不支持的文件：{file.filename}")
        uploaded.append((file.filename or "未命名图片", await file.read()))
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "queued", "total": len(uploaded), "completed": 0, "current_file": "", "rows": [], "invoices": [], "files": uploaded, "workers": worker_count}
    asyncio.create_task(run(job_id, requested))
    return {"job_id": job_id, "total": len(uploaded), "completed": 0, "status": "queued"}

async def run(job_id: str, columns: list[str]):
    job = jobs[job_id]; job["status"] = "processing"
    try:
        def progress(done, _total, index):
            job["completed"] = done; job["current_file"] = job["files"][index][0]
        docs = await asyncio.to_thread(extractor.read_many, [content for _, content in job["files"]], progress, job["workers"])
        named = [(name, lines) for (name, _), lines in zip(job["files"], docs, strict=True)]
        job["invoices"] = [{**extract_invoice_fields(lines), "_source": name} for name, lines in named if is_invoice(lines)]
        job["columns"], job["rows"] = build_payment_rows(columns, named)
        job["status"] = "completed"; job["completed"] = job["total"]
    except Exception as exc:
        job["status"] = "failed"; job["error"] = str(exc)

@app.get("/api/status/{job_id}")
def status(job_id: str):
    job = jobs.get(job_id)
    if not job: raise HTTPException(404, "任务不存在或已过期。")
    return {key: job.get(key) for key in ("job_id", "status", "total", "completed", "current_file", "columns", "rows", "error") if key != "job_id"} | {"job_id": job_id}

@app.post("/api/export")
def export(payload: dict):
    job = jobs.get(payload.get("job_id"))
    if not job or job.get("status") != "completed": raise HTTPException(422, "任务尚未完成。")
    images = {name: content for name, content in job["files"]}
    data = create_reimbursement_workbook(job["rows"], images, images, job["invoices"])
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=receipt-extraction.xlsx"})
