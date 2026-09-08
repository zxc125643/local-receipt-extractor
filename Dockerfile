FROM python:3.12-slim-bookworm
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 libgl1 libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt backend/paddle-requirements.txt ./
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple -r requirements.txt \
    && pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple -r paddle-requirements.txt
COPY backend ./backend
COPY static ./static
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=3 CMD curl -fsS http://127.0.0.1:8765/health || exit 1
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8765"]
