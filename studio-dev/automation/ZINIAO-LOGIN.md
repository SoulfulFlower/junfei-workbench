# 紫鸟站点与钧飞插件登录脚本

正式入口为 `ziniao_plugin.py`。工作台发布任务会调用同一入口，不需要逐次手工切站或打开插件。

```powershell
python -X utf8 studio-dev/automation/ziniao_plugin.py --store-id 27852913493513 --store-name "示例店铺" --market UK --seller Example Store --account "示例ERP账号" --ensure-site --allow-market-dom-click --receipt "research-e2e-20261117/uk-login-receipt.json"
```

运行目录为钧飞工作台根目录。参数 `--market` 支持 US、UK；DOM 点击属于显式方法授权，只有已获对应店铺和市场授权时才传 `--allow-market-dom-click`。当前持久授权仅覆盖账号 2 / 示例店铺 / Example Store / UK，保存在 `ziniao-market-authorizations.json`，不扩展为发布授权。

脚本按顺序核对紫鸟店铺 ID 和名称、实际 Seller Central 域名和唯一已选市场、已安装的钧飞插件入口、插件的国家/店铺/ERP 用户。菜单选项中出现英国、工具栏写英国、导航成功或点击成功都不能替代实际已选市场核验。

同店铺错市场时，授权模式可以操作已观测的市场菜单。每个控件只尝试一次；结果未知先回读，不循环重点击。已选中英国时不重新切换。登录页需要密码、验证码或其他人工验证时，失败回执会保留；脚本不读取密码、Cookie 或 Token。

`--ensure-site` 在插件身份核验后，会用同一店铺当前标签恢复目标 Seller Central 页面，再次核对唯一已选店铺/国家和 HTTPS origin，最终保留真实卖家后台页面，不让插件网页替代后台内容脚本所在文档；不创建新标签。回执保留此前 `pluginUrl` 和 `pluginObservation` 身份证明，并记录 `identityCheckOrder`、`afterPluginSelection`、`sellercentralRetained`。恢复或最终核验失败时返回非零、`loginVerified: false`、`sellercentralRetained: false`，先前插件核验仍单独留证，不能声称后台页面已恢复。

只有回执同时满足 `sellercentralConfirmed: true`、`sellercentralSelection.label: "Example Store 英国"`、英国 origin、插件英国/Example Store/示例ERP账号，以及 `sellercentralRetained: true`、`afterPluginSelection.label: "Example Store 英国"` 和对应 origin，才继续 ERP。保留卖家后台页面不等于豁免申请已完成；后台队列状态仍须用原申请回执核对。

2026-11-17 已用上述正式入口完成真实英国切站与插件登录；再次运行也通过，第二次无需市场选择。随后正式工作台原美英任务49再次实测了“站点→插件→恢复站点”顺序，英国回执 `sellercentralRetained: true` 且最终实际标签 `Example Store 英国`。本款最终美英ERP发布受理号14991361/14994125，登录脚本自身不保存商品、不上传图片、不提交刊登。
