# 正常页面选品研究模块

`native_sellersprite_research.mjs` 接收调用方已独占的 EGO Page，提供：

- `collectNativeReverse(page, {candidateAsin, queryAsin}, {base, prefix, start})`
- `collectNativeMining(page, {candidateAsin, keyword, sourceAsin?}, {base, prefix, start})`
- `captureVisibleReviews(page, expectedAsin)`
- `readNativeKeywordState(page)`

先用实际页面中的“关键词反查”或“关键词挖掘”入口打开对应模式。`start: true` 只在正常输入框提交一次新查询；已有查询待返回时使用 `start: false`，不重复提交。`base` 为调用方提供的绝对目录并以 `/` 结尾，`prefix` 只使用字母、数字、下划线和连字符。模块不创建或接管工作区，也不访问 ERP、1688 详情、付费模型或业务接口。

当前已实测范围为 Amazon US / 75020。候选 ASIN、配送位置、当前模式和查询文字不一致即停止。验证码由调用方按 EGO 技能停止并交还；模块不会绕过验证。

`ui.visibleRows` 只表示虚拟表当时渲染的行；`ui.declaredTotal` 是原 UI 显示值。两者都不能当作已下载全表。只有正常“导出”按钮产生的原始 XLSX 已保存、文件名 ASIN 与查询对应且 ZIP 签名通过，结果才为 `status: collected`，同时保存文件大小及 SHA256。导出未完成为 `export_pending`；仅观察而未要求导出为 `observed`；空结果为 `empty`；不能证明响应切换为 `unresolved`。不把缺失搜索量补零。导出失败先读当前状态，调用方决定是否仅重新导出，不能重跑整个旧回合。

`native_amazon_discovery_chain.mjs` 的 `captureSellerChain(task, page, observedProduct, {outputDirectory, prefix})` 沿实际商品 Seller 链接、公开 Seller 主页、该主页实际店铺链接采集。输入商品应含已观察到的 `ui.asin/url/delivery/sellerLinks`。逐步核对 HTTPS Amazon 域名、相同 seller token 和 US75020。输出公开 Seller 信息、店铺商品标题/ASIN/图片/可见增强数据以及来源链。不推断品牌、日期或商业可行性。

同模块 `searchTitleGlobally(page, {query, sourceTitle, sourceAsin, keywordType?, basis?}, {outputDirectory, prefix})` 先点击实际 Amazon 主页标志清除店铺过滤，再搜索标题开头。返回结果必须不含 `m`、`me` 或 `s=merchant-items`。扩展词显式传 `keywordType: expanded` 和可核对的 `basis`，保留原 `sourceTitle`，不能把扩展词冒充原商品标题。原生店铺搜索会保留 merchant 范围，不能仅因搜索框显示 All 就称全站搜索。

当前批次原始回合仅作为历史证据保留；复用上述模块编排新回合，不重放旧脚本。隔离检查：`node --test automation/native_sellersprite_research.test.mjs automation/native_amazon_discovery_chain.test.mjs`。
