# local-receipt-extractor AGENTS.md

## 目标

为报销材料提供完全本地、离线运行的截图/PDF识别、整理和 Excel 导出。

## 地图

- `backend/app/main.py`：本地 API、任务、历史记录和导出接口。
- `backend/app/services/receipt_extractor.py`：OCR、字段提取、去重、票据匹配及 Excel 生成。
- `static/index.html`：本地浏览器界面。
- `Dockerfile`、`docker-compose.yml`：部署镜像及本地数据持久化。
- `paddle-models/official_models/`：构建镜像时预置的 PaddleOCR 模型文件；权重不提交到 Git。

## 规范

- 运行时必须完全离线：截图、PDF、OCR 文本、历史记录和导出文件都留在用户设备/Ubuntu 主机。
- 禁止把文件或识别结果发送给云端 AI、OCR API、第三方存储或遥测服务；除非用户明确改变这一要求。
- PaddleOCR 在本地执行，检测和识别模型应在部署构建前准备好并固化进 Docker 镜像。容器运行和用户处理流程不得下载模型或依赖外网。
- 模型的首次获取仅属于部署准备；获取后将模型放入 `paddle-models/official_models/` 再构建镜像。
- 保持报销数据使用本地 SQLite 和 Docker 数据卷持久化，不引入外部数据库或云同步。
