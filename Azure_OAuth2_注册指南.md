# Azure OAuth2 注册指南

为 Outlook 批量注册工具配置 OAuth2 权限，使注册的账号能通过 IMAP 收信（用于接收 ChatGPT/Claude 等的验证码）。

---

## 第一步：创建应用

1. 打开 https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/CreateApplicationBlade

2. 填写：
   - **名称**: `OutlookBatch`（随便填）
   - **受支持的账户类型**: 选 **"任何组织目录中的帐户"**（红色警告，但是选这个）
   - **重定向 URI**: 类型选 **Web**，值填 `http://localhost`

3. 点击 **注册**

4. 注册成功后，在 **概述** 页面复制 **应用程序(客户端) ID** —— 这就是 `client_id`

![图片说明](https://learn.microsoft.com/en-us/azure/active-directory/develop/media/quickstart-register-app/portal-01-app-registrations.png)

---

## 第二步：添加 API 权限

1. 左侧菜单 → **API 权限** → **添加权限**

2. 点 **Microsoft Graph** → **委托的权限**

3. 搜索并勾选以下权限：
   ```
   ✅ offline_access
   ✅ IMAP.AccessAsUser.All
   ✅ Mail.ReadWrite
   ✅ Mail.Send
   ✅ User.Read
   ```

4. 点击 **添加权限**

5. 点击 **"代表...授予管理员同意"**（需要管理员权限，如果没有请联系管理员 — 如果用的是个人账号可能没有这个按钮，跳过也行）

---

## 第三步：创建客户端密码

1. 左侧菜单 → **证书和密码** → **新建客户端密码**

2. 说明填 `outlook-batch`，过期选 **24个月**

3. 点击 **添加**

4. **立即复制"值"列的内容**（关闭页面后就看不到了）—— 这个就是 `client_secret`

---

## 第四步：配置到工具

启动后端后，通过 API 配置：

```bash
# 替换成你的值
curl -X PUT http://127.0.0.1:8765/settings/oauth2 ^
  -H "X-Desktop-Token: dev-token" ^
  -H "Content-Type: application/json" ^
  -d "{\"client_id\":\"你的客户端ID\",\"redirect_url\":\"http://localhost\",\"scopes\":[\"offline_access\",\"https://outlook.office.com/IMAP.AccessAsUser.All\",\"https://graph.microsoft.com/Mail.ReadWrite\",\"https://graph.microsoft.com/Mail.Send\",\"https://graph.microsoft.com/User.Read\"]}"
```

或者在网页 UI 的 **设置 → OAuth2配置** 中填入：
- **Client ID**: 第一步复制的值
- **Redirect URL**: `http://localhost`
- **Scopes**: `offline_access https://outlook.office.com/IMAP.AccessAsUser.All https://graph.microsoft.com/Mail.ReadWrite https://graph.microsoft.com/Mail.Send https://graph.microsoft.com/User.Read`

---

## 第五步：验证工作

配置好后注册新账号，注册流程会自动：
1. 注册 Outlook 邮箱
2. 弹出 OAuth2 授权页面 → 点击确认
3. 自动获取 `refresh_token` 并保存到数据库

之后在账号列表可以对已有账号点击 **OAuth2 授权** 补登 token。

---

## 流程图

```
Azure 注册应用
     │
     ▼
获取 client_id
     │
     ▼
在工具设置中填入 client_id
     │
     ▼
注册 Outlook 账号 →
    自动弹出授权页 →
    同意后获得 refresh_token →
    存入数据库 →
    可通过 IMAP 收信
```

---

## 常见问题

**Q: 没有"授予管理员同意"按钮？**
A: 个人 Microsoft 账号（@outlook.com / @hotmail.com）没有这个按钮，不影响使用。注册时会弹出 OAuth 授权页面，手动确认即可。

**Q: 重定向 URI 必须是 http://localhost 吗？**
A: 是的。工具内部启动了一个本地服务来接收授权回调，必须是 `http://localhost`。不能是 `https`，不能加端口。

**Q: 拿到了 `refresh_token` 有什么用？**
A: 有了 `refresh_token`，工具可以通过 IMAP 协议读取该邮箱的邮件，自动提取其他平台（ChatGPT、Claude 等）发来的验证码。如果不配 OAuth2，注册的邮箱只是纯邮箱，不能自动收验证码。

**Q: client_secret 和 client_id 有什么区别？**
A: `client_id` 是应用的公开标识，`client_secret` 是密码。在工具中只需要填 `client_id`，`client_secret` 在 OAuth2 授权码流程中不直接使用。
