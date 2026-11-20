"""Exact local handoff receipts, committed with the receiving service's job."""
def record(db, scope, job, stage):
    if scope is None:
        return
    db.execute('''CREATE TABLE IF NOT EXISTS codex_handoffs (
        account INTEGER, product TEXT, market TEXT, request TEXT, job TEXT, stage TEXT,
        PRIMARY KEY(account, product, market, request))''')
    db.execute('''INSERT INTO codex_handoffs VALUES(?,?,?,?,?,?)
        ON CONFLICT(account,product,market,request) DO UPDATE SET stage=excluded.stage
        WHERE job=excluded.job''', (*scope,job,stage))


def lookup(db, scope):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='codex_handoffs'").fetchone():
        return None
    row=db.execute('SELECT job,stage FROM codex_handoffs WHERE account=? AND product=? AND market=? AND request=?',
                   scope).fetchone()
    return {'jobId':row[0],'handoffStage':row[1]} if row else None
