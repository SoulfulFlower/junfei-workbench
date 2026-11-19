# 1688 串行采集与丢失工作区恢复

正式入口仍为账号隔离的 `/api/supplier-capture/request`、`result`、`status`、`resume`，全部使用同一持久 FIFO 队列及官方 EGO runtime。采集完成后沿用配置的至少 90 秒间隔，不使用独立 HTTP、全局键鼠或并行详情抓取。

验证或登录暂停只在用户完成后通过 `{confirmed:true}` 读取原页面，不导航回商品、刷新或重放未知执行。

2026-11-17 新增已授权流程恢复选项：`POST /api/supplier-capture/resume`，JSON `{confirmed:true,reconnectMissingBrowser:true}`。它仅适用于当前账号正持有的 paused/reading 任务：暂停原因必须精确为 `task space not found: <原spaceId>`，原 run 的 `result.json` 必须具有相同原因和完整相同 browser 绑定，且没有恢复进行中。该选项不是验证码、登录、执行未知或其他账号任务的恢复授权。

服务端保留原 capture ID、队列 created/FIFO、URL、旧 run/receipt，向 capture_events 追加原 run/browser/回执 SHA256 和新 run。runtime 先用官方 `listTaskSpaces()` 证实原 ID 仍不存在，记录创建意图后才创建唯一 `Junfei 1688 serial collection reconnect <runId>`；仅其唯一 agent 创建的空白 p1（精确 `about:blank`、实际 EGO 原生 `chrome://newtab/` 或其文档别名 `chrome://new-tab-page/`）可作为原队列 URL 的首次导航入口。收到创建身份即保存 createdSpace，导航前再持久保存完整新绑定。原工作区仍存在、创建结果未知、非空白新页或实际验证均停止，不换另一个工作区重试。

对旧版本已创建工作区但误拒原生 newtab 的回执，同一显式选项可执行一次严格对账：当前 reason 必须为 `reconnect_blank_page_required`，原 terminal result 的 creating/runId/previousBrowser 必须一致，且完整追溯到前一条精确 missing-space 回执。runtime 只接回 inventory 中唯一精确匹配原 creation run 名称、agent 所有的既有工作区 ID；仍须只有唯一原生空白 p1。此分支不调用按名称创建，不 takeOver 用户工作区，记录 `existingCreationRunId` 和 `creationCalls:0`。找不到、同名歧义、多页、远端页面、验证或未知结果都停止，不能重新创建。

已绑定但因原生 document alias 被误拒的旧回执还须校验当前 browser、bound.browser、createdSpace 完全一致，并逐层追溯 bound → 原 creation → 原 missing 回执及 SHA256；不接受未知、验证或循环历史。runtime 检查的是原 missing 工作区仍不存在，而已绑定工作区必须继续存在且与原名称/ID一致。旧 bound 证明和全部旧文件不覆盖，新 run 记录 previousStage/reconciledBoundBrowser；browserDiagnostics 分别保留 tabs URL、page.url() 和 document.URL 的安全地址及原生空白判断，不读 Cookie，远端 URL 去掉查询参数。

一次性 reconnect 标记在该 run 的所有结果中消耗；新绑定留给后续串行采集使用。恢复失败或未知不清空旧身份，不自动重新创建；后续仍按原持久回执核对。该入口不启动或重启账号服务，也不修改产品资料或发布任务。
