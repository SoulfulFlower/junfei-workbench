"""Recalculate apparel quote scenarios from verified per-product inputs.

Pure local estimate: no ledger enrollment, price update or publication.
"""
import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING
import hashlib
import json
from pathlib import Path


def calculate(spec, config, quote_root):
    d = lambda value: Decimal(str(value))
    pricing = config['pricing']
    if pricing.get('method') != 'quote_cost_markup':
        raise ValueError('需要当前已授权的报价定价政策')
    required = ('purchaseCny', 'domesticCny', 'packagedWeightG', 'lengthCm', 'widthCm', 'heightCm', 'marketTotalUsd')
    if any(name not in spec or isinstance(spec[name], bool) for name in required):
        raise ValueError('采购、国内运费、真实包装重三维及含运市场价必须齐全')
    values = {name: d(spec[name]) for name in required}
    if any(not value.is_finite() or value < 0 or (name != 'domesticCny' and value == 0) for name, value in values.items()):
        raise ValueError('价格或包装数据无效')
    fx = spec['gbpFxEvidence']
    execution_day = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d')
    if (fx.get('url') != 'https://www.boc.cn/sourcedb/whpj/' or fx.get('currency') != 'GBP' or
            fx.get('basis') != 'spot_sell_per_100' or not fx.get('publishedAt') or not fx.get('observedRaw')):
        raise ValueError('英国汇率须保留执行日中行现汇卖出价依据')
    if fx['publishedAt'][:10] != execution_day:
        raise ValueError('英国汇率不是本次中国执行日，不沿用旧批次价格')
    gbp_fx = d(fx['cnyPer100'])/100
    if not gbp_fx.is_finite() or gbp_fx <= 0:
        raise ValueError('英镑汇率无效')
    scenario = pricing['draft_estimation']
    if scenario.get('scope') != 'draft_only':
        raise ValueError('缺少基础报价情景')
    billed = max(values['packagedWeightG']/1000,
                 values['lengthCm']*values['widthCm']*values['heightCm']/d(pricing['volumetric_divisor']))
    grams = (billed*1000).to_integral_value(rounding=ROUND_CEILING)
    results = {}
    for market, country, rate in [('US', 'US', d(pricing['exchange_rate_cny_per_usd'])), ('UK', 'GB', gbp_fx)]:
        policy = pricing if market == 'US' else pricing['marketplace_policies']['UK']
        fee, markup = d(policy['platform_fee_rate']), d(policy['cost_markup_rate'])
        if not 0 <= fee < 1 or markup < 0:
            raise ValueError('费率或成本加价政策无效')
        candidates = []
        for channel in pricing['preferred_channels_by_product_type']['apparel'][market]:
            filename, code = channel.split('|', 1)
            if Path(filename).name != filename:
                raise ValueError('报价文件路径无效')
            raw = (Path(quote_root)/filename).read_bytes()
            table = json.loads(raw)
            for row in table['records']:
                if (row.get('channel_code') != code or row.get('country_code') != country or
                        not d(row['start_weight']) <= grams <= d(row['end_weight'])):
                    continue
                freight = billed*d(row['first_freight'])+d(row['handling_fee'])+d(scenario['surcharge_rmb'])
                total = values['purchaseCny']+values['domesticCny']+freight+d(scenario['other_costs_rmb'])
                net = rate*(1-fee)
                price = (total*(1+markup)/net).quantize(d('.01'), rounding=ROUND_CEILING)
                result = {'channel': channel, 'sourceRow': row['source_row'], 'quoteSha256': hashlib.sha256(raw).hexdigest(),
                          'sourceHeader': table.get('source_header'), 'billedWeightKg': str(billed),
                          'rateCnyKg': str(row['first_freight']), 'handlingCny': str(row['handling_fee']),
                          'freightCny': str(freight), 'totalCostCny': str(total), 'formulaPrice': str(price),
                          'currency': 'USD' if market == 'US' else 'GBP', 'fxCnyPerUnit': str(rate)}
                if market == 'US':
                    result['profitAtMarketPriceCny'] = str(values['marketTotalUsd']*net-total)
                candidates.append(result)
        if not candidates:
            raise ValueError('该包装没有匹配的'+market+'服装报价档位')
        results[market] = sorted(candidates, key=lambda row: d(row['totalCostCny']))
    return {'supplierUrl': spec['supplierUrl'], 'inputs': spec, 'scenarios': results,
            'selected': {market: rows[0] for market, rows in results.items()},
            'positiveEstimatedMarketProfit': d(results['US'][0]['profitAtMarketPriceCny']) > 0,
            'scope': 'quote_based_draft_base_scenario', 'publicationReady': False,
            'assumptions': scenario, 'limits': ['基础情景未确认附加费按已有授权计入；不是承运或利润保证。',
            '报价有效性沿用用户2026-11-06确认；仍保留原表、适用线路与包装档位依据。']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', required=True)
    parser.add_argument('--config', required=True)
    parser.add_argument('--quote-root', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = calculate(json.loads(Path(args.spec).read_text(encoding='utf-8-sig')),
                       json.loads(Path(args.config).read_text(encoding='utf-8-sig')), args.quote_root)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'positiveEstimatedMarketProfit': result['positiveEstimatedMarketProfit'],
                      'selected': result['selected'], 'output': str(Path(args.output).resolve())}, ensure_ascii=False))
