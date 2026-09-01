# 本地截图提取到 Excel

独立的本地 OCR 项目，支持 JPG、PNG、WEBP、PDF 混合上传，按自然语言列名提取支付信息，并将匹配/未匹配发票写入 Excel 的 `发票明细` 工作表。

## Docker 启动

```bash
docker build -t receipt-extractor .
docker run --rm -p 8765:8765 receipt-extractor
```

浏览器打开 `http://服务器IP:8765/`。页面可调 1–4 个 OCR 线程；默认 2 个，适合低 CPU 占用的 Ubuntu 主机。
