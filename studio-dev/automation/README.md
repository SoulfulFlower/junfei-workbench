## 2026-11-15 选品直接进入产品档案

工作台已取消独立产品库、共享和认领。循环选品核验通过后直接通过当前登录账号的 `/api/discovery/promote` 建立或关联产品档案，使用 `/products` 继续研究、Listing、图片与ERP交接；不调用共享库add/claim。原有产品已经在档案中，不重复复制或重新导入。按账号、站点和ASIN排重，保留货源、竞品与CLI来源关联及已有文案、图片。旧 `/library` 地址转到产品档案；历史存储和兼容接口不作为新的共享入口。本条优先于下文旧产品库/认领相关描述。

## 2026-11-13 默认发布顺序：美国发布中即可接续英国

默认规则为美国站取得真实发布任务号且进入发布中（accepted/publishing）→复制到对应英国站→重新打开核对英国目标、原父子SKU及颜色尺码/图序→核对GBP售价、适用品牌豁免和英国运输模板→英国发布。父SKU、全部子SKU保留美国精确字符串，不加后缀、不重编号；原生复制自动生成的新SKU须纠正并保存回读后才能发布。美国无需等待发布成功或全部在售；无回执、失败、未知结果不触发。已复制、已提交或未知结果先查原记录，不以新任务重建。

规则在config.json的publishing.cross_marketplace_followup，供以后新任务快照使用，本次不处理任何现有产品。英国定价按当款有效经营资料重算，不将美元数直接作为英镑，也不套用旧批次估价。正式发布入口已接至listing-workbench/publication_flow.py与junfei-publisher/ego-publication-workflow.mjs：交付页明确点击“发布美国并接续英国”后，由后台依次完成美国发布、英国登录核对、原生复制、英国准备及发布；一键采集仍只保存草稿。账号英国店铺/运输模板配置与本款erpDelivery.UK经营资料分开保存。未知发布、复制、保存均复用原任务回执只读对账，不自动再提交；任务中心可恢复。当前维护只做隔离测试与只读验收，真实ERP执行结果须另以实际任务号核实。

## 2026-11-07 SellerSprite详情卡缺日期时核验原始导出

插件登录失效先用其官方“同步网页端账号”恢复已有登录。详情卡仍不显示日期而“产品查询”表能显示时，可使用该表的“导出”保存原始XLSX（“导出明细”是历史销量入口，不作日期证据）。`sellersprite_date.py`只接受含官方Note来源说明、对应站点工作表、唯一准确ASIN行和明确上架时间的原件；验证文件SHA256、行号、日期转录和商品链接，禁止借父体或另一子体日期。批次spec可设置`date_export_file`，日期证据注明`sellersprite_extension_export`并保存原件及浏览器导出回执；不能伪装成详情卡DOM。近30天、排名、货源、利润及其它准入规则保持原有要求。新增自动校验已通过流程测试；不代表已选够或已刊登。

## 2026-11-07 选品与刊登使用独立EGO工作区

用户要求“单开1个工作区”后，选品使用TaskSpace2 `Amazon-selection30-20261107`，配置在`browser.task_bindings.selection`。命令为`py -3 -X utf8 automation/ego_browser.py run <新脚本.mjs> --binding selection --timeout 120`，恢复时`resume --binding selection`。指定绑定不存在或不完整时失败，不回退默认工作区。默认browser.task_space_id=4及刊登页面保留；选品不得接管/交还/关闭工作区4。旧选品标签原样保留，新页面不复制Cookie，验证仍交还选品工作区2。工作区隔离不等于独立系统窗口或独立登录账号；保持既有禁止原生全局键鼠的保护规则。

## 2026-11-06 紫鸟钧飞后台插件自动登录（用户明确）

先打开紫鸟对应店铺窗口中的亚马逊卖家后台，确认当前目标站点，再点击浏览器右上角“钧飞跨境”；亚马逊后台插件自动登录。不要绕到扩展管理页或独立插件登录页。检查自动登录结果后才进入EGO的钧飞ERP页面执行品牌同步、豁免及刊登。用户要求以后智能体自行控制完成，正常动作不再逐次交还；系统故障或必须人工处理的验证据实交还。2026-11-06本次“示例店铺”美国站插件登录由用户点击并确认，不能写成智能体点击验收成功。

用户2026-11-06确认当前提供的物流表有效，服装可以走服装专线。服装渠道候选保存在config.pricing.preferred_channels_by_product_type.apparel，非服装不套用服装线路；按实际包装重量与体积重取大匹配档位。来源表日期原样保留，其当前有效性来源记为本次用户确认，未确认的最低计费、进位及附加费仍留说明。开衫WYJ20261104131157用户已明确批准售价$32.45，服装线路比较不自动撤销该明确售价。

## 2026-11-06 当前选品与整款作图操作规则

2026-11-07 新增 AI 分镜门槛：使用图片工作台生成并保存当前产品完整 AI 分镜，核对并确认后从对应卡片或整套入口发起生图。后续返修与换色沿用分镜图位。服务端拦截没有可核验分镜的新增生图，旧任务仍可查询。

Listing 用工作台生成或改写。将当前站点真实关键词数据导入并勾选，五点优先采用真实月搜索量 500–8000 的相关词，同组先按购买率排序。回查最终文案中的实际落词。英文描述按 `listing-workbench/listing-generation-prompt.txt` 固定为产品小标题、逐行属性、包装行和两条 Notes。后端拒绝不符合结构的结果，已有草稿保留供修订。

全自动选品固定使用 `C:/Users/Administrator/.codex/skills/cyclic-product-discovery/SKILL.md` 循环选品技能，由 `amazon-full-pipeline` 总控调度：标题首句→Amazon搜索→商品→Seller→店铺商品列表→其他商品→新标题首句→下一轮搜索。先读取同行店铺池和全局排重表，再按当前config核验日期、品牌、同款任意卖家的数值排名、1688同款货源和成本利润；有利润才入围并采集到明确账号的产品库。候选发现不计作合格入围或实际入库。

图片顺序固定为：**先完成并选定首色整套母版→工作台“变体换色”完成其余可刊登颜色的整套图片→逐颜色逐图位检查→绑定同色实际尺码子SKU→整款审核及导出**。当前gallery_count为7，每色应有完整7张，整款总数为可刊登颜色数×gallery_count（包含首色）；4色即28张，不能只生成其他颜色主图或用异色附图补齐整款。变体换色依据真实颜色参考，保持商品结构、配件、纹理及印花；不适合换色的图位用对应实图或重新制作，无依据时保留阻断。无货源颜色尺码按既定规则剔除，原始采集与原因保留，不扩造组合、不将选项覆盖当库存。

提交前先核对账号、产品、母版、颜色、图位、预算及已有任务；结果未知先对账，不重发。全部拟刊登颜色套图的实际文件、尺寸、顺序、SKU映射及要求的审核状态通过后才导出，不冒充人工审核。本节更新操作规程，不代表新增或部署了无人值守执行器，不授权额外生图、发布或定时任务。

### 服装尺码图

1. 服装 AI 分镜必须预留尺码图。现行每色 7 张套图固定第 7 张，计入原有套图张数。
2. 优先采用供应商尺码表或实物测量。缺少胸围、衣长、袖长等款式适用数据时，先查已核实同款的竞品尺码图，记录站点、ASIN、原图、同款依据、尺码对应关系、单位及测量口径。确认同款且尺码对应一致的数值可用于审阅稿。正式使用前须核实数据适用于本批货源。只有相似款或尺码对应不上时，仅参考测量项目、示意和排版，数值留待核实。
3. 用核实后的数值逐项排版并校对。区分成衣平铺尺寸和建议人体尺寸，标明单位，覆盖全部拟刊登尺码并核对对应子SKU。各色尺寸一致可共用无颜色指向的尺码图，各色仍分别绑定第 7 图位。尺寸有差异时分别制作。
4. 正式导出及刊登前逐色检查尺码图、来源适用性和SKU映射。资料不足标记「待补尺码」，留在审阅阶段。

## 2026-11-06 用户恢复后的窗口保护

用户回复继续后恢复原TaskSpace4。实际核验：元数据读取和第7款工作台API入库没有唤起已最小化的EGO；不宣称独立系统窗口隔离已完成。只用专属Page，优先官方Page.cdp导航和DOM读写，不激活整个EGO应用、不发原生键鼠。停止点击1688货源插件跳转（疑似最近活动窗口目标，尚未确认原因）；在专属1688图片搜索Page内上传主图作为既有备用方法。用户恢复EGO用于工作或再次反馈干扰时立即停止。

## 2026-11-06 浏览器干扰再次发生，暂停页面操作

用户确认后台操作仍影响其窗口后，已交还TaskSpace4并停止脚本162。仅分工作区、CDP windowId及DOM后台交互不能证明隔离有效；不要自动接管或继续页面操作。先验证真正独立的专属窗口并取得用户继续指令。当前新增入库6/30，媒体采集不计为第7款入库。

## 2026-11-06 专属选品窗口补充

用户要求只用选品专属框，避免控制其正在使用的浏览器。当前仅操作 TaskSpace 4 `Amazon-cyclic30-20261106`；运行入口核对工作区 ID、名称与 agent 归属。EGO 的 CDP windowId 不证明独立系统窗口；不要操作用户空间0或对整个 EGO 应用发送原生鼠标键盘/缩窗输入。优先在指定 Page 内后台导航、DOM 交互和读取，验证码仍交还该专属空间。

> **2026-11-05 钧飞ERP刊登规则（用户确认）**：先用紫鸟CLI打开或复用对应店铺，完成店铺登录并确认站点，再在该紫鸟窗口打开钧飞插件并确认插件登录；以上登录优先完成后，切换到另一个浏览器EGO中的ERP编辑页，同步目标店铺品牌、选适用品牌并在ERP申请豁免，然后完善Listing，最后回查同一产品的ERP豁免状态，显示“允许销售”且其他检查通过、已有发布授权才发布。品牌不固定为Generic；Amazon来源商品的Generic选品规则不因此改变。两个浏览器分别保持登录，不复制Cookie。完整操作规范见 [总控技能](C:/Users/Administrator/.codex/skills/amazon-full-pipeline/SKILL.md)。历史Seller Central豁免证据不能代替ERP状态。本次为规程更新，不表示已修改或部署执行器、完成申请或发布。

<!-- current-user-guide-20261103 -->
> **2026-11-05 货源缺失变体按用户新指令剔除**：先完整采集；找不到货源的颜色和尺码不进入本次刊登，原始采集与排除原因保留。账号1实际保存修订242：绒面款45→25子款（5色、M–3XL），菱格款64→30子款（5色、S–3XL），保留全部原始45/64条供追溯；开衫16子款保留。两款剩余规格的货源选项覆盖及导出行数核对通过，不把选项覆盖写成库存保证。新增供应商详情参考图及本地原件证据，排除工厂宣传图和其他商品推荐图。棕色开衫平铺尺码已在修订241保存并重检资料项通过。采集插件v0.7.14三款真实详情读取15/7/17张，源码、员工包与登录下载ZIP一致；已安装插件未重载、EXE未重建。证据outputs/available-variants-save-20261105.json；无新增付费或发布。
> **2026-11-05 全部子体的货源选项覆盖检查（源码服务已部署）**：supplier_variants.py已接入任务中心事实阶段，以实际已采集子体逐条比较同一货源的可见颜色、尺码及有记录的具体组合。账号1有来源的资料已保存并回读revision240；实际三款准备检查确认：开衫16子体选项覆盖通过，绒面上衣45子体中20个、菱格开衫64子体中34个未覆盖。保留全部已采集子体，不扩造组合，不把选项匹配当库存。页面入口为第一步底部“已采集产品资料与准备清单”→“编辑资料与变体”；EGO已读取实际4色4码16组合表单，未保存或改人工审核。另将same_product_rank_policy纳入新任务策略快照，按用户指令允许候选自身或其他卖家的同款排名；无此策略的历史任务保持原限制。110项工作台Python、27项流程、9项表单JS检查通过。11个SQLite备份后重载源码服务PID36816；EXE未重建。图片/颜色生产表与部署前一致，4个未知外部记录保留，无新增付费或发布。证据outputs/supplier-variant-coverage-deployment-20261105.json；准备检查不代表产品完成或上架。
> **2026-11-05 开衫刊登属性复核**：ERP草稿172581550中发现残留的90% Acrylic/10% Polyester、500g、30×40×10cm与已采集货源不符。已按原始货源证据修正为Acrylic（不宣称比例）、450g、45×30×3cm，补长袖和单件数量，并选择本次指定Migrated Template；保存成功后重开逐字段核对，16个子款和28张图库保留，未发布。证据 outputs/brown-erp-source-field-correction-20261105.json。后续每款都须把ERP实际属性与该款货源逐项对照，不能把ERP预填值或推荐模板当成本品事实；材质百分比、包装尺寸/重量和件数尤其需核对。当前仍缺人工文案/图片审核及正式物流费用依据，不因豁免“允许销售”直接发布。
> **2026-11-05 四色套图完成并保存草稿**：账号1开衫 IMP-US-B0HQ6T361R / WYJ20261104131157 复用已选7张Brown母版，经工作台换色完成Camel、Light Pink、Yellow各7张，合计28张2048×2048图片。问题图保留历史，定点重做或本地修正后重新视觉检查；三色均为awaiting_manual，未冒充人工审核。钧飞草稿172581550在示例店铺-美国、KIMEETOL下保存成功，并重开逐一核对16个子款的主图及7张顺序。未发布、未记在售。实际工作台导出ZIP验证28张、16条已采集子体映射，缺图/排除项为空。用户单独批准此款生图预算¥8，配置以产品ID覆盖，其他产品仍¥5；38笔按美元日汇率加缓冲预留合计¥4.94，未结算。Camel供应商SKU预览标有AI生成，仅作颜色指南，仍需实物对色。证据 outputs/brown-four-colours-saved-gallery-readback-20261105.json、outputs/brown-four-colour-delivery-verification-20261105.json、outputs/brown-four-colour-workbench-view-20261105.json。图片包 outputs/WYJ20261104131157-four-colours-delivery-20261105.zip。工作台相关检查与27项流程测试通过；源码服务已重载，未重建EXE，其他两款历史未知生图提交未重提。
> **2026-11-05 APIMart实测成功**：用户更新密钥后，账号1认证200；使用真实供应商棕色开衫参考图首次提交Brown-白底主图，任务task_01M6MMWCSBBKQSYJA0M0MXPTN3实际完成并保存2048×2048成图。服务响应cost=0.015原样保留；当日报价$0.015/2K图及中行美元卖出价6.6924，含20%缓冲预留¥0.13，不代表人民币账单结算。已修复顶部成图统计遗漏独立API任务的问题，EGO确认显示1张且图片加载2048×2048。该图仍为待最终审核候选，未完成整套图或新品刊登。旧Codex Tools未知提交保留，未重提。证据 outputs/apimart-brown-test-result-20261105.json；成图 outputs/apimart-api-test-20261105/Brown-main.png。JS检查及27项流程测试通过。
> **2026-11-05 切回APIMart（历史切换检查）**：按用户最新指令，账号1工作台生图服务切为APIMart，并停用config中Codex Tools订阅模式。切换时旧密钥曾返回401；后续用户更新密钥的成功实测见上一条。证据 outputs/workbench-return-apimart-20261105.json。
> **2026-11-05 09:07 根因补充**：仅用缺少所有生图参数的空请求验证，不触发图片生成。已复现Python-urllib/3.12标识被原样转发后返回403 HTML、Cloudflare错误1010；反代将其笼统归为权限不足。不能据此判定账号没有生图权限。正式生产仍受阻，未伪装客户端或绕过防护，需使用上游支持的客户端或正式图片API渠道。证据 outputs/codex-tools-1010-diagnosis-20261105.json。
> **2026-11-05 生图故障定位**：Codex Tools 错误现已脱敏持久保存并关联提交，当前视觉套图页面可展开“生图提交待核对”查看；未知提交不再显示为生成中或持续轮询。绿色菱格开衫首张主图实测仍被反代返回502，明确原因为“1个账号全部被上游拒绝，权限不足1个”，上游内容为HTML。该分类不能证明具体账号缺少权限；CLI登录和用量查询正常，尚待区分生图权限和网络防护。错误397554308a5744a08050446f116befb7已保存，无成图、无新品刊登。11库备份重载后原表哈希一致，未重提旧请求。证据 outputs/image-diagnostics-deploy-20261105.json、outputs/codex-tools-green-result-20261105.json。
> **2026-11-04 21:50 Codex Tools 图片接口**：用户明确改用本机反代，账号1已配置 `http://127.0.0.1:8787/v1`、gpt-image-2、edits、medium；真实模型认证200。本机例外仅限固定地址，不放宽其他内网或图片下载。新增订阅请求独立台账，须核对反代池全部为ChatGPT订阅账号，不记零元或已结算；其他付费接口预算不变。190项工作台、27项流程及JS检查通过，11库备份后重载原表哈希一致。12张已恢复供应商原图及三款Generic豁免证据已合并到产品库，修订233。Burgundy参考图编辑实测反代502，未返回图片；提交0865bc83f8d8475da919efb79401f275保留unknown，禁止重提。待核对Codex Tools最近错误；尚未新品刊登。证据 outputs/codex-tools-image-integration-20261104.json。
> **2026-11-04 17:55 图片采集补充检查**：插件源码与员工接入包已同步到v0.7.13，实际加载成功且尺寸更大才采用1688原图；导入器保留缩略图来源、尺寸及失败记录。150项相关检查通过，另通过JS语法检查。此补充尚未重载运行中服务及已安装插件，未做浏览器采集实测。EGO工作区5仍交由用户填写图片接口配置；未新增付费生图、ERP提交或产品库修改。证据 outputs/supplier-image-capture-checkpoint-20261104.json。
> **2026-11-04 17:10 生图接口与浏览器配置**：用户批准失效工作区4后新建专用 EGO 工作区5 `Workbench-image-interface-20261104`，工作台 p1；已更新 config.json，旧标签不复用。当前本地 Python 工作台端口18765已加载 OpenAI兼容图片适配：按账号配置地址/模型/密钥/协议/质量，沿用 IvyeaOps 提示词编译、预算预留及未知提交防重发。159项工作台、27项流程检查及JS语法通过；11库在线备份，重载前后数据逐表哈希一致，两条历史 submit_unknown 保留。审计见 listing-workbench/docs/IVYEA-IMAGE-AUDIT-20261104.md；部署证据 outputs/openai-image-deployment-20261104-round2.json。当前账号新接口尚缺有效密钥及对应报价，未新增付费生图或新品刊登；当前 Python 实例更新不代表旧EXE发行包更新。
> **2026-11-04 最新选品补充**：使用 cyclic-product-discovery 技能；先搜索标题首句，同款任意卖家的商品有数值销售排名即可找货源，不再限定必须其他卖家或候选自身ASIN有排名，无排名高低门槛。优先点击Amazon增强面板的“1688货源”，跟踪实际异步标签，按公开销量优先核实同款目标规格；按config.json报价公式核算，有利润才入围并采集入当前账号产品库。关键成本缺失不得先入库凑数。技能、总控路由、配置及CLI校验源码已同步；旧任务保留快照，未重新打包或重启运行EXE，不声称桌面版校验已更新。
> **2026-11-03 15:28 当前生效规则**：近30天上架（卖家精灵商品上架日期）、Amazon品牌明确Generic、不查专利（记未检索）。已重新打包并切换EXE至 `D:/AmazonAgentReleases/20261103-generic-30days/AmazonAgent/AmazonAgent.exe`，桌面快捷方式同步。24项流水线、92项选品/任务/API及包内规则、隔离EXE导出/定价/账号隔离检查通过；9库已备份，生产数据及刊登回执哈希未变。新建任务采用新规则；旧任务保留快照，重检需留历史。下方7天及EXE未更新的描述为历史记录。证据：`automation/data/generic-30days-deployment-20261103.json`。
> **2026-11-03 15:05 最新选品规则**：只选Amazon商品页品牌明确为Generic的产品；按用户指令不查外观/实用专利，证据明确记“未检索”，不得记为无专利或检索通过。配置与CLI／网页校验源码已更新，23项流水线、91项选品及任务中心/API测试通过；当前EXE尚未重新打包，不能宣称运行EXE已采用新校验器。原椅套B0G6Z1FHFQ及长枕套B0H87695G1因非Generic退出两款新品批次，CLI保留blocked及来源。椅套指定$12.65仅留该款记录。ego工作区11卖家精灵登录失效，已交还用户登录；不得在用户确认前接管。

> **当前使用说明（2026-11-03）**：[项目总结与使用说明](../listing-workbench/docs/项目总结与使用说明.md)。当前桌面快捷方式指向 `D:/AmazonAgentReleases/20261103-patent-policy/AmazonAgent/AmazonAgent.exe`。编织包父SKU `MTkzMzU-ZKNOPITD` 已按用户“发布中即交付”标准完成，最后核对13:49，尚未验证Amazon在售；已归档至 `D:/桌面/潘总写的产品/MTkzMzU-ZKNOPITD`。以下是各阶段历史记录，旧发行路径及“未接入／失败”描述须结合时间阅读。当前由工作台与Codex+ego脚本协作执行，不能视为EXE全链无人值守。

2026-11-03 编织包发布修正：原发布任务14928651返回99022。实际读取钧飞公开前端保存序列化代码，非空默认单位会携带空数值同组提交；已通过UI清空capacity、item_package_weight、item_package_dimensions全部单位，保存并重开确认三组全空，实际json-update请求不再包含三组属性。未虚构容量/包装尺寸/包装毛重。原任务已第二次提交，当前发布中，未核实在售；禁止第三次自动提交，先核对真实结果。原失败记录保留，工作台账号1已同步第二次处理中。证据automation/data/woven-empty-attribute-amendment-20261103.json、woven-republish-operation-20261103.json。22项流水线回归通过。

2026-11-03 尺寸匹配修复已打包部署：当前运行D:/AmazonAgentReleases/20261103-dimension-match/AmazonAgent/AmazonAgent.exe，桌面“亚马逊智能体工作台”指向此版本。8库已备份；切换前后产品、任务、生图与费用/提交记录逐表哈希不变，原ERP两次台账SHA不变。包内尺寸回归及隔离EXE七图导出、报价重算、跨账号拒绝检查通过。证据automation/data/dimension-match-deployment-20261103.json。无新增付费/ERP写入，ego仍交还用户登录。

2026-11-03 尺寸匹配修复：agent_sourcing.py原先把50×100cm与60×100cm、150×100cm误记为尺寸属性匹配；现解析共享单位的所有轴，以计数比较尺寸并支持英寸换算，结构化详情冲突优先于标题。新增错误轴、数字片段、正方形、等值单位和原9×25in与50×100cm不匹配的回归测试。92项货源/任务中心/API、21项流水线测试通过。只影响候选匹配信号，不改变销量优先规则、不把匹配分数当同款认证、不修改已有产品或选品状态。当前ego工作区10已交还用户登录SellerSprite，未收到完成回复；第三次ERP诊断保存确认仍待回复。无新增付费或ERP操作。

2026-11-03 进度显示修正：agent-center.js对selection.skipped的既有产品显示“货源资料（选品未执行）”，详情明确不计为新入选，不改变任务结果。71项任务中心/API、21项流水线测试及JS语法检查通过。仅备份并更新当前quote-pricing发行版的静态资源，未重打包EXE、未重启或写数据库；ego账号1真实刷新已核对标签。证据automation/data/selection-label-static-deployment-20261103.json。ERP原SKU两次保存上限保持不变，额外诊断保存仍待用户回复。

2026-11-03 最新部署：`D:/AmazonAgentReleases/20261103-quote-pricing/AmazonAgent/AmazonAgent.exe`。quote_pricing.py按config汇率6.8、佣金15%、成本加价50%、体积系数8000，选配置内普货渠道及实际重量档位，以Decimal向上取美分；原JS和prepare_product固定公式已停用，缺价不再回退。报价JSON随EXE打包。草稿基础情景明确排除未确认附加费/其他费用，保留报价日期、源文件SHA、源行、包装依据及警告，不是最终价格；JS发布拒绝draft_estimate_only依据。网页任务展示草稿估价表。100项相关测试、6项Node定价测试、21项流水线及隔离EXE七图导出/实际报价/本地重算/账号隔离测试通过，8库备份并切换，资料/任务/10条生图记录一致。

原生产任务4e3684d3e4cc43bdbac2ce2f4b64bb74通过新增refresh-preflight受限入口重算本地计划：只允许blocked、draft且明确未绑定未操作ERP，原快照须一致；先归档旧计划并关闭下载，再重算，不调用ERP、不清零SKU次数、不新建任务。旧$34.08计划保留于preflight-history；当前顺丰CD报价第9行，日期2023-06-26，975g/90×8×8cm基础运费104.0625元，草稿估价$31.06。已真实UI展开核对。报价有效期、渠道尺寸限制、折叠尺寸和额外费用仍未证实；不得宣称最终售价或利润。原SKU两次422台账SHA未变，无新增付费、ERP上传、保存或发布。仍缺新品ERP绑定，422具体后端原因未证实；只读前端源码确认store提交form/suppliers/images/items而无前端rules，不能据此宣称已修复422。证据data/quote-pricing-deployment-20261103.json、quote-pricing-live-refresh-20261103.json、quote-pricing-ui-20261103.json。下文为历史记录。

2026-11-03 最新部署：`D:/AmazonAgentReleases/20261103-agent-draft-review-owner/AmazonAgent/AmazonAgent.exe`。新增独立智能体草稿审核记录，绑定当前账号、整款资料、文案和逐图源SHA256；内容/顺序/账号变更失效，不能用于发布或冒充人工审核。真实发现管理员主进程WORKER_USER=0不等于账号ID，已改按account_spaces.legacy_owner解析并增加回归。94项相关测试、21项流水线和隔离EXE检查通过，8库备份后部署，资料和任务不变。账号1独立备选WYJ20261102142256已补Clear颜色映射、原图SHA及实际审核记录；原检查任务四项检查通过，生产任务4e3684d3e4cc43bdbac2ce2f4b64bb74实际生成交付ZIP和本地格式计划，因无ERP绑定停止，未操作ERP。实测发现该本地计划仍由旧运费公式产生$34.08，不能作为已核实售价；须接入config报价定价并重新预检，不能将格式绿色结果当作经营数据正确。原SKU两次422上限不变，无新增付费或ERP写入，独立备选不是自动选品成功。证据：`data/agent-draft-review-owner-deployment-20261103.json`、`data/agent-draft-review-owner-recheck-20261103.json`、`data/reviewed-production-result-20261103.json`。下文为历史记录。

2026-11-03 图片兼容部署：运行 `D:/AmazonAgentReleases/20261103-erp-image-size/AmazonAgent/AmazonAgent.exe`。生成套图导出保持小于5MiB的原文件；达到限制则在原尺寸下转换高质量JPEG，透明区域合成白底，记录原始/交付SHA256、字节数及转换参数。转换后仍超限则拒绝导出，不更改审核标记。82项图片导出/任务/API测试、21项流水线回归和隔离EXE大图导出/跨账号拒绝测试通过；切换前备份8库，刷新后产品/任务/10条图片任务一致。账号1独立备选WYJ20261102142256已通过工作台真实导出7图（4图转换），全部2048×2048且小于5MiB，原图来源哈希、图序和文案核对一致；未新增付费、ERP上传或保存。证据：`data/erp-image-size-deployment-20261103.json`、`data/erp-image-size-postdeploy-20261103.json`、`data/erp-image-size-live-export-20261103.json`。文案与图片审核仍待衔接，原SKU两次422保存限制不变，未完成新品草稿或发布。

2026-11-03 用户最新货源规则（优先于下文历史确认要求）：按公开页面销量优先选择供应商；供应商页面已提供的信息、图片默认采用，不再逐家询问或等待额外确认。保留销量原文及口径（已售、全网销量不可混为同一指标）、来源网址及对应规格。未提供的数据留空，不编造重量、报价或认证，不将其他规格价格套用目标规格；图片使用依据仍为用户默认采用，不伪称供应商授权。此规则已通过20261103-source-default部署进入实际候选排序和采用入口；默认采用记录不伪造六项人工检查，保留来源和授权。当前同日后续图片兼容发行包含此功能；旧任务必须明确重检后才使用新规则，不自动记为通过。

2026-11-02 最新部署：产品库整包桥接已接入并切换至 `D:/AmazonAgentReleases/20261102-library-package-bridge/AmazonAgent/AmazonAgent.exe`。任务中心新增“ego产品库文案与套图整包保存”能力，须明确当前账号/产品/店铺/US站/ego页面绑定，全部生产前置检查、文案及图片审核通过，并使用产品已明确保存的美元售价。原导出ZIP的变体、图序和文件字节必须一致；持久回执先于打开新表单，已有SKU记录或未知结果拒绝重发。产品库保存后仍返回未完成状态，不冒充目标店铺草稿或在售。当前没有新增产品库绑定，SKU WYJ20261102142256 保留两次失败上限，不第三次提交。

84项任务中心/API/产品库/ERP测试、57项ERP组件测试、21项流水线回归及隔离EXE检查通过。切换前备份8个SQLite数据库；真实ego刷新后核对账号1、原产品资料SHA256、10条图片任务及全部任务状态一致，新能力可读取。生图已按用户授权启用，每款¥5/每日¥200，当日中行美元卖出价加20%缓冲；已有10次生成合计预留¥1.20，实际账单未结算。本次桥接部署新增付费/ERP上传/ERP保存均0，商品仍待审核，完整流程未完成。证据：`automation/data/library-bridge-deployment-20261102.json`、`automation/data/library-bridge-postdeploy-20261102.json`。下文为较早阶段记录，未接入EXE的描述仅适用于当时版本。

2026-11-02 整包保存源码已衔接：saveLibraryPackage复用既有产品库保存观察与422回执，保存前独立核对原文案/价格/变体及同账号整包身份，再逐变体打开图片选择器读取完整顺序并取消关闭；保存后重开重复上述检查。父表只显示首图，不再以首图代表全部图片。提交前写总回执；超时、422、重开后字段变化保留unknown，不重发；成功仅表示产品库保存回读一致，不表示店铺草稿或在售。57项ERP组件测试覆盖模拟保存成功、隐藏图片变化、跨账号、磁盘失败、超时、重开价格变化和422错误保存，21项流程回归通过。本轮真实上传/保存/付费均0，未接入EXE；商品审核及原SKU两次上限不变。证据automation/data/library-package-save-source-20261102.json。

2026-11-02 新增产品库整包准备组件 `junfei-publisher/ego-library-package.mjs`：把文案/价格/变体、图片上传和逐变体配图组织为同一持久回执。入口冻结输入、校验所有变体映射、拒绝校准图及未审核商品图；子操作创建和每次写入必须先写总回执，上传超时保留原图片意图并进入 requires_reconciliation，不自动重传。最终核对父SKU/文案/经营字段、图库顺序、逐变体账号及完整配图回执。ledger.create 必须拒绝既有操作，不得绕过两次尝试限制。新增5项测试含完整组合执行、上传超时及同回执重入拒绝；连同既有组件57项通过。此为源码组合准备器，不打开新表单、不保存产品、不发布，尚未接入EXE；商品图仍待审核，原SKU仍禁止第三次提交。以下是真实UI校准历史。

2026-11-02 ERP产品库图片传输与变体配图已真实校准：新增ego-library-images.mjs，只接收明确父SKU及空图库；上传前持久记录意图，检查单图小于5MB、尺寸/用途/源SHA256，服务器下载逐字节回读，不明结果不重传。变体选择器按真实“＋”添加，等待异步缩略图就绪；确认仅提交本地选择器，重新打开检查完整顺序，不点击产品保存。实测仅上传一张1600×1600原创校准图，SHA256一致，绑定一个未保存变体并重开验证，最后取消丢弃整个产品表单；新增产品保存请求0，原SKU两次台账SHA256未变。校准回执合并曾残留pending字段，经真实页面和远端SHA对账后保留历史并清除；源码改为显式null，未重复上传。服务器校准文件仍存在，不宣称已删除。证据automation/data/library-image-ui-calibration-20261102.json及library-image-binding-calibration-20261102.json。52项ERP测试通过；此为ego脚本组件，尚未接入EXE新品生产工具或完成商品七图保存，422原因仍未证实，未发布。

2026-11-02 ERP价格/变体适配进展：ego-library-draft.mjs新增可选commerce（USD父价格、子SKU/颜色/尺寸/价格及依据），按真实表头和列位置填写；保存前及重开后断言这些值，其他物流字段和图片保持不变。发现同路由goto保留已打开表单，新增可见对话框拦截，避免重复点击添加。真实UI校准已用明确的合成测试金额1.23填写父价和一行变体并回读，随后取消丢弃；1.23不是售价，未写工作台产品或经营配置，原保存台账SHA256未变、原SKU仍两次上限。首次校准在填写前被旧空表单拦截，核实空表单后在同一校准回执继续，无保存重试。证据automation/data/library-commerce-ui-calibration-20261102.json。41项ERP适配测试、21项流程测试通过。该模块仍由ego脚本调用，未接入EXE生产创建工具；图片上传/变体配图、真实售价、ERP新品保存和店铺草稿创建尚未完成，不能称为全流程已跑通。

2026-11-02 任务中心已接通生成图片选择检查：复用导出的账号/产品/任务状态/顺序及视觉方案校验，只读元数据，不下载或重新生图。显式选择无效时不回退旧母版，旧换色集不再冒充覆盖；所选图片仍待审核。真实账号1原检查任务重检后显示“已选生成套图：7张，待审核”，逐项与保存的导出顺序一致，产品、原候选及审核标记未变。81项相关测试、21项流程回归和隔离EXE导出/检查/账号隔离冒烟通过；8库备份后切换至D:/AmazonAgentReleases/20261102-generated-gallery-inspection/AmazonAgent/AmazonAgent.exe，PID35516。证据data/gallery-inspection-live-20261102.json、gallery-inspection-deployment-20261102.json。ERP只读空表单无必填标记且无变体；当前文本适配器未填价格、图片、变体，422原响应未保留，具体原因仍未证实，原SKU保持两次上限。证据data/library-422-readonly-diagnosis-20261102.json。本轮新增付费和ERP保存均0，未发布。

2026-11-02 工作台原生七图导出已实测：新增generated_gallery.py及交付/视觉页的“生成图片导出顺序”。明确选择当前账号、同产品的已完成image_provider任务；按顺序导出，校验单帧格式、最短边配置和可选SHA256，缓存原结果，不重新生图。视觉母版更换后拒绝沿用旧选择；选择生成任务后不混入未重新绑定的旧换色集；图片始终awaiting_manual、humanReviewed=false。新版D:/AmazonAgentReleases/20261102-generated-gallery-export/AmazonAgent/AmazonAgent.exe，PID56680，切换前8库备份；78项导出/任务/API、21项流程回归及双账号隔离EXE冒烟通过。账号1在真实界面保存7图顺序、点击原ZIP按钮，实际产物outputs/chizhe-952542058876-50x100/WYJ20261102142256-workbench-export.zip已逐图核对2048×2048、顺序、SHA256和保存文案；原候选及人工审核状态未变。证据data/gallery-export-live-verification-20261102.json、gallery-export-deployment-20261102.json。新增付费调用0、ERP写入0；422原因仍未证实，未第三次提交。以下“标准导出尚未衔接”为较早状态。

2026-11-02 七图审核资料已形成：账号1独立备选1688-952542058876-CLEAR-15-50X100共10次生成（含3张原构图不符后的各一次返工），全部结果已核查，选取7张2048×2048图片，保存当前账号素材并刷新回读验证SHA256。预算10笔合计预留¥1.20，实际人民币费用未结算。预览及独立审核ZIP在outputs/chizhe-952542058876-50x100/gallery-review.html和WYJ20261102142256-review-bundle.zip；ZIP逐图哈希校验通过。七图是审核候选，非实物一致性保证，未将humanReviewed/productionApproved写为true。标准delivery_export尚不消费这些image_provider任务/素材，不能把独立包称为工作台完整导出。ERP新品仍为两次422后停止，未第三次保存、未发布。证据data/chizhe-gallery-workspace-save-20261102.json、chizhe-gallery-revisions-20261102.json、chizhe-gallery-budget-20261102.json。21项流程回归通过。以下较早首张图记录为历史进展。

2026-11-02 生图已按用户最新确认启用：每款¥5、每日¥200，当天中行美元现汇卖出价加20%缓冲、向上取整到分。已修复APIMart gpt-image-2遗漏resolution参数（当前官方文档为比例size及小写1k/2k/4k），部署D:/AmazonAgentReleases/20261102-image2-resolution/AmazonAgent/AmazonAgent.exe；95项图片/预算/任务接口、21项流程测试与隔离EXE冒烟通过，切换前8库备份。账号1独立备选1688-952542058876-CLEAR-15-50X100首次真实付费辅助图任务task_01M6DHRFQWMMB330W6YWG4ZTDR已完成并下载，2048×2048；保留¥0.12费用预留，服务响应cost=0.015仅原样记录，人民币实际费用尚未账单结算。不是主图/完整七图，不代表选品通过或ERP成功。本次未操作ERP。证据data/chizhe-first-paid-image-20261102.json、chizhe-first-paid-image-poll-20261102.json、chizhe-paid-image-workspace-save-20261102.json。以下历史“生图关闭/未付费”以本记录为准。

2026-11-02 最新确认：供应商页面图片默认可用，无需等待图片授权。旧任务中的“授权仍未补齐”仅为历史记录，不作为新增授权要求；任务采用新策略重检时保留历史，不伪造商家许可。实际核图、商品匹配与其他事实检查继续执行。

2026-11-02 本地选品台账核对已部署至D:/AmazonAgentReleases/20261102-local-ledger/AmazonAgent/AmazonAgent.exe。网页dailyQuotaSource支持captureType=local_selection_ledger，包含ledgerPath、sha256、checkedAt；服务端只读取config.json指定的项目内CSV，重算哈希、跨批次ASIN重复及中国时区同店当日数量。文件改变、日期过期、当日记录缺Seller ID、配额已满或不完整记录均拒绝本地证据。该核对只读，不预留配额、不写正式入选表，后续正式入选仍需持久写入。原网页来源证据路径保留，不自动升级为已核实。

账号1产品IMP-US-B0HKJ1WKT2真实重检已不再缺台账或描述词商标检查，仍因brand、designPatent、utilityPatent、imageRights阻断。USPTO商标字段查询CM:("TABLE PROTECTOR" OR "DESK MAT" OR "CLEAR PVC")返回3个DEAD记录；此结论仅限所查描述词，不是供应商品牌授权或法律保证。官方专利检索tablecloth AND PVC返回会话限流，没有专利结果，保留needs-data。供应商询价只收到问候，没有规格/报价/毛重或图片授权，未重发。84项任务/接口/选品测试、20项流程回归及隔离EXE冒烟通过，8个SQLite已备份，未付费生图/下单/修改ERP。证据automation/data/local-ledger-deployment-20261102.json、pvc-ip-ledger-gate-live-20261102.json、pvc-trademark-phrases-20261102.json、pvc-patent-search-limited-20261102.json。

2026-11-02 同款排名结构化证据已部署：仅接受实际匹配ASIN的SellerSprite MCP asin_detail原始JSON，严格核对asin、整数bsrRank及固定HTTPS端点，拒绝带凭据/查询参数、异常端口及排名不一致的证据。账号1桌垫IMP-US-B0HKJ1WKT2已真实重检：商品日期2026-10-29、中国FBM、前台其他卖家strong同款B0GWXSFRV8及其排名525729不再缺失；IP/素材和台账核对仍阻断，不等于选品通过。ego搜索框原生粘贴图片已实测，1688在原标签页显示结果，5条未核验货源观察保存到该产品。山东巨丰684168261363询价经用户明确批准后只发送一次，聊天显示已读并回复问候，目标规格/报价/毛重/权利仍待答复；不得重复发送。历史发行D:/AmazonAgentReleases/20261102-matched-mcp-rank/AmazonAgent/AmazonAgent.exe，8个SQLite已备份；82项任务/接口/选品测试、20项流程回归、隔离EXE冒烟通过。证据data/matched-mcp-rank-deployment-20261102.json、data/pvc-matched-rank-gate-live-20261102.json、data/pvc-supplier-observations-live-20261102.json及data/supplier-send-684168261363-20261102.json。未生图、未下单、未修改ERP。

2026-11-02 新日期口径已部署并在账号1原候选任务真实重检，旧seller_listing口径已归档；识别SellerSprite“上架日期/上架时间”标签。81项任务/接口/选品测试、19项流程回归、前端测试及隔离EXE冒烟通过。历史发行D:/AmazonAgentReleases/20261102-product-date-label/AmazonAgent/AmazonAgent.exe；8个SQLite数据库已备份。B0HNTGP9R4定向日期查询返回空，网页关键词查询显示无关ASIN，均未采用为候选日期证据，仍blocked。没有新增生图或ERP修改。证据data/product-date-policy-live-20261102.json、data/product-date-label-deployment-20261102.json。

2026-11-02 用户批准新的近7天口径：按**卖家精灵商品上架日期**筛选，明确标注其不代表该卖家独立上新。配置 selection.freshness_basis=sellersprite_product_listing；商品日期单独保存（网页 productListedDate、CLI product_listing_date），要求SellerSprite HTTPS来源及带日期标签的完整年月日原文，不能用月份、排序或Amazon首次可售日期替代。中国卖家、FBM、前台其他卖家exact/strong同款、该同款SellerSprite数值排名、IP/素材、排重与配额条件继续保留。新任务保存口径快照；网页旧blocked任务只有显式“更新资料重检”才采用新口径，归档旧口径与结果。CLI已有任务保留历史配置，不重建/重置绕过。以下历史卖家日期描述以本条为准。

## 2026-11-02 用户更新货源与图片规则（优先于历史授权要求）

上述源码规则已打包并切换运行：D:/AmazonAgentReleases/20261102-supplier-default-images/AmazonAgent/AmazonAgent.exe，PID5300、端口18765。切换前核查4个任务全部blocked、无图片任务/费用预留，8个SQLite在线备份并通过完整性检查；隔离EXE登录/预算/UI冒烟通过，实际账号1回读确认新素材提示及供应商选择记录保留。旧任务尚未重检，不把部署记为选品通过。驰哲透明1.5mm、50x100cm页面展示价15.60元、库存99820块；件重尺表90x8x8cm、重量975g，未明确标注毛重。非原9x25英寸规格。未生图、未下单、未修改ERP。证据data/supplier-default-policy-deployment-20261102.json及supplier-default-policy-live-20261102.json。

货源按公开销量、经营年限、回头率及店铺信息择优，不再要求逐家联系。供应商页面图片默认按用户决定使用，无需等待商家授权回复；记录basis=user_default_supplier_use_not_supplier_license，不能伪称已取得商家许可或将rightsVerified写成true。素材保留detail.1688.com商品来源及实际核图记录，排除竞品图片和未授权标识。页面规格、报价和重量仍须分别如实取证，不推算缺项。优先复核驰哲952542058876（已采集10万+件/7年/回头率45%）；目标9x25英寸未在页面现成规格中出现，不能混写成已有50x100cm款。

config.json已保存上述经营规则；源码选品检查及图片传输支持独立user_default依据，旧blocked任务快照与运行EXE尚未升级，不能把配置保存说成旧任务通过或部署完成。85项任务中心/接口/选品、21项流程、27项Node适配、8项入口测试通过。用户决定另存账号1候选IMP-US-B0HKJ1WKT2的sourcingPolicyDecision，并回读验证。

## 专属浏览器：ego（lite）

2026-11-02卖家来源实测修复：工作台原观察草稿误把商品页卖家名称预填为国家来源，现改为单独支持browser_seller_profile，严格校验Amazon站点、资料页路径、Seller ID及原文；国家来源仅预填真实经营资料，履约来源仍来自商品页，不自动认证国家/FBM。账号1候选IMP-US-B0HNTGP9R4（SKU WYJ20261102123059）通过真实界面加入任务b96d4892fb41428f8e34b658ca11e250；人工智能核对同一Seller ID的地址CN和商品页Shipper / Seller qigan//后，保存CN/FBM事实并重检，不再报告这两项缺失，日期/前台同款/排名/IP仍阻断。CLI任务849bf4849c724202单独保留blocked，网页与CLI未自动同步。92项相关测试、18项流程回归、隔离EXE冒烟及真实新接口/任务回读通过。运行EXE切换至D:/AmazonAgentReleases/20261102-seller-profile-source/AmazonAgent/AmazonAgent.exe，SQLite已备份，未付费或操作ERP。证据data/candidate-cn-fbm-check-live-20261102.json、data/seller-profile-source-deployment-20261102.json。SellerSprite实际MCP元数据仅提供商品上架月份/排序，不提供卖家独立上架日期查询；不能据此放行七天卖家上新，日期口径待用户选择。

2026-11-02新增只读店铺采集模块ego-seller-store.mjs：仅读取当前ego中指定US/UK Seller ID的Amazon店铺搜索页，核对导航前后来源、Seller ID和排序控件，读取标题/ASIN/图片/价格控件，不读取整卡或插件注入的候选BSR。调用方先读跨批次排重CSV并传入已用ASIN。实际已读取qigan//卖家资料的CN地址，并把Newest Arrivals前两页32张不同ASIN商品卡保存到账号1的选品调研，报告6698c8e6abdf4fa0b7ccfdc54fa8547e和e9c56fcd4bf043aab9f434ed0360260a；重新读取报告并检查工作台渲染成功。32张卡不等于32种款式，排序不证明七天卖家上架，当前无新增合格入选；FBM、日期、同款/IP等仍待核验。此模块由Codex脚本调用，尚未接入工作台自动浏览循环或EXE新按钮。第二页load超时已核对其实际完成且未提交，再读当前页采集，没有重开或重发。

2026-11-02图片传输校准：新增junfei-publisher/ego-draft-images.mjs，观察图库使用卡片勾选框中的原图URL，不依赖内嵌base64缩略图；上传前校验文件SHA256、真实尺寸、单帧格式、商品图审核/权利依据及草稿身份，逐张暂存并断言原图库顺序和草稿字段不变。模块不保存/发布，未接入网页生产执行。原创文字校准图已真实上传并下载核对SHA256，未保存、刷新后原七张图片恢复；服务器测试对象仍存在。失败首轮为原生sharp加载导致ego runtime断开，已保留失败并以无上传开始的真实对账后修复；不重置未知操作。证据data/erp-image-upload-calibration-20261102.json，19项适配测试、18项流水线回归通过；此为传输校准，不是生产商品图完成。

2026-11-02模型设置已接通账号独立的生图报价预览，真实UI显示APIMart gpt-image-2/2K为$0.015、当天中行美元卖出价6.6652，按拟采用的20%缓冲计算每张预留0.12元、七张0.84元。换算仅为预算估算，仍需账单结算；用户未确认换算规则，未启用付费生图，未形成费用预留。images.fx_budget_policy的USD换算路径默认拒绝，只有明确启用daily_boc_usd_sell_buffer及20%缓冲且当天报价/汇率齐全才可用于预留。EXE读取项目实时config.json；当前发布D:/AmazonAgentReleases/20261102-image-usd-budget/AmazonAgent/AmazonAgent.exe，UI证据data/image-usd-budget-live-20261102.json。106项相关测试和18项流水线回归通过；选品、材质/毛重、图片权利、图片制作及完整刊登仍未跑通。

2026-11-02工作台已有草稿桥接已实测：任务详情的“重新读取已保存ERP草稿”经ego核对绑定的172528873并回写观察，Generic/7.69美元/库存88及全部文案一致；不保存、不发布、不推进生产状态。绑定按账号、产品、店铺、站点限定在config.json.browser.erp_account_bindings。生产全部前置阶段通过才允许调用受限文案同步；共享独立工具回执排重，未知结果不重发。图片上传、新品创建、发布和在售查询仍缺适配。当前EXE：D:/AmazonAgentReleases/20261102-workbench-ego-bridge/AmazonAgent/AmazonAgent.exe；真实UI证据data/workbench-ego-bridge-live-20261102.json，72项桥接/任务/API测试、18项流水线回归及隔离EXE冒烟通过。

用户2026-11-02指定ego（lite）为专属浏览器。配置在config.json的browser：工作区ID 1，名称“亚马逊智能体专属工作区”，ERP p1、货源 p2、客服 p3。登录状态使用ego本身，不复制Edge Cookie；不默认启动或回退Edge。开始操作先读ego-browser技能并运行其skill命令。

运行 `py -3 -X utf8 automation/ego_browser.py status` 检查连接；`run 绝对路径.mjs` 在同一Ego工作区执行已审阅脚本，脚本通过全局amazonTask使用官方Page API。每轮新建脚本文件，不重放旧步骤。入口先写execution_unknown记录；超时/异常保留记录，相同脚本路径和内容再次执行会被阻止，必须先核对网页真实结果。runtime_returned只代表脚本返回，不代表消息送达或ERP成功。不要修改脚本或换路径绕过未知任务记录。

用户手动完成登录/验证并明确确认后，可运行 `py -3 -X utf8 automation/ego_browser.py resume` 恢复原工作区；未确认前不调用。2026-11-02已完成1688验证、钧飞登录，并实际发送两家供应商询问。洗漱包回复eva，密封条回复“没有，目前都在排单”，均不足以补齐供货及权利证据。发送及原文记录见data/supplier-send-*、supplier-reply-*。

Ego API不是Playwright。现有brain-worker、listing.mjs、existing-draft及旧EXE按钮仍是历史Edge入口，尚未全部迁移；不得把新统一运行入口描述为旧程序已全部改造。后续浏览器脚本从Ego运行时逐项适配，不直接用旧Playwright脚本启动浏览器。

2026-11-02新增ego-existing-draft.mjs：核对草稿URL、店铺、ERP SKU后修改有来源的产品文案，精确选择草稿保存按钮。updateEgoDraft按固定顺序持久记录、填写、保存、查未发布列表及重开后的实际值；超时和核对失败保持save_unknown，创建回执使用独占文件防止重发。现支持title、highlights、五条bullets、description、terms，逐字段要求来源，按标题75/亮点125/五点每条500/描述2000字符、后台词249字节检查。五点和后台词虽共用placeholder，但额外断言所属表单及关键词容器结构，页面变化即停止。已用工作台账号1的产品ERP-172528873实测整合执行器：五项文案保存、同一未发布列表行核对、重开逐项一致，售价/库存/处理时间/运费模板保持原值。回执data/ego-draft-executions/2aebc8439530061dfa178e0e2585d69c7f853df8601998ed252da4cfd5574911.json。此适配不覆盖新品创建/图片上传/发布，不能称为全流程刊登完成。

桌面app.py连接按钮改为ego同一工作区观察连接，“修改已有草稿”接入上述文案执行器。ego_link.ego_draft_command读取请求JSON，在原项目automation/data/ego-draft-executions记录操作；同一草稿身份+目标文案不受请求文件改名或更改证据文字影响，已有回执先对账。请求包含draftId、store、erpSku、patch和逐字段evidence。不支持的修改在本地停止；批量保存/发布在ego配置下停止，不启动Edge。新版打包包含ego-existing-draft.mjs、project-root.txt，读取本机原项目实时config，不复制登录状态。EXE --ego-check-output 绝对路径.json只观察连接并输出摘要，不接管已交还用户的工作区。独立工具新版路径D:/AmazonAgentReleases/20261102-ego-copy-fields/JunfeiDraftAgent/JunfeiDraftAgent.exe，桌面“钧飞ERP-ego专属版.lnk”已指向新版；EXE连接冒烟通过。网页任务中心尚未自动调用该执行器。

## 2026-11-02 图片库保存执行器补充（源码，未部署）

`junfei-publisher/ego_link.py` 新增 `ego_image_command(request_path, save_library=False)`，准备ego图片调用但不自行运行浏览器、不接管用户控制。请求只接受draftId/store/erpSku/assets；图片内容哈希与草稿身份决定固定回执，改路径、说明、用途或顺序不能绕过，重叠图片的拆分批次要求先对账。执行时使用工作台共用ego-workbench.lock；异常保留锁及原操作记录，成功只释放锁。已暂存商品图可进入独立保存步骤，未知上传/已有保存回执不重发，校准图不能升级为商品图保存。入口8项测试含生成脚本语法、持久身份及未知结果检查；尚未接入UI/EXE或真实调用。

`junfei-publisher/ego-draft-images.mjs` 的 `stageImageLibrary` 现保留完整七项文案快照，并回读服务器原文件核对SHA256；失败保留观察到的URL及upload_unknown，不重传。`saveStagedImageLibrary` 为独立保存入口，仅接受同一草稿中全部上传成功、远端内容一致、已审核且权利明确的商品图片；拒绝calibration_only及旧的不完整快照。保存前核对原文案、经营参数、图库URL顺序及尺寸，先持久写image_save_unknown，再点精确草稿保存按钮、核对未发布列表身份并重开验证。未知结果不自动重试。

此入口只验证产品图片库持久保存，**不验证变体主辅图分配，不代表图片制作或整款刊登完成**；尚未接入工作台/打包EXE，尚未做真实商品图片保存校准。26项Node图片/已有草稿适配测试通过；既有服务器校准对象只读回验一致，未重新上传或保存。证据data/erp-image-remote-readback-20261102.json。浏览器因1688滑块验证已交还用户，完成验证并明确回复后才恢复同一ego工作区。

# 亚马逊固定生产流程

2026-11-03 全局外观专利筛查口径已接入源码：config.selection.design_patent_policy适用于以后所有产品，新建CLI任务和网页任务保存策略快照。允许有实际查询、来源原文、判断说明且searchPerformed=true、obviousOverallMatchFound=false的no_obvious_match状态；图样不可得不单独拒绝。未检索、缺原文或发现明显相似仍拒绝。旧任务保留快照，须明确重检，不自动改为通过。22项流水线及90项选品/任务中心/API测试通过；网页改动尚未重打包部署至当前EXE，不宣称运行EXE已经采用新校验器。

2026-11-02既有草稿Generic校准：ego草稿适配新增品牌/制造商的受限成对Generic修改，拒绝任意新品牌。真实页填值出现制造商重复Generic，保存前断言阻止了提交；重读已保存页面对账确认未保存后，保留原记录继续第二次操作，逐项修正字段，最终只点一次保存、核对未发布列表并重开验证。原草稿172528873的两字段均为Generic，五项文案、7.69美元/库存88/处理3天/运费模板未变；未发布。原始失败、修复和最终结果均在同一回执data/ego-draft-executions/993cd918a3d5d22ff8f7d1c481c8fc737eee19727f181b6041af762afd0d2b84.json。Generic只是当前授权默认值，不证明品牌/IP/制造商事实已核实。

执行器填写品牌/制造商时，跳过已匹配的联动值，否则分两步清空、等待空值后填入，避免实际观察的重复拼接。草稿读入及重开等待运费模板加载再断言。ego_link恢复入口必须显式提供同一草稿未保存的对账文件，仅首次stopped_before_save可继续一次；同一回执保留previousAttempts、原记录SHA256及对账来源，锁和原记录校验防止并发覆盖。running/save_unknown/已保存记录仍不可重发，达到两次停止后不能自动清零重试。

新增网页入口：工作台侧栏“智能体任务中心”，详见 `listing-workbench/AGENT-CENTER.md`。网页中心有账号隔离的档案、可选AI规划及后台工具循环；与本目录CLI台账尚未自动同步，不把准备检查当作生产完成。

当前默认配置：`test-wyj-us`（示例店铺-美国 / US，Migrated Template，库存88），刊登模式为 `draft`；生图默认关闭，沿用已有图片。需要生图时必须先设置每款与每日预算；发布模式必须按任务取得用户明确授权。CLI中的默认档案用于新任务快捷选择，多店铺仍可显式指定其他档案。

入口：在本项目根目录运行 `py -3 automation/pipeline.py readiness` 查看固定配置和未接入环节，运行 `py -3 automation/pipeline.py status` 查看任务台账。这版是 **Codex驱动的固定流程与持久台账**，不是已经接通全部外部系统的无人值守服务。CLI不会自行选品、生图或点击发布；Codex按总控技能执行实际步骤并回写证据。尚未创建定时任务，尚未提交真实商品或产生生成费用。

## 2026-11-03 当前全局规则与真实刊登结果

所有产品在选品阶段实际检索外观专利；未发现整体外观明显相似的有效专利便继续，记录“本次检索未发现明显相似专利”，图样不可得不单独阻断，不断言专利不存在。已部署到 `D:/AmazonAgentReleases/20261103-patent-policy/AmazonAgent/AmazonAgent.exe`，桌面快捷方式已切换。22项流程、90项选品/任务/API、包内规则和隔离EXE七图导出/定价/账号隔离测试通过；9库备份，切换前后资料、任务、生图和刊登回执一致。证据 `automation/data/patent-policy-deployment-20261103.json` 与 `patent-policy-postdeploy-20261103.json`。

账号1编织包 `IMP-US-B0GY4WTGN1`：产品库147631273已保存回读；店铺草稿172559444已核对7图、文案、黑色子SKU和$38.47售价。实际提交生成发布任务14928651，返回99022，父/子SKU均缺容量、包装重量及包装长宽高，实际页面schema将三组标为required。没有亚马逊在售证据，不重复发布、不用产品尺寸冒充包装尺寸。现有650g是用户指定的货源重量依据，并非已核实包装毛重。当前结论见 `automation/data/woven-delivery-current-20261103.json`，原提交与错误保留在 `woven-publish-operation-20261103.json`，工作台已回写失败观察。

## 固定顺序

循环选品 selection（使用cyclic-product-discovery；按最新用户指令与config核验） → 货源 sourcing → 竞品关键词 research → 文案 listing → 图片 images（首色整套母版→变体换色完成其余颜色整套图） → 导出 export → 刊登 publish → 在售核对 verify。以下专利检索等历史要求以最新用户指令和任务策略为准，不自动套用到新批次。

2026-11-03 最新用户规则覆盖下方历史专利待复核要求：完成实际检索后，未发现整体外观明显相似的有效专利便按经营筛查规则继续；相关专利号、一般纹理相似或图样不可取得不单独阻断。证据须记录“本次检索未发现明显相似专利”，保留范围及读取失败记录，不断言法律上不存在专利、不虚记已完成图样比对。编织包采用决定见 automation/data/woven-patent-screening-decision-20261103.json。此变更不自动把其他检查或整个选品台账记为通过。

2026-11-03 用户纠正执行顺序：外观专利检索在选品阶段完成，不能拖到生图后或发布前。必须保存检索范围、来源、图样比对及判断依据；只找到专利号不算完成，未定候选维持blocked，不开展文案生产、付费生图或ERP刊登。既有CLI选品IP检查继续生效；网页与CLI台账未同步，Codex直接调用工具时也必须先遵守此顺序。本次编织包在外观复核未完成前已制作草稿，属于执行顺序错误；保留产物与费用记录，不因此放行选品或发布。

每款永久ID；SQLite保存阶段、尝试次数、配置快照、领取token和事件历史。重复站点+源商品ID拒绝创建。阶段只能依序通过；真实证据及产物文件SHA256归档。完成刊登只表示全变体已提交，最后一步全部在售才显示done。证据校验要求操作者如实检查；布尔值和文件哈希本身不能证明内容真实或图片质量合格。

## 多店铺设置

品牌与素材规则：供应商页面上的品牌名（例如本候选观察到的“祥亚”）和第三方品牌/商标（例如“3M”）不得写入 Listing 标题、五点、描述、后台词或图片文案，也不得暗示授权关系。刊登品牌按2026-11-05规程，从目标店铺实际同步出的品牌中选择适用于本品的品牌，不固定Generic，不把同步结果当作本品适用证明。带有未授权品牌标识的供应商图片不得使用；供应商页面图片按用户决定默认可用，不要求商家授权书或回复；保留1688来源和实际核图记录，使用依据记为user_default_supplier_use_not_supplier_license，不冒充商家许可。删除品牌词不能替代产品、商标、专利或图片权利核验，也不代表规避侵权。

双击本目录 `店铺配置.vbs` 打开配置窗口；也可运行 `py -3 automation/settings.py`。可新增/选择档案，填写ERP店铺、站点、运费模板、库存及草稿/发布模式，并单独配置生图开关和全局预算。窗口不登录ERP、不提交商品。默认档案由 `config.json` 的 `defaults.profile` 指定；选择/编辑其它档案不会覆盖默认项。启用生图时每款及每日预算必须填写，关闭时使用已有素材。

已继承历史工作流：库存88、处理3天、FBM及美元定价公式；品牌按目标店铺同步结果与本品适用性选择，不继承历史Generic默认值。店铺/站点不沿用历史批次；每个任务指定配置。不要用紫鸟环境名推断ERP授权店铺名。

```powershell
py -3 automation/pipeline.py profile-set my-us --store "实际ERP店铺名" --market US --shipping-template "实际运费模板" --quantity 88 --mode draft
py -3 automation/pipeline.py profiles
py -3 automation/pipeline.py add --profile my-us --market US --source-id "真实源ASIN"
py -3 automation/pipeline.py claim 任务ID
py -3 automation/pipeline.py template 任务ID
```

`claim` 返回的 `required_checks` 是待满足门槛，不表示检查已经通过；只有提交真实证据并通过 `finish` 校验后，阶段才会推进。

`template`输出证据JSON结构，checks初始全部false，实际核验后才改true。保存到产品任务目录，来源记录URL、读取时间、原文与判断；artifacts填实际绝对文件路径。finish会校验并持久保存内容：

选品阶段另外要求 `selection_evidence`：7天内的卖家上架日期、中国卖家与FBM原文、已打开且关键词一致的Amazon前台搜索、其他卖家的exact/strong同款及该同款SellerSprite数值排名、五项IP/素材记录（图片项可按已配置的user_default规则通过，其余项目仍须clear）、配置指定排重CSV的当前SHA256与无重复结果、同店当日不超过2款的配额证据。任一缺失或状态待复核都不能通过选品阶段；`template`会生成字段骨架。选品证据通过后会把ASIN以 `validation_candidate` 写入同一排重CSV，阻止跨批次重复；正式商品表仍需按技能要求生成并复核。

```powershell
py -3 automation/pipeline.py finish 任务ID --token 领取返回的token --evidence "证据JSON绝对路径"
py -3 automation/pipeline.py hold 任务ID --token 领取返回的token --status blocked --reason "缺包装重量"
py -3 automation/pipeline.py hold 任务ID --token 领取返回的token --status uncertain --reason "提交请求超时，需核对ERP"
py -3 automation/pipeline.py resume 任务ID --reconciled-no-submission "已查实际ERP及服务商，确认未提交；证据路径……"
```

running任务重启后保留，绝不自动重新提交。若实际已成功，使用原token和真实证据finish；确认未提交才resume。每阶段最多2次尝试，失败达到上限先修复诊断，不自动清零。缺资料产品隔离后继续其它ready任务。

`config.json`修改影响新任务；已有任务使用创建时快照。生图开启时先用 `reserve-image-cost 任务ID --max-rmb 金额` 登记本次单次费用的最高限额，再领取图片阶段；同一产品和本地自然日的已结算费用及未完成预留会累计占用预算。生成任务结果未知时保留预留，不得释放或重发。账单核实后用 `settle-image-cost 预留ID --actual-rmb 金额 --note "账单核验依据" [--external-id 服务商任务号]` 结算；确认未收费时金额填 `0` 并在备注说明。`image-budget-status` 查看当日明细。超出预留或配置上限的实际收费会记录为 `over_budget` 并阻断该图片阶段完成；本地闸门无法阻止服务商违反报价或对单次调用事后加价，因此只允许在调用前费用明确、单次最高费用不超过预留时提交，不能把本地台账描述为供应商侧硬封顶。

## 现有模块接入位置

| 阶段 | 现有实现 | 执行方式与缺口 |
|---|---|---|
| 选品 | cyclic-product-discovery技能、outputs店铺池及排重表 | Codex执行标题首句→商品→Seller→店铺其他商品→新关键词循环；入库要求按用户指令与config.json核验 |
| 货源 | listing-workbench/agent_sourcing.py、importer.py | 会读取已采集的1688候选中排名前三的公开详情并留摘要；不自动搜索页面、采用供应商或确认同款/报价/权利，浏览器采集与人工选定仍未自动化 |
| 研究 | competitors.py、sellersprite.py、market_research.py | 工作台现有接口；需要可用登录/数据源，不猜评论或搜索量 |
| 文案 | provider.py、listing_skills.py | 用当前账号工作台调用并保存真实产品文案 |
| 图片 | ivyea_pipeline.py、visual_studio.py、colour_sets.py | 先完成首色整套母版，再用变体换色完成其余可刊登颜色整套图；逐图位检查并绑定同色子SKU，保存外部任务号再恢复查询，不盲目重发 |
| 导出 | delivery_export.build | 使用工作台导出入口；核查缺图和待审状态，不把草稿当合格 |
| 刊登 | junfei-publisher/listing.mjs | 有本地validate及图片预处理；recipe.json未校准，真实页面需适配 |
| 核对 | ERP列表及Amazon实际状态 | 尚无统一自动查询执行器；按子SKU核对，不以ASIN创建代替在售 |

工作台导出文件名与prepare_product.py输入不完全相同，多颜色转换也有限制。未实现自动格式转换，不直接把ZIP交给prepare_product并声称兼容。钧飞app.py及library_fill等脚本还需在真实页面核对；recipe未校准不能靠修改布尔值绕过。

## 首款试跑前尚需

1. 默认使用 `test-wyj-us` 店铺档案；新店铺须先创建独立档案。当前默认沿用已有图片，不产生生图费用。
2. 人工草稿试刊观察记录见 `automation/data/junfei-draft-calibration-20261031.json`；通用刊登脚本仍未校准，草稿列表行与旧 checkpoint 中的不同草稿 ID 仍需对账。
2. 核实当前登录与模型服务，指定工作台账号，不读取无关员工资料。
3. 对钧飞实际页面完成类目、变体、附图、属性、保存及提交结果适配，先验证真实草稿。
4. 将上述阶段逐一接为执行器，补成本预留与扣减，再运行小批量故障恢复测试，最后启用范围明确的自动发布。

检查：`py -3 automation/pipeline.py doctor`。缺配置时返回1；运行错误返回2。回归：`py -3 -m unittest discover -s automation -p "test_*.py"`。


2026-11-02 产品库变体读取修复（源码，未部署）：实测Element UI表头/表体分表，变体四个输入均为placeholder；ego-library-draft.mjs改按表头及列位置读取SKU/颜色/尺寸/价格和图片，暂存/保存核对包括变体快照，非空变体表停止以免覆盖。实际只添加空行检查后关闭未保存表单，没有第三次保存。证据automation/data/erp-library-variant-reader-live-20261102.json；36项Node适配和21项流程回归通过。尚未证明422原因，也未完成新品创建。


2026-11-02 标称规格修订及采集修复：账号1的独立备选1688-952542058876-CLEAR-15-50X100（SKU WYJ20261102142256）已保存含标称尺寸、1–3cm测量误差、厚度误差及收缩预留的文案和尺寸示意；刷新回读、图片SHA256、原候选不变检查通过。旧尺寸图标记supersededBy，不作交付。证据data/chizhe-tolerance-save-20261102.json。供应商图片默认可用；没有新ERP草稿或发布。采集插件0.7.12新增开放V-DETAIL-Z详情图读取，源码与员工包一致，ego真实页面读到19张详情图；证据data/supplier-detail-collector-live-20261102.json。插件ZIP为outputs/Junfei-Collector-0.7.12.zip；尚未更新安装中的扩展或打包EXE，不能宣称界面已全部部署。
# 循环选品的长期店铺收藏（用户2026-11-06补充）

循环发现的同行店铺保存至 `selection.store_pool`（当前为 `outputs/同行店铺记忆库.csv`），按站点与卖家ID去重，保留店铺链接、最新上架排序链接、首次发现及最近访问日期、来源商品与核验记录，供后续批次继续选品。缺失的国家等字段留空，收藏状态不代表店铺或产品已经通过选品核验。后续复用店铺时仍须按当前配置重新核对商品日期、品牌、同款排名、货源、成本利润及每日配额。

2026-11-06 用户要求切回钧飞插件找货源并修复跨工作区跳转。已修复实际加载的钧飞采集插件2.9.60：货源请求保存发送标签的窗口身份，新标签明确绑定原窗口并后台打开，身份失效时停止。已重载扩展并真实点击验证，1688标签p8与Amazon来源p4同窗口且同属选品TaskSpace4。恢复优先使用钧飞“1688货源”；不操作用户工作区0。SellerSprite入口曾实际产生跨工作区标签，尚未修改其插件，只保留已有专属页导航备用。修复、备份与证据见 `junfei-publisher/source-window-fix/README.md` 和 `outputs/cyclic30-20261106/junfei-plugin-window-fix/`。本结论只验证钧飞该入口，不保证其它插件行为。

