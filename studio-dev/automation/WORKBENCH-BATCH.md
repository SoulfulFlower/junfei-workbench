# 当前批次脚本入口

用户2026-11-17要求把稳定流程固化，后续优先复用这些入口。当前已在真实账号2执行批量状态、追加货源与原双站刷新；任务与文件回执在本批`batch-runs`保留。

`workbench_batch.py`复用本批`spaces.json`中已核验的工作台账号和页面。一次运行集中读取货源队列、多个货源结果与多个原刊登任务，每次保留新的UTF-8 EGO round及完整JSON回执。

```powershell
python -X utf8 studio-dev/automation/workbench_batch.py status --session research-batch3-20261117/spaces.json --supplier https://detail.1688.com/offer/1090760227673.html --job b99a3ee5ddd74995acb19bc585435bc0 --job 5a545c9f526a4a14a4f77ca59cd47efa --output-dir research-batch3-20261117/batch-runs
```

追加货源使用` supplier-add --execute`，重复`--supplier`可一次入队多款。详情页面完全由正式供应商队列打开，仍保留90秒间隔。已采集/已排队结果直接复用；请求未知保留原意图，不自动再请求。

原刊登刷新使用`observe --execute --job 原任务ID`，要求账号一致、两个原站点任务号已存在且后台允许观察。一次只调度一个原任务；ERP有其他RPA或后台任务时先等待其释放。该动作只通过正式`observeOnly`重新读取原刊登，不保存商品、不重试发布、不复制草稿。

空间丢失、用户接管、登录或验证码按实际状态停止，不新建浏览器、不读取登录秘密。脚本不会启动文案/生图/采集交付/新发布；这些阶段继续使用已有正式模块的事实与版本检查。未知原任务、图像缺资料、货源版型不符必须保留阻断，不能靠脚本造数补齐。

`supplier_image_review.py --capture 已采结果.json --output-dir 图片目录`只读队列已经观察到的公开图片，批量保存原图、SHA及核对拼版。不会请求1688详情页或把下载成功当同款通过。每份输入支持正式API的`body.supplier`或` supplier`结构。

`candidate_pricing.py --spec 本款事实.json --config 当前经营配置.json --quote-root 报价目录 --output 核算.json`按实际包装三维与重量取大、匹配US/UK服装档位、采购及国内运费分别计入。GBP汇率必须是本次中国执行日的中行现汇卖出价，保留来源。市场价利润单独计算，不能拿公式自动加价的正利润代替市场判断。

`native_sellersprite_research.mjs`提供正常US页面`collectNativeReverse`和`collectNativeMining`，传实际Page、候选与ASIN/关键词、绝对输出目录。保留来源与ASIN/US75020/模式校验，结果行标记`visibleRows`；完整数据以原生XLSX及SHA为准。有结果但未收到下载时为`export_pending`，禁止自动循环查询。

`ziniao_inventory_observe.py`通过紫鸟原生CLI的Seller Central可见多SKU筛选读取旧刊登状态。先用原input/受理/在线回执核对真正的父子SKU清单，再传`--expected`（`{accountId:2,families:[{parentSku,children:[{sku}]}]}`）、原`--parent-sku`、店铺/target/seller/market及输出路径。实际核唯一可见市场头及精确筛选集合，记录每行ASIN、状态列、原文和列标题，不保存商品、不上传、不重发、不读取隐藏表单。短暂加载只在同页有限读取；`--observe-current`完全不再导航。

出现“正在加载商品”或同类英文加载状态时，即使仍残留上一轮匹配行也返回`pending`，不报告完整状态；同页有限等待后仍未完成会保留回执并以退出码2停止。外层批处理应检查退出码，不能继续导航下批而丢失这次待核对状态。页面完成后的新只读回执单独保存，旧加载回执保留。

本批Nov18已真实核美国原外套3子、荷叶边75子（5批各15）、罗纹30子，共108；英国荷叶边75子与罗纹30子，共105。批次结果必须按原完整集合合并核对：无缺漏、无重复、无多SKU歧义；历史已知ASIN精确匹配，原先未知的ASIN单独记新观测，不能拿US ASIN当UK历史绑定。`coverageVerified`只说明集合齐全，仍要检查实际状态列；不能把“受理”“在售”“完善商品信息”“缺少的信息”与“被禁止搜索”混为一类，也不能据此跳过图片交付合同或称以后永久无错误。完整证据见`research-batch3-20261117/independent-original-US108-native-summary-20261118.json`和`independent-original-UK105-native-summary-20261118.json`；产品状态会变化，后续仍以同原SKU最新观察为准。

`native_supplier_observation.mjs`提供 `observeCurrentSupplier(page, {offerId})`，用于补读正式串行队列当前已经打开的同一货源详情页。调用者从该队列的实际绑定取 Page，并传明确的原 offer ID；模块不寻找或新建工作区。它在读取前、页面内及返回后严格核对 HTTPS、`detail.1688.com` 和原 `/offer/ID.html`，不导航、刷新、选色、滚动、加载图片、调用接口或操作采购。验证提示会报 `SUPPLIER_HUMAN_VERIFICATION_REQUIRED`，调用者按原队列规则停止并交还，不继续另一条路径。

```javascript
const {observeCurrentSupplier} = await import('file:///C:/Users/Administrator/Documents/ChatGPT/%E9%92%A7%E9%A3%9E%E5%B7%A5%E4%BD%9C%E5%8F%B0/studio-dev/automation/native_supplier_observation.mjs');
// page 来自当前正式供应商队列绑定；offerId 必须来自本次已采原记录。
const observation = await observeCurrentSupplier(page, {offerId: '771375926367'});
```

结果保留完整 `fullVisibleText`，避免白名单丢掉普通价、PLUS、首单券、起订量和国内运费语境；同时返回当前 `selectedColourNames/selectedColours`、全部 `colourButtons`、当前真实 `skuRows`、不设字段白名单的属性及原始属性表、`packagingTables` 和当前 DOM 已观察的公开供应商 CDN 图片。属性投影之外保留 `attributeEntries/attributeSections/attributeSummary` 供核对原文。缺失或尚未挂载的内容留空，不自动加载或推断；选色后须由调用者核对原生 UI 已稳定，再以当前选色和报价共同判断适用范围。观察不自动改变采购成本、产品事实、生产颜色或资格状态。

2026-11-17已在正式队列22/p1原货源771375926367实际执行只读核对：黑色平口、10色按钮、13条SKU报价、45项属性（含7项顶部参数）、1张件重表、56个已观察图片URL，完整文本3977字。原页面与控制保留；证据为 `research-batch3-20261117/native-supplier-observation-actual-029.json`，DOM选择器依据为 `native-supplier-summary-dom-028.json`。此回执仅证明该次读取，不保证其他货源数据完整，也不把展示价视为结算价。
