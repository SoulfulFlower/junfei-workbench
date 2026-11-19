# 钧飞工作台 · Junfei Workbench

用于亚马逊产品档案、选品研究、Listing 文案、图片分镜与套图、变体换色以及钧飞 ERP 采集和刊登的本地工作台。

本仓库是当前项目的源码快照。实际账号、密码、API 密钥、加密凭据、浏览器会话、SQLite 数据库、产品资料、历史执行回执及本机部署配置均不包含在内。

## 目录

- `studio-dev/listing-workbench/`：Python 后端、账号隔离、产品和图片制作、ERP 交接及采集插件。
- `studio-dev/listing-workbench/visual-ui/`：React / TypeScript 图片工作台。
- `studio-dev/junfei-publisher/`：钧飞 ERP 采集、草稿、图库回读与刊登执行器。
- `studio-dev/automation/`：选品、定价、浏览器连接及批量工作流脚本。
- `studio-dev/packaging/`：便携包构建和验证。

## 本地启动

需要 Python 3.12、Node.js 22+；浏览器自动化需另行安装和配置 EGO / 紫鸟 CLI。

在仓库根目录执行：

```powershell
Copy-Item studio-dev/automation/config.example.json studio-dev/automation/config.json
python -m venv .venv
.venv/Scripts/python -m pip install -r studio-dev/listing-workbench/cloud_requirements.txt
cd studio-dev/listing-workbench/visual-ui
npm ci
npm run build
cd ..
../../.venv/Scripts/python -X utf8 desktop_launcher.py
```

默认本地地址为 `http://127.0.0.1:18765`。首次使用自行创建账号，模型密钥在本地设置或通过受支持的环境变量配置。示例配置禁用生图与自动发布；店铺、预算及浏览器绑定需自行设置。`start.ps1` 是复用现有本机账号库的维护入口，新环境请使用上述 `desktop_launcher.py`。

换色分割需要的 ONNX / HQ-SAM 模型权重未入库，来源和校验信息见 `models/` 下的 README、manifest 及相关模块。第三方依赖、虚拟环境、构建产物和研究副本需按需安装，不包含本机已下载的大文件。

## 开发与检查

模块边界见 [MODULES.md](studio-dev/listing-workbench/MODULES.md)。测试应使用隔离数据和模拟服务；执行生产脚本前自行配置目标账号及授权，保留未知任务和外部回执，避免重复提交。

```powershell
python -X utf8 -m unittest discover -s studio-dev/automation -p "test_*.py"
```

源码保留原有模块文档和兼容入口，部分文档包含早期实现说明；实际行为以当前代码为准。仓库上传不表示已完成新环境安装或真实 ERP 验收。

## 许可与来源

组合工作台沿用 **AGPL-3.0-only**。原有版权、许可证及来源声明保留在 [SOURCE-NOTICE.md](studio-dev/listing-workbench/SOURCE-NOTICE.md)、[AGPL-3.0](studio-dev/listing-workbench/LICENSE-AGPL-3.0.txt) 和 `visual-ui/NOTICE.md`。分割模型及其他第三方组件遵循各自许可证。
