# 工作台模块维护索引



`publication_coat_facts.py` 的独立 `usCoatFacts:true` 接续只用于原美国COAT真实schema预检失败、尚未发送保存或发布的同账号原任务。核对当前产品已登记完整货源观察的链接、时间、原图、文件Hash和冻结文案，从实际“拉链／灯笼袖／长袖／普通款”派生属性；普通纯涤纶服装的危险品目录分类单独记推断、非供货认证。原输入和失败预检完整归档，不清空保存意图或重建任务。`ego-coat-attributes.mjs` 按真实嵌套schema映射并复跑全部父子校验；无明确来源不产生隐式默认。



ERP原生采集及英国接续的产品类型推荐采用已匹配真实路径的完整 `label.el-radio` 进行可信点击，不点击装饰性的内部span。2026-11-21实际Fleece弹窗的内span被同一对话框拦截，完整标签成功；英国仍额外核对原节点value和完整文字。保留原草稿/采集ID、来源路径与匹配分数，仍按实际schema校验，不更换类别或绕过保存检查。



`publication_inputs.publication_facts` 优先保留同货源实际货号。货号缺失时，普通服装可读取逐产品明确授权的 `publicationAttributeDefaults.modelName`，值必须精确等于该产品实际父SKU，并保留 `user_configured_defaults`、`supplierVerified:false` 和时间、授权范围。此值只赋为卖家命名的 `modelName`，不生成供应商货号或条码，不修改已冻结任务；其他产品和新电脑不能自动继承授权。隔离检查见 `test_seller_model_name.py`。



`../junfei-publisher/ego-collection-prepare.mjs` 解析实际 SKIRT schema 的 `skirt_size.0.size`，美英分别按真实枚举和条件约束核实尺码类别及体系。与既有 shirt/bottoms 维度共用后续草稿、发布和回读，不将裙装尺寸套入上衣字段，也不跳过未知或混合尺码阻断。



短裙原美国任务可通过 `POST /api/publication/continue` 的独立 `usSkirtFacts:true`，由 `publication_skirt_facts.py` 核对当前账号同一1688货源、真实型号、原始标题中唯一腰型及“图案：纯色”，追加有历史快照的保存前修订。不得修改已冻结保存或已发布记录；Mini来自冻结Style明确mini skirt，Regular仅在真实schema明确对应标准尺码时使用。原货源标题的其他营销词不随该修订进入刊登。



`prepared_colour_gallery.py` 将当前账号已完成的同色来源排版及原生修图候选，按当前母版/真实变体照片/实际文件哈希幂等接入颜色图库。只保留原生 `validating`/`reviewing` 起点，由 `colour_sets.py` 的既有同款与逐图质检继续处理，不继承独立候选的SKU权限或伪造审核通过。需要逐图真实来源、技术构图检查及完整图位；既有同色任务只沿原记录修复。



2026-11-21 图片引擎重做：`image_engine.py` 管理账号独立候选任务，`image_engine_prompts.py` 编译原创分镜/修图指令，`colour_transfer.py` 提供彩色、黑白灰、参考照片三分支换色。`visual-ui/ImageEngine.tsx` 是图片步骤正式入口。`POST /api/image-engine/start` 校验当前产品与requestId；`GET /api/image-engine/tasks`、`/task` 仅读取/对账，不重发生图。任务保存源Hash、蓝图、模型回执、原始输出及交付图，不自动绑定SKU或覆盖正式母版。



付费调用通过 `image_provider.submit` 的服务端 `image_engine_task_id`，核对已持久化pending意图，沿用预算、提交台账和未知查询。分析、策划、生图与质检显式使用同账号Codex Tools。服装可自动识别部件；其他商品须明确选区。可选模型换色修整合成回选区，原始模型输出另存。



正式套图新策划 `layout-director-v3` 取消3C模板的hero上限及强制远景/无商品图；没有版式时附原创构图蓝图。旧原版策划函数及历史方案保留，正式七图与真实尺码依据合同保留。自由套图逐张指令只传当前图位，真实无文字细节优先原像素裁切，避免把整套需求画成拼图或重画缝线。



更新：2026-11-13。按当前代码入口划分维护范围，供定位、修改和验收使用。这里规定维护边界，不表示所有模块已经拆成独立目录或独立服务。业务规则继续以用户指令和上级 AGENTS.md 为准。



2026-11-15：工作台取消独立产品库、共享和认领。统一入口为 `/products` 产品档案，旧 `/library` 重定向；`product-library.js` 仅保留旧链接兼容。循环选品通过 `discovery_intake.py` / `product_archive.py` 直接在当前账号建档及排重，不再经过共享库。



同日取消独立质检中心和人工审核待办，旧 `/quality` 返回产品档案。`publication-tasks.js` 的 `productCompletionRecord` / `productDisplayStatus` 根据当前账号真实ERP发布回执派生“已完成”，仅草稿、失败或未知不完成；列表、筛选、统计和编辑器复用该口径。不重写原产品状态或人工审核历史，自动图片和接口检查仍保留。



产品档案的“需要处理”同时读取 `product_progress.py` / `/api/products/progress` 的当前账号只读摘要：当前各交付物分镜的最新逐图结果、当前母版换色集及文案/ERP原任务异常。旧分镜、旧图位失败及另一账号任务不计入；`awaiting_manual` 不创建人工待办，真实发布受理仍优先显示“已完成”。摘要不恢复任务、不重发、不回写独立CLI台账。



`listing_format_recovery.py` 处理原初稿及润色已完整返回、尚未进入语义审校的单件包装格式失败。`POST /api/listing-jobs/continue-format` 限同账号、原任务、两份原回执哈希及同货源“单件”证据，仅允许补 `packageContents` 和 `packageContentsEvidence`；冻结旧输入后接续尚未提交的审校。已有后续响应或其他事实变更阻断，同请求幂等，保留原任务与历史响应。未知或失败接续不自动重发。



AI 分镜卡 `production_method=blocked` 由 `ivyea_pipeline.shot_source` 与 `visual_studio.slot_references` 共同拦截。预检须显示对应 `SOURCE_EVIDENCE` 错误；有可用主图也不能替代卡片缺失的依据，不因 `product_presence=absent` 或历史缺图读取选项绕过制作限制。



`ivyea_pipeline.project_size_chart` 优先读取当前档案明确选择的供应商或同款竞品尺寸依据。已有旧项目的供应商表不能覆盖当前选择的竞品表；当前明确提交的表无效时不恢复旧表。仅没有当前表字段的旧档案保留历史表兼容读取。



ERP图片交接共用 `../junfei-publisher/ego-explicit-galleries.mjs`：父体封面、逐子SKU独立七图、旧继承图库的图片字段迁移和断点回读。采集流程与发布前检查共同调用；空子图库不能放行。原生复制及英国保存遵守同一图库合同。



服装第7图由 `ivyea_pipeline.required_size_chart` 校验来源、刊登尺码覆盖和成图校对记录。`studio_bridge` 绑定当前分镜的尺码证据，`erp_collection` 绑定母版文件及逐色第7图来源，`delivery_export` 在审阅备份清单标记尺码缺口。



原英国标识纠正由 `publication_identifiers.py` 与 `../junfei-publisher/ego-publication-identifiers.mjs` 负责，沿同一个正式 `repairIdentifiers` 入口创建独立修订并使用专用 `uk_identifiers` 阶段，不重放旧属性/媒体修复。SHIRT30 的三项编码错误与 SWEATSHIRT75 的100980/13013分别校验；后者还需当前原任务的正常只读豁免检查，不能只凭属性中的豁免true清除顶层条码。仅在原US逐SKU明确为空、引入码和错误逐条对应时恢复原ID/type；真实GTIN、SKU、图片、价格和其他属性不替换。保存/重试各自只有一个持久意图，未知只回读。源码与隔离测试通过不代表原商品已经保存或恢复。



1688 串行采集的显式丢失工作区恢复合同见 [SUPPLIER-CAPTURE.md](SUPPLIER-CAPTURE.md)。仅原暂停回执确认 `task space not found`、runtime 再确认原 ID 不存在时可通过 `reconnectMissingBrowser:true` 创建原任务的新连接；验证、登录和未知结果不适用。



2026-11-21：图片构图自动门禁由 image_composition.py 提供，image_quality/visual_studio/product_artwork/colour_sets 消费生成期结果，delivery_export 与 erp_collection.finished_snapshot 对实际文件重新检查。报告绑定策略版本及SHA256，ERP资产 compositionCheck 保留测量依据；publication_flow.start 在新发布前通过 finished_snapshot 再校验，不改已受理或未知任务。中性底像素分析与包内SCHP服装分割互补，尺码表单独处理；无模型或无法完成检查不放行，不新增付费请求。



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



2026-11-21 构图 v2：完整穿着图结合 SCHP 与 U2Net 的目标服装区域，避免仿麂皮长裤被人体模型误作上衣。细节图不按完整人体分割面积判定，仍保留空图、套小图和留白检查，并由原生单图/整套语义复核核实具体结构；导出与 ERP 快照沿当前分镜传递 detail 图位，不能用旧审核标记覆盖文件检查。自然长条产品通过真实裁切减少留白，不拉伸商品凑满方图。



构图 v3 对已识别的下装，仅在完整衣物域中从真实下装语义种子向下恢复相连、同衣料色系的区域，排除种子上方外套及分离背景，不降低原占比要求。报告保留真实种子数、恢复范围和文件 SHA256；失败记录不改写，按新策略对原文件重检。



英国COAT保存前实际schema失败时，`ukCoatWeave` 独立正式接续把逐品经营默认冻结到原任务；校验同账号、原复制草稿、美国原受理和真实英国schema，归档旧输入及失败预检。织法Plain记user_configured_defaults和supplierVerified:false；同款100%polyester、制造商及Jackets分类分别来自冻结事实，不生成内衬或认证。X-Small/XX-Small仅在真实枚举唯一匹配XS/XXS时映射，歧义及数字尺码仍停止。英国schema在尺码解析前持久保存，以便普通必填问题沿原回执定位。





2026-11-22 官方原始模板接入：`official_image_templates.py` 按不可变ID校验240张真实配图及原始提示词、24项完整修图配置与配图，`official-image-templates/manifest.json`保存来源与逐文件SHA256。新自由套图与正式AI分镜均引用原配图和完整原文，不回退简化蓝图。`visual-ui/OfficialColour.ts`执行原始配置11级GLSL滤镜；`official_colour_result.py`核对资源哈希、执行顺序、选区外原像素及alpha。原始供应商字段仅作来源元数据，分析/生成仍走当前账号Codex Tools、预算及原生回执。原件、失败图和未知提交保留；候选图不自动绑定SKU或替换已发布图库。私有服务端提示词和原生曲线助手未取得，不声称完整私有实现复原。



原片锁定模式（可选）由 `image_source_layers.py` 执行：按原配图/完整原文编排，AI只制作背景及许可文字，真实商品/细节由同款原片图层合成；保存来源哈希、裁切与输出坐标、蒙版及模型背景原件。该模式保留原拍摄姿态，不声称AI生成了新商品角度。换色先由后端将原件解码为无损RGBA PNG，避免浏览器/JPEG解码舍入差异；原JPG及其哈希保留，选区外像素和透明度检查不降低。





### 2026-11-22 服装编排、修图扩写与原生GPU链



独立图片引擎通过apparel_suite冻结图种数量、参考角色/哈希、模特/场景一致性与逐图原模板；正式服装策划复用同一身份/中性光/流苏约束，原七图尺码事实门禁保留。repair_prompt_pipeline保存原配置及typed nodes，needOptimize默认false，显式开启时只经当前账号Codex Tools扩写。garment_colour_mask结合衣物/人体语义与原片细边，保护肤色、靴子和流苏间隙。OfficialColour为原生11pass WebGL2链，交付明确启用选区外原RGBA恢复；official_colour_result验证源码、逐级顺序及实际像素SHA。原片锁定模式保留商品姿态和纤维，不作为新角度生成。仅新任务应用，不改历史记录或发布状态。





实测迭代：sku_colour_recipe（measured-sku-native-controls-v1）提供账号/商品校验后的POST /api/image-templates/colour-recipe，按实际选区取源衣料锚点，编译原GLSL参数；深色用光影混合加乘性曲线，避免直接减亮导致暗部截断。ImageEngine和Skill显式matchTargetSample选项保存校准审计。source layers v3修复浅色针织内部透明孔洞，摄影场景门禁拒绝模板示意圈/空卡片。修图显式原片锁定仅调整背景，保留原姿态和商品。无文字细节优先真实方形子裁切，记录实际坐标及等比缩放，保留请求原坐标。





2026-11-22 其他商品复测：浅色绗缝外套暴露袖片被ATR误作手臂、粗蒙版局部校色产生色斑、原片上装修图中裤装被误抠的问题。garment_colour_mask v2要求衣物语义和原片Lab共同支持才恢复误标袖片，显式保护优先；腰部硬件启发式不套用上装。image_fidelity对已接近原色的浅中性色保留原始模型像素，继续独立复核；source_layer按upper保留非目标裤装不透明内部，缓存分品类和新版。sku_colour_recipe v2支持一次实测GPU预览反馈，通过原生R/G/B曲线校准中间调，保留初始预览、参数和反馈审计；不覆盖已有自定义曲线、不接受选区外已变的预览、不盲目重复。全部三项测试保存为独立候选，不覆盖旧图、不绑定SKU或发布。



### 2026-11-22 工具自动选区、独立验收与有限纠错

主模块为独立作图引擎。`image_tools.py`提供账号内持久`POST /api/image-tools/start`和`GET /api/image-tools/task`，任务类型selection/colour_check，冻结productId、输入文件SHA和当前Codex Tools路线；requestId重放只读原意图，运行中断不自动重复付费分析。`image_tool_vision.py`复用现有视觉协议与原始回执。`automatic_garment_selection.py`由当前账号视觉分析自动产生衣料/保护约束，本地联合SAM解码，仅明确点矛盾时回退原像素GrabCut，然后matting、数字门禁及独立视觉复核；最多一次内部自动修正。已返回计划的纯本地错误可核对签名后接续，历史图片、计划与失败回执保留；未知调用仍停止。

`automatic_image_quality.py`联合实际源图/蒙版/成图/目标参考图、选区外RGBA不变、中间调及独立视觉检查，检测漏衣料、肩带/皮肤溢色、材质与结构变化。选区外零变化不再直接证明identityPreserved。qualityCheckId绑定服务端真实文件SHA、产品及目标RGB，客户端不能自报通过。ImageTools.ts和“钧飞商品作图”Skill从原图自动识别与取色，保存GPU初始预览和一次曲线反馈；成图明确选区缺陷可触发一次自动选区修正，再检查。仍有阻断则保留失败候选，不替换母版、不自动绑定SKU或发布。

套图与自由修图在原参考图和用户要求不变的条件下，可根据实际阻断复核自动重试一次；保留初次模型输出与回执。原片锁定任务和原片裁切不得偷偷重画商品。人工/代理手工标点、裁样或修图不能计为工具自动通过；统计分开记录首次通过、自动纠正通过、阻断及人工干预。模型通过不等于人工审核，小样本通过不保证任意商品零返修。


### 2026-11-22 自动取色与高质量原片前景

`automatic_reference_sample.py`把目标参考取色与完整源选区分开：reference_sample任务只验证同款衣料中间调样本，保存真实RGB像素、坐标、样区NPZ及SHA，sampleVerified=true不代表完整衣物选区，eligibleAsSourceSelection=false。源图仍由selection完整覆盖和独立成图检查负责；selected_receipt同时核对产品、上/下装类别、原图/蒙版与source_garment用途，不能用目标小样代替源蒙版。当前账户Codex Tools负责样本规划与独立复核，不按颜色名猜RGB。

原片锁定的整人物前景使用`foreground_matting.py`调用固定revision和SHA的BiRefNet-matting离线worker，保存float alpha和原RGB，不再默认用SCHP类别及猜测背景颜色强删手机、帽子或衣物。`image_fidelity.source_layer(...,backend='legacy')`仅保留旧策略重现；缺模型不暗中降级。模型资产、MIT许可、原代码及环境清单在models/foreground-matting。当前本机为隔离CPU环境（实测约17秒推理），它只读依赖既有HQ-SAM CPU site-packages，生产Python不升级；未安装或宣称CUDA推理，其他电脑须按依赖合同重新安装。模型推理不等于视觉通过，仍需检查手/手机、帽檐/发丝、空隙、边缘和背景残留。

背景修图交付按原片自然比例合成到方形画布，不将竖图拉伸为方形。工具修复后可用reusePlateTaskId核对同商品、同原片、同要求和同模板的已完成空背景及完整扩写回执，重新合成并复核，避免重复生成背景；原失败任务保持不变。光影修整仅在初始换色已通过时提交，最终合成图必须重新走目标色专用检查，不能沿用初始qualityCheckId或通用“贴近源色”检查。

工具在网络调用前保存modelIntents pending，收到完整回执后completed，异常留unknown；同源未决任务不因新requestId或算法升级再次付费。/api/image-tools/retry只为已明确rejected且工具版本变化的旧选区失败派生确定性任务，保存parentTaskId；unknown/interrupted继续先对账。小样本通过不能据此承诺所有商品零返修。


### 2026-11-22 自动补漏保留、来源复核与细节门禁

`automatic_mask_revision.py`作为独立作图工具的选区纠正模块，由image_tools消费服务端真实qualityCheckId和previousSelectionTask。先核账号隔离后的商品/品类/用途、原片和原选区及成图SHA；客户端issues/locations不作为纠正授权。仅纯漏选且保护物、结构、材质和目标色均保真的成图复核可合并旧选区与新选区，原片证据支持的保护区优先归零。候选canonical回执、源像素、蒙版PNG、原保护区/标签/domain均重新核对；新蒙版继续执行原数字门禁和一次新独立源图/选区复核，不继承旧通过标记。mixed/leak不直接合并。未知或pending调用先对账，不换requestId付费重试；失败保留新旧证据，不覆盖旧母版。

selection内部最多3次有界分析（初次加2次自动修正）；成图明确选区缺陷最多触发一次外层纠正。automatic_image_quality v3增加最多6个来源绑定的细节放大区域，包含保护路径、真实边缘及下装流苏区域，保存原像素bbox和对应哈希；原独立视觉与颜色/选区外RGBA门槛不降低。目标取色reference_sample仍只证明真实衣料色样，不能充当完整源蒙版。零返修是优化目标，单元测试或少量样图通过不构成任意商品零返修保证。

selection v7对受光差异的背景开口增加真实gap样本：要求当前自动计划与前轮独立复核共指、原局部分割背景标签及稳定源像素、远离真实衣料且与外界背景色度一致，再沿原像素边界恢复保护区。保留原Lab/色度距离和边界、前景冲突门槛，不按白色/颜色名删除。新增sourceBackgroundPaletteLab和localGapExemplars审计；纯本地回放通过只证明该修复路径，真实选区与最终成图仍须独立验收。


### 2026-11-22 自动衣料候选与矛盾约束校验

`garment_component_proposals.py`为现有selection规划提供最多6个非primary衣料小区域的原图/假设对照，保存真实源像素、组件与裁图SHA、原图bbox、真实内部点及显示坐标映射。它只提议，不认证同款、不修改蒙版、不调用模型；规划仍须根据当前商品和原图选点或拒绝。候选沿用当前衣物语义、源衣料Lab与保护证据；不按产品专用坐标、颜色名或手工裁图补洞。后立领等本地证据不足的区域不因真实其他部位通过而自动认证。

selection内部纯漏选守恒只使用同一不可变原片run中的实际候选、已通过数字检查及明确misses非空/leaks为空的前轮独立复核；合并后保护与原alpha优先，重新执行原数字门禁及当前独立视觉检查，不继承旧pass、不增加轮数。primary标签与human背景、源颜色明显冲突的FG点不能无条件作为衣料锚点，须保存实际源RGB/类别与拒绝诊断，避免误点背景污染背景开口判断。该策略不宣称已解决任何未实测部件，也不将未通过的选区交付为成图。


### 2026-11-22 局部归属核实与离线实例纠正

`automatic_local_selection.py`消费服务端核对的源图、旧选区、实际成图、canonical源回执及QC。报告坐标仅为机器假设；先由当前账号Codex Tools在绑定原图的局部对照中核实目标衣料归属，uncertain停止。真实miss才用局部模型形成候选，ROI外旧alpha保持不变；解剖、显式、已证背景和真实负点等硬保护不可释放。模型宽ribbon只在衣料/遮挡物双实例证据齐备时局部释放，不能因颜色接近或模型正提示响应就染配件。源模型语义与颜色冲突的孤立点仍需来源佐证。之后原数字门禁、新独立源图复核及最终完整换色QC全部保留。

`sam2_local_backend.py`经models/local-instance固定worker调用本地SAM2.1-Hiera-Large，revision665f8e2ad61cf5f53d65644ff27c8ee525124610，权重SHA dc407dce21301fd94abb395c5099b4f2c455fdc8a8f261ac3d0ea6d4cd197230，Apache-2.0。CPU隔离环境固定Transformers5.0.0并只读复用既有torch2.6+cpu，不升级全局包、不使用CUDA；原片/点/角色/模型/环境/worker/输出哈希均校验，模型响应不自证通过，负点矛盾和损坏缓存不默默兜底。源码与运行副本模型许可、资产和环境有独立安装清单；新电脑须按合同安装，不继承本机绝对路径或密钥。

QA v4只把source-bound localGrounding的最多两个实际原图区域优先纳入细节复查；下装仍保留两处实际下摆，总细节数不超过6。局部记录明确为未认证证据，不覆盖QA flags、数值阈值或原失败记录。auditOnly/maskChangedPixels=0也须新源图复核及一次有新局部证据的完整成图检查；无可信证据不循环重评刷通过。Skill区分首次通过、实际像素修正、证据澄清及未通过，不把接口成功等同零返修。


### 2026-11-22 局部纠错v2与历史失败回归

局部核实允许检查服务端漏选报告及疑似溢色提醒，但当前local v2只增加已证实的漏衣料；实际非目标染色、归属不明或缺完整证据仍停止，不降级为全局重规划。256像素原图ROI、独立衣料实例和必要遮挡物实例、原硬保护、新源图复核及最终成图检查均保留。质检报告的原坐标不是前景标签，不把auditOnly或mask URL变化计作真实像素纠正。

历史v3-details失败报告仅可在原片、旧蒙版、实际旧成图、账号/商品和canonical选区回执完整绑定时作为纠错研究假设，旧通过不授权新交付。verified_colour要求当前v4-grounded-details策略及当前源图/蒙版/目标/成图字节绑定；历史报告和失败状态不回写。未知/pending调用先对账，不换requestId重复付费。

真实历史失败回归已在普通工作台selection→原GPU链→colour_check→image-engine入口完成：外套头发环内漏衣料由模型核实，局部自动补入1368像素；ROI外选区、成图选区外RGBA及原alpha变化均为0，新源图与完整换色复核通过，手工标点/蒙版干预0。裤子腰边疑似误选仍被归属不确定阻断，不统计为通过。回归通过不保证任意商品零返修，候选不自动覆盖正式母版或发布图库。


### 2026-11-23 自动去误选与原片排版边界

主模块仍为独立图片引擎。automatic_local_selection v3在源图、旧mask、实际旧成图、原QC及canonical回执完整绑定后支持true_leak：Codex核实原片非目标和实际染色点，离线衣料/非目标双实例共同验证；只删除ROI内有界弱alpha连通区域，原不透明衣料、真实衣料锚点和ROI外选区不变。未知归属、实例冲突、过大/截断区域和不透明误选继续停止。纯漏选路径及原硬保护保留，不把删除误选换名为补漏选。QA v5仅接受新证据类型以引导实际局部复查；数值验收政策不变，新完整成图复核仍必需。历史v3/v4失败只能作有绑定的研究假设，不能授权新交付。

image_source_layers v7使用原alpha的可靠边缘覆盖识别真实摄影截断，半透明白底/JPEG噪点不得触发左右锚定；保留策划水平位置，原片上下均截断时以等比缩放贯穿画布上下，避免悬浮的牛仔裤或躯干平切。不能无损容纳时拒绝，不拉伸、不补画缺失身体。完整覆盖画布的模型detail图层按原自动策划的真实裁切及位置拼接，不再替换成单幅通用裁切；不凭代理指定坐标凑验收。

套图/修图本地工具修复后，通过新版本任务的reusePlateTaskId复用原任务已明确完成并通过emptyPlateCheck的最终空背景、同一原片/要求/模板及原扩写回执；保留原失败图、付费背景及任务号，重新合成和独立验收。未知提交不重发，已经失败的旧状态不改为通过。候选不替换正式母版或发布图库。


### 2026-11-23 发丝连续alpha与同一物体覆盖

automatic_local_selection v6可让实际protectedPartsPreserved=false、其余身份/材质/目标色保真且源/输出绑定完整的selection泄漏报告进入纠错研究；这不授权交付或提升旧flag。local_hair_matte以当前账号视觉核实的原图衣料/发丝点、原生衣料与非目标双实例、独立人体发丝标签建立trimap，再以原RGB的colour-line闭式matting求解连续alpha。NumPy/SciPy向量化Laplacian与已安装独立实现的小样本矩阵对照一致，避免包级JIT初始化；线性残差只证明求解，不是视觉通过。原RGB不处理，原生目标衣料实例、强衣料色度证据、真实衣料锚点和ROI外选区保留；允许降低被错选发丝的选区alpha，不把错误的opaque选区当成真实衣料。只修改与本轮确认的染色点相连区域，边缘渐变与面积预算有界，冲突仍拒绝。

单个质检点不代表发丝物体完整范围。工具可从同一个独立发丝连通物体的旧选区自动提出覆盖ROI；最多6个256像素原图区域，总面积仍不超过35%，不同人物/其他连通物体不纳入。新增ROI只是假设，每个仍由同一次当前账号视觉核实；原图/旧alpha/实际旧成图逐区域分图给模型，避免长拼图缩小。随后逐区离线分割/连续alpha、一次新全源图复核、一次完整成图检查；不增加QA循环来刷通过，不使用代理手填坐标或蒙版。旧失败保留，不扩大数值验收门槛。


### 2026-11-23 同视角参考发丝证据与精确候选编号

主模块为独立图片引擎选区。image_tools.py在原账号/商品/QC/图像字节核对后，向automatic_local_selection.py传入服务器原QC绑定的真实reference；reference_pose_evidence.py提供严格同视角变体对齐、源/参考哈希、重投影误差、非目标稳定比例及衣料实际变色证据。分析仍使用当前账号Codex Tools。参考RGB不复制到成图，不用发丝亮度代替被遮挡衣料亮度推断颜色。

local v10保留原POLICY，在付费核实前自动规划不同的256像素原图上下文窗口，完整覆盖同一发丝物体的选中候选，包括混合边缘；最多6处、联合面积35%、单区修改上限0.5%源像素/15%区域及8像素边缘渐变均未扩大。每区最大可能改动量先检查，不能满足原预算即停止。候选按实际染色可见度和空间分布排列，仅单独展示列加编号；Codex必须独立核实源图、旧alpha和旧成图并返回evidenceWitnessId，后端解析精确源像素，避免模型自由坐标漂移。编号本身不证明归属。

降低发丝选区alpha仍需实际变色的真实衣料正点、原生衣料/非目标双实例、独立人体发丝标签及严格配对未变化证据。每区候选的原生衣料实例须保持；原真实衣料锚点、硬保护和ROI外选区保持；新源图复核及完整换色检查不可省略。缺参考、对齐失败或证据不足不启用该额外证据；原有有界matting路径和拒绝行为保留。自动候选不是代理手工标点或蒙版。

SAM2后端v3保留固定模型及环境，同时保留原生单候选及多候选的3个结果，形成4个原生候选，先核对全部原前景/背景点，再在有效候选中按模型分数排序。保存全部原生logits/分数/选中编号并与实际选区字节交叉验证，maskPixelsForced=0；没有合法候选仍停止。真实失败输入按原始机器点重放后，最高分但违反保护的候选被排除，其余合法原生候选自然满足全部点约束。该结果不证明商品质量，完整源图与成图检查仍必需。

local_hair_matte v3以严格未变发丝提供确定背景种子，原生衣料提供前景种子，在源图与配对参考的6维RGB特征上求闭式连续alpha，减少压缩差异/物理混合像素残留成灰点。未变像素RGB容差仍为3，没有将混合像素改称未变；只降低有双实例/语义支持的同一源发丝物体选区，不处理源RGB或复制参考RGB。3维既有求解与独立实现矩阵一致，新增压缩噪点和已知物理混合比例用例验证连续边缘，模型全图检查仍必需。

QA v6在原完整图/缩略图/6处细节之外，增加源图绑定的手部保护对照：原图、实际alpha、实际输出、RGBA绝对差值显示。已有语义标签只是候选，不能用数字零差异覆盖独立复核的false旗标；所有原POLICY、错误阻断、未知调用保护和一次纠正上限不变。原v5把未变化指甲误报染色的失败保留，v6只以新的原像素对照证据完整复核一次；复核前后成图文件SHA完全一致，没有重画或修改图片。



### 2026-11-23 官方模板实际生成与策划格式接续

独立图片引擎套图新请求冻结templateExecutionPolicy=official-artwork-v1。image_engine.py不再因服装detail/copy=[]自动改走原图裁切；默认逐图将真实原模板配图和完整原文送入Codex Tools，result.templateExecution记录实际提交证据。显式preserveSourcePixels仍保留原片合成用途，不冒称完整模板生图。apparel_suite.py的策划说明与此模式一致。

新模板生成的独立检查同时看真实模板配图并返回templateFollowed；泛化单张裁切丢弃指定版式不能通过，缺明确结论也不放行。事实/商品颜色/构造仍优先，不要求复制示例商品、宣称或品牌。自动纠正仍至多一次，旧成图和回执保留。

normalize_shots支持明确的scene.composition、detailCrops和x/y/width/height原坐标结构，不改坐标或商品事实，仍核对范围、来源、文本和图数。reusePlanTaskId只复用已完整返回且在图片提交前因已知字段格式失败的同款同意图策划；核对源Hash、模板、角色和完整brief，冻结父任务与原始策划Hash。未知/有pending/providerJobId/已有成图不适用，不能用此入口重复付费。test_template_execution.py包含真实失败策划、默认模板细节生成和不执行模板的阻断回归。


模板多分区本地校色的已知衣料边界冲突只停止该自动像素变换，原生图保留并执行相同的颜色/构造/模板独立检查；不是把冲突蒙版应用到图文卡片，也不授予质量通过。原独立换色功能及其门禁不变。reuseGeneratedTaskId限这一已知后处理失败，核对同一冻结意图、原提供方completed状态、原生图SHA、逐图原提示词及完整参考顺序后接续；已检查前缀保留，未检查原生图继续完整QA，剩余图位才新提交。原失败与提供方任务号均保留，不重发已完成的图片。已校验的原策划不重新解释默认textBox，接续仍由冻结服装合同核对图位、来源、模板和数据。


### 2026-11-23 按原生图种调用卖点排版

REA原服装type69的pointStyles仅绑定卖点图，选择N项同步N张；实测ins无layoutImageUrl，point匹配所选C63。前端仅提交id/style/imageUrl/materialSource/tabType，完整最终模型载荷属于服务端未知。工作台使用已核验原配图和完整公开模板提示词送入自己的Codex，是独立适配。

image_engine.py的新服装图种请求默认point-only-v1，apparel_suite.py按pointTemplateIds将真实模板逐个只绑定seller，不再轮转分给ins/model/white/size。选中模板数与seller数量必须一致；自然图种单独生成，无卖点图时不加载无关广告模板。所选人物与场景作为独立生图及复核参考，指定一致性失败继续阻断。旧冻结任务不回写；显式layoutTemplateIds保留自由模板创作扩展。A+为独立语义，未混入卖点计数或绕过正式七图合同。

ImageEngine/ApparelSettings/OfficialTemplates同步实际选中数量并锁定卖点数，其他图种独立，结果可查看真实对应模板、配图/完整原文提交状态和原QC提醒。默认允许模板图文；无文字仍由用户控制。源图锁定的自然场景允许无广告模板，不冒称完整模板重绘。test_point_template_routing覆盖图种隔离、数量/ID核验、自然摄影无模板、旧自由创作兼容及一致性复核；隔离检查和实际UI控件验证不代表新成图质量验收。


2026-11-24：服装候选新增显式 `apparelSuite.artDirection="template-led-v1"`，由 `apparel_art_direction.py` 提供原模板画面分析契约和模板优先渲染编译，实际入口 `image_engine.process` 调用 `image_engine_prompts.director_for`。逐图templateDesign必须绑定原模板ID并描述主体、配图、细节栏、文字层级和画幅适配；缺失或冲突先停止。无字只改文字层，原商品事实、颜色、流苏及独立质检不变。原片锁定与重新摄影策略分开，旧冻结请求默认原策略。当前账号模型、预算和方图配置不变；旧七图的尺码、关联及发布合同不变。界面“保留原模板整体版式（试用）”显式启用，不默认替换旧流程。风格字符串可无损放入style.photography；原样例保留。仅此已知未提交图片的格式失败可按冻结输入恢复，不重做策划，不恢复未知模型提交。实测与限制见逆向Linkfox/analysis/learn-linkfox-20261124。


2026-11-24 新商品回归后默认模板编排：独立图片引擎新建生成式服装候选套图默认 template-led-v1；界面按服装图种制作时默认勾选“保留原模板整体版式”，可显式关闭。原 requestId、策划/生成恢复继承冻结策略；未知提交不重发，原片锁定仍保留原策略。正式七图、尺码、SKU、换色、修图、模型、账号与预算合同不变。另一款真实浅粉立领绗缝外套 IMP-US-B0HQP3HWHK 的白底/场景/C63/C50 共4张一次完成，无自动纠正和手工修图；逐张原尺寸及300像素对照未见重大结构或颜色问题。轻微偏粉、头发遮挡与配图渐隐提醒保留，不宣称任意商品零返修。55项隔离检查、TypeScript/Vite通过。原图、实际原生输出、成图、来源Hash、回执与门槛见逆向Linkfox/analysis/new-product-gate-20261124。


2026-11-24 用户七图默认与尺码共用：图片创作台默认白底主图1、细节2、种草3、尺码1，图序白底→细节→种草→第7张尺码。新正式服装七图同样验证此组合；历史方案保持原规则。尺码使用当前档案有来源且覆盖全部拟售尺码的原始数值，本地确定性排版并独立复核，不让图片模型重抄数字。新候选以sizeRenderingPolicy=verified-typeset-v1冻结该路径，旧requestId/恢复任务不追改。整套本地换色在母版尺码位冻结sharedSizeChart源字节SHA，跳过分割/滤镜，复用同一文件和URL供全部颜色/尺码；选区编辑及独立像素换色禁止改该尺码位。来源、表格、构图、可读性及独立QA仍须通过，换色其他图位和SKU/发布规则不变。202项隔离检查和TypeScript/Vite通过；实际补图和回执见逆向Linkfox/analysis/seven-image-settings-20261124。


2026-11-24 用户要求种草也用原模板且展示不重复：新服装默认useLifestyleTemplates=true，可在图片创作台分别选细节/种草模板。lifestyleTemplateIds按不可变ID绑定每张ins的真实原配图和完整原文，默认C15/C17/C30等不同版式；白底和尺码仍独立。此为用户要求的Codex独立扩展，原生LinkFox type69 ins实测无layoutImageUrl，不能冒称取得其私有最终载荷。新请求lifestyleVarietyPolicy=distinct-template-presentation-v1要求逐图声明场景/成人形象/姿态/景别/构图/搭配，原商品图片只锁商品不锁原穿着者；不同模板ID不代替实际差异。单图原QA/一次纠正上限不变，整组实际成图还须逐对检查场景、人物和展示，任一false或漏图对均阻断，不循环整组重生。旧冻结任务不自动加此策略；原非模板ins保持原自然摄影行为。新正式七图方向与旧任意数量方向分开，避免相互冲突。209项隔离检查与TypeScript/Vite通过。原任务及新模板实测见逆向Linkfox/analysis/lifestyle-template-variety-20261124；旧相似场景留在seven-image-settings-20261124。


2026-11-24 种草实际整组失败后的编译修复：apparel_art_direction将完整lifestylePresentation送入真正的render prompt，并明确当前人物/搭配优先于模板示例人物。新任务冻结lifestylePromptPolicy=explicit-presentation-v1；旧requestId维持原策略签名。对已完成、单图通过但整组因人物重复失败且实际prompt可证明漏了该字段的旧版任务，apparelSuite.reuseLifestyleTaskId只复用同商品/源Hash/完整brief/模板/事实/参考角色的原策划和已完成提供方字节；由原失败图对自动选仍有一次额度的图位。保留其他原图及SHA，只重绘选中的图位；累计一次纠正额度跨父子任务，原失败和整组QA均保留；不重做策划，不接未知提交，修复后任务不得递归再用此入口。新图后仍执行完整单图及三图逐对独立检查，不按不同模板ID或文字策划自动通过。212项隔离检查通过。


2026-11-24 尺码图换版：核对240个已抓取原模板提示词及配图后，未找到专用服装尺码表；L61/A25是其他商品尺寸展示，不冒称官方服装尺码模板。新增我们自己的editorial-split-v1，参考服装杂志式标题/照片分区，大商品预览+清晰原数值表；classic-v1旧版可选。新候选默认新版，旧冻结chart无style仍沿旧版。支持sizePreviewTaskId绑定当前商品已完成、白底、独立QA通过的真实候选及SHA，仅作视觉预览，不作为尺寸事实。shared_size_chart继续从当前真实供应商表逐字排版，保留全部行列、单位和跨变体同一文件；不调用生图模型重抄数字。新样式经60项检查、TypeScript/Vite构建；同款实际成图与替换清单见逆向Linkfox/analysis/size-chart-redesign-20261124。

2026-11-24 尺码版式实际检查失败后的修复：editorial renderer v2执行左半大商品、右半暖白底标题与原表；sizeLayoutCompiler=layout-contract-v2将同一明确几何合同用于策划/渲染/检查。纯数据尺码任务直接建立确定性版式计划，不伪称AI分镜，也不重复调用策划模型；其他套图仍正常AI策划，尺码位保存原策划描述后绑定真实排版合同。原失败及相同数值保留，独立图像/数值检查不放宽。62项检查通过。


2026-11-24 用户明确允许生成式颜色变体：独立图片引擎repair可显式带generatedColourVariant。generated_colour_variant.py核对同账号/商品、已完成且独立过检的母版任务/结果SHA、真实目标照片和原模板配图/完整原文；不能从未知、失败母版或尺码图派生。实际入模为母版、目标实图、原模板（若有），准确颜色词由原copy记录替换。此路线是Codex生成式编辑，明确不保证选区外像素逐字节保持，不能冒充原GPU换色；默认旧流程及全部旧请求不变。独立QA同时对照实际输出、母版、目标实图及原模板，身份、同款、目标色、材质、全部重复衣料、保护内容、构图、文字、模板等必需flag逐项为true且无issues才可通过。仍最多一次自动纠正；未知不重发、原失败/原生输出/回执保留，不自动替换正式图库或发布。共用尺码图继续同一文件。实测与隔离检查见逆向Linkfox/analysis/all-colours-gallery-20261124。


### 2026-11-24 商品作图流程整理
- 主入口 `visual-ui/ImageWorkflow.tsx`、`ImageEngine.tsx`：首色套图 → 颜色变体 → 检查保存；智能修图独立标签。保留默认白底1/细节2/种草3/共用尺码1，细节与种草按原模板配图及原文制作。
- `GeneratedColourVariant.tsx` 复用已有生成式颜色变体后端：已过检母版、同款真实色样、原模板和原质检；原请求持久保存在当前页面会话，未知状态不改请求ID、不重新创建。刷新只查询。
- `image_workflow_sources.py` 为 GET `/api/image-engine/sources` 提供当前账号、同产品已完成并过检的母版列表，核对当前文件哈希、模板提交凭证，排除尺码图和失败任务。不触发生成、不写产品记录。
- 旧商品分镜改为折叠历史，只读保留成图；旧母版换色/SKU关联、精确像素工具均可显式展开。A+保留独立兼容编辑器 `LegacyVisualStep.tsx`。未删除任务、原图、提示词、回执、正式图库、SKU关联或后端兼容API，未修改质检门槛及发布权限。


### 2026-11-24 自动化入口与接续整理
- 当前总览位于 `../automation/工作台自动化入口与接续.txt`；以原生任务为准，旧CLI台账、网页任务中心及Codex循环不是同一个调度服务。新版图片候选到正式图库/SKU的通用交接尚待实现，不以候选completed自动放行导出或ERP。
- `agent_image_preparation.inventory` 纳入同账号同产品 `image_engine.sqlite3/tasks` 与 `image_tools.sqlite3/tasks` 的只读历史；后者无product_id列，逐条按productId过滤。进行中、未知、中断以及failed但含未知模型意图/unverified结果均阻断；不导入执行器、不轮询模型、不写数据库。完成历史不授权正式图、预算或发布。
- 检查：`python -X utf8 -m unittest test_agent_image_preparation test_agent_handoff test_agent_center test_agent_api`，以及上级automation流程回归。维护保留原循环暂停、任务状态、图片、预算和权限。


### 2026-11-24 店铺轮转任务配置弹窗
- `store-rotation-setup.js` 在任务中心提供“启动任务 · 配置店铺”：有序多店、紫鸟名称、ERP登录名称、美国/英国ERP店铺名称，默认每店每轮3款新商品；支持仅美国、增删及调整顺序。
- `store_rotation_setup.py` 及 GET/POST `/api/agent/rotation-setup` 保存当前账号的名称映射及不可变版本，支持requestId幂等、配置版本冲突检查和按setupId读取旧版本。只保存待核对名称，不写正式ERP目标/production-loop，不创建模型、浏览器、Codex或发布任务。
- 保存后生成可复制/下载的Codex接续说明；publishAuthorized/codexStarted保持false。前端请求固定账号Header，晚到响应不跨账号或导航显示；未知保存沿原requestId核对。配置不是已登录、已绑定、预算或发布授权。
- 入口由index.html加载独立JS，server.py仅路由和鉴权。检查：test_store_rotation_setup、任务中心/API回归、现有JS回归及实际弹窗核对。


### 2026-11-24 原图入口关联颜色变体
- `visual-ui/SourceColourPicker.tsx` 在图片引擎原图上传前列出本商品已记录颜色，直接选择已有同色图，可切换已关联参考图；上传新图时清除旧颜色关联，选图/上传均清除旧选区。被排除或无图颜色不可直接使用。
- `image_source_variants.py` 提供 GET `/api/image-engine/variants`（只读）和 POST `/api/image-engine/prepare-variant-source`（仅验证关联并缓存参考原图，不生图）。优先同款变体主图；远程图复用已有CDN白名单下载器，缓存原始来源SHA与本地实际文件SHA。
- 新请求 `sourceVariant:{receiptId}` 经当前账号、产品、颜色、原参考和子SKU集合及文件哈希校验，冻结进原任务request，套图规划接收本次来源颜色。记录仅为作图来源，不改变母版、供货、SKU配图、质检或发布权限；旧请求字段缺省保持兼容。
- 原请求与历史任务不修改；lossless转换仅在实际像素相同时保留关联。组件在产品切换/卸载后忽略旧请求返回。检查：test_image_source_variants、test_image_engine、test_image_engine_integration及visual-ui构建。
