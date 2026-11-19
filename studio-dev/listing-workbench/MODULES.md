# 工作台模块维护索引

更新：2026-11-13。按当前代码入口划分维护范围，供定位、修改和验收使用。这里规定维护边界，不表示所有模块已经拆成独立目录或独立服务。业务规则继续以用户指令和上级 AGENTS.md 为准。

2026-11-15：工作台取消独立产品库、共享和认领。统一入口为 `/products` 产品档案，旧 `/library` 重定向；`product-library.js` 仅保留旧链接兼容。循环选品通过 `discovery_intake.py` / `product_archive.py` 直接在当前账号建档及排重，不再经过共享库。

同日取消独立质检中心和人工审核待办，旧 `/quality` 返回产品档案。`publication-tasks.js` 的 `productCompletionRecord` / `productDisplayStatus` 根据当前账号真实ERP发布回执派生“已完成”，仅草稿、失败或未知不完成；列表、筛选、统计和编辑器复用该口径。不重写原产品状态或人工审核历史，自动图片和接口检查仍保留。

产品档案的“需要处理”同时读取 `product_progress.py` / `/api/products/progress` 的当前账号只读摘要：当前各交付物分镜的最新逐图结果、当前母版换色集及文案/ERP原任务异常。旧分镜、旧图位失败及另一账号任务不计入；`awaiting_manual` 不创建人工待办，真实发布受理仍优先显示“已完成”。摘要不恢复任务、不重发、不回写独立CLI台账。

ERP图片交接共用 `../junfei-publisher/ego-explicit-galleries.mjs`：父体封面、逐子SKU独立七图、旧继承图库的图片字段迁移和断点回读。采集流程与发布前检查共同调用；空子图库不能放行。原生复制及英国保存遵守同一图库合同。

原英国标识纠正由 `publication_identifiers.py` 与 `../junfei-publisher/ego-publication-identifiers.mjs` 负责，沿同一个正式 `repairIdentifiers` 入口创建独立修订并使用专用 `uk_identifiers` 阶段，不重放旧属性/媒体修复。SHIRT30 的三项编码错误与 SWEATSHIRT75 的100980/13013分别校验；后者还需当前原任务的正常只读豁免检查，不能只凭属性中的豁免true清除顶层条码。仅在原US逐SKU明确为空、引入码和错误逐条对应时恢复原ID/type；真实GTIN、SKU、图片、价格和其他属性不替换。保存/重试各自只有一个持久意图，未知只回读。源码与隔离测试通过不代表原商品已经保存或恢复。

1688 串行采集的显式丢失工作区恢复合同见 [SUPPLIER-CAPTURE.md](SUPPLIER-CAPTURE.md)。仅原暂停回执确认 `task space not found`、runtime 再确认原 ID 不存在时可通过 `reconnectMissingBrowser:true` 创建原任务的新连接；验证、登录和未知结果不适用。

## 模块与代码入口

以下文件路径相对于本目录，`../` 指向 studio-dev。

| 模块 | 负责内容 | 主要代码入口 | 数据及边界 |
|---|---|---|---|
| 工作台框架 | 导航、页面挂载、保存同步、公共组件、关于说明 | [index.html](index.html)、[enhancements.js](enhancements.js)、[product-editor.js](product-editor.js)、[visual-ui/ProductEditor.tsx](visual-ui/ProductEditor.tsx)、[visual-ui/AboutOpenSource.tsx](visual-ui/AboutOpenSource.tsx) | 共享界面和版本同步；业务判定调用相应模块 |
| 产品档案 | 父产品、SKU、资料、归档、选品直接建档 | [product_sku.py](product_sku.py)、[product_archive.py](product_archive.py)、[discovery_intake.py](discovery_intake.py)、[import.js](import.js) | 当前账号 workspace 的 products；不共享、不认领；product_library.py仅保留历史兼容 |
| 资料采集 | ASIN 原始资料、实际子体、1688 串行采集、素材来源 | [asin_reference.py](asin_reference.py)、[supplier_capture.py](supplier_capture.py)、[supplier_capture_runtime.mjs](supplier_capture_runtime.mjs)、[importer.py](importer.py)、[supplier_facts.py](supplier_facts.py)、extension/ | 原始采集及缓存；供应商观察不等于库存保证；采集与 AI 洞察分开 |
| 研究与洞察 | 卖家精灵反查、挖词、评论、素材与 ASIN 洞察 | [sellersprite.py](sellersprite.py)、[competitors.py](competitors.py)、[review_insights.py](review_insights.py)、[product_insights.py](product_insights.py)、[ivyea_asin_insights.py](ivyea_asin_insights.py) | 关键词来源、勾选状态、事实及洞察版本；不直接生成或替换文案 |
| Listing 文案 | 生成、去 AI 味、校验返修、持久任务恢复、锁定、历史及关键词标注 | [listing_jobs.py](listing_jobs.py)、[listing-jobs.js](listing-jobs.js)、[provider.py](provider.py)、[listing_skills.py](listing_skills.py)、[listing_locks.py](listing_locks.py)、[ivyea_copy_core.py](ivyea_copy_core.py)、[visual-ui/KeywordTextarea.tsx](visual-ui/KeywordTextarea.tsx)、[visual-ui/keyword-marks.ts](visual-ui/keyword-marks.ts) | copy 按产品/站点保存；默认生成由服务端任务替换并备份历史，浏览器仅读回；冲突保留稿，未知请求不重发 |
| 母版套图 | 分镜、原图选择、图位、生成结果及套图质检 | [visual_studio.py](visual_studio.py)、[studio_bridge.py](studio_bridge.py)、[ivyea_pipeline.py](ivyea_pipeline.py)、[ivyea_render_core.py](ivyea_render_core.py)、[storyboard_variety.py](storyboard_variety.py)、[visual-ui/VisualStep.tsx](visual-ui/VisualStep.tsx) | 项目、分镜和逐图位任务；不得把 AI 通过写成人工确认 |
| 变体换色 | 母版颜色、同色图、子 SKU 关联、恢复变体、本地换色与颜色质检 | [variant_colours.py](variant_colours.py)、[colour_sets.py](colour_sets.py)、[colour-sets.js](colour-sets.js)、[local_colour_tasks.py](local_colour_tasks.py)、[pixel_recolour.py](pixel_recolour.py)、[colour_quality.py](colour_quality.py) | 可见颜色与可制作颜色分开；恢复保留 excludedVariants 和 variantEligibilityHistory，不改原 SKU |
| 交付导出 | 成图顺序、逐色图位覆盖、备份包、文件及清单 | [generated_gallery.py](generated_gallery.py)、[colour_master.py](colour_master.py)、[delivery_export.py](delivery_export.py)、[product_table_export.py](product_table_export.py) | 读取原成图及哈希；正式CSV按listingEligibleVariants沿用原SKU，排除事实另留manifest；主色与草稿映射共用完整母版图序，自动关联不伪造人工审核；reviewRequired按实际缺口计算；导出不得触发生图或补齐虚构规格 |
| ERP 一键采集 | 目标账号/店铺/站点、快照、查重、上传、转草稿及回读 | [erp_collection.py](erp_collection.py)、[erp_collection_inputs.py](erp_collection_inputs.py)、[visual-ui/ErpCollection.tsx](visual-ui/ErpCollection.tsx)、[../junfei-publisher/ego-collection-workflow.mjs](../junfei-publisher/ego-collection-workflow.mjs) | 持久检查点及原文件哈希；未知提交先对账；转草稿不等于发布授权 |
| 美国→英国发布 | 原美国草稿提交、发布中复制、英国资料/SKU校正与发布、后续状态复核及原任务媒体恢复 | [publication_flow.py](publication_flow.py)、[publication_inputs.py](publication_inputs.py)、[visual-ui/PublicationFlow.tsx](visual-ui/PublicationFlow.tsx)、[publication-tasks.js](publication-tasks.js)、[../junfei-publisher/ego-publication-workflow.mjs](../junfei-publisher/ego-publication-workflow.mjs)、[../junfei-publisher/ego-publication-recovery.mjs](../junfei-publisher/ego-publication-recovery.mjs) | 原父子SKU和图片URL复用；最新失败阻断旧受理完成；两站原ID可显式只读复核；媒体恢复需单独冻结原任务范围，核图片并持久意图后仅点原生入口一次，未知只按原ID对账 |
| 任务与流程 | 任务中心、阶段核验、研究交接、选品证据、断点恢复 | [agent_center.py](agent_center.py)、[agent_erp_collection.py](agent_erp_collection.py)、[agent_handoff.py](agent_handoff.py)、[discovery_intake.py](discovery_intake.py)、[cyclic_discovery.py](cyclic_discovery.py)、[../automation/README.md](../automation/README.md) | 正式ERP草稿交付复用erp_collection目标、任务与回执；原历史链保留，不另建上传捷径 |
| 账号与模型服务 | 身份、权限、账号运行空间、密钥、模型传输、预算 | [accounts.py](accounts.py)、[account_spaces.py](account_spaces.py)、[app_paths.py](app_paths.py)、[secrets_store.py](secrets_store.py)、[image_provider.py](image_provider.py)、[openai_image_provider.py](openai_image_provider.py)、[image_budget.py](image_budget.py) | 账号隔离、密钥保护、预算和外部请求回执；被多个业务模块共用 |

## 常用检查入口

变体换色的实际文件分层、兼容入口及加载顺序详见 [变体换色模块维护](COLOUR-MODULE.md)。

Python 命令在本目录运行。下表是定位检查的起点，按改动选择，不能替代逐文件确认测试的隔离方式。测试成功不代表生产数据已经更新或外部任务已完成。

| 修改范围 | 针对性检查 |
|---|---|
| 产品档案 | `py -3 -X utf8 -m unittest test_product_table_export test_product_insights`；涉及删除时加 `node --test test_product_deletion.cjs` |
| 资料采集 | `py -3 -X utf8 -m unittest test_asin_reference test_supplier_capture test_importer test_supplier_facts test_supplier_variants`；`node --test test_supplier_capture_runtime.cjs` |
| 研究与洞察 | `py -3 -X utf8 -m unittest test_competitors test_sellersprite test_review_insights test_product_insights` |
| Listing 文案 | `py -3 -X utf8 -m unittest test_ivyea_listing_trial test_listing_format test_listing_locks test_listing_brand_policy`；标注改动加 `node --test test_keyword_marks.cjs` |
| 母版套图 | `py -3 -X utf8 -m unittest test_visual_studio test_studio_bridge test_worn_image_prompt` |
| 变体换色 | `py -3 -X utf8 -m unittest test_colour_associations test_colour_sets test_colour_master test_local_colour_tasks test_local_colour_api test_colour_quality`；`node --check colour-sets.js` |
| 交付导出 | `py -3 -X utf8 -m unittest test_delivery_export test_generated_gallery test_product_table_export` |
| ERP 一键采集 | `py -3 -X utf8 -m unittest test_erp_collection test_erp_collection_inputs`；外部浏览器适配按 ../junfei-publisher 对应测试核对，保持隔离数据 |
| 美国→英国发布 | `py -3 -X utf8 -m unittest test_publication_flow test_publication_inputs test_publication_api test_publication_policy`；发布/复制/英国准备与编排Node测试使用模拟页面，不操作真实ERP |
| 任务与流程 | `py -3 -X utf8 -m unittest test_agent_center test_agent_api test_agent_handoff`；全流程规则改动在 studio-dev 运行 `py -3 -X utf8 -m unittest discover -s automation -p "test_*.py"` |
| 账号与模型服务 | 按涉及能力选 `test_accounts`、`test_secrets`、`test_image_budget`、`test_openai_image_provider`；账号检查使用隔离环境，不在并行生产维护中停止其他账号的真实任务 |
| 共用前端 | TS/TSX 改动在 visual-ui 运行 `npm run build`；普通 JS 对实际改动文件运行 `node --check`；验收具体受影响页面 |

## 模块间的接口约定

1. 采集模块保留原始颜色、尺码、ASIN 和图片来源；洞察模块引用这些资料，不改写为未经核实的事实。
2. 研究模块提供勾选词和真实指标；文案模块保存实际入模词。关键词展示不改变生成时选词结果。
3. 母版模块提供已保存分镜和完成图位；换色模块引用母版及同色资料。目标颜色展示不得绕开货源、SKU 和参考图校验。
4. 换色模块的 `display_catalog` 供展示，`catalog` 供制作及导出校验。`/api/colours/master` 与 `/api/colours/reinstate` 校验产品版本，分别保存母版变化和变体恢复历史。
5. 交付与 ERP 模块只消费完成的图片、真实变体和明确经营资料，保留已有草稿和未知请求记录。
6. 账号与模型服务模块提供共用基础能力；不得通过跨账号读取数据库、复制密钥或另开付费路径来修复单个产品。
7. 默认文案走 `/api/listing-jobs/start`。完成稿、字段锁合并、替换前copyHistory与任务状态由 `listing_jobs.py` 同库事务保存；前端不得再次POST生成结果制造双历史。关页只停止浏览器轮询，不取消服务端任务。进程中断仅核对原持久结果，没有完成回执时保留待核对，不自动重发模型。
8. 任务中心正式ERP交付选择账号已配置的destination，止于原生草稿回读。已有完成回执需与当前成品核对，运行中/未知任务复用原ID；新任务不能绕过旧SKU提交或未知结果限制。
9. 新美国任务通过 `publication_policy.py` 保存publicationFollowup。交付页“发布美国并接续英国”调用`/api/publication/start`，原美国ERP采集回执需与当前成品匹配，英国目标与本款GBP资料齐全才排队。`publication-flow/jobs.sqlite3`持久记录原intent及美英回执；关页不取消服务端任务，未知状态只允许同ID对账。现有草稿任务、历史记录和发布授权不自动扩展。

## 每次维护的交付内容

- 写清本次主模块、问题触发方式和预期行为。
- 对照本表定位文件；需要跨模块时列出接口与受影响页面，再修改直接相关代码。
- 字段变化兼容既有产品和历史回执；需要迁移时先做隔离验证，保留可回退记录。
- 检查通过后按影响范围加载服务；报告代码、构建、服务和真实验收各自的完成状态。
- 留下必要证据，说明尚待补充的资料；不因维护完成就把生产任务标记完成。

## 历史资料与共享文件

`server.py`、`index.html`、`enhancements.js`、`visual-ui/ProductEditor.tsx` 当前仍跨模块共用。修改时按路由、函数或组件范围定位；新增复杂能力逐步抽到业务文件，避免把所有需求继续集中到共享入口。

一次性试跑、修复、生产脚本及历史说明保留为追溯资料，不能替代正式模块入口。产品数据库、已生成图片、原始提示词、许可及历史记录继续按既有规则保存。
