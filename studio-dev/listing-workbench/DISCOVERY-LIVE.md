# 有界真实发现接续：隔离源码试运行

`discovery_live.py` 是显式启动、有限次数的只读浏览器发现接续器。它不是完整商业选品器。页面导航及观察可以真实执行，但保存位置仅是隔离的发现观察账本；同款、排名、1688 货源、成本利润、生产产品入库、生图、上传及发布全部没有接通。

## 必须满足的隔离边界

- 只允许源码运行，拒绝 frozen 打包程序和员工 account worker。
- 导入前明确设置 `JUNFEI_DISCOVERY_LIVE=isolated-read-only`。
- `JUNFEI_ACCOUNT_DATA` 必须为操作系统 TEMP 下的专用目录，不能是 TEMP 根目录或生产 DATA；图谱、采集和控制表均在该目录。解析后的数据库路径不能逃逸。
- 明确设置 `JUNFEI_PROJECT_ROOT` 为另一个 TEMP 项目目录，其中存在 `automation/config.json`。解析后的配置不得指向目录外。只需白名单浏览器配置，不应复制服务密钥。
- DATA 内存在 `discovery-live-isolation.json`，精确内容为 `schemaVersion:1`、`mode:"isolated-read-only"`、`owner:当前账号整数`、`taskSpaceId:专用空间整数`、`dedicatedSpace:true`。
- 当前配置中其他已启用账号不得使用同一空间。选定空间不得是源码项目原始 `automation/config.json` 中任何发现绑定或 ERP 空间，包括本机原有 4/5。实页验收必须新建专用空间，核实 agent 所有权，使用该空间已存在的专用页面。
- 隔离标记只是操作者的明确声明，不是机器级所有权证明。互斥覆盖同一隔离 DATA 的账号和空间，**不跨员工独立数据库、不同安装或不同机器**。生产连续执行仍需要独立设计跨账号共享持久协调。

应用默认不显示生产自动启动按钮。即使 API 调用 start，上述默认拒绝条件仍在模块内部生效。导入模块、应用启动、查看状态和重复 start 不会重启已有任务。

## 接口

由已认证的服务端提供整数 owner；HTTP 请求不得提供 owner、租约、令牌、网址、查询词、脚本、凭据或回调。

- `start(user, data)`：data 精确包含 `runId, cycleId, expectedRevision, sourceEventId, maxActions, maxRounds, maxSeconds, planFingerprint`。计划指纹来自同一账号、循环、版本、动作和轮次限额的当前 `discovery_plan.prepare`。起点必须是实际已记录 keyword 或 captured store。
- `maxActions` 为 1–20 的累计逻辑动作数，标题派生也计一次。一次浏览器导航加采集是一个逻辑动作，不是声称只有一次底层 SDK 调用。失败、取消及未知均不退还额度。
- `maxRounds` 为 1–20 的绝对轮次编号上限，不是“再跑几轮”。
- `maxSeconds` 为 15–600 秒，start 时保存绝对截止时间，后续刷新不延长。运行时超时受剩余时间约束。不能强行证明异步浏览器操作已经停止；截止后仍不明的结果保留 unknown。
- `status(user, runId)`：只读，不暴露绑定路径、命令或令牌；报告已保存观察的实际阶段数、已用额度和未解决步骤。不把计划、标题派生或原始历史种子算作新浏览器采集。
- `stop(user, runId, cancel=False)`：持久停止标记并禁止下一次派发。已记录派发意图的步骤保留 unknown，不因停止就当成失败或允许重试。
- `owner_write_guard(user)`：同一 DATA 中 API 手工图谱写入应在整个 mutation 期间持有此上下文。`assert_owner_idle` 可用于只读准备操作。
- `planner_barrier(user)`：账号级只读屏障。协调器内部 ContextVar 仅排除自身 run；不能由 HTTP 或 JSON 构造。

同一 runId 的相同输入只返回原状态，不重新启动、不增加预算。不同输入复用编号被拒绝。崩溃后的 reserved/dispatch_unknown/unknown 均不会自动续跑、抢占或重放；未知需人工核对原始回执，当前版本没有清除屏障或强制恢复接口。不要换编号或 DATA 目录重试未知动作。

## 一个确定分支，而非最优选品

从指定来源沿 `keyword → search → seller → store → title prefix → search` 深度优先接续。每一步重新根据真实新增观察准备当前计划。搜索或店铺有多个产品时选择原始观察顺序中第一个未处理候选，保存零基 `chosenVisibleIndex` 和 `coverage_smoke_first_visible_unhandled_not_quality_ranking` 策略。保留全部原始观察节点。

这是一条覆盖性试运行分支，不表示最佳商品、销量排序、同款或 EXACT。相似性始终未评估。实际可用的变体证据继续只用于计划的标题分支排重，不代替 Seller 或同款核验。

标题策略为“实际标题前 8 个空白分隔词，最长 300 字符”。保留精确大小写、标点、双空格及品牌；不改写、不翻译、不删词、不创造扩展词。结果必须是原始标题的连续开头。若第一词本身超过 300 字符则停止。该机械前缀是可审计的冒烟策略，不是语义关键词优化。

遇到验证码、登录、访问阻挡、错误身份、配置/图谱变化、未知结果或未支持页面立即停止，不换另一分支、不绕过限制、不自动重试。

## 持久化与锁

`live_runs` 和 `live_steps` 与原有 `attempts` 位于同一 `discovery_browser.DB`。`BEGIN IMMEDIATE` 原子预留动作和消耗额度；同账号或同空间已有 active/stopping/unknown run 会阻止手工/并行采集。未知、损坏或不识别的控制历史 fail closed。步骤使用账号级逻辑目标唯一约束，换循环或 runId 不会重复已尝试目标。

私有 `_Lease` 仅由内存协调器生成，数据库只保存其摘要；桥接器在同一采集预留事务校验，在派发前先持久化 `dispatch_unknown`。浏览器脚本在导航前、导航后和读取后检查停止标记。真实回执通过固定采集器验证后才允许接入观察图谱。

保存观察和完成步骤在一个 SQLite ATTACH 事务中，使用 rollback journal 和 FULL synchronous；WAL 被拒绝，不偷偷修改数据库日志模式。版本、图谱、采集历史和配置在关键边界重读。原始 graph API 若绕过 owner_write_guard 直接写入，会使运行停止；源码内部能力不是抵抗任意本地程序的安全沙箱。

并行手工采集请求可能留下一个 blocked 回执，改变历史指纹，进而令试运行保守停止。这是安全拒绝，不应描述成可同时操作同一页面。

## 验证与尚未证明的内容

运行 `python -B -X utf8 -m unittest test_discovery_live -v`。测试先隔离导入 DATA，之后每例使用 TEMP 图谱、采集及配置。网络被禁用；浏览器在控制单测中被 mock。另有真实 `capture_live` 与私有租约集成测试，仅替换 subprocess 为写入合成结果的 fixture，仍不是实页证据。

覆盖有限完整合成链、原始标题前缀、深度优先选择、累计和绝对轮次限额、输入拒绝、生产/frozen/员工隔离、跨账号和同空间屏障、损坏历史、并发预留、重复 start、不退款、停止前后、超时未知、图谱/配置变化、ATTACH 完成回滚及预留额度回滚。

任何真实验收需另存真实输入源、专用空间/页面身份、每次回执、实际执行阶段和最终状态。离线测试或本文件不证明真实连续链通过，不证明其他电脑冷启动通过，也不构成完整选品、入库或发布授权。

## 2026-11-06 real pilot result and diagnostic follow-up

The isolated real pilot stopped with page_or_ownership_changed before navigation.
navigationDispatched and collectorDispatched were both false. It produced no
fresh browser observations. The original blocked run, its database and artifacts
remain unchanged; no reset, continuation or live retest was performed for this
diagnostic change.

The retained receipt does not distinguish a Page-handle metadata mismatch from a
later ownership, tab identity or URL recheck failure. The cause is undetermined.
This result does not establish a user takeover or an SDK defect.

A later source-only change adds optional navigationDiagnostics to these refusals.
It records only a fixed checkpoint enum, boolean comparisons and fixed
JavaScript type names. It contains no actual URL, space/page/target identifier,
error text, command, credential or secret. Strict schemas are checked when reading
runtime output and stored receipts. Malformed runtime diagnostics retain an
unknown outcome; malformed stored diagnostics are not returned to callers.

All original identity, ownership, source, target, stop and replay guards remain.
Diagnostics cannot authorize navigation or convert a refusal into success.
Missing or mistyped Page metadata and changed ownership/tab/URL fixtures remain
blocked; the unchanged valid synthetic case succeeds. These diagnostics have
only been validated offline with a fake SDK and temporary data, not on a real
browser. No exact real Page-handle shape has yet been recorded for this failure.


## 2026-11-06 hydrated Page binding correction

The navigation runtime now uses the matching fresh `task.tabs()` inventory
record's `.page`. EGO 0.6.2.7 returns a hydrated Page there, while
`task.page(label)` is lazy and has no targetId before its first resolving call.
The old immediate target comparison was statically incompatible with this SDK.
This does not retrospectively establish the cause of the retained blocked run.

Missing or mismatched label, space, target, Page, and non-agent page origin fail
closed. Original and fresh inventory Page metadata plus fresh space ownership
are checked before navigation, after navigation, and after capture. A fulfilled
`goto()` is accepted only when its receipt is the SDK's exact empty ordinary
object. Dialogs, popups, malformed or unknown receipts retain execution_unknown,
with no collector, no retry, and no success claim.

The SDK still resolves a Page label internally on each operation. These are
pre/post checks, not atomic target pinning or a cross-process browser lock. An
observed rebind on the original handle rejects results even if inventory has
returned to the old target. A narrow isolated read-only smoke test cannot prove
global cancellation/quiescence or production multi-account coordination.

The non-navigation manual capture runtime is unchanged and is not covered by
this correction; its label-resolution race remains a separate migration issue.
The original blocked real run, space 6, and its retained DATA are not reset,
cleared, resumed or retried. Offline navigation fixtures reproduce lazy Page
behavior, hydrated inventory handles, changed identity/ownership, exact receipt
requirements, stops and late outcomes. Real results, if separately performed,
are recorded independently in `outputs/handle-binding-20261106`, never in the
original run's evidence. Production automatic execution remains disabled.


### Separate one-shot real contract smoke result

At 2026-11-06 12:42 UTC, a newly authorized dedicated space 7 and separate
TEMP DATA performed one distinct keyword search attempt. The hydrated Page
identity/ownership checks passed far enough to dispatch navigation. The official
CLI returned code 0 after about 20.17 seconds, but the script recorded
`execution_unknown` at `navigation_dispatched`; the collector was not dispatched.
The retained fixed catch does not include the exception type, so a navigation
timeout is not established by this evidence. The target page's final state and
remote quiescence are unknown. Process exit is not browser success.

The live run is persistently `unknown/capture_unknown`, usedActions=1 of 1,
unresolvedStepCount=1, fresh observations=0, qualified/imported/published=0. Its
worker exited. No retry, new branch, same-ID replay, finish, cleanup, browser
inspection or further navigation followed this result. The test space and its
DATA remain retained; the old blocked space 6 was never operated. All old
retained evidence/TEMP data and production config/database hashes stayed equal.

Evidence: `outputs/handle-binding-20261106/acceptance-result.json`,
`capture-results.json`, `runtime-calls.json`, and `verification-manifest.json`.
The independent test validates that the lazy-handle pre-dispatch mismatch is
removed in this installed SDK. It does not validate a successful real search,
seller/store collection, an automatic multi-round chain, or another PC startup.
The available EGO update was not installed; this test pinned version 0.6.2.7.
