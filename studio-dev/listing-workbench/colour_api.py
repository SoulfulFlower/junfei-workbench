"""HTTP adapter for existing /api/colours routes.

The shared server authenticates and selects the account runtime first. This
adapter receives that runtime's database/lock; no global workspace is selected.
"""
import json
from urllib.parse import urlsplit
import colour_sets
import colour_associations
import local_colour_tasks
import pixel_recolour

GET_PATHS = frozenset(['/api/colours/sets', '/api/colours/image', '/api/colours/export'])
POST_PATHS = frozenset(['/api/colours/reinstate', '/api/colours/master', '/api/colours/start', '/api/colours/start-all', '/api/colours/approve', '/api/colours/retry', '/api/colours/repair-local', '/api/colours/repair-local-batch', '/api/colours/review-local', '/api/colours/continue', '/api/colours/local/readiness', '/api/colours/local/configure', '/api/colours/local/start', '/api/colours/local/start-all', '/api/colours/local/pause', '/api/colours/local/resume', '/api/colours/pixel/sources', '/api/colours/pixel/selection', '/api/colours/pixel/save', '/api/colours/pixel/render', '/api/colours/pixel/commit'])


POST_PATHS = POST_PATHS | frozenset(['/api/colours/local/sample-reference'])
POST_PATHS = POST_PATHS | frozenset(['/api/colours/pixel/segment','/api/colours/pixel/inspect'])
POST_PATHS = POST_PATHS | frozenset(['/api/colours/pixel/auto','/api/colours/pixel/uploaded-source'])
POST_PATHS = POST_PATHS | frozenset(['/api/colours/local/prepare'])


def get(handler, path, database):
    self = handler
    from urllib.parse import parse_qs
    q=parse_qs(urlsplit(self.path).query)
    try:
        if path.endswith('/sets'):
            pid=q.get('productId',[''])[0]
            with database() as conn:row=conn.execute('SELECT body FROM workspace WHERE id=1').fetchone()
            product=next((p for p in (json.loads(row[0]) if row else {}).get('products',[]) if p['id']==pid),None)
            if not product:raise ValueError('当前账号产品不存在')
            return self.reply(200,colour_sets.current_sets(pid,product))
        if path.endswith('/image'):
            raw,mime=colour_sets.image_bytes(q.get('id',[''])[0],int(q.get('slot',['-1'])[0]));return self.reply(200,raw,mime)
        import io,zipfile
        colour=colour_sets.get(q.get('id',[''])[0]);buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as archive:
            for item in colour['items']:
                if not item.get('image'):continue
                raw,mime=colour_sets.image_bytes(colour['id'],item['slot'])
                import re
                color=re.sub(r'[\\/:*?"<>|]','_',str(colour.get('color') or ''))[:60]
                archive.writestr((color+str(item['slot']+1).zfill(2) if color else 'A'+str(item['slot']+1))+('.png' if mime=='image/png' else '.jpg'),raw)
            archive.writestr('审核说明.txt','换色图片与自动检查记录。完整通过检查的当前颜色套图会自动关联同色子SKU，无需人工确认。未通过或资料不完整的图位不关联；下载不代表已经发布。')
            archive.writestr('image-manifest.json',json.dumps({'color':colour.get('color'),'colorKey':colour.get('colorKey'),'status':colour['status'],'humanReviewed':colour.get('manual') is True,'skuBinding':colour.get('skuBinding'),'referenceWarnings':colour.get('referenceWarnings',[]),'items':[{'slot':item['slot'],'status':item['status'],'hasImage':bool(item.get('image')),'qc':item.get('qc')} for item in colour['items']]},ensure_ascii=False,indent=2))
        return self.reply(200,buffer.getvalue(),'application/zip')
    except (ValueError,KeyError) as e:return self.reply(400,{'error':str(e)})


def post(handler, path, user, database, lock):
    self = handler
    LOCK = lock
    if path in ('/api/colours/reinstate', '/api/colours/master'):
        import variant_colours
        data=json.loads(self.read_body(16*1024))
        if not isinstance(data,dict) or type(data.get('revision')) is not int:
            raise ValueError('请提交当前产品库版本后重试')
        with LOCK, database() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row=conn.execute('SELECT revision,body FROM workspace WHERE id=1').fetchone()
            revision=row[0] if row else 0
            if data['revision']!=revision:
                return self.reply(409,{'error':'产品资料已更新，请刷新后重新核对','revision':revision})
            workspace=json.loads(row[1]) if row else {'products':[]}
            p=next((p for p in workspace.get('products',[]) if p['id']==data.get('productId')),None)
            if not p:raise ValueError('当前账号产品不存在')
            action=colour_associations.reinstate if path.endswith('/reinstate') else colour_associations.set_master
            updated,changed=action(p,data,{'id':user['id'],'name':user['name']})
            review=workspace.get('reviews',{}).get(p['id'])
            if changed:
                p.clear();p.update(updated)
                if p.get('status')=='已通过':p['status']='需修改'
                review={**(review or {}),'images':False,'note':'颜色关联已更新，请重新核对图片'}
                workspace.setdefault('reviews',{})[p['id']]=review
                revision+=1
                conn.execute('UPDATE workspace SET revision=?,body=? WHERE id=1',
                             (revision,json.dumps(workspace,ensure_ascii=False)))
        return self.reply(200,{'revision':revision,'product':p,'review':review,'changed':changed})
    if path in ('/api/colours/local/readiness','/api/colours/local/prepare','/api/colours/local/configure','/api/colours/local/start','/api/colours/local/start-all','/api/colours/local/pause','/api/colours/local/resume','/api/colours/local/sample-reference'):
        data=json.loads(self.read_body(32*1024))
        if not isinstance(data,dict):raise ValueError('本地换色请求必须为JSON对象')
        with database() as conn:row=conn.execute('SELECT body FROM workspace WHERE id=1').fetchone()
        p=next((p for p in (json.loads(row[0]) if row else {}).get('products',[]) if p['id']==data.get('productId')),None)
        if not p:raise ValueError('当前账号产品不存在')
        try:return self.reply(200,local_colour_tasks.action(path.rsplit('/',1)[1],data,p))
        except local_colour_tasks.NotReady as error:return self.reply(409,{'error':str(error),'localReadiness':error.details,'imageGenerationSubmitted':False})
    if path in ('/api/colours/pixel/sources','/api/colours/pixel/selection','/api/colours/pixel/auto','/api/colours/pixel/uploaded-source','/api/colours/pixel/segment','/api/colours/pixel/inspect','/api/colours/pixel/save','/api/colours/pixel/render','/api/colours/pixel/commit'):
        data=json.loads(self.read_body(16*1024*1024))
        if not isinstance(data,dict):raise ValueError('换色请求必须为JSON对象')
        with database() as conn:row=conn.execute('SELECT body FROM workspace WHERE id=1').fetchone()
        p=next((p for p in (json.loads(row[0]) if row else {}).get('products',[]) if p['id']==data.get('productId')),None)
        if not p:raise ValueError('当前账号产品不存在')
        return self.reply(200,pixel_recolour.action(path.rsplit('/',1)[1],data,p))
    if path in ('/api/colours/start','/api/colours/start-all','/api/colours/approve','/api/colours/retry','/api/colours/repair-local','/api/colours/repair-local-batch','/api/colours/review-local','/api/colours/continue'):
        data=json.loads(self.read_body(32*1024))
        with database() as conn:row=conn.execute('SELECT body FROM workspace WHERE id=1').fetchone()
        state=json.loads(row[0]) if row else {}
        p=next((p for p in state.get('products',[]) if p['id']==data.get('productId')),None)
        if not p:raise ValueError('当前账号产品不存在')
        # Also protect already-open pages using the old primary URLs:
        # their model=gpt-image-2 payload must not trigger paid generation.
        if path in ('/api/colours/start','/api/colours/start-all'):
            try:return self.reply(200,local_colour_tasks.action(path.rsplit('/',1)[1],data,p))
            except local_colour_tasks.NotReady as error:return self.reply(409,{'error':str(error),'localReadiness':error.details,'imageGenerationSubmitted':False})
        return self.reply(200,({'/api/colours/start':colour_sets.start,'/api/colours/start-all':colour_sets.start_all,'/api/colours/approve':colour_sets.approve,'/api/colours/retry':colour_sets.retry,'/api/colours/repair-local':colour_sets.repair_local,'/api/colours/repair-local-batch':colour_sets.repair_local_batch,'/api/colours/review-local':colour_sets.resume_local_review,'/api/colours/continue':colour_sets.continue_remaining}[path])(data,p))
