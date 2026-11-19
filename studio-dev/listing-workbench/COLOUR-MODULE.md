# 变体换色模块维护

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
