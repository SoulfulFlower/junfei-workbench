# 变体换色模块维护



2026-11-21：撞色蕾丝等单一面料目标无法正确表示时，可把同色实图排版或原生图片引擎的定点修复候选，经 `prepared_colour_gallery.adopt` 明确接入正式颜色图库。该入口校验当前商品、已确认母版、本色真实子体主图及文件哈希、完整逐图候选、原生任务归属与终态；同色已有原任务时不重建。只创建待真实检查的记录，不赋予质检通过或人工审核。原颜色工作线程继续执行同款比对、逐图质检和正常SKU关联。原生引擎旧失败回执保留，修复后的实际像素独立检查；默认本地换色入口仍不调用生图API。



2026-11-21：显式保存的编辑器选区由服务端记录 `editedSelection`，绑定原图 `sourceHash` 和该次 `revision`，不冒称自动识别或人工审核。`selection_needs_refresh` 同时用于就绪检查和批处理准备；识别器升级只刷新尚未编辑的旧自动选区，保留已修正的真实衣料、文字与五金保护区。旧选区无此记录时，核对实际像素后通过正式保存入口生成新修订，不能直接补自动版本号放行。



2026-11-21：新版 `fabric-tone-v9-selective` 使用 `colour_transfer.py` 独立分支：彩色保留局部HSV变化；黑白灰按选区亮度分位与相对明暗重映射；显式参考照片按所选部件Lab统计转移。保护区及原透明通道优先，选区外恢复原像素。现有配方与高级控制保留，新版本生成新回执，不重算已批准图。



图片创作台换色为独立候选，可自动识别服装部件或导入/涂选精确选区，非服装不能套衣料识别。默认本地处理，可明确追加Codex Tools光影修整，使用候选+原图+选区三参考，再将结果限制在选区内；未声称验证模型原生mask参数，不自动修改母版及子SKU。



2026-11-20：由工作台用实测表直接排版的尺码图，自动换色只识别版式预留的原照片区域。区域来自实际原图排版记录和母版文件哈希，换色选区不能从请求传入或扩展。表格、标题、单位和照片以外的像素全保护，目标颜色仍从已核实子变体主图取得。



2026-11-20 `auto-cloth-v11` 修复局部构图漏换。原衣料、SAM 和人体识别先提供衣服边界，再从已选中的布面学习色相。只恢复与原衣料相连、颜色相符且有衣服证据的遗漏。肩部在画面外的特写允许补回由人体模型误判成背景的衣身。深折痕仅在衣料轮廓内部恢复，手和指甲按原图肤色与人体部位保护。薄带修复限于衣服轮廓内、颜色匹配并与衣料相连的窄条，肩领和发丝旁的补选限于已有选区紧邻、与衣料高度同色的窄边。裁切特写边缘还会处理同色像素留下的原色细线。背景、文字、用户保护区和色相不匹配的发丝不参与补选。更换版本时，工作台只为尚未过检的图位重新计算本地选区，仍从对应变体主图取色。



2026-11-15 边缘收尾：当前 `auto-cloth-v7` 保留v6的衣料/发丝识别，仅在无最佳SAM和U2上衣支持且贴包的弱证据边缘按主体尺度做减法圆顺，不扩大包染色；新恢复衣岛及这些边缘的2px窄带用原图局部matting形成灰度alpha。每个求解tile为96px加12px可靠边界，最大120×120，不做整图稀疏求解；衣料内核与人体/包/发丝保护优先。`selection.automaticBoundary`记录削除、软像素、ROI和耗时，图层字段仍为0–255灰度选区，现有渲染链直接使用alpha。当前机器已装PyMatting 1.1.16（MIT）、Numba 0.68.0，已固定进`cloud_requirements.txt`，此次未额外安装或下载。`prepare_matting`先创建账号DATA下`numba-cache`，同时设置`NUMBA_CACHE_DIR`与已导入的Numba config，再import PyMatting，避免Windows在只读site-packages测试缓存写入时长时间重试。正式入口从账号DATA下SAM缓存的父目录推导该目录；账号工作进程不共用图像数据。空闲工作进程启动前可用相同`JUNFEI_ACCOUNT_DATA`子进程调用`garment_auto.prepare_matting(app_paths.DATA/'numba-cache')`预热，禁止依赖用户默认缓存目录。实测冷导入+首小ROI约31.5秒，热进程首ROI含import约0.625秒，其余单ROI0–0.016秒。44项隔离检查及七构图四色真实本地回归见`research-e2e-20261115/colour-v5-fix.md`；离线预览不等于生产过检。



2026-11-15 全流程实测修订：`auto-cloth-v6`加入本地SCHP/ATR人体部位模型，用头发、裸手和包的语义证据保护非衣物，并从多组自动MobileSAM候选与原图像素恢复被手遮挡的衣袖。衣服语义不再被直接强制并入最终选区；低分整人候选不能扩展恢复范围，暗色裤装的缝线对比证据传播至相应裤区，并排除内部少量背景色样。人体域先闭合小洞再约束恢复范围，隔离窗框和椅子；发边小组件需相邻衣料、原图颜色及纹理证据，零语义锚的小孔还需梯度方向和多尺度频谱高度吻合，较长暗发仍受保护。小型人体衣料片还须有最佳SAM部分支持及邻衣纹理，避免被细化步骤误删；对新增衣料岛用附近真实衣料锚的Lab色度中位数、MAD与实际分布保护覆盖的暖褐发丝，不按整片遮挡区填色。不包含产品坐标或人工点。固定模型、MIT许可和SHA256见`models/human-parser`，`install_colour_models.py`显式恢复两个模型，运行时不下载。版本变化时未过检套图的自动配方重新读取变体主图，旧配方进入历史；明确手调和已过检图片保留。服装分镜同时要求文字位于非衣料空白处或小块不透明中性底，避免换白衣后白字不可读。



同次实测移除质检放大图按图位硬编码的坐标。`colour_sets.review_inputs`按实际变化范围扩边提供通用上下文；显式复核以当前原图与结果左右、上下边界对照覆盖争议范围，保留旧检查与文件哈希，不改变质检阈值。ERP采集 verified 后发布区只读刷新就绪状态，保留原任务、运行状态及未保存经营资料，不触发发布。



2026-11-15 最新：用户要求“不要上传，仍取变体主图颜色；替换原批量换色”。默认页面现在直接选择目标变体，`local/prepare`读取该颜色已关联的`amazon_variant_main`，用本地U2Net衣服解析、MobileSAM及原像素边缘细化自动生成选区，再仅对衣料区域取代表Lab颜色。无需上传、人工提示点、框选取色或首次手填配方。`automatic_colour_reference.py`保存实际主图URL、子ASIN、源文件SHA256、取色方法和模型版本；不按颜色名称猜RGB。默认不使用供应商图代替缺失的变体主图。



旧单色及全部颜色按钮、旧`/start`和`/start-all`兼容入口统一走`automatic-variant-main-v1`。所有变体事实、主图与未知任务先完成预检，再自动取逐色配方及准备完整母版选区，最后才创建原生本地任务；仍不调用生图API。已完整过检的颜色保留。旧非自动选区迁移为新修订时，旧图层与保护区记录仍留在不可变历史；新自动选区标记随以后的手工微调保存，避免反复重算。旧颜色配方移入`recipe_history`，新任务冻结`colourSource`与逐图源Hash、选区修订。`PREPARATION_LOCK`避免快速切色和批量启动并发覆盖共用选区；运行中不重写选区。



`garment_auto.py`的`auto-cloth-v1`在本机完成衣服语义识别、独立小块提示点生成、SAM边界识别及轮廓范围内GrabCut补全；点是模型生成的，不要求用户标点。模型安装清单及原许可在`models/cloth-parser`，用`install_colour_models.py`显式恢复固定SHA256的ONNX；运行时不下载模型。选区外及保护区仍保留原图像素，RGBA透明通道仍由统一渲染链保留。手动取色和画笔保留为可选调整，上传入口已从默认工作流移除，旧上传预览接口仅兼容历史记录，不能关联SKU。



2026-11-15：按用户“用RPA分析复刻、不接LinkFox API”的最新要求，实操其上传后的抠图编辑器和调色面板，复现本地选区、调色与导出工作流。现有参考图取色与对比原图保留；`fabric-tone-v8`加入色调、亮度、光影强度、向内柔化边缘、去杂色、三段RGB色彩平衡及RGB/红/绿/蓝控制点曲线。预览可自动更新，PNG与ZIP、整套颜色配方共用`colour_tuning.py`校验和同一渲染链。保护区、选区外及原透明通道不改变；旧配方补默认值，不重算或覆盖旧成图。



初版`garment_workflow.py`把本地MobileSAM ONNX接入`pixel/segment`入口，并提供保留/去除点、遮挡衣料补入、反选、选区导入及透明预览。它现在是可选的细节调整工具；默认自动流程见本文件顶部。旧入口继续核对账号、产品、母版Hash和选区版本，不声称LinkFox私有算法、生成式边缘重绘或逐像素效果完全相同。初版分析证据保留于`research-linkfox-20261115`及`artifacts/换色功能复刻-20261115`；全自动及最新主图取色证据分别位于`artifacts/全自动衣服识别-20261115`与`artifacts/变体主图自动批量换色-20261115`。



2026-11-15：`colour_binding.py`校验当前母版、同色资料、完整过检图位及原SKU；`colour_sets.py`在后台完成及页面读取时保存独立的自动关联回执。关联采用比较旧记录后写入，避免覆盖并发修图。旧manual/status及图片、检查历史保持原值；`delivery_export.py`通过skuBindingReady将自动关联用于对应SKU图片列，不冒充humanReviewed。页面不再展示重复“最近的选区修正”区域或人工确认按钮。



2026-11-13：在现有文件入口上拆分维护，不迁移数据库，不修改接口地址、字段、提示词、任务状态或历史记录。



## 页面层



| 文件 | 职责 |

|---|---|

| [colour-page.js](colour-page.js) | 颜色选择、同色参考图、子体明细、母版、换色结果及颜色关联界面 |

| [colour-pixel-tools.js](colour-pixel-tools.js) | 高级选区、保护区、预览、PNG/ZIP 下载及修正版提交界面 |

| [colour-view-rules.js](colour-view-rules.js) | 页面展示条件：已确认母版、其他颜色及按钮可用状态；不替代后端校验 |

| [colour-sets.js](colour-sets.js) | 旧工作台挂载适配与共用页面钩子，保留既有加载和执行顺序 |



`index.html` 按 `colour-api.js → colour-view-rules.js → colour-pixel-tools.js → colour-page.js → colour-sets.js` 加载。页面和高级工具通过接口客户端通信，不直接执行 HTTP 请求。



## 接口层



- [colour-api.js](colour-api.js)：前端 HTTP、JSON/字节读取、上传和工作空间保存同步。保留账号变化、并发编辑和版本冲突保护。

- [colour_api.py](colour_api.py)：后端 `/api/colours/*` 路由、请求解析、工作空间事务及响应。共用 `server.py` 先完成鉴权和账号运行空间选择，再委托本模块。

- 原有 sets/image/export、母版与恢复、local、pixel 和换色任务接口继续使用相同地址。旧生成入口继续遵守本地换色限制，不因模块拆分恢复付费生成。



## 校验与业务层



- [variant_colours.py](variant_colours.py)：整理颜色、实际子体及参考图。`catalog` 供制作与导出，`display_catalog` 供页面显示；旧同名函数保留兼容委托。

- [colour_rules.py](colour_rules.py)：母版是否已确认、恢复候选是否满足供货/尺码/子SKU/参考图条件、旧完整保存请求的母版校验。

- [colour_associations.py](colour_associations.py)：通过校验后，生成保留原 SKU 和原排除记录的产品副本及恢复/母版历史，不自行写数据库或调用模型。

- [colour_sets.py](colour_sets.py)、[local_colour_tasks.py](local_colour_tasks.py)、[pixel_recolour.py](pixel_recolour.py)、[colour_quality.py](colour_quality.py)：沿用既有换色台账、任务、渲染与质检执行。



数据依赖方向为：页面 → 前端接口客户端 → 已鉴权的后端接口 → 业务操作/校验 → 现有台账与任务。校验及产品更新文件不依赖 HTTP 服务，不执行生图或上传。



## 兼容与数据边界



- 母版只能选已确认颜色；供货未确认的目标颜色继续显示原图、来源和实际子体，保持禁止制作。

- 明确恢复时保留 `excludedVariants`、原始 variants、子 SKU 字符串和原任务记录，追加 `variantEligibilityHistory`。

- 母版变化记录 `masterColorHistory`；恢复和母版修改使用当前产品库修订，冲突时不覆盖。

- API、目录函数和旧前端挂载入口保持兼容。拆分不重写旧数据、重新出图或重传 ERP。

- 新文件位于应用根目录，沿用现有打包和对应源码收集方式；新增脚本须同时列入服务端静态白名单。



## 检查



在本目录运行对应检查；环境中 `py -3` 不可用时使用已安装的 Python 可执行文件。



```text

node --test test_colour_module_ui.cjs

node --check colour-api.js

node --check colour-view-rules.js

node --check colour-page.js

node --check colour-pixel-tools.js

node --check colour-sets.js

py -3 -X utf8 -m unittest test_colour_associations test_colour_sets test_colour_master test_colour_quality test_local_colour_tasks test_local_colour_api test_pixel_recolour test_pixel_recolour_api test_delivery_export

py -3 -X utf8 -m unittest test_garment_selection test_garment_workflow test_colour_tuning

py -3 -X utf8 -m unittest test_garment_auto test_automatic_colour_reference

```



前端检查覆盖请求格式、版本冲突、账号切换、保存期间的新编辑、展示/制作区分及旧挂载顺序。后端使用隔离数据库核对鉴权、恢复、历史、旧接口及导出兼容。



真实产品验收只读比对产品、可制作/排除子体及历史台账哈希，核对原母版、目标色参考图和拦截行为。供货证据不足时，不为验收写入虚构供货资料。



2026-11-21：自动取色失败或取到非衣料时，可经原生 sample-reference 从已绑定变体主图的实际衣料区域取样，再将 referenceSample 和 reviewerType=agent 交 configure。服务端重新核对原照片 SHA256、区域和目标色，配方记录 agent_verified_reference_patch、原子 ASIN 及 humanReviewed:false；历史自动配方保留。保存普通辅助图类型修改时创建新版本，主图和尺码表类型不能改作辅助图绕过检查。



自动变体主图取色 v2：不足可见图像 0.5% 或不足50个有效衣料像素时不生成目标色，避免把少量误分割的上衣/五金当成裤装。实际参考图的衣料样本可按上文原生入口保存可复算证据。边界返修优先使用真实衣料/背景点的 MobileSAM、原像素 GrabCut 和软边 matting，记录实际点、源哈希和选区修订；不以大块硬多边形或颜色阈值替代复杂衣料与椅子、皮肤的边界。



换色质检 v2（ecommerce-balanced-v2-scene-boundaries）：对照原母版的结构确认像素归属后再判断漏色或溢色。椅面、木材、皮肤和阴影保持原场景外观；仅凭接近衣料或棕色相似不足以判成衣料。真实衣料大块漏色、背景染色和商品结构变化继续阻断。策略更新不改写旧质检，必须对当前成图重新执行检查并保留回执。





2026-11-22 官方原始模板接入：`official_image_templates.py` 按不可变ID校验240张真实配图及原始提示词、24项完整修图配置与配图，`official-image-templates/manifest.json`保存来源与逐文件SHA256。新自由套图与正式AI分镜均引用原配图和完整原文，不回退简化蓝图。`visual-ui/OfficialColour.ts`执行原始配置11级GLSL滤镜；`official_colour_result.py`核对资源哈希、执行顺序、选区外原像素及alpha。原始供应商字段仅作来源元数据，分析/生成仍走当前账号Codex Tools、预算及原生回执。原件、失败图和未知提交保留；候选图不自动绑定SKU或替换已发布图库。私有服务端提示词和原生曲线助手未取得，不声称完整私有实现复原。



原片锁定模式（可选）由 `image_source_layers.py` 执行：按原配图/完整原文编排，AI只制作背景及许可文字，真实商品/细节由同款原片图层合成；保存来源哈希、裁切与输出坐标、蒙版及模型背景原件。该模式保留原拍摄姿态，不声称AI生成了新商品角度。换色先由后端将原件解码为无损RGBA PNG，避免浏览器/JPEG解码舍入差异；原JPG及其哈希保留，选区外像素和透明度检查不降低。





2026-11-22 REA曲线修正：`visual-ui/NativeCurves.js`替换先前分段线性LUT，保留原自然三次样条、float32、截断及通道合成顺序；`OfficialColour.ts`与Skill运行资产使用同一实现。固定种子130组、399360字节与原WASM零差异（每通道2–8点），只证明CPU查找表，不声称整张GPU图像或私有服务端一致。旧成图/回执不回写。





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



2026-11-24 用户七图默认与尺码共用：图片创作台默认白底主图1、细节2、种草3、尺码1，图序白底→细节→种草→第7张尺码。新正式服装七图同样验证此组合；历史方案保持原规则。尺码使用当前档案有来源且覆盖全部拟售尺码的原始数值，本地确定性排版并独立复核，不让图片模型重抄数字。新候选以sizeRenderingPolicy=verified-typeset-v1冻结该路径，旧requestId/恢复任务不追改。整套本地换色在母版尺码位冻结sharedSizeChart源字节SHA，跳过分割/滤镜，复用同一文件和URL供全部颜色/尺码；选区编辑及独立像素换色禁止改该尺码位。来源、表格、构图、可读性及独立QA仍须通过，换色其他图位和SKU/发布规则不变。202项隔离检查和TypeScript/Vite通过；实际补图和回执见逆向Linkfox/analysis/seven-image-settings-20261124。
