# 钧飞 ERP 独立刊登窗口

双击 `启动刊登窗口.vbs`，或运行 `py -3 app.py`。需要 Python 3.10+（含 Tk）和 Node.js 22+，目标浏览器为 Microsoft Edge。

## 当前实现与边界

独立窗口可选择产品 JSON、显示店铺/站点/变体、安装依赖、本地校验、生成等比例最短边1600像素的图片副本，并从独立入口修改已存在的草稿。原图不改动。定价、颜色尺码、SKU和文案校验复用已有店小秘引擎。

**钧飞 ERP 页面尚未适配，不能直接一键上架。** `recipe.json` 是待校准配置，包含店小秘流程示意，不是钧飞真实字段。未校准时窗口阻止保存/发布；不要仅将 calibrated 改为 true。需要针对钧飞实际页面补齐类目、创建变体、全部附图、必填属性、运费模板以及保存和提交结果断言，并用真实草稿验证。

## 使用

大脑执行器默认使用程序目录下独立的 `brain-state/edge-profile`。需要升级执行器并保留专属 Edge 登录状态时，可在 `brain-state/edge-profile.path` 写入旧专属配置的绝对路径，或设置 `JUNFEI_EDGE_PROFILE_DIR` 环境变量。**同一 Edge 配置同时只能由一个执行器使用**；启动新版前先完全关闭旧版浏览器和 worker。该目录含登录会话，不要分享或同步到云端。

1. 点击“安装依赖”。
2. 参考 `products.example.json` 创建真实产品 JSON（数组）；图片路径相对于 JSON 所在目录。每个产品明确填写店铺、站点、币种、SKU、文案、运费模板、颜色尺码、图片、库存。示例内容不能发布。Word和散装文件夹的自动识别暂未实现。
3. 点击“本地预检”，输出在产品 JSON 同目录 `junfei-output`；检查 plan.json 和 images 图片副本。仅 USD 可根据成本重量计算售价，其它币种须明确提供价格。颜色与图片仍需人工确认。
4. “修改已有草稿”接受单独请求 JSON，先做本地检查，再显示草稿ID、店铺、ERP SKU和修改字段供确认。只支持已校准的现有草稿字段，不创建新品或提交发布。引擎启动独立 Edge 登录会话，手动登录后按提示继续。不读取现有 Edge 密码，不在源码保存凭据。
5. 保存/提交有未知结果时停止批次。已有执行记录的产品会跳过；不要修改 id 或删除记录强制重发。submitted 仅表示提交，不能代表亚马逊在线。

页面配置支持 goto、fill、click、select、check、upload、assertText、assertValue、assertCount 和 eachVariant。配置中的操作会真实点击网页，只使用经过核对的本地可信配置。参考原引擎 `D:\亚马逊智能体\dianxiaomi-auto` 与店小秘操作流水线；不直接沿用其选择器、店铺和站点授权。

`junfei-output/browser-profile` 包含登录会话，请勿分享；输出含产品计划与执行证据。此工具不自动跨站、不移动原资料、不清理图片空间、不定时重试。关闭窗口可能中断提交，须人工核对实际状态。

验证：`node --test`；`py -3 -m py_compile app.py`。

## 已有草稿修改适配器（2026-11-01）

`existing-draft.mjs` 是独立入口，桌面窗口的“修改已有草稿”按钮会调用它；脚本直接使用已观察的钧飞表单定位，不依赖未校准的通用 recipe。仅修改明确指定的已有草稿，不创建商品或发布。请求 JSON 结构如下（实际店铺和 ERP SKU 必须与页面完全一致）：

```json
{"draftId":"明确的草稿ID","store":"明确的店铺","erpSku":"ERP列表实际SKU","patch":{"price":"7.69","quantity":"88"}}
```

运行 `node existing-draft.mjs --request request.json` 只校验请求，不操作 ERP。加 `--run --output 独立任务目录` 才打开独立 Edge 登录窗口执行。内置浏览器的登录不会转移到此窗口。允许 patch 字段为 title、description、price、quantity、handlingDays；值必须明确，不操作分类、品牌、运费模板或产品属性。

适配器先核对编辑地址、店铺、ERP SKU，填写后断言；保存前持久记录 saving_unknown，之后核对成功提示、同一草稿列表行且为未发布，重新打开检查持久值，才记录 draft_saved_verified。输出 record.json 和 result.png，登录资料仅在该任务 browser-profile。任务目录独占锁和已有记录阻止重复执行；异常退出遗留的锁或未知记录须先核对 ERP，不能删记录重试。

真实人工页面已验证旧草稿172528873的编辑、保存、列表和重开（见 automation/data/junfei-draft-reconciliation-20261101.json）。**新适配器仅通过模拟页面和故障注入测试，尚未真实浏览器端到端验证，也尚未接入网页任务中心。** 2026-11-01尝试复用内置浏览器时控制连接不可用，适配器未触发保存。通用 recipe 继续保持 calibrated=false。

独立 EXE：`D:/AmazonAgentReleases/20261101-junfei-tabs/JunfeiDraftAgent/JunfeiDraftAgent.exe`，桌面快捷方式 `D:/桌面/钧飞草稿修改工具.lnk`。EXE包含本地 Python/Tk 界面、Node.js、Playwright及脚本依赖，无须系统安装Python或Node。Microsoft Edge仍需已安装。2026-11-01修复专属 Edge 被关闭后 worker 仍报告 ready 并占锁的问题，并让执行器跟随新开的结果标签页、在标签关闭时回退到其他活动标签；新增标签页的URL仍必须通过精确来源白名单。生命周期、标签页跟踪、URL策略及桌面执行器测试通过，真实页面端到端流程仍待验证。

执行器网络白名单按精确来源校验：钧飞 ERP、本机工作台，`https://s.1688.com`、`https://www.1688.com` 和 `https://detail.1688.com`，以及 1688 图片搜索专用路由 `https://air.1688.com/kapp/1688-search/pc-image-search/`。`air.1688.com` 其它路径、1688 登录、购物车、订单和付款域名不在白名单。修改白名单后运行 `npm run check`，并将 `brain-worker.mjs`、`brain-url-policy.mjs` 及其依赖模块一起更新至独立版 `_internal` 目录。

2026-11-02 实测校准：旧洗漱包草稿172528873通过专属Edge队列完成颜色、尺寸修正及保存后重开核对，仍未发布。参数栏EVA与图片PVC冲突，材质已清空；尺寸图130×130×220mm，属性长5.12、宽5.12、高8.66英寸。证据：automation/data/junfei-dimensions-fix-20261102.json。

existing-draft新增patch字段color、material、widthInches、heightInches、lengthInches。属性需在evidence对象中逐字段写来源；material允许空串以清除冲突值。尺寸仅在页面单位精确为英寸(Inches)时写入，最多两位小数且为正数，不修改单位。下拉选项唯一完整匹配。新字段纳入保存前断言、未知状态留存、保存后重开核对。真实HTML隔离回放通过；新版脚本真实会话端到端仍待验证，未接入网页任务中心，新品recipe保持未校准。

## 当前ego文案草稿工具（2026-11-02）

用户当前专属浏览器为ego，以上Edge入口属于历史实现。当前桌面“钧飞ERP-ego专属版.lnk”指向D:/AmazonAgentReleases/20261102-ego-copy-fields/JunfeiDraftAgent/JunfeiDraftAgent.exe；“修改已有草稿”读取请求JSON，经ego_link和ego-existing-draft.mjs在已有ego工作区执行。没有Edge回退，不创建新商品或发布。

patch允许title、highlights、bullets（恰好五条单行字符串）、description、terms，evidence须逐字段说明来源。标题75、亮点125、五点每条500、描述2000字符，后台词最多249 UTF-8字节。身份和五点/关键词所属表单结构先核对；保存前持久化save_unknown，保存后核对未发布列表身份并重开逐项比较，同时核对售价、库存、处理时间及运费模板未变化。相同身份和目标内容的回执阻止改名重放。

真实实测使用账号1工作台产品ERP-172528873的事实编辑稿，保存至示例店铺-美国草稿172528873，ERP SKU MTkzMzU-I18DXZWC，五项文案均重开验证一致，published=false。回执为automation/data/ego-draft-executions/2aebc8439530061dfa178e0e2585d69c7f853df8601998ed252da4cfd5574911.json。8项ego适配测试、完整39项Node测试、4项桌面连接测试及新EXE连接检查通过。网页任务中心未接入此执行器；图片上传、新品创建及发布仍未完成。
# 图片库保存适配（2026-11-02 源码更新）

Python入口 `ego_link.ego_image_command(request_path, save_library=False)` 返回准备好的ego命令，不执行浏览器。默认只暂存；保存必须显式选save_library=True且仅允许审核/权利通过的商品图片。请求JSON只含draftId、store、erpSku、assets，assets字段沿用JS执行器定义。调用方负责账号与产品绑定、生产前置检查及授权，不能把此低层入口直接暴露给网页客户端。执行器共用ego-workbench.lock；异常保留锁，须先核查原操作，不删除锁或改文件重试。

`ego-draft-images.mjs` 提供两个分离入口：`stageImageLibrary` 上传暂存并回读远端SHA256；`saveStagedImageLibrary` 只保存全部审核/权利通过的真实商品图片库，并重开同一未发布草稿核对图库顺序、尺寸、文案与经营字段。后者拒绝校准图、未知上传和缺完整文案快照的旧回执。两者分别需要独占持久回执，不能在未知结果后建立新回执重发。

图片库保存不等于变体图片分配或整款刊登完成。此更新尚未接入工作台、打包EXE或做真实生产图片保存校准；不得用校准图片验证生产保存。



2026-11-02 产品库变体读取修复（源码，未部署）：实测Element UI表头/表体分表，变体四个输入均为placeholder；ego-library-draft.mjs改按表头及列位置读取SKU/颜色/尺寸/价格和图片，暂存/保存核对包括变体快照，非空变体表停止以免覆盖。实际只添加空行检查后关闭未保存表单，没有第三次保存。证据automation/data/erp-library-variant-reader-live-20261102.json；36项Node适配和21项流程回归通过。尚未证明422原因，也未完成新品创建。
