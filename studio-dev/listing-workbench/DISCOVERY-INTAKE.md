# 循环发现建档与 CLI 台账

此功能用于隔离开发工作台。CLI 继续持有执行权，网页负责核验入库与读取已关联任务状态。产品库沿用工作区 SQLite、已有产品 ID、SKU 和站点文案。数据库启动时增加 `discovery_product_links` 表，旧表和已有记录由原入口读取。

1. 使用独立的 `JUNFEI_ACCOUNT_DATA` 启动开发工作台。CLI 使用 `automation/pipeline.py --db <本账号数据目录>/pipeline.sqlite3 --config <隔离配置> ...`，选品和货源的完成回执由现有 `Pipeline.finish` 保存。历史台账如需验证，先使用单独的、范围已确认的账号副本。网页仅从本账号运行数据目录读取固定文件 `pipeline.sqlite3`，不接受上传台账或指定数据库路径。
2. 在「选品调研」保存循环发现证据，打开对应批次，进入「核验后建档」。选中最多 30 个有搜索或店铺观察的商品，点击「核验并加入产品库」。标题种子与被明确排除的搜索观察不构成建档依据。
3. 每个候选必须有与当前账号、站点和 ASIN 一致的 CLI 任务，选品和货源阶段均有唯一完成回执，并有选品排重预留、同款 1688 货源及正利润报价证据。使用现有 `qualify_cyclic_20261104.py` 的回执格式，包括 `sourcing_evidence.accountId` 和 `selected_quote.profit_at_market_price_rmb`。只有阶段勾选、缺账号、缺结构化报价和估算亏损均停在待核对。
4. 新档案与 CLI 关联在同一事务写入。站点和 ASIN 相同则复用原档案。历史 SKU、Listing、素材和产品资料保留。已删除档案、冲突身份及有待对账的网页任务留在待处理。每次操作返回实际新增、关联、沿用或阻断结果。报价利润保留原估算范围，生产资料及发布审批仍按现有流程检查。
5. 到「智能体任务中心」查看 `CLI 台账 · 关联产品`。在对应 CLI 任务续跑或对账。网页不会替 CLI 启动、重置或推进阶段。CLI 台账不可读时关联仍可见，状态显示待核对。原网页任务可以查看，已关联产品的网页启动及批量启动会被拦截。

开发版以本机单实例、按账号运行目录为边界。当前没有双向写入、自动接管、跨电脑共享 SQLite 或生产迁移。新增入口使用已有会话、同源校验及工作区修订号。发现图谱继续按观察记录存储，观察条数和实际建档结果分别显示。

## 竞品 ASIN 随选品建档

在独立选品 EGO 工作区首次打开 Amazon 或切换站点时，先通过「配送至」设置目标国家邮编。核对页头回显并记录观察位置后，再搜索、读价格或采集商品。

在候选的 CLI 选品完成回执内，`selection_evidence.ranked_competitors` 使用数组，每条记录包含以下字段。

- `asin`、`parent_asin`、`marketplace`、`title`、`match_level`（`exact` 或 `strong`）、`match_evidence`。卖家可见时记录 `seller_id` 和 `seller_name`。候选自身的已核实父体写入 `selection_evidence.candidate_parent_asin`。
- `search` 包含 `keyword` 和 `url`。使用实际打开的同站点 Amazon 搜索页。
- `rank` 包含 `value`（正整数）、`category`、`source`、`url`、`raw` 和 `checked_at`。Amazon 搜索商品卡用 `Amazon search page extension`，原文保留 ASIN 和「#数值 in 类目」。Amazon 详情用 `Amazon product page`，网址指向该 ASIN，原文保留对应类目排名。卖家精灵用 `SellerSprite MCP`，原文 JSON 含 `asin` 与 `bsrRank`，网址用不含密钥的 MCP 服务地址。

工作台取消选品中心后的技能入口仍为当前账号的 `/api/discovery/ingest` 和 `/api/discovery/promote`。新档案保存最多 5 条有效证据及同站点商品链接，按 Parent ASIN 去重，并逐行预填到竞品关键词输入框。少于 3 条显示待补。旧回执及已有档案沿用原数据。

管理员在「产品库 → 从我的档案添加」选择循环选品档案并点「采集并添加」。工作台先采集该款 ASIN 的商品页和主图，再使用已核实的竞品 ASIN 获取卖家精灵关键词、评论样本及分析。已保存且匹配的结果会复用。资料不齐时保留已完成步骤和错误提示，补齐后才加入共享库。认领会复制商品页参考、竞品资料及供应商素材到个人档案。共享库和个人档案优先用 ASIN 主图作缩略图。已有共享记录沿用原图片。

原竞品组每款均成功查询且都无评论正文时，工作台从已核实的同站点 Amazon 搜索结果查找补充来源。卖家精灵核对 ASIN、父体与数值排名，模型对照主图判断结构相似性，最后验证评论正文。只采用一款，在评论报告的 `supplement` 中保留来源与相似依据。原竞品 ASIN 和关键词研究保持原样。接口出错或找不到合格参考时，继续保留已保存资料并暂停共享。
