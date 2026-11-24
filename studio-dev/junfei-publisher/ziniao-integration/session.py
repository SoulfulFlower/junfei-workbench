"""连接已由官方 startBrowser 启动的紫鸟；不重启店铺、不读取凭据。"""
import json
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
ROOT=Path(__file__).resolve().parent
def connect():
    state=json.loads((ROOT/'running.local.json').read_text(encoding='utf-8'))
    if str(state.get('statusCode'))!='0':raise RuntimeError('没有成功启动的紫鸟店铺')
    port=int(state['debuggingPort'])
    if not 1<=port<=65535:raise ValueError('无效端口')
    options=webdriver.ChromeOptions()
    options.add_experimental_option('debuggerAddress',f'127.0.0.1:{port}')
    return webdriver.Chrome(service=Service(str(ROOT/'drivers/chromedriver.exe')),options=options)
