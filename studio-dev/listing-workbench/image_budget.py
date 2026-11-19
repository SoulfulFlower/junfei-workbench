"""Account-local image generation reservations. Provider bills require reconciliation."""
import json
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from pathlib import Path
import app_paths
import runtime_environment
import codex_tools_quota


class BudgetBlocked(ValueError):
    """A known rejection before any paid generation request."""


def configuration():
    """The desktop points to the same live operating policy as the CLI."""
    return runtime_environment.configuration(app_paths.APP)['images']


def limits():
    try:
        config = configuration()
        policy = {'enabled': config.get('enabled') is True,
                'perProductFen': fen(config['per_product_budget_rmb']),
                'dailyFen': fen(config['daily_budget_rmb'])}
        overrides = config.get('per_product_budget_overrides', {})
        if not isinstance(overrides, dict): raise ValueError()
        if overrides:
            policy['perProductOverridesFen'] = {}
            for product_id, entry in overrides.items():
                if not isinstance(product_id, str) or not product_id.strip() or not isinstance(entry, dict) or not entry.get('authorization'): raise ValueError()
                policy['perProductOverridesFen'][product_id] = fen(entry['budget_rmb'])
        return policy
    except (OSError, KeyError, TypeError, ValueError, InvalidOperation):
        raise ValueError('生图经营配置缺失或无效，未调用付费接口') from None


def product_limits(product_id):
    policy = limits()
    amount = policy.get('perProductOverridesFen', {}).get(product_id)
    if amount is not None: policy = {**policy, 'perProductFen': amount}
    return policy


def fen(value, zero=False):
    try:
        if isinstance(value, bool):
            raise ValueError()
        amount = Decimal(str(value)) * 100
        if not amount.is_finite() or amount != amount.to_integral_value() or amount < (0 if zero else 1):
            raise ValueError()
        return int(amount)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError('人民币金额必须为精确到分的有效数字') from None


def day():
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS image_costs (
        id TEXT PRIMARY KEY, product_id TEXT NOT NULL, day TEXT NOT NULL,
        reserved_fen INTEGER NOT NULL, actual_fen INTEGER, state TEXT NOT NULL,
        external_id TEXT, body TEXT NOT NULL)''')


def verified_quote(root, provider, data, preview=False):
    if provider=='OpenAI-compatible' and data.get('providerEndpoint')==codex_tools_quota.BASE:
        return {**codex_tools_quota.verify(configuration().get('codex_tools',{}),data),
                'reservationBasis':'chatgpt_subscription_quota'}
    try:
        quotes = json.loads((Path(root) / 'image-price-quotes.json').read_text(encoding='utf-8'))
        for quote in quotes['quotes']:
            if not isinstance(quote, dict):
                continue
            if (quote.get('provider') == provider and quote.get('model') == data.get('model')
                    and quote.get('endpoint') == data.get('providerEndpoint')
                    and quote.get('size') == data.get('size', '1:1')
                    and quote.get('resolution') == data.get('resolution', '1K')
                    and quote.get('quantity') == 1
                    and (provider != 'OpenAI-compatible' or all(quote.get(k) == data.get(k) and data.get(k)
                                                               for k in ('protocol','quality')))
                    and quote.get('verified') is True and quote.get('source')
                    and isinstance(quote.get('source'), str)
                    and date.fromisoformat(quote.get('verifiedAt', '')) <= date.fromisoformat(day())
                    and date.fromisoformat(quote.get('validUntil', '')) >= date.fromisoformat(day())):
                if quote.get('currency') == 'CNY':
                    return {**quote, 'maximumFen': fen(quote['maximumRmb']), 'reservationBasis': 'provider_cny_quote'}
                if quote.get('currency') == 'USD':
                    return converted_quote(quote, preview=preview)
    except (OSError, KeyError, TypeError, ValueError, InvalidOperation):
        pass
    raise ValueError('未核实此服务、模型、比例和分辨率的单次人民币最高费用；未调用付费接口')


def converted_quote(quote, preview=False):
    """A user-enabled budget conversion, never a verified CNY provider charge."""
    policy = configuration().get('fx_budget_policy', {})
    enabled = (policy.get('mode') == 'daily_boc_usd_sell_buffer' and policy.get('enabled') is True
               and policy.get('bufferPercent') == 20)
    if not enabled and not preview:
        raise ValueError('美元报价的预算换算规则未启用')
    fx = quote.get('fx', {})
    if (fx.get('currency') != 'USD/CNY' or fx.get('date') != day()
            or fx.get('source') != 'https://www.boc.cn/sourcedb/whpj/'
            or fx.get('rateType') != 'bank_sell_per_usd'
            or date.fromisoformat(quote['verifiedAt']) != date.fromisoformat(day())):
        raise ValueError('美元预算需要当天核实的中行现汇卖出价和模型报价')
    amount, rate = Decimal(str(quote.get('maximumUsd'))), Decimal(str(fx.get('rate')))
    if (isinstance(quote.get('maximumUsd'), bool) or isinstance(fx.get('rate'), bool)
            or not amount.is_finite() or not rate.is_finite() or amount <= 0 or rate <= 0):
        raise ValueError('美元报价或汇率无效')
    base = amount * rate
    reserved = (base * Decimal('1.20') * 100).to_integral_value(rounding=ROUND_CEILING)
    return {**quote, 'maximumFen': int(reserved), 'reservationBasis': 'usd_fx_budget_estimate',
            'estimatedRmb': str(base), 'bufferPercent': 20, 'conversionPolicyEnabled': enabled,
            'note': '按当天中行现汇卖出价加20%缓冲预留，向上取整到分；不是人民币收费保证或已结算账单。'}


def reserve(conn, root, attempt, data):
    """Called inside the same IMMEDIATE transaction as the submission journal."""
    policy = product_limits(attempt['productId'])
    if not policy['enabled']:
        raise ValueError('生图当前关闭；请先核实报价并启用经营配置，未调用付费接口')
    if attempt['provider']=='OpenAI-compatible' and data.get('providerEndpoint')==codex_tools_quota.BASE:
        return codex_tools_quota.reserve(conn,configuration().get('codex_tools',{}),attempt,data,day())
    quote = verified_quote(root, attempt['provider'], data)
    amount = quote['maximumFen']
    schema(conn)
    if conn.execute("SELECT 1 FROM image_costs WHERE state='over_budget' LIMIT 1").fetchone():
        raise ValueError('存在超预算账单，先核对费用和经营配置，未再次提交')
    product_used = conn.execute('''SELECT COALESCE(SUM(CASE WHEN state='reserved'
        THEN reserved_fen ELSE actual_fen END),0) FROM image_costs WHERE product_id=?''',
        (attempt['productId'],)).fetchone()[0]
    # Unsettled prior days remain reserved until the provider bill is reconciled.
    daily_used = conn.execute('''SELECT COALESCE(SUM(CASE WHEN state='reserved'
        THEN reserved_fen ELSE actual_fen END),0) FROM image_costs WHERE day=? OR state='reserved' ''',
        (day(),)).fetchone()[0]
    if product_used + amount > policy['perProductFen']:
        raise ValueError('每款生图预算不足，含历史费用和未结算预留；未再次提交')
    if daily_used + amount > policy['dailyFen']:
        raise ValueError('每日生图预算不足，含未结算预留；未再次提交')
    conn.execute('INSERT INTO image_costs VALUES (?,?,?,?,NULL,?,NULL,?)',
                 (attempt['id'], attempt['productId'], day(), amount, 'reserved',
                  json.dumps({'quote': quote, 'limits': policy}, ensure_ascii=False)))
    return {'reservationId': attempt['id'], 'reservedFen': amount, 'currency': 'CNY'}


def settle(conn, data):
    actual = fen(data.get('actualRmb'), zero=True)
    note, external_id = data.get('evidence'), data.get('externalId')
    if not isinstance(note, str) or not 8 <= len(note.strip()) <= 2000:
        raise ValueError('结算需提供账单核实依据，零费用也须确认未收费')
    if not isinstance(external_id, str) or not 1 <= len(external_id.strip()) <= 200:
        raise ValueError('结算需提供服务商任务号或账单对账编号')
    schema(conn)
    row = conn.execute('SELECT product_id,day,reserved_fen,state,external_id,body FROM image_costs WHERE id=?',
                       (data.get('reservationId'),)).fetchone()
    if not row or row[3] != 'reserved':
        raise ValueError('费用预留不存在或已结算，不可重复记账')
    if row[4] and row[4] != external_id.strip():
        raise ValueError('服务商任务号与预留记录不一致')
    body = json.loads(row[5])
    policy = body['limits']
    current = product_limits(row[0])
    others = conn.execute('''SELECT product_id,day,CASE WHEN state='reserved' THEN reserved_fen
        ELSE actual_fen END FROM image_costs WHERE id<>?''', (data['reservationId'],)).fetchall()
    product_used = sum(amount for product, _, amount in others if product == row[0])
    daily_used = sum(amount for _, date, amount in others if date == row[1])
    over = (actual > row[2] or actual + product_used > min(policy['perProductFen'], current['perProductFen'])
            or actual + daily_used > min(policy['dailyFen'], current['dailyFen']))
    state = 'over_budget' if over else 'settled'
    body.update(evidence=note.strip(), settledAt=datetime.now(timezone.utc).isoformat())
    conn.execute('UPDATE image_costs SET actual_fen=?,state=?,external_id=?,body=? WHERE id=?',
                 (actual, state, external_id.strip(), json.dumps(body, ensure_ascii=False), data['reservationId']))
    return {'reservationId': data['reservationId'], 'state': state, 'actualFen': actual, 'currency': 'CNY'}


def status(conn, product_id=None):
    schema(conn)
    rows = conn.execute('SELECT id,product_id,day,reserved_fen,actual_fen,state,external_id FROM image_costs ORDER BY rowid DESC').fetchall()
    fields = ('reservationId', 'productId', 'day', 'reservedFen', 'actualFen', 'state', 'externalId')
    return {'limits': product_limits(product_id) if product_id else limits(), 'day': day(), 'currency': 'CNY',
            'reservations': [dict(zip(fields, row)) for row in rows],
            'subscriptionRequests':codex_tools_quota.status(conn),
            'subscriptionPolicyEnabled':configuration().get('codex_tools',{}).get('enabled') is True,
            'note': '本地费用预留，不代表服务商侧硬封顶；实际收费需账单核实，未知任务不释放。'}
