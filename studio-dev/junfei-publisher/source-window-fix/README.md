# 钧飞1688货源标签归属修复

适用：钧飞跨境采集插件 2.9.60 的未打包安装版。修复 `getTaobaoAddr` 和 `getAddr` 消息打开货源搜索时未指定窗口、因而跟随当前窗口的问题。

每次请求从消息发送者保存 tab ID 和 window ID。打开前重新核对原标签仍在原窗口；将新标签绑定原窗口、设置 opener，并在后台打开。原标签关闭、移动或身份缺失时停止，禁止回退到当前窗口。

`automation/patch_junfei_source_window.py` 校验原始文件哈希和版本后备份并修改 service worker，另安装 `source-tab-window.mjs`。不会修改权限、账号或 Cookie。插件升级可能覆盖本修复，未知版本须重新审计，不直接套用。

2026-11-06 已应用到 EGO 实际加载目录 `C:/Users/Administrator/Downloads/钧飞跨境-采集插件 V2.9.60` 及项目缓存副本，并重新加载该扩展。真实点击 B0HN4SH3MS 的“1688货源”后，新标签 p8 与来源 p4 的 windowId 一致，且属于专属 TaskSpace4。证据：`outputs/cyclic30-20261106/junfei-plugin-window-fix/live-click-result.json`。这是这条入口的验证，不代表所有第三方插件都已修复。

验证命令：

```powershell
node --test junfei-publisher/source-window-fix/test-source-tab-window.mjs
py -3 -m unittest discover -s automation -p "test_*.py"
```

恢复原版：先核对 `installed-backup/patch-evidence.json` 所指目录和当前修改哈希，再将同目录 `service_worker.original.js` 恢复为插件 `js/service_worker.js`，并在扩展页面重新加载。保留备份；不要对不认识的新版文件直接覆盖。
