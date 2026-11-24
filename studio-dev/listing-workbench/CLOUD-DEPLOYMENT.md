# 公网部署

目标实例：腾讯云新加坡 `lhins-f6ifdvvn`，公网 IP `203.0.113.10`。
Ubuntu 24.04 LTS，2核4GB，60GB SSD。

## 目录与运行方式

- `/opt/junfei/workbench`：软件及 `data` 数据目录。
- `/opt/junfei/venv`：独立 Python 环境。
- `/etc/junfei/master.key`：Linux 上模型密钥的加密主密钥，只允许 root 和服务账号读取。
- 服务使用无登录权限的 `junfei` 账号运行，应用只监听 `127.0.0.1:18765`。
- Nginx 对外提供 HTTPS；80 端口用于证书验证和跳转，不提供登录接口。
- `systemctl status junfei` 查看状态，`journalctl -u junfei -n 100` 查看日志。

## 首次迁移

在原电脑运行 `py cloud/package.py`，生成 `../cloud-deployment/junfei-cloud.zip`。
使用 SQLite online backup 导出每个数据库，保留产品、文案、图片、审核账号和员工独立空间。
部署包排除原 Windows 的 DPAPI 密钥、浏览器会话、采集配对令牌、办公室 TLS 私钥及测试备份。
已保存账号的密码哈希保留，迁移后需重新登录；每位用户重新填写自己的模型密钥和插件配对码。

把部署包上传到服务器后，首次安装：

```sh
sudo install -d /opt/junfei/workbench
sudo unzip /home/ubuntu/junfei-cloud.zip -d /opt/junfei/workbench
sudo bash /opt/junfei/workbench/cloud/install.sh
```

不要在已上线且员工已编辑的服务上重新覆盖 `data`。后续更新先备份，仅替换代码和编译资源。

## IP HTTPS

使用支持 IP 标识的新版 Certbot，向 Let's Encrypt 申请 shortlived IP 证书。
证书属于短期证书，必须启用自动续签，并保持80端口的 ACME 验证路径可访问。
证书签发后运行 `sudo bash /opt/junfei/workbench/cloud/enable-https.sh`。
`systemctl list-timers 'junfei-*'` 查看续签和备份计划。

## 数据与备份

`junfei-backup.timer` 每天 UTC 19:30（北京时间次日03:30）备份，保留最近7份。
备份位于 `/opt/junfei/backups`，只有 root 可读取，含数据及配套加密主密钥。
恢复时必须同时恢复主密钥，否则已有模型密钥无法解密。
同服务器备份不能防止整机或磁盘丢失，后续可另配独立备份存储。

本地服务和云服务是两个独立副本，没有双向同步。迁移完成后应统一使用云端地址，避免两边分别编辑。

## 安全边界

保留注册审核、员工独立产品及模型 API 配置。只在明确设置 `JUNFEI_TRUST_PROXY=1` 且请求来自回环地址时信任 HTTPS 反向代理标记；首位管理员创建接口在该模式禁用。
临时部署 SSH 密钥仅在用户同意后添加，部署完成移除，不保留长期管理凭据。
