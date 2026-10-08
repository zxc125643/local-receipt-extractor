# 本地截图 / 发票提取系统

这是一个独立部署的离线报销整理工具。图片、PDF、OCR 结果、历史记录和导出的 Excel 都留在 Ubuntu 主机，不调用云端 AI。

## 功能

- 微信、支付宝、订单、支付截图、普通发票、客运票和 PDF 混合上传，单批最多 200 个文件。
- 自然语言指定提取列；自动补充发票状态、费用用途、分类置信度、分类依据和核对状态。
- 1–4 个 OCR 工作线程可调，显示逐文件进度。
- 同文件哈希去重与交易身份去重，提示重复数量且不重复计入合计。
- 支付与发票只有在金额、日期、商家身份均可靠一致时才合并；证据不足会拆开并标记人工核对。
- 支付无发票、支付加匹配发票、仅发票三种情况均进入支付明细；空的发票明细表不会生成。
- 本地历史、重命名、删除、重新打开和再次导出。
- 快速补录：`出差餐补320`、`车票8+8.43+105+10`；类型标记为“无票无支付记录”并计入合计。
- 按报销模板导出，包含付款/发票图片、分类审计信息、有票/无票汇总及自动日期区间。

## Ubuntu Docker 部署

```bash
cp .env.example .env
nano .env                 # RECEIPT_ACCESS_TOKEN 留空即可免口令访问
# 镜像构建时会把 PaddleOCR 中文检测和识别模型预下载并固化，运行时不需要联网下载。
docker compose up -d --build
docker compose ps
```

默认访问地址：`http://服务器IP:8766/`。可在 `.env` 修改 `HOST_PORT`，容器内部始终使用 8765。

Docker 构建阶段会加载 `PP-OCRv6_medium_det` 和 `PP-OCRv6_medium_rec`。全新克隆仓库时，构建机需要能访问 ModelScope；在本机 Ubuntu 部署时，`.env.example` 默认使用 Clash 的 `127.0.0.1:7897` 代理。若模型已下载，可放到 `paddle-models/official_models/`，构建时会复制到镜像中。运行容器不挂载模型缓存卷，也不会在运行时联网下载模型。Python 包使用阿里云镜像安装。

## 数据与隐私

- 历史数据库和原始文件保存在 Docker 卷 `receipt-data`。
- OCR 模型保存在 Docker 卷 `receipt-models`。
- `.env` 不会被打进镜像；不要把真实口令提交到 GitHub。
- 删除历史批次时会同时删除该批次的本地原图和去重索引。

## 本地测试

```bash
uv run --python 3.12 \
  --with-requirements backend/requirements.txt \
  --with-requirements backend/test-requirements.txt \
  pytest -q
```

测试覆盖字段提取、严格发票匹配、客运票、费用分类、去重、历史/补录持久化和 Excel 导出。
