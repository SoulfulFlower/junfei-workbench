"""Smoke-test a packaged desktop build without touching the user's data."""
import argparse
import http.cookiejar
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import time
import urllib.request
import zipfile


def request(opener, url, method='GET', body=None):
    data = None if body is None else json.dumps(body).encode('utf-8')
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={'Content-Type': 'application/json'} if data is not None else {})
    with opener.open(req, timeout=5) as response:
        return response.read()


def smoke(executable, port):
    executable = Path(executable).resolve(strict=True)
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', port))
    with tempfile.TemporaryDirectory(prefix='amazon-agent-smoke-') as temp:
        env = os.environ.copy()
        env.update(JUNFEI_ACCOUNT_DATA=temp, JUNFEI_PORT=str(port), JUNFEI_OPEN_BROWSER='0')
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        process = subprocess.Popen([str(executable)], cwd=temp, env=env, creationflags=flags)
        base = f'http://127.0.0.1:{port}'
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        try:
            for _ in range(60):
                if process.poll() is not None:
                    raise RuntimeError(f'Packaged app exited early with code {process.returncode}')
                try:
                    health = json.loads(request(opener, base + '/api/desktop-health'))
                    if health.get('app') == 'amazon-listing-workbench':
                        break
                except Exception:
                    time.sleep(.5)
            else:
                raise RuntimeError('Packaged app did not become healthy within 30 seconds')

            username = 'smoke' + secrets.token_hex(5)
            password = secrets.token_urlsafe(24) + 'Aa1!'
            credentials = {'username': username, 'password': password, 'name': 'Smoke Test'}
            request(opener, base + '/api/auth/setup', 'POST', credentials)
            request(opener, base + '/api/auth/login', 'POST', credentials)
            budget = json.loads(request(opener, base + '/api/image/budget'))
            if (budget.get('currency') != 'CNY' or budget.get('reservations') != []
                    or budget.get('limits', {}).get('perProductFen') != 500
                    or budget.get('limits', {}).get('dailyFen') != 20000
                    or budget.get('limits', {}).get('enabled') is not False):
                raise RuntimeError('Packaged image budget does not match the configured CNY5/CNY200 disabled policy')
            selection_ui = request(opener, base + '/selection.js').decode('utf-8')
            if '智能体自动挑选前10个并启动核验' not in selection_ui:
                raise RuntimeError('Packaged app is missing the automatic candidate triage workflow')
            agent_ui = request(opener, base + '/agent-center.js').decode('utf-8')
            if '供应商图默认可用' not in agent_ui or '确认图片使用权或已获得供应商许可' in agent_ui:
                raise RuntimeError('Packaged sourcing UI does not reflect the user supplier-image policy')
            archive = request(opener, base + '/api/auth/extension-download')
            with zipfile.ZipFile(__import__('io').BytesIO(archive)) as bundle:
                manifest = json.loads(bundle.read('extension/manifest.json'))
                popup = bundle.read('extension/popup.js')
                if manifest.get('version') != '0.7.11' or 'clipboardWrite' not in manifest.get('permissions', []):
                    raise RuntimeError('Downloaded extension version or permissions are incorrect')
                if b'copyAmazonReferenceToClipboard' not in popup or b'navigator.clipboard.write' not in popup or b'chrome.tabs.create' not in popup or b'linkedAsin' not in popup or b'clearAssociation' not in bundle.read('extension/popup.html') or b'uploadReference' not in popup or b'input.files=transfer.files' in popup:
                    raise RuntimeError('Downloaded extension is missing the image-search handoff')
                if b'captureAmazon' not in popup or b'/api/selection/capture' not in popup:
                    raise RuntimeError('Downloaded extension is missing Amazon page observation capture')
                if b'openFrontSearch' not in popup or b'captureFrontSearch' not in popup:
                    raise RuntimeError('Downloaded extension is missing Amazon title-search observation capture')
                if b'captureSellerSprite' not in popup or b'browser_sellersprite_search' not in popup:
                    raise RuntimeError('Downloaded extension is missing SellerSprite page observation capture')
                if b'capture1688Search' not in popup or b'browser_1688_image_search' not in popup:
                    raise RuntimeError('Downloaded extension is missing 1688 image-search candidate capture')
                if b'is1688SearchUrl' not in popup or b'/kapp/1688-search/pc-image-search/' not in popup:
                    raise RuntimeError('Downloaded extension is missing the observed air.1688.com image-search route')
                collector = bundle.read('extension/1688-search.js')
                if (b'1688-search.js' not in bundle.read('extension/popup.html')
                        or b'func:collect1688SearchPage' not in popup
                        or b'data-renderkey' not in collector or b'priceItem' not in collector):
                    raise RuntimeError('Downloaded extension is missing the observed 1688 card collector')
                if b'captureSellerStore' not in popup or b'/api/selection/capture-seller-store' not in popup:
                    raise RuntimeError('Downloaded extension is missing Seller ID storefront observation capture')
            print('SMOKE_OK: packaged app health, isolated setup/login, disabled CNY5/product CNY200/day image budget, automatic candidate triage UI, and v0.7.11 account-scoped Amazon/SellerSprite/1688/Seller ID observations and clipboard image-search extension download')
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', required=True, help='Path to the packaged AmazonAgent.exe')
    parser.add_argument('--port', type=int, default=18766, help='Unused localhost port (default: 18766)')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('port must be between 1024 and 65535')
    smoke(args.exe, args.port)

