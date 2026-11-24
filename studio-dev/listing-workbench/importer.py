"""Read public product pages from a fixed domain allowlist; never follow login redirects."""
import html
import re
from html.parser import HTMLParser
import urllib.request
from urllib.parse import urlsplit, parse_qs


MARKET_DOMAINS = {'US': 'com', 'JP': 'co.jp', 'UK': 'co.uk', 'DE': 'de', 'FR': 'fr', 'IT': 'it', 'ES': 'es', 'CA': 'ca', 'IN': 'in', 'MX': 'com.mx'}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def clean(value):
    return html.unescape(re.sub(r'\s+', ' ', re.sub('<[^>]+>', ' ', value))).strip()


def fetch(url):
    if (urlsplit(url).hostname or '').endswith('1688.com'):
        raise ValueError('1688必须使用统一浏览器采集队列，不发送独立HTTP请求')
    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept-Language': 'en-GB,en;q=0.9'})
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
        return response.read(4 * 1024 * 1024).decode('utf-8', errors='replace')


def fetch_amazon(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=12) as response:
        return response.read(4 * 1024 * 1024).decode('utf-8', errors='replace')


def parse_amazon(page):
    title = re.search(r'<span[^>]*id="productTitle"[^>]*>(.*?)</span>', page, re.S)
    name = clean(title.group(1)) if title else ''
    class Sections(HTMLParser):
        def __init__(self):
            super().__init__(); self.stack = []; self.parts = {'feature-bullets': [], 'productDescription': [], 'bylineInfo': []}
            self.breadcrumbs=[];self.breadcrumb=None
        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag not in ('img', 'br', 'hr', 'input', 'meta', 'link', 'source', 'wbr'):
                self.stack.append((tag, attrs.get('id', '')))
            if tag=='a' and any(key=='wayfinding-breadcrumbs_feature_div' for _,key in self.stack):
                self.breadcrumb={'url':attrs.get('href',''),'parts':[]};self.breadcrumbs.append(self.breadcrumb)
        def handle_endtag(self, tag):
            if tag=='a':self.breadcrumb=None
            for i in range(len(self.stack)-1, -1, -1):
                if self.stack[i][0] == tag:
                    del self.stack[i:]; break
        def handle_data(self, text):
            if any(t in ('script', 'style') for t, _ in self.stack): return
            if self.breadcrumb is not None and text.strip():self.breadcrumb['parts'].append(text.strip())
            for key in self.parts:
                if any(k == key for _, k in self.stack) and text.strip(): self.parts[key].append(text.strip())
    parsed = Sections(); parsed.feed(page)
    bullets = parsed.parts['feature-bullets']
    images = list(dict.fromkeys(re.findall(r'"hiRes"\s*:\s*"(https://[^" ]+)"', page)))[:14]
    breadcrumbs=[]
    for entry in parsed.breadcrumbs:
        label=' '.join(' '.join(entry['parts']).split())
        if not label:continue
        url=entry['url'];node=parse_qs(urlsplit(url).query).get('node',[''])[0]
        breadcrumbs.append({'name':label,'url':url,'nodeId':node if node.isdigit() else None})
    return {'title': name, 'bullets': [b for b in bullets if b], 'description': ' '.join(parsed.parts['productDescription'])[:12000], 'brand': ' '.join(parsed.parts['bylineInfo']), 'referenceImages': images,
            'category':' > '.join(row['name'] for row in breadcrumbs),
            'categoryEvidence':{'source':'amazon_wayfinding_breadcrumbs','breadcrumbs':breadcrumbs} if breadcrumbs else None}


def parse_supplier(page, url):
    import json
    class Document(HTMLParser):
        def __init__(self):
            super().__init__();self.meta={};self.scripts=[];self.parts=[];self.script=None;self.title=False;self.name=[]
        def handle_starttag(self,tag,attrs):
            attrs=dict(attrs)
            if tag=='meta':self.meta[attrs.get('property') or attrs.get('name','')]=attrs.get('content','')
            if tag=='script':self.script=[]
            if tag=='title':self.title=True
        def handle_endtag(self,tag):
            if tag=='script' and self.script is not None:self.scripts.append(''.join(self.script));self.script=None
            if tag=='title':self.title=False
        def handle_data(self,value):
            if self.script is not None:self.script.append(value)
            else:
                self.parts.append(value)
                if self.title:self.name.append(value)
    doc=Document();doc.feed(page)
    title=doc.meta.get('og:title') or ''.join(doc.name).strip()
    if any(x in title for x in ('登录','验证','访问受限','安全检查')):raise ValueError('1688 要求登录或安全验证，请打开货源页完成验证后使用采集插件')
    attrs={};images=[]
    def image(value):
        if isinstance(value,str):
            value=html.unescape(value).replace('\\/','/')
            if value.startswith('//'):value='https:'+value
            if re.match(r'^https://cbu\d+\.alicdn\.com/img/ibank/',value):images.append(value)
    def walk(value,depth=0):
        if depth>30:return
        if isinstance(value,dict):
            key=value.get('attributeName') or value.get('name') or value.get('propertyName')
            val=value.get('attributeValue') or value.get('value') or value.get('propertyValue')
            if isinstance(key,str) and isinstance(val,(str,int,float)) and 0<len(key)<100:attrs[key]=str(val)[:4999]
            for k,v in value.items():
                if k in ('subject','offerTitle') and isinstance(v,str) and 5<len(v)<500:
                    nonlocal title
                    title=v
                if k in ('image','imageUrl','fullPathImageURI','originalImageURI','url'):image(v)
                if isinstance(v,(dict,list)):walk(v,depth+1)
        elif isinstance(value,list):
            for item in value[:1000]:walk(item,depth+1)
    for script in doc.scripts:
        candidates=[script.strip()]
        match=re.search(r'(?:window\.)?(?:__INIT_DATA|__GLOBAL_DATA|__INITIAL_STATE__)\s*=\s*',script)
        if match:candidates.append(script[match.end():])
        for candidate in candidates:
            try:walk(json.JSONDecoder().raw_decode(candidate)[0])
            except (ValueError,TypeError):pass
    for value in re.findall(r'(?:https:)?//cbu\d+\.alicdn\.com/img/ibank/[^\s"<>\\]+',html.unescape(page)):image(value)
    text='\n'.join(doc.parts)
    for key in ('材质成分','材质','面料','款式','颜色','尺码','产品尺寸','商品尺寸','包装尺寸','包装规格','产品重量','净重','毛重','价格','采购价','包装内容','包装清单','图案','适合季节'):
        match=re.search(r'(?:^|\n)\s*'+key+r'\s*[：:]\s*([^\n]{1,1000})',text)
        if match:attrs.setdefault(key,match.group(1).strip())
    images=list(dict.fromkeys(images))[:80]
    title=re.sub(r'\s*[-_－]\s*(?:阿里巴巴|1688).*$','',title).strip()
    if not 5<len(title)<500 or not (attrs or images):raise ValueError('页面未返回完整商品资料，可能需要登录或浏览器加载；请打开货源页使用采集插件')
    return {'url':url,'title':title,'attributes':attrs,'images':images,'captureMethod':'server-public-page'}


def preview(data):
    asin=str(data.get('asin','')).strip().upper();market=data.get('market','UK');source=str(data.get('source','')).strip()
    if market not in MARKET_DOMAINS or (asin and not re.fullmatch(r'[A-Z0-9]{10}',asin)):raise ValueError('请输入有效 ASIN 并选择支持的站点')
    offer=re.fullmatch(r'https://detail\.1688\.com/offer/(\d+)\.html(?:\?[^\s]*)?',source) if source else None
    if source:
        parsed=urlsplit(source)
        if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or any(ord(c)<32 for c in source):
            raise ValueError('请填写有效的 HTTP 或 HTTPS 货源网址，不支持带账号密码的链接')
    if not asin and not source:raise ValueError('请至少填写 ASIN 或货源链接')
    if source:
        parsed=urlsplit(source)
        for code,domain in MARKET_DOMAINS.items():
            if parsed.hostname in ('amazon.'+domain,'www.amazon.'+domain):
                found=re.search(r'/(?:dp|gp/product)/([A-Za-z0-9]{10})(?:[/?]|$)',parsed.path)
                if not found:raise ValueError('请使用含 ASIN 的亚马逊商品详情链接')
                detected=found.group(1).upper()
                if asin and asin!=detected:raise ValueError('ASIN 与亚马逊链接中的 ASIN 不一致')
                asin=detected;market=code;source='';offer=None
                break
    url=f'https://www.amazon.{MARKET_DOMAINS[market]}/dp/{asin}' if asin else ''
    warnings=[];amazon={'title':'','bullets':[],'description':'','referenceImages':[]}
    if asin:
        try:
            import sellersprite
            item=sellersprite.Client().connect().call('asin_detail',{'marketplace':market,'asin':asin})
            amazon.update(title=str(item.get('title') or ''),bullets=[x for x in (item.get('features') or []) if isinstance(x,str)],brand=str(item.get('brand') or ''),provider='SellerSprite MCP')
            for key in ('zoomImageUrl','image','imageUrl','mainImage','images','imageUrls'):
                values=item.get(key,[])
                if isinstance(values,str):values=[values]
                if isinstance(values,list):
                    for value in values:
                        if isinstance(value,str) and value.startswith('https://') and value not in amazon['referenceImages']:amazon['referenceImages'].append(value)
            if not amazon['title']:warnings.append('卖家精灵未返回商品标题，请稍后重试或补充参考资料。')
            warnings.append('亚马逊资料为竞品参考，不自动作为自有产品材质、尺寸等事实；关键词与评论请进入产品工作台联合分析。')
        except Exception:
            warnings.append('卖家精灵商品详情读取失败，本次未采集到亚马逊资料，请重试；货源导入仍可独立进行。')
    supplier={'url':f'https://detail.1688.com/offer/{offer.group(1)}.html' if offer else source, 'title':'','attributes':{},'images':[]}
    if offer:
        import supplier_capture
        capture = supplier_capture.request(supplier['url'])
        if capture['status'] == 'collected':
            supplier = capture['supplier']
            warnings.append('已复用保存的1688资料，未重复打开商品页；价格、库存仍以实际下单核对为准。' if supplier.get('reused') else '1688浏览器采集已完成；价格、库存仍以实际下单核对为准。')
        else:
            supplier.update(captureId=capture['id'], captureStatus=capture['status'])
            warnings.append(capture.get('message') or '1688资料已加入统一串行队列，采集结果将在此处自动更新。')
    if source and not offer:
        supplier['manualEntry']=True
        warnings.append('已保留货源网址。该网站暂未适配自动采集，请填写产品名称和货源补充资料，创建后可上传真实图片；不会从竞品推测产品属性。')
    return {'asin':asin,'market':market,'amazonUrl':url,'amazon':amazon,'supplier':supplier,'warnings':warnings}


def read_supplier(url):
    import supplier_capture
    return supplier_capture.read(url)


def autofill_supplier(product):
    source = product.get('sourceImport', {})
    supplier = source.get('supplier', {})
    attrs = supplier.get('attributes', {})
    previous = product.setdefault('autoImportedFields', {})
    def put(key, value):
        if value and (not product.get(key) or product.get(key) == previous.get(key)):
            product[key] = value
            previous[key] = value
    split = lambda s: list(dict.fromkeys(x.strip() for x in re.split('[,，、]', s) if x.strip()))
    put('brand', 'Generic')
    put('manufacturer', 'Generic')
    put('sourceUrl', supplier.get('url', ''))
    put('style', product.get('supplierScope') or attrs.get('款式') or attrs.get('款型') or supplier.get('title', ''))
    material = attrs.get('材质成分') or attrs.get('材质') or attrs.get('面料名称') or attrs.get('面料', '')
    main_material = attrs.get('主面料成分', '')
    families = [('聚酯', '涤纶', 'polyester'), ('聚酰胺', '锦纶', 'nylon'), ('棉', 'cotton'), ('羊毛', 'wool')]
    family = lambda text: {i for i, words in enumerate(families) if any(w in text.lower() for w in words)}
    if family(material) and family(main_material) and family(material).isdisjoint(family(main_material)):
        material = '面料外观：' + (attrs.get('面料名称') or attrs.get('面料') or '待确认') + '；供应商成分字段矛盾，具体纤维及比例待供应商确认，不得在文案中宣称成分比例。'
        product['materialConflict'] = {'composition': attrs.get('材质成分', ''), 'mainMaterial': main_material, 'mainContent': attrs.get('主面料成分的含量', '')}
    put('material', material)
    colors = [c for c in split(attrs.get('颜色', '')) if not re.search(r'供货|现货|库存|大量|代发|慎拍|起批|混批|勿拍|运费|补差|\d+\s*(?:g|kg|克|码)|[SMLX]{1,4}\s*[-~至]\s*\d?X?L', c, re.I)]
    scope = product.get('supplierScope', '')
    scoped = [c for c in colors if scope and c.startswith(scope + '-')]
    if scoped:
        colors = scoped
    put('colorNames', ','.join(colors))
    sizes = split(attrs.get('尺码', ''))
    put('sizeNames', ','.join(sizes))
    measured = attrs.get('产品尺寸') or attrs.get('商品尺寸') or attrs.get('尺寸')
    put('dimensions', measured or ('可选尺码：' + ', '.join(sizes) + '；未提供衣长、胸围等实测尺寸，请勿推断。' if sizes else ''))
    put('purchasePrice', attrs.get('采购价') or attrs.get('价格', ''))
    put('packageDimensions', attrs.get('包装尺寸') or attrs.get('包装规格', ''))
    put('productWeight', attrs.get('产品重量') or attrs.get('净重', ''))
    put('packageWeight', attrs.get('包装重量') or attrs.get('毛重', ''))
    put('packageContents', attrs.get('包装内容') or attrs.get('包装清单', ''))
    put('features', '；'.join(k + '：' + attrs[k] for k in ('面料名称', '面料', '产品类别', '风格', '领型', '门襟', '版型', '袖长', '服装口袋样式', '里料', '款式', '是否连帽', '是否可脱卸', '图案', '适合季节') if attrs.get(k)))
    product['colors'] = max(1, len(split(product.get('colorNames', ''))))
    product['sizes'] = max(1, len(split(product.get('sizeNames', ''))))


def merge_browser_capture(state, data):
    import supplier_facts
    structured = supplier_facts.normalize(data)
    url = str(data.get('url', ''))
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.netloc != 'detail.1688.com' or not re.fullmatch(r'/offer/\d+\.html', parsed.path):
        raise ValueError('仅接受1688商品详情页面')
    title, attributes, images = data.get('title'), data.get('attributes'), data.get('images')
    if not isinstance(title, str) or not 5 < len(title) < 500 or any(x in title for x in ('验证码', '登录', '访问受限')):
        raise ValueError('未读取到商品标题，请先完成登录或验证')
    if not isinstance(attributes, dict) or not all(isinstance(k, str) and isinstance(v, str) and len(k) < 100 and len(v) < 5000 for k, v in attributes.items()):
        raise ValueError('商品属性格式不正确')
    if not attributes and not images:
        raise ValueError('页面没有可采集商品资料，请展开属性并等待加载')
    if not isinstance(images, list):
        raise ValueError('商品图片格式不正确')
    images = list(dict.fromkeys(u for u in images if supplier_facts.image_url(u)))[:80]
    image_capture=supplier_facts.image_capture(data,images)
    asin = str(data.get('asin', '')).upper()
    market = data.get('market', 'UK')
    if market not in MARKET_DOMAINS or (asin and not re.fullmatch('[A-Z0-9]{10}', asin)):
        raise ValueError('站点或ASIN不正确')
    canonical = 'https://detail.1688.com' + parsed.path
    target_id = str(data.get('targetProductId') or '')
    if target_id:
        product = next((p for p in state['products'] if p['id'] == target_id), None)
        if product is None:
            raise ValueError('目标产品不存在或已删除，请返回当前账号产品库重新打开货源，未创建新产品')
    else:
        product = next((p for p in state['products'] if (asin and p.get('sourceImport', {}).get('asin') == asin and p.get('sourceImport', {}).get('market') == market) or (not asin and p.get('sourceImport', {}).get('supplier', {}).get('url') == canonical)), None)
    if product is None:
        pid = 'IMP-' + market + '-' + asin if asin else '1688-' + re.search(r'\d+', parsed.path).group()
        if any(p['id'] == pid for p in state['products']):
            raise ValueError('相同产品编号已存在，请检查关联信息')
        product = dict(id=pid, name=title, cat='服装', owner='待分配', colors=1, sizes=1, status='待补资料', color='#a6b39a')
        state['products'].insert(0, product)
    source = product.setdefault('sourceImport', {'asin': asin, 'market': market, 'amazonUrl': f'https://www.amazon.{MARKET_DOMAINS[market]}/dp/{asin}' if asin else '', 'amazon': {'title': '', 'bullets': [], 'referenceImages': []}})
    source['supplier'] = {'url': canonical, 'title': title, 'attributes': attributes, 'images': images, 'captureMethod': 'browser-extension', 'retrievedAt': str(data.get('capturedAt', ''))[:80]}
    source['supplier'].update(structured)
    source['supplier'].update(image_capture)
    source['supplierNotes'] = '\n'.join(k + '：' + v for k, v in attributes.items())
    source['warnings'] = ['货源资料已由浏览器采集，属性来自供应商页面；仍需核对款式、实际规格和尺码表。']
    autofill_supplier(product)
    if product['status'] in ('已通过', '待审核'):
        product['status'] = '需修改'
        state['reviews'][product['id']] = {'copy': False, 'images': False, 'note': '货源资料更新，需要重新核对'}
    return product['id']
