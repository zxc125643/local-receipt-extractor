FROM node:22-slim AS ui-build
WORKDIR /app
ARG HTTP_PROXY
ARG HTTPS_PROXY
ENV HTTP_PROXY=${HTTP_PROXY} HTTPS_PROXY=${HTTPS_PROXY}
COPY package.json package-lock.json ./
COPY desktop/package.json desktop/package.json
COPY ui/package.json ui/package.json
RUN npm ci --workspace ui --include-workspace-root=false --ignore-scripts
COPY ui ./ui
RUN npm run build --workspace ui

FROM python:3.12-slim-bookworm
WORKDIR /app
ARG HTTP_PROXY
ARG HTTPS_PROXY
ENV HTTP_PROXY=${HTTP_PROXY} HTTPS_PROXY=${HTTPS_PROXY} http_proxy=${HTTP_PROXY} https_proxy=${HTTPS_PROXY}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libgl1 && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple -r backend/requirements.txt
COPY backend/receipt-requirements.txt ./backend/receipt-requirements.txt
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple -r backend/receipt-requirements.txt
COPY backend ./backend
COPY --from=ui-build /app/ui/dist ./ui/dist
EXPOSE 8765
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8765"]
