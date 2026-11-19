# 紫鸟官方 WebDriver 接入

官方开通文档：https://open.ziniao.com/docSupport?docId=99
官方接口文档：https://open.ziniao.com/docSupport?docId=98

本机紫鸟：6.26.6-latest.26。用户已确认开通 WebDriver 权限。
已安装隔离 Python 环境，含 Selenium 4.52.0、requests 2.34.2。
官方示例已下载至 vendor，仅供参考，未执行。

须先正常退出紫鸟和店铺窗口，再以以下参数启动现有客户端：
`--run_type=web_driver --ipc_type=http --port=19886`

运行 `.venv/Scripts/pythonw.exe connect.py`，在本地窗口填写紫鸟公司名、用户名、密码，检查 updateCore 和 getBrowserList。
密码只用于本机官方接口请求，不持久化；店铺列表保存为 shops.local.json 并已忽略版本控制。
当前只实现连接预检，不会启动店铺、切站、提交商品。
Chromedriver 须在取得店铺实际 core_version 后匹配安装。
