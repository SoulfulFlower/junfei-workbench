# 跨电脑运行与只读自检

## 新版便携包（2026-11-06 第二阶段）

已新增 AmazonAgentPortable.spec 和 packaging/build_portable.py。只收录运行资源与干净默认配置，不使用旧打包脚本中的原电脑项目指针。新包自带 Python 固定工具入口与 Node；正常启动将运行资源复制到独立个人数据目录，配置和执行记录保留在那里，不写入安装目录。不同构建版本不会直接覆盖旧运行目录。

已完成同机隔离搬迁启动验收，真实第二台电脑仍未验证。完整使用方式以压缩包内“使用说明.txt”为准。以下第一阶段记录描述源码启动和显式项目覆盖，不代表旧 EXE 已自动升级。


2026-11-06：这一阶段提供项目目录可配置和迁移诊断，不代表已完成无人值守选品、制图、发布，也不自动改动线上服务。

## 两种使用方式

- 只在其他电脑操作工作台网页：可连接已经部署的服务，使用各自账号。云端和本机目前是独立数据库，先确定哪一端是唯一生产来源，避免两端同时编辑。
- 在另一台电脑执行浏览器流程：需要完整项目目录、本机 Python 3.10+、Node.js、EGO，以及在该电脑重新核对的店铺登录、专属工作区和页面绑定。复制一个 EXE 不等于迁移这些依赖。

## 显式指定项目位置

在启动工作台的同一个 PowerShell 窗口，为本次进程设置：

    $env:JUNFEI_PROJECT_ROOT = 'D:\AmazonWorkbench'
    $env:JUNFEI_PYTHON = 'C:\Path\To\Python\python.exe'

第一项必须是包含 automation/config.json 的完整项目绝对目录。第二项可选，用于指定实际 Python 可执行文件，不填写 py 启动器或命令参数。源码运行默认复用当前 Python；打包程序寻找本机 Python，不将 GUI EXE 当作 Python。

目录优先级：JUNFEI_PROJECT_ROOT → 有效的 project-root.txt → 随包配置 → 源码相邻项目目录。旧指针失效时停止并提示配置，不悄悄使用另一份经营预算。显式配置错误时也不会自动回退。

上述变量只影响由此窗口新启动的进程，不会更改系统设置，不会迁移账号、密钥、历史数据库或浏览器登录。

## 只读自检

在 listing-workbench 目录运行：

    python -B runtime_environment.py --json

也可只为本次诊断指定新目录：

    python -B runtime_environment.py --project-root 'D:\AmazonWorkbench' --json

自检不会读取模型密钥、写数据库、访问网络、启动浏览器、调用模型或刊登。它检查必要项目文件、Python 文件、Node.js、EGO 路径、脚本目录和工作区配置格式。退出码 0 只表示这些本机文件检查通过，不证明依赖版本、登录、授权、发布或在售验证已通过。readyForUnattendedRun 始终为 false，直到整条执行链另行完成验证。

## 迁移前检查

1. 完整备份并选定唯一数据来源，保留未知状态操作记录，不能清空重发。
2. 核对 automation/config.json 的 EGO 路径和脚本目录，不照搬原电脑的用户名路径。
3. 在新电脑重新确认 TaskSpace、页面、店铺和站点；不复制 Cookie、令牌或 DPAPI 密钥。
4. 重新配置各自模型服务；127.0.0.1 地址只指向运行服务的那一台电脑。
5. 先离线测试和本地预检，再按授权验证真实草稿与发布链。
6. 本次源码变更未重打包、重启本机服务、上传云端或更改真实刊登状态。

验证命令：

    python -B -m unittest test_runtime_environment test_agent_center test_agent_api test_agent_erp test_agent_library test_image_budget
    python -B -m unittest discover -s automation -p "test_*.py"

测试需用独立临时目录；不要把生产数据目录指定为测试目录。
