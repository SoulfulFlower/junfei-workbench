# 钧飞工作台 · Junfei Workbench

用于亚马逊产品档案、选品研究、Listing 文案、图片分镜与套图、变体换色以及钧飞 ERP 采集和刊登的本地工作台。

仓库包含工作台源码、Codex 项目技能、示例配置和构建脚本。真实账号、API 密钥、浏览器会话、数据库、商品资料及历史回执保存在各自的运行环境中。

## 近期更新

- **商品页与任务中心**采用统一的按钮和状态样式。发布、只读核对和恢复操作各有明确入口。
- **后端派单与审批**按账号、商品和站点冻结核对资料。Codex 回传意见，运营员确认后由后端执行。审批中断时沿原请求查询，运营员确认未提交并记录依据后可重新派单。
- **CLI 恢复与交付**保留外部任务号及原领取凭据，校验 Listing、逐色成品图、子 SKU 配图和 ZIP 文件哈希。CLI 通过工作台保存的 ERP 原回执核验在售状态。操作步骤见 [CLI 流水线说明](studio-dev/automation/README.md)。
- **Windows 便携版**包含 ERP 适配模块和固定工具。构建成功前会实际迁移启动，检查全新账号初始化、本地资源及属性校验。

## 目录

- `studio-dev/listing-workbench/`：Python 后端、账号隔离、产品和图片制作、ERP 交接及采集插件。
- `studio-dev/listing-workbench/visual-ui/`：React / TypeScript 图片工作台。
- `studio-dev/junfei-publisher/`：钧飞 ERP 采集、草稿、图库回读与刊登执行器。
- `studio-dev/automation/`：选品、定价、浏览器连接及批量工作流脚本。
- `studio-dev/packaging/`：便携包构建和验证。

## 用 Codex 操作单款商品

在同一个仓库目录打开 Codex，使用 `$amazon-full-pipeline` 或 `$cyclic-product-discovery`。登录工作台，在目标商品的「运营状态与 Codex」生成 30 分钟配对码。通过 Codex 运行环境的 `JUNFEI_CODEX_TOKEN` 提供配对码。默认连接 `http://127.0.0.1:18765`，远程工作台通过 `JUNFEI_CODEX_URL` 配置 HTTPS 地址。

在商品页选择「派给 Agent 核对」。后端按当前可用动作生成任务编号、核对步骤、固定输入和返回格式。已配对的 Codex 使用 `next --wait 30` 接收派单，用 `review RESULT.json` 交回意见。报告缺口时任务停止；核对通过后，运营员可确认，由后端运行原业务流程。正式发布与恢复写入仍在发布页确认。挂接独立 CLI 台账的商品显示原 CLI 任务及阶段。

## 本地启动

需要 Python 3.12、Node.js 22+；浏览器自动化需另行安装和配置 EGO / 紫鸟 CLI。

在仓库根目录执行：

```powershell
if (!(Test-Path studio-dev/automation/config.json)) {
    Copy-Item studio-dev/automation/config.example.json studio-dev/automation/config.json
}
python -m venv .venv
.venv/Scripts/python -m pip install -r studio-dev/listing-workbench/cloud_requirements.txt
cd studio-dev/listing-workbench/visual-ui
npm ci
npm run build
cd ../../junfei-publisher
npm ci
cd ../listing-workbench
../../.venv/Scripts/python -X utf8 desktop_launcher.py
```

默认本地地址为 `http://127.0.0.1:18765`。首次使用自行创建账号，模型密钥在本地设置或通过受支持的环境变量配置。示例配置禁用生图与自动发布；店铺、预算及浏览器绑定需自行设置。`start.ps1` 是复用现有本机账号库的维护入口，新环境请使用上述 `desktop_launcher.py`。

换色分割需要的 ONNX / HQ-SAM 模型权重未入库，来源和校验信息见 `models/` 下的 README、manifest 及相关模块。第三方依赖、虚拟环境、构建产物和研究副本需按需安装，不包含本机已下载的大文件。

## 构建 Windows 便携版

完成上述 Python 依赖、前端构建和 ERP 的 Node 依赖安装后，回到仓库根目录。在 Windows x64 执行以下命令。输出目录须为新目录，建议使用较短的绝对路径。

```powershell
.venv/Scripts/python -m pip install pyinstaller
.venv/Scripts/python -X utf8 studio-dev/packaging/build_portable.py --output "$env:TEMP\JunfeiBuild"
```

构建目录中的 `dist/AmazonAgentPortable/` 为完整便携包，迁移时复制整个目录。`build-result.json` 记录构建结果，`smoke-result.json` 记录本机迁移测试。实际店铺、付费服务及第二台 Windows 电脑需另行验收。

## 开发与检查

模块边界见 [MODULES.md](studio-dev/listing-workbench/MODULES.md)。测试应使用隔离数据和模拟服务；执行生产脚本前自行配置目标账号及授权，保留未知任务和外部回执，避免重复提交。

```powershell
python -X utf8 -m unittest discover -s studio-dev/automation -p "test_*.py"
```

源码保留原有模块文档和兼容入口，部分文档包含早期实现说明；实际行为以当前代码为准。仓库上传不表示已完成新环境安装或真实 ERP 验收。

## 许可与来源

组合工作台沿用 **AGPL-3.0-only**。原有版权、许可证及来源声明保留在 [SOURCE-NOTICE.md](studio-dev/listing-workbench/SOURCE-NOTICE.md)、[AGPL-3.0](studio-dev/listing-workbench/LICENSE-AGPL-3.0.txt) 和 `visual-ui/NOTICE.md`。分割模型及其他第三方组件遵循各自许可证。
