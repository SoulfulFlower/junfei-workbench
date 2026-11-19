亚马逊工作台智能体：Windows 便携验证版
适用：Windows x64。本版用于跨电脑安装验证，不代表选品到发布已全自动完成。

使用
1. 将整个 AmazonAgentPortable 文件夹解压到较短的本地目录，不要只复制 EXE，也不要在压缩包内直接运行。
2. 双击 AmazonAgentPortable.exe。首次打开需要创建本机工作台账号。
3. 默认地址 http://127.0.0.1:18768，仅供这台电脑访问。启动程序和固定工具入口已内置 Python；Node.js 也随包提供。
4. 默认不启用付费生成、不设置店铺或浏览器工作区、不发布商品。各电脑分别配置自己的模型服务与店铺。
5. 真实浏览器流程仍需该电脑有 EGO 运行环境、有效登录和正确的专属工作区。软件不会自动安装它、迁移登录或打开普通浏览器作为替代。

数据与升级
- 本版默认创建全新的个人数据目录：%USERPROFILE%\AmazonWorkbenchPortableData。
- 不带原电脑账号、数据库、模型密钥、Cookie、旧经营配置或发布记录；不会自动接管原本机或云端数据。
- 本机、其他电脑与云端没有自动同步。开始生产前先确定唯一数据来源。
- 关闭网页不等于退出后台程序。备份数据前应结束本版 AmazonAgentPortable.exe 进程，再复制整个数据目录。
- 当前不同构建版本不会直接覆盖已有运行目录和执行记录；升级需另行核对迁移，不能清空未知操作记录来重新提交。
- 软件暂未进行代码签名；不要为运行它关闭系统防护。

只读自检
在 PowerShell 中运行本包的 EXE，并指定一个尚不存在的 JSON 报告文件：
  .\AmazonAgentPortable.exe --self-check "$env:TEMP\workbench-check-new.json"
已有同版本个人配置时检查该配置；首次使用时检查干净默认配置。不会登录、调用模型或发布。
文件存在时不会覆盖，请换一个报告文件名。

验证范围
已在原 Windows 电脑上复制到另一个含中文和空格的目录，在全新临时账号数据、独立端口和没有 Python/Node 的 PATH 中启动验收。
已验证工作台登录、静态页面、插件包、对应源码下载、内置工具帮助输出、Node/sharp 依赖和未配置浏览器时停止。
尚未在另一台实体电脑冷启动；尚未完成整条无人值守选品、货源、制图、发布及在售核对。
本次未部署云端、未修改生产数据、未调用付费模型或真实 ERP。

许可与源码
组合软件按 AGPL-3.0-only 提供。许可与第三方说明在 _internal 中。
对应源码在 _internal\corresponding-source.zip，也可登录工作台后下载“本部署对应源码”。
源码包含干净默认配置、前后端源码、构建脚本及依赖锁文件，不含公司数据与凭据。

本版恢复保护更新（2026-11-06）
AI规划在调用前保存意图和输入校验值；收到合法结果后先保存检查点。恢复时复用已保存结果，未知结果不重复收费。旧执行返回不会覆盖新的任务状态。完整说明见对应源码中的 AUTOMATION-RECOVERY.md。
同一个账号数据目录只运行一个工作台服务实例，不支持多电脑共享同一SQLite目录。
已增加合成任务队列验收：没有真实产品时停在选品未接通，不继续调用模型或ERP。此项不是完成真实选品。

原选品任务文案接续（本版增量）
选品入队的原任务在资料和选品规则通过后，可明确开启竞品研究与文案。填写预算并确认费用说明后仅排队，点击开始才执行；强制止于文案，不生图、不导出、不上传或操作ERP。预算记录不是硬上限。真实选品到模型生成尚未实跑。说明见源码中的 SELECTION-TO-COPY.md。

Image preparation: original selection-to-copy tasks can preview a read-only colour/SKU checklist. No image generation, budget reservation, image approval or ERP permission is granted. Task budgets are NOT all-provider hard spending caps. See corresponding source: listing-workbench/IMAGE-PREPARATION.md. CLI carryover safety fix is included as source; its ledger remains separate.

Local-only cyclic discovery ledger: import already captured structured JSON to trace title phrase -> search product -> observed Sold by seller link -> seller catalogue -> new product -> next phrase. Explicit read-only Seller preview/save is also available for a pre-bound current product page. All records remain unverified. No automatic browser search, qualification or product import is performed. See corresponding source listing-workbench/CYCLIC-DISCOVERY.md. No cloud deployment or shared cross-computer database is configured.

本地 Seller 只读采集：本包可在明确配置账号独立的 EGO 空间和页面绑定后，读取当前商品页卖家链接，先预览再明确保存。不会自动接管、导航、交还控制或初始化绑定。验证码、未登录、页面或权限变化会停止；未知执行状态不自动重试。已完成离线模拟、本机隔离验收和一个 US 商品页 Seller 提取器实测；这不代表所有站点或完整选品流程已验证。另一台电脑冷启动仍未验证，也没有实现完整自动选品或全系统费用硬封顶。

独立发现浏览器配置（本版增量）
- 只使用配置顶层 discovery_browser：engine 为 ego-lite，cli 为本机已安装 CLI 的绝对文件路径，account_bindings 按本地登录会话数字账号 ID 分开。
- 每个启用条目需 enabled=true、非负整数 task_space_id、非空 task_space_name 与 page_label。发现空间不能等于 ERP 的 browser.task_space_id，不要为发现功能修改 ERP 路由。
- 旧 browser.discovery_account_bindings 不再生效，也不会回退到 ERP 的 CLI 或空间。管理员需按本机真实账号及已授权独立页面配置；不能直接复制旧电脑的 ID、路径或登录状态。
- 本包 discovery_browser 的 cli 为空，account_bindings 为空。构建校验禁止携带专用 CLI 路径和任何账号绑定，即使绑定已禁用。
- 采集范围只跟踪当前账号的有效发现路由。无关 ERP/经营配置变更可以继续；当前发现路由变化、新的 ERP 空间冲突或页面身份变化会阻止结果保存。
- 详细结构与迁移说明见源码中的 listing-workbench/DISCOVERY-BROWSER.md。

可选真实 HTTP 验收
对应源码内 packaging/verify_live_discovery.py 仅供明确选用，不在 EXE 启动、离线测试或打包时自动运行，也不作为便携运行时文件分发。它需要真实 keyword/search 源观察、事先配置的独立商品页和 --read-bound-browser 选项，并在新输出目录创建隔离账号数据库，不写正式业务账本。
2026-11-06 09:27:44 UTC 已通过一次真实标题/搜索源观察 → 本地 HTTP Seller 采集 → 明确保存隔离账本的验收：1 次真实读取、3 条隔离事件，搜索源含 5 个可见商品。重复请求未重复读取，错误父事件、旧版本、跨来源及错账号请求均阻止；超时测试是在成功后主动注入，不是真实 EGO 超时。正式业务账本未写，测试工作区内容未变。
这些观察仍未核验，合格数和产品入库数为 0。该结果不证明任意输入来源真实，不代表全部站点兼容、Seller 到店铺再到下一商品的完整循环、同款/排名/货源/利润核实或商品发布已完成。另一台实体电脑冷启动仍待验证。细节和证据路径见源码中的 DISCOVERY-BROWSER.md。


当前卖家列表与下一词预览
已保存 Seller 可明确读取当前绑定的 /s?me=SellerID 卖家列表；品牌旗舰店不作为卖家列表。不会自动导航、翻页或遍历全店。结果先预览，明确保存后才进入独立证据链；可选择列表商品、输入标题开头词，预览后再保存下一轮 keyword。不会自动搜索新词、判断同款、核算利润或导入产品。新词保留列表原标题和观察时间，不冒充新商品详情页核验。
商品 Seller 与卖家列表读取共用未知状态保护；不能换接口、换类型或清空记录绕过。对应源码另含 opt-in 的 packaging/verify_live_store.py，仅用于隔离账户测试，不在 EXE 启动时运行，也不进入便携运行目录。

真实卖家列表接续验收（2026-11-06 09:50 UTC）
已通过实际卖家页面链接进入商品列表，读取16张结果卡；其中新商品详情标题与列表标题一致。通过本地API的一次列表只读采集和明确保存，隔离账本形成原标题词→搜索→Seller→卖家列表/新商品→下一标题词，共5条事件。新词仅待搜索，未自动执行。新商品自身购买框Seller未复采，列表关系不等于卖家再次核实。没有产品入库、付费、上传、发布或生产部署。
重复请求不重读，标题预览不写账本，跨类型未知状态也阻止继续采集。故障超时为主动注入，不能说成真实网页超时。实际浏览器界面点选未全测；API/账本实测与离线UI测试分别记录。另一台电脑冷启动仍未验证。具体证据见对应源码中的DISCOVERY-BROWSER.md。


下一轮搜索与有界接续预览
当前绑定页面可以明确读取下一轮实际搜索结果，词和站点取自已保存 keyword。搜索/Seller/列表共用未知状态保护，结果需明确保存；不会自动判同款。新增后续步骤预览，输入最多动作数和最大轮次序号，仅显示建议，绝不自动导航、连续执行或写账本。预览上限不是跨请求执行配额，也不是费用硬封顶。详情见源码 DISCOVERY-PLAN.md；verify_live_search.py 只作显式隔离验收，不随启动运行。

2026-11-06 10:10 UTC 已完成下一轮搜索页的真实隔离HTTP验收，48张结果卡保存为第6条来源事件。有界计划只读、不执行，未知状态阻止三类采集。候选核对发现疑似同系列变体重复及非同款；未入围或产品入库。没有自动连续导航；现有ASIN去重不等于父体家族去重。详情见DISCOVERY-PLAN.md，仍未部署或验证另一台电脑冷启动。

来源时序补充：随后仅对隔离账本做直接本地接续测试，新增原始较早搜索观察及两条完整Seller证据，共9条事件。原搜索观察时间10:03:05，Seller检查10:05/10:08，不能倒挂到10:10的后采集事件。B0HJVZ4GTH当时只保存卖家链接，未保存完整商家标签；该Seller事件没有写入严格接续图，也未补造标签。相同详情 ASIN 与图像比较另存来源报告。具体见chronological-seller-append-verification.json与chronological-seller-graph.json；所有观察仍未独立核实，入围/产品入库为0。

证据审校：B0HJVZ4GTH 只有相同详情 ASIN 与图像/规格比较，源商品另有 twister 引用；候选完整父子映射尚未取得。统一标记为“疑似同系列变体”，不能称已独立验证同父体。先前隔离图中的比较备注属于报告者的待核实判断，最终审校图将使用收紧后的措辞。

变体证据与接续保护：本版增加当前页变体控件只读采集及账号隔离评估。缺少双向、来源绑定的证据时保持待核验，不按标题、品牌或相同详情 ASIN 合并。满足严格证据条件时只减少重复的标题词接续建议，仍保留每个商品的 Seller 核验及原始记录。正式父 ASIN 没有明确证据仍为未知。
有限轮次/动作上限与停止、取消、未知不重试已做离线模拟；没有真实自动连续导航执行器，界面仅能查看安全检查。另机冷启动仍需实际另一台电脑验证，不以本机迁移烟测代替。

新增有限接续源码试验：对应源码包含 discovery_live.py 及安全回归测试。其真实运行只允许明确指定的 TEMP 隔离数据、临时项目配置、新专用 EGO 空间及固定预算，普通工作台、员工运行时和本便携程序一律拒绝启动；没有生产自动运行按钮。它不自动入围、导入产品、付费或刊登。正式多账号运行仍需共享协调锁及进一步实机验收。


本机共享空间协调核心（源码增量，尚未接入生产）
对应源码提供 shared_browser_space.py：显式初始化并绑定协调库身份后，可让同一 Windows 用户下主动接入的不同工作台账号和进程互斥使用同一 EGO 空间。派发前持久记录未知状态，崩溃或超时不按时间/PID自动解锁重试。该模块不在便携运行时加载，不初始化本机协调库，也没有修改既有选品、ERP、CLI或历史脚本入口。
这不是全机所有程序的强制锁，也不覆盖不同 Windows 用户或一次运行多步骤之间的间隙。正式启用仍需逐一接入经过审查的固定执行器、核验实际操作空间及终态，并停用旧入口。当前只做新 TEMP 数据的离线多进程验收，未启动生产自动运行，未重试原阻挡任务。详见源码 automation/SHARED-BROWSER-SPACE.md 和 SHARED-BROWSER-ADOPTION.md。


整轮持锁的隔离选品接续（固定离线模拟）
对应源码新增 discovery_live_coordinated.py：一个共享空间操作覆盖完整的隔离选品运行、步骤间隙、子进程/工作线程结束、账本回读和终态证据落盘。选品控制器与采集桥使用实际代码，浏览器传输固定为同步合成测试，实际网页调用为零，合成观察不算真实选品、入围或产品入库。
该入口仅用于新建 TEMP 数据与明确绑定的测试协调库；不在 EXE 启动时运行，不新增 HTTP 路由，也未改造或禁用旧选品、ERP、CLI入口。旧入口仍可绕过协作锁，不能据此并行操作同一个真实浏览器空间。异常后保留未知状态和历史回看，不自动续跑或解锁。详见源码 listing-workbench/DISCOVERY-LIVE-COORDINATED.md。
