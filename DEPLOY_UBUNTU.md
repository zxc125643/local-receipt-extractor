# Ubuntu 局域网部署

在 Ubuntu 主机安装 Docker Engine 和 Docker Compose Plugin 后，进入项目目录执行：

```bash
cp .env.example .env
nano .env
docker compose up -d --build
```

把 `.env` 中的 `CORE_GATEWAY_TOKEN` 改成一串长随机口令。首次构建会下载本地 OCR 引擎；后续图片识别不访问云端。

查看主机局域网地址：

```bash
hostname -I
```

例如输出 `192.168.1.88`，则在手机或电脑浏览器打开 `http://192.168.1.88:8765`，并输入同一份访问口令。若启用了 UFW：

```bash
sudo ufw allow from 192.168.1.0/24 to any port 8765 proto tcp
```

服务会设置为 Docker 常驻容器，Ubuntu 重启后会自动恢复。更新程序时运行：

```bash
docker compose up -d --build
```
