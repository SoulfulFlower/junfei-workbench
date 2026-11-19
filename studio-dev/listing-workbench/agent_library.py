"""Account-bound production bridge to Ego's product library, never store publish."""
import hashlib
import csv
import io
import json
import re
import subprocess
import uuid
import zipfile
from decimal import Decimal
from pathlib import Path
from PIL import Image
import agent_erp
import app_paths
import runtime_environment


def binding(user, task):
    config = json.loads((agent_erp.project_root() / 'automation/config.json').read_text(encoding='utf-8'))
    browser = config['browser']
    matches = [b for b in browser.get('erp_library_bindings', {}).get(str(user), [])
               if b.get('product_id') == task.get('productId') and b.get('store') == task['profile']['store']
               and b.get('marketplace') == task['profile']['marketplace']]
    if len(matches) != 1 or matches[0].get('enabled') is not True:
        raise ValueError('当前账号产品没有启用的ERP产品库绑定')
    b = matches[0]
    if (browser.get('engine') != 'ego-lite' or task['profile']['mode'] != 'draft'
            or b.get('marketplace') != 'US' or not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', b.get('parent_sku', ''))
            or not re.fullmatch(r'p\d+', b.get('page', ''))):
        raise ValueError('产品库绑定必须明确ego页面、父SKU和US草稿模式')
    if task.get('libraryDraftOnly'):
        name = b.get('task_binding')
        selected = browser.get('task_bindings', {}).get(name)
        if (not isinstance(selected, dict) or name == 'selection'
                or type(selected.get('task_space_id')) is not int or selected['task_space_id'] <= 0
                or not selected.get('task_space_name')
                or not Path(selected.get('script_directory') or '').is_absolute()
                or selected.get('pages', {}).get('erp') != b['page']):
            raise ValueError('请为此商品配置专属钧飞草稿浏览器工作区及ERP页面')
        browser = {**browser, **selected, 'binding': name}
    return browser, b


def package_for(user, task):
    browser, b = binding(user, task)
    image_policy = json.loads((agent_erp.project_root() / 'automation/config.json').read_text(encoding='utf-8')).get('images', {})
    if image_policy.get('supplier_image_policy') != 'user_default_supplier_images':
        raise ValueError('未配置用户默认图片使用依据，不能生成商品图使用回执')
    if task.get('taskMode') != 'production' or not all(task.get('results', {}).get(k, {}).get('ok') for k in
            ('facts', 'research', 'listing', 'images', 'export', 'junfeiPreflight')):
        raise ValueError('产品库保存需要生产任务及全部资料、研究、文案、图片、交付预检通过')
    p = task['snapshot']['product']
    if p.get('id') != task['productId'] or p.get('sku') != b['parent_sku']:
        raise ValueError('产品库绑定与当前产品快照SKU不同')
    import agent_review
    import generated_gallery
    draft_images = False
    if p.get('generatedGallerySelection'):
        selection = p['generatedGallerySelection']
        draft_images = agent_review.gallery_approved(p, generated_gallery.selected(p, selection.get('sourceStudioProjectId')))
    if ((task['snapshot'].get('review', {}).get('images') is not True and not draft_images)
            or (task['snapshot'].get('review', {}).get('copy') is not True
                and not agent_review.copy_approved(p, task['snapshot']['listing']))):
        raise ValueError('产品库保存需要已审核文案和图片')
    if p.get('brandUseAuthorized') is True and p.get('brand') not in ('', None, 'Generic'):
        raise ValueError('产品库整包仅支持Generic')
    tid = task['id']
    if not re.fullmatch(r'[a-f0-9]{32}', tid):
        raise ValueError('任务编号无效')
    root = app_paths.DATA / 'agent-results' / tid
    raw = (root / 'delivery.zip').read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != task['results']['export'].get('sha256'):
        raise ValueError('交付包已变化，不能沿用原预检')
    out = root / 'junfei-preflight'
    provenance = json.loads((out / 'preflight-record.json').read_text(encoding='utf-8'))
    if provenance.get('taskId') != tid or provenance.get('deliverySha256') != digest:
        raise ValueError('预检与当前任务交付包不匹配')
    plans = json.loads((out / 'products.json').read_text(encoding='utf-8'))
    if len(plans) != 1:
        raise ValueError('产品库整包只接受当前单产品')
    plan = plans[0]
    if any(plan.get(k) != value for k, value in {'parentSku':b['parent_sku'], 'store':b['store'], 'marketplace':'US', 'currency':'USD', 'brand':'Generic', 'sourceUrl':p.get('sourceUrl')}.items()):
        raise ValueError('预检商品身份不匹配')
    listing = task['snapshot']['listing']
    for key, field in [('title','title'), ('description','description'), ('searchTerms','terms')]:
        if plan.get(key) != listing.get(field):
            raise ValueError('预检文案与任务快照不同')
    bullets = listing.get('bullets')
    if isinstance(bullets, str): bullets = [x.strip() for x in bullets.splitlines() if x.strip()]
    if plan.get('bullets') != bullets:
        raise ValueError('预检五点与任务快照不同')
    # Never consume the legacy fixed freight formula here. Only explicit saved
    # variant prices are accepted until quote-based pricing is adapted.
    prices = p.get('junfeiVariantPrices') or {}
    if not isinstance(prices, dict):
        raise ValueError('变体售价必须是按SKU保存的明确USD金额')
    assets, bindings, variants, seen = [], [], [], {}
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        if len(z.namelist()) != len(set(z.namelist())):
            raise ValueError('交付包存在重复文件名')
        prefix = b['parent_sku'] + '/'
        rows = list(csv.DictReader(io.StringIO(z.read(prefix + 'variants.csv').decode('utf-8-sig'))))
        manifest = json.loads(z.read(prefix + 'image-manifest.json'))
        exported = {row['sku']: row for row in rows}
        planned_skus = [v['sku'] for v in plan['variants']]
        if (len(exported) != len(rows) or len(set(planned_skus)) != len(planned_skus)
                or set(planned_skus) != set(exported)):
            raise ValueError('预检变体集合与原交付包不同')
        for v in plan['variants']:
            row = exported[v['sku']]
            entries = sorted((e for e in manifest['images'] if e.get('color') == row['color']), key=lambda e: e.get('slot', 999))
            main = next((e['file'] for e in entries if e.get('slot') == 0), '')
            if (row.get('parent_sku') != b['parent_sku']
                    or any(v.get(k) != row.get(k) for k in ('sku', 'color', 'size'))
                    or v.get('mainImage') != main or not main
                    or v.get('images') != [e['file'] for e in entries if e['file'] != main][:8]):
                raise ValueError('预检变体规格或图片顺序与原交付包不同')
            price = str(prices.get(v['sku'], ''))
            if not price and v['sku'] in plan.get('pricingBasis', {}):
                import quote_pricing
                estimate = quote_pricing.estimate(p, 'US', len(plan['variants']))
                if (plan['pricingBasis'][v['sku']] != estimate or
                        task['results']['junfeiPreflight'].get('pricingBasis', {}).get(v['sku']) != estimate):
                    raise ValueError('报价定价依据已变化，请重新核对原计划，不能沿用旧售价')
                price = estimate['priceUsd']
            planned_price = str(v.get('price', ''))
            if (not re.fullmatch(r'(?:0|[1-9]\d{0,4})(?:\.\d{1,2})?', price)
                    or not re.fullmatch(r'(?:0|[1-9]\d{0,4})(?:\.\d{1,2})?', planned_price)
                    or Decimal(price) <= 0 or Decimal(planned_price) != Decimal(price)):
                raise ValueError('变体缺少与快照一致的明确USD售价；不使用旧固定运费公式')
            price = format(Decimal(price), '.2f')
            variants.append({k:v[k] for k in ('sku','color','size')} | {'price':price})
            indices = []
            for name in [v['mainImage'], *v['images']]:
                target = (out / name).resolve()
                if out.resolve() not in target.parents or not target.is_file():
                    raise ValueError('产品图片路径越界或不存在')
                data = z.read(name)
                if data != target.read_bytes():
                    raise ValueError('产品图片与原交付包不同')
                sha = hashlib.sha256(data).hexdigest()
                if sha not in seen:
                    with Image.open(io.BytesIO(data)) as image:
                        if image.format not in ('PNG','JPEG') or min(image.size) < 1600 or len(data) >= 5*1024*1024:
                            raise ValueError('产品库图片必须PNG/JPEG、至少1600像素且小于5MB')
                        width, height = image.size
                        image.verify()
                    seen[sha] = len(assets)
                    assets.append({'path':str(target), 'sha256':sha, 'width':width, 'height':height,
                        'purpose':'reviewed_product_image', 'reviewed':True,
                        'rightsBasis':'user_default_supplier_use_not_supplier_license', 'sourceUrl':p['sourceUrl'],
                        'noUnauthorizedMarks':True, 'reviewerType':'agent' if draft_images else 'human',
                        'reviewScope':'draft_only',
                        'evidence':f'Account {user}; task {tid}; reviewed image export SHA256 {digest}; user default use, not supplier license'})
                indices.append(seen[sha])
            bindings.append({'sku':v['sku'], 'indices':indices})
    if not variants or not 1 <= len(assets) <= 9:
        raise ValueError('产品库整包需要变体和1–9张去重图片')
    request = {'accountId':user, 'productId':p['id'], 'store':b['store'], 'marketplace':'US', 'mode':'library_draft',
        'sourceUrl':p['sourceUrl'], 'sku':b['parent_sku'], 'brand':'Generic', 'manufacturer':'Generic',
        'title':plan['title'], 'description':plan['description'], 'bullets':bullets, 'terms':plan['searchTerms'],
        'notes':'产品库草稿；未加入店铺、未发布',
        'evidence':{k:f'Account {user}; task {tid}; verified snapshot/export {digest}' for k in ('sourceUrl','title','description','bullets','terms')},
        'commerce':{'currency':'USD', 'price':variants[0]['price'], 'variants':variants,
                    'evidence':{'price':'Saved USD prices or recomputed quote-based draft estimate; parent uses first variant; not a final live price', 'variants':f'Validated delivery for task {tid}'}}}
    return browser, {'request':request, 'assets':assets, 'bindings':bindings}


def sync_library(user, task):
    command_prefix = runtime_environment.ego_command(agent_erp.project_root())
    browser, package = package_for(user, task)
    project = agent_erp.project_root()
    # Reuse the independent calibration's SKU barrier as well as the aggregate
    # operation barrier. New task IDs or image/copy changes cannot bypass it.
    sku = package['request']['sku']
    previous = project / 'automation/data/ego-library-draft-executions' / f'{user}-{sku}.json'
    receipt = project / 'automation/data/ego-library-package-executions' / f'{user}-{sku}.json'
    if previous.exists() or receipt.exists():
        raise ValueError('此账号SKU已有产品库操作记录，先对账；不创建新任务绕过或重试')
    folder = agent_erp.folder_for(task)
    script_dir = Path(browser['script_directory'])
    script_dir.mkdir(parents=True, exist_ok=True)
    script = script_dir / ('workbench-library-' + uuid.uuid4().hex + '.mjs')
    receipt.parent.mkdir(parents=True, exist_ok=True)
    module = project / 'junfei-publisher/ego-library-package.mjs'
    script.write_text(f'''const fs=await import('node:fs/promises');
const {{stageLibraryPackage,saveLibraryPackage,validateLibraryPackage}}=await import({json.dumps(module.as_uri())});
const input={json.dumps(package,ensure_ascii=False)};
await validateLibraryPackage(input);
const receipt={json.dumps(str(receipt))},previous={json.dumps(str(previous))};
try{{await fs.access(previous);throw Error('原SKU已有操作，停止');}}catch(e){{if(e.code!=='ENOENT')throw e;}}
const ledger={{create:async record=>{{const f=await fs.open(receipt,'wx');try{{await f.writeFile(JSON.stringify(record,null,2));await f.sync();}}finally{{await f.close();}}}},write:async record=>{{const tmp=receipt+'.tmp';const f=await fs.open(tmp,'w');try{{await f.writeFile(JSON.stringify(record,null,2));await f.sync();}}finally{{await f.close();}}await fs.rename(tmp,receipt);}}}};
const page=globalThis.amazonTask.page({json.dumps(binding(user,task)[1]['page'])});
const record=await stageLibraryPackage(page,input,ledger,{{openNew:true}});
await saveLibraryPackage(page,record,ledger);
''', encoding='utf-8')
    command = command_prefix + ['run', str(script), '--timeout', '180']
    if task.get('libraryDraftOnly'):
        command += ['--binding', browser['binding']]
    with agent_erp.browser_lock(user, task) as state:
        state['keep'] = True
        try:
            response = subprocess.run(command,capture_output=True,timeout=195,
                                      creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except subprocess.TimeoutExpired:
            raise ValueError('产品库执行结果未知；保留浏览器锁和原SKU回执，不重发') from None
        if response.returncode or not receipt.is_file():
            (folder/'library-error.txt').write_bytes(response.stdout + response.stderr)
            raise ValueError('产品库执行未返回可核对成功回执，需核对原操作；不重试')
        record = json.loads(receipt.read_text(encoding='utf-8'))
        if (record.get('status') != 'library_package_saved_reopened_verified' or record.get('saved') is not True
                or record.get('published') is not False or record.get('input') != package
                or any(record.get(k) != package['request'][k] for k in ('accountId','productId','sku'))
                or not re.fullmatch(r'\d+', str(record.get('libraryId', '')))):
            raise ValueError('产品库回执未证明本账号整包保存成功，保留原操作待核对')
        state['keep'] = False
    return {'ok':False, 'librarySaved':True, 'libraryId':record['libraryId'], 'published':False,
            'receiptSha256':hashlib.sha256(receipt.read_bytes()).hexdigest(),
            'issues':['产品库整包已保存并重开核对；尚未加入目标店铺草稿，不代表完整刊登或在售'],
            'reason':'产品库保存完成，下一步为目标店铺草稿适配'}
