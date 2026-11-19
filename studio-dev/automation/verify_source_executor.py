"""Isolated live read-only source smoke; no credentials, model calls or ERP actions."""
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
from contextlib import closing


def main():
    if len(sys.argv) != 3:
        raise SystemExit('Usage: py -3 automation/verify_source_executor.py HTTPS_1688_OFFER_URL OUTPUT_REPORT')
    url, output = sys.argv[1], Path(sys.argv[2]).resolve()
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'listing-workbench'))
    with tempfile.TemporaryDirectory(prefix='source-executor-') as folder:
        root=Path(folder)
        os.environ['JUNFEI_ACCOUNT_DATA']=str(root)
        os.environ['JUNFEI_ACCOUNTS_DB']=str(root/'accounts.sqlite3')
        for key in ('DEEPSEEK_API_KEY','APIMART_API_KEY','SELLERSPRITE_MCP_KEY','JUNFEI_SHARED_CREDENTIALS'):
            os.environ.pop(key,None)
        import secrets_store
        secrets_store.ROOT=root/'credentials'
        import agent_center as agent
        import agent_sourcing as sourcing
        if not sourcing.source_url({'sourceUrl':url}): raise SystemExit('Only HTTPS detail.1688.com offer URLs supported')
        workspace={'products':[dict(id='source-smoke',name='Isolated source verification, never publish',market='US',sourceUrl=url)],'copy':{},'reviews':{}}
        with closing(sqlite3.connect(root/'studio.sqlite3')) as c,c:
            c.execute('CREATE TABLE workspace(id INTEGER PRIMARY KEY,revision INTEGER,body TEXT)')
            c.execute('INSERT INTO workspace VALUES(1,1,?)',(json.dumps(workspace),))
        profile=agent.save_profile(1,dict(name='Isolated verification',store='TEST ONLY',marketplace='US',shippingTemplate='TEST ONLY'))
        task=agent.create(1,dict(goal='Read source only; no paid services or publication',profileId=profile['id'],productId='source-smoke',taskMode='production',autoSourcing=True))
        agent.start(1,task['id'])
        deadline=time.monotonic()+60
        while task['id'] in agent.ACTIVE and time.monotonic()<deadline:time.sleep(.1)
        if task['id'] in agent.ACTIVE:raise RuntimeError('Live worker still active; retain running process and inspect it')
        task=agent.detail(1,task['id'])
        result={'url':url,'taskId':task['id'],'taskStatus':task['status'],'facts':task['results'].get('facts'),
                'paidCallsEnabled':False,'erpActions':False,'productionDataModified':False}
        if task.get('sourcingReportAvailable'):result['sourceReport']=sourcing.report(1,task['id'])
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'report':str(output),'taskStatus':task['status'],'sourceStatus':result.get('sourceReport',{}).get('status','not_saved')}))


if __name__=='__main__':main()
