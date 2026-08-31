# 方格志 V2 · 小红书离线海报工作台

基于 Vue 3、TypeScript 和 Fabric.js 的本地海报编辑器。不调用任何 AI，不依赖外部 CDN；支持浏览器、手机和后续 Tauri 客户端共用同一种项目格式。

## V2 能力

- 使用 Fabric.js 图层画布，图片可以在格子内直接拖动、缩放和裁切。
- 双击画布图片或点击“手动裁切”可打开大尺寸裁切窗口，电脑端拖动/滚轮、手机端拖动/滑杆均可使用。
- 固定导出小红书竖版 `1080 × 1620` PNG，预览缩放不影响导出清晰度。
- 2×3、3×3、3×4、4×3、5×5 框架，以及多套本地样式模板。
- 除预设模板外，可手动设置画布、边框、备注、标题颜色，以及圆角和格子间距，并一键应用到全部图片页。
- 一个项目可包含多个图片页；一级标题、可选二级标题和每格步骤说明分别保存。
- 一次上传任意数量素材；本页已用、其他页已用和未使用状态跨页显示。
- 新素材保存在服务器文件目录，SQLite 只保存项目数据和素材引用，不再把大图 Base64 塞进数据库。
- 兼容读取旧版草稿。旧版 Base64 素材会在用户实际修改并保存时迁移到素材目录；仅打开项目不会触发保存。
- 自动保存、明确的保存成功/失败提示、项目打开和确认删除。
- 桌面三栏编辑界面和独立的手机底部操作界面。

## Docker 长期运行（推荐）

```bash
docker compose up -d --build
```

访问：

- 网页：`http://服务器局域网IP:8765`
- API健康检查：`http://服务器局域网IP:8766/health`

第一次启动时，如果项目目录里存在旧版 `drafts.db`，容器会自动复制到 `docker-data/drafts.db`。后续持久化内容位于：

```text
docker-data/
├─ drafts.db
└─ assets/
```

升级镜像不会删除这里的数据。建议定期备份整个 `docker-data` 目录。

## 开发运行

安装依赖：

```powershell
npm install
```

启动草稿与素材服务：

```powershell
py -3 server.py
```

另开终端启动前端：

```powershell
npm run dev
```

访问 `http://127.0.0.1:8765`，手机使用电脑的局域网IP。Vite会把 `/api` 和 `/assets` 转发到8766端口。

## 验证

```powershell
npm test
py -3 -m unittest tests.test_server
npm run build
```

## 数据说明

- `drafts.db` / `docker-data/drafts.db`：项目JSON与索引。
- `assets/` / `docker-data/assets/`：按SHA-256去重后的原图。
- 项目JSON保存稳定素材ID、图层坐标、缩放比例和模板样式，不保存操作系统本地路径。
