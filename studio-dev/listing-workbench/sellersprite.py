"""SellerSprite Streamable HTTP MCP client. Credentials stay on the local server."""
import json
import os
import re
import threading
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, parse_qs, urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler
import secrets_store
import sellersprite_cache

ENDPOINT = 'https://mcp.sellersprite.com/mcp'
KEY = secrets_store.load('sellersprite') or os.environ.get('SELLERSPRITE_MCP_KEY', '')
LOCK = threading.Lock()


def key_value(value):
    if not isinstance(value, str) or len(value) > 4000 or any(c in value for c in '\r\n'):
        raise ValueError('卖家精灵 MCP 密钥格式不正确')
    value = value.strip()
    if value.startswith('https://'):
        parsed = urlsplit(value)
        if parsed.hostname != 'mcp.sellersprite.com' or parsed.path != '/mcp' or parsed.port not in (None, 443) or parsed.username:
            raise ValueError('请使用官方 MCP 快速集成 URL 或单独密钥')
        value = parse_qs(parsed.query).get('secret-key', [''])[0]
        if not value:
            raise ValueError('快速集成 URL 未包含 secret-key')
    if not value.isascii() or any(c in value for c in '\r\n'):
        raise ValueError('密钥应为英文字符，请核对复制内容')
    return value


def current_key():
    # Read on each request: existing account workers immediately see admin changes.
    return secrets_store.load('sellersprite') or os.environ.get('SELLERSPRITE_MCP_KEY', '')


def public():
    return {'hasKey': bool(current_key()), 'endpoint': ENDPOINT, 'provider': '卖家精灵 MCP', 'shared': True, 'cache': sellersprite_cache.stats()}


def configure(data):
    global KEY
    value = key_value(data.get('api_key', ''))
    with LOCK:
        if data.get('clearKey'):
            secrets_store.save('sellersprite', '')
            KEY = ''
        elif value:
            secrets_store.save('sellersprite', value)
            KEY = value
    return public()


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Client:
    def __init__(self, key=None):
        self.key = key if key is not None else current_key()
        if not self.key:
            raise ValueError('请先在模型设置中保存卖家精灵 MCP 密钥')
        self.session = None
        self.version = '2024-11-05'
        self.tools = {}

    def rpc(self, method, params=None, notification=False):
        request_id = uuid.uuid4().hex
        body = {'jsonrpc': '2.0', 'method': method}
        if not notification:
            body['id'] = request_id
        if params is not None:
            body['params'] = params
        headers = {'secret-key': self.key, 'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream'}
        if self.session:
            headers['Mcp-Session-Id'] = self.session
        if method != 'initialize':
            headers['MCP-Protocol-Version'] = self.version
        # Match the official quick-integration URL; keep the URL out of logs.
        endpoint = ENDPOINT + '?' + urlencode({'secret-key': self.key})
        request = Request(endpoint, data=json.dumps(body).encode(), headers=headers, method='POST')
        try:
            with build_opener(NoRedirect()).open(request, timeout=90) as response:
                if response.headers.get('Mcp-Session-Id'):
                    self.session = response.headers['Mcp-Session-Id']
                if notification:
                    return {}
                if 'text/event-stream' in response.headers.get('Content-Type', ''):
                    parts, consumed = [], 0
                    for raw in response:
                        consumed += len(raw)
                        if consumed > 8 * 1024 * 1024:
                            raise ValueError('MCP 返回数据过大')
                        line = raw.decode('utf-8').rstrip('\r\n')
                        if line.startswith('data:'):
                            parts.append(line[5:].lstrip())
                        elif not line and parts:
                            result = json.loads('\n'.join(parts)); parts = []
                            if isinstance(result, dict) and result.get('id') == request_id:
                                return self.result(result)
                    if parts:
                        result = json.loads('\n'.join(parts))
                        if isinstance(result, dict) and result.get('id') == request_id:
                            return self.result(result)
                    raise ValueError('MCP 未返回对应请求的结果')
                raw = response.read(8 * 1024 * 1024 + 1)
                if len(raw) > 8 * 1024 * 1024:
                    raise ValueError('MCP 返回数据过大')
                result = json.loads(raw)
                if not isinstance(result, dict) or result.get('id') != request_id:
                    raise ValueError('MCP 响应编号不匹配')
                return self.result(result)
        except HTTPError as error:
            if 300 <= error.code < 400:
                raise ValueError(f'卖家精灵 MCP 返回 HTTP {error.code} 跳转，连接地址或服务网关需要核对；这不能证明密钥或额度有问题。未跟随跳转，避免泄露密钥') from None
            raise ValueError(f'卖家精灵 MCP 返回 HTTP {error.code}；请求未成功，不能仅凭此判断额度不足。请核对鉴权方式和服务状态；未自动重试') from None
        except (URLError, TimeoutError):
            raise ValueError('卖家精灵 MCP 连接失败或超时；未自动重试，请先核对额度消耗') from None
        except (json.JSONDecodeError, UnicodeError):
            raise ValueError('卖家精灵 MCP 返回格式无法解析') from None

    @staticmethod
    def result(message):
        if 'error' in message:
            raise ValueError('卖家精灵 MCP 拒绝请求，请检查密钥、工具权限及参数')
        if not isinstance(message.get('result'), dict):
            raise ValueError('MCP 结果格式不正确')
        return message['result']

    def connect(self):
        init = self.rpc('initialize', {'protocolVersion': self.version, 'capabilities': {}, 'clientInfo': {'name': 'junfei-listing-workbench', 'version': '1.0'}})
        self.version = init.get('protocolVersion', self.version)
        self.rpc('notifications/initialized', notification=True)
        cursor = None
        for _ in range(10):
            listing = self.rpc('tools/list', {'cursor': cursor} if cursor else {})
            for tool in listing.get('tools', []):
                if isinstance(tool, dict) and isinstance(tool.get('name'), str):
                    self.tools[tool['name']] = tool
            cursor = listing.get('nextCursor')
            if not cursor:
                break
        return self

    def call(self, name, arguments):
        return sellersprite_cache.get_or_fetch(name,arguments,lambda:self._call_remote(name,arguments))

    def _call_remote(self, name, arguments):
        if name not in self.tools:
            raise ValueError('当前 MCP 未提供 '+name+' 工具，请核对套餐权限')
        schema = self.tools[name].get('inputSchema', {})
        props = schema.get('properties', {})
        # SellerSprite exposes some tools with a nested request DTO.
        if 'request' in props and props['request'].get('type') == 'object' and 'request' not in arguments:
            request_schema = props['request']
            request_props = request_schema.get('properties', {})
            request = {k: v for k, v in arguments.items() if k in request_props}
            if any(k not in request for k in request_schema.get('required', [])):
                raise ValueError(name+' 工具参数定义发生变化，请更新对接')
            arguments = {'request': request}
        arguments = {k: v for k, v in arguments.items() if k in props}
        if any(k not in arguments for k in schema.get('required', [])):
            raise ValueError(name+' 工具参数定义发生变化，请更新对接')
        result = self.rpc('tools/call', {'name': name, 'arguments': arguments})
        if result.get('isError'):
            raise ValueError('卖家精灵 '+name+' 查询失败，请检查站点、ASIN、权限或剩余额度')
        payload = result.get('structuredContent')
        if payload is None:
            text = '\n'.join(c.get('text', '') for c in result.get('content', []) if c.get('type') == 'text')
            try:
                payload = json.loads(text)
            except (json.JSONDecodeError, TypeError):
                raise ValueError('卖家精灵工具未返回可解析的 JSON 数据') from None
        if not isinstance(payload, dict):
            raise ValueError('卖家精灵数据格式不正确')
        if 'code' in payload and payload['code'] != 'OK':
            code = str(payload['code'])
            allowed = {'ERROR_SECRET_KEY', 'ERROR_SECRET_KEY_OVERDUE', 'ERROR_VISIT_MAX', 'ERROR_SECRET_KEY_INVALID', 'ERROR_PARAM'}
            raise ValueError('卖家精灵查询失败：'+(code if code in allowed else '请检查权限、额度及查询参数'))
        data = payload.get('data', payload)
        if not isinstance(data, dict):
            raise ValueError('卖家精灵未返回有效商品数据')
        return data


def test_key(data):
    key = key_value(data.get('api_key', '')) or current_key()
    client = Client(key).connect()
    names = sorted(client.tools)
    return {'ok': True, 'tools': names, 'supported': all(n in names for n in ('asin_detail', 'traffic_keyword')), 'message': '✓ MCP 连接成功，已获取工具列表。尚未执行商品查询；实际查询权限和额度需运行后确认。'}


BULLET_SEARCH_RANGE = (500, 8000)


def mine_keywords(seeds, market, *, search_range=None):
    client = Client().connect()
    page_limit = 2 if search_range else 5
    filters = {}
    if search_range:
        schema = client.tools.get('keyword_miner', {}).get('inputSchema', {}).get('properties', {})
        props = schema.get('request', {}).get('properties', schema)
        if not {'minSearch', 'maxSearch'} <= props.keys():
            raise ValueError('当前卖家精灵关键词挖掘接口不支持月搜区间')
        filters = dict(zip(('minSearch', 'maxSearch'), search_range))
    results = []
    fields=('keyword','keywordCn','searches','products','updatedTime','purchases','purchaseRate','trafficPercentage','month','conversionKeywordType','relevancy')
    for seed in list(dict.fromkeys(seeds))[:3]:
        entry={'seed':seed,'items':[],'status':'failed','pages':0,'pageLimit':page_limit}
        if search_range:
            entry['searchRange'] = list(search_range)
        seen=set()
        for page in range(1,page_limit+1):
            try:
                data=client.call('keyword_miner',{'marketplace':market,'keyword':seed,'page':page,'size':100,
                                                  'order':{'field':'searches','desc':True},**filters})
                rows=[item for item in (data.get('items') or []) if isinstance(item,dict) and isinstance(item.get('keyword'),str)][:100]
                added=0
                for item in rows:
                    if search_range:
                        try:
                            searches = float(item.get('searches'))
                        except (ValueError, TypeError):
                            continue
                        if not search_range[0] <= searches <= search_range[1]:
                            continue
                        item = {**item, 'searches': searches}
                    key=' '.join(item['keyword'].casefold().split())
                    if key and key not in seen:
                        seen.add(key);entry['items'].append({k:item.get(k) for k in fields});added+=1
                entry.update(total=data.get('total'),status='ok',pages=page)
                total=data.get('total')
                if not rows or not added or len(rows)<100 or isinstance(total,(int,float)) and page*100>=total:break
            except ValueError as error:
                entry['error']=str(error)
                entry['status']='partial' if entry['items'] else 'failed'
                break
        entry['truncated']=entry['pages']==page_limit and (not isinstance(entry.get('total'),(int,float)) or len(entry['items'])<entry['total'])
        results.append(entry)
    return results


def read_sources(asins, market):
    client = Client().connect()
    sources = []
    for asin in asins:
        source = {'asin': asin, 'url': 'https://www.amazon.'+{'US':'com','UK':'co.uk','JP':'co.jp','DE':'de','FR':'fr','IT':'it','ES':'es','CA':'ca','IN':'in','MX':'com.mx'}[market]+'/dp/'+asin, 'provider': 'SellerSprite MCP', 'title': '', 'bullets': [], 'description': '', 'brand': '', 'keywordData': [], 'limitations': [], 'status': 'failed'}
        try:
            item = client.call('asin_detail', {'marketplace': market, 'asin': asin})
            source.update(title=str(item.get('title') or '')[:2000], brand=str(item.get('brand') or ''), bullets=[x[:6000] for x in (item.get('features') or []) if isinstance(x, str)][:10])
            # overviews is an attribute JSON string, not the product description.
            source['limitations'].append('卖家精灵 ASIN 详情未提供产品描述正文，未把属性或 A+ 标识当作描述')
        except ValueError as error:
            source['limitations'].append(str(error))
        try:
            traffic = client.call('traffic_keyword', {'marketplace': market, 'asin': asin, 'page': 1, 'size': 100})
            source['keywordData'] = [{field: k.get(field) for field in ('keyword', 'keywordCn', 'searches', 'products', 'rankPosition', 'updatedTime', 'purchases', 'purchaseRate', 'trafficPercentage', 'month', 'conversionKeywordType', 'relevancy')} for k in (traffic.get('items') or []) if isinstance(k, dict) and isinstance(k.get('keyword'), str) and 1 <= len(k['keyword']) <= 200][:100]
            source['keywordTotal'] = traffic.get('total')
            source['limitations'].append('每个 ASIN 仅读取第 1 页，最多 100 个反查词；非全量关键词')
        except ValueError as error:
            source['limitations'].append(str(error))
        source['status'] = 'ok' if source['title'] or source['keywordData'] else 'failed'
        if source['status'] == 'failed':
            source['error'] = '卖家精灵暂未返回可用商品详情或反查词，可能尚未收录或采集未完成；这不表示 ASIN 无效。' + '；'.join(source['limitations'])
        sources.append(source)
    return sources
