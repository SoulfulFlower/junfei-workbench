# 软件许可与来源

ASIN 洞察的逐图分析、汇总、结构化分析和文本包装提示词来自 IvyeaOps 提交 `51f5141b475e64b67638f396451d887531caa761` 的 `server/app/routers/listing/analyze.py`、`ai.py`，并附原版 `amazon-listing-creative` 和 `amazon-asin-cosmo-rufus-audit` 技能的实际注入节选。见 `ivyea_asin_prompts.py`，按 AGPL-3.0-only 提供。

2026-11-04 图片接口适配：`openai_image_provider.py` 参考 IvyeaOps 提交 `51f5141b475e64b67638f396451d887531caa761` 的 `routers/assistant.py` 和 `routers/listing/images.py` 中可配置 Images 接口、参考图及同步/异步返回机制；提示词继续使用已迁入的编译器。新增账号隔离、预算及未知提交防重发的本项目适配，未迁移参考项目私有密钥。审计见 `docs/IVYEA-IMAGE-AUDIT-20261104.md`。

`product_pixels.py` 来自上述 IvyeaOps 版本的 `listing_image_compositor.py`，用于原图主体提取与保真排版；`product_artwork.py` 为本工作台新增的排版及任务适配。

文案技能方法参考 IvyeaOps 的 `amazon-listing-creative` 与 `amazon-asin-cosmo-rufus-audit`：证据分类、买家问题、五点扫描式表达、先纠错后润色及缺失资料降级。规则已按本软件的卖家精灵数据、站点字段、关键词搜索量偏好和事实约束重新编写，未照搬其广告建议、工具依赖或未经验证的政策断言。

本版本迁移IvyeaOps真实视觉编辑组件，组合后的工作台按AGPL-3.0-only提供。详见LICENSE-AGPL-3.0.txt及visual-ui/NOTICE.md。软件页面提供“下载本部署对应源码”，用于向访问软件的用户提供对应源码；不包含公司产品、密钥或员工账号数据。来源版本：51f5141b475e64b67638f396451d887531caa761。

此前文档中“没有复制程序代码”描述仅适用于之前独立实现版本，本次迁移已使用上述开源组件代码。


2026-10-27 核心迁移：`ivyea_render_core.py` 保留上述版本 `visuals.py` 的原版版式词汇、整套风格、精确图文合同编译器及视觉总监策划提示模板；`ivyea_copy_core.py` 保留 `copywriting.py` 的候选文案规则和提示组装函数。`ivyea_pipeline.py` 是适配现有产品/素材/账号/模型服务的新增编排。图片服务新增原版 `gpt-image-2` 像素画布与 `input_fidelity: high` 调用契约。未迁入与此工作台无关的 IvyeaAgent 全套运营工具。
生图真值白底检测 `ivyea_white_source.py` 取自 IvyeaOps 提交 `51f5141b475e64b67638f396451d887531caa761` 的 `server/app/routers/listing/common.py`，按 AGPL-3.0-only 提供。

`psd_writer.py` is copied from IvyeaOps commit `51f5141b475e64b67638f396451d887531caa761`, `server/app/services/psd_writer.py`, under AGPL-3.0-only. The authenticated export adapter follows the original final-artwork and hidden product-reference layer structure.

