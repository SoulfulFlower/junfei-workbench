"""Quote-based draft estimates. No legacy fixed freight or assumed live price."""
import hashlib
import json
import re
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from pathlib import Path
import app_paths


def number(value, label, positive=False):
    try:
        if isinstance(value, bool): raise InvalidOperation
        result=Decimal(str(value))
        if not result.is_finite() or result < 0 or (positive and result <= 0): raise InvalidOperation
        return result
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(label+'无效') from None


def calculate(policy, cost, weight, dimensions, rate, handling, surcharge, other):
    cost=number(cost,'采购价',True);weight=number(weight,'包装重量',True)
    dims=[number(x,'包装尺寸',True) for x in dimensions]
    if len(dims)!=3: raise ValueError('包装长宽高必须完整')
    divisor=number(policy.get('volumetric_divisor'),'体积系数',True)
    fx=number(policy.get('exchange_rate_cny_per_usd'),'汇率',True)
    fee=number(policy.get('platform_fee_rate'),'佣金')
    markup=number(policy.get('cost_markup_rate'),'成本加价率')
    if fee >= 1: raise ValueError('佣金必须小于100%')
    volume=dims[0]*dims[1]*dims[2]/divisor
    billed=max(weight,volume)
    freight=billed*number(rate,'公斤价')+number(handling,'处理费')+number(surcharge,'附加费')
    total=cost+freight+number(other,'其他费用')
    price=(total*(1+markup)/(fx*(1-fee))).quantize(Decimal('.01'),rounding=ROUND_CEILING)
    return {k:str(v) for k,v in {'volumetricKg':volume,'chargeableKg':billed,
        'freightRmb':freight,'totalCostRmb':total,'priceUsd':price}.items()}


def policy():
    import agent_erp
    return json.loads((agent_erp.project_root()/'automation/config.json').read_text(encoding='utf-8'))['pricing']


def estimate(product, market, count=1):
    config=policy()
    if config.get('method')!='quote_cost_markup' or market!='US':
        raise ValueError('此站点未配置报价定价，请填写明确变体售价')
    scenario=config.get('draft_estimation',{})
    if scenario.get('scope')!='draft_only': raise ValueError('未配置草稿估价情景')
    if count>1 and not product.get('purchasePriceUniformAcrossVariants'):
        raise ValueError('请确认采购价适用于全部颜色和尺码，或填写逐变体售价')
    if count>1 and not product.get('packageWeightUniformAcrossVariants'):
        raise ValueError('请确认包装重量适用于全部颜色和尺码，或填写逐变体售价')
    match=re.fullmatch(r'\s*(?:RMB|CNY|¥|￥)?\s*(\d+(?:\.\d{1,2})?)\s*(?:元|RMB|CNY)?\s*',str(product.get('purchasePrice') or ''),re.I)
    if not match: raise ValueError('缺少明确人民币采购价')
    cost=number(match[1],'采购价',True)
    match=re.fullmatch(r'\s*(\d+(?:\.\d+)?)\s*(g|gram|grams|克|kg|千克)\s*',str(product.get('packageWeight') or ''),re.I)
    if not match: raise ValueError('缺少带单位包装重量')
    weight=number(match[1],'包装重量',True)/(1 if match[2].lower() in ('kg','千克') else 1000)
    observation=product.get('supplierPackageObservation') or {}
    if observation.get('adoptedAsPackageWeight') is True:
        if observation.get('sourceUrl')!=product.get('sourceUrl') or number(observation.get('weightG'),'货源重量',True)!=weight*1000:
            raise ValueError('货源包装记录与当前产品不同')
        dims=[observation.get(k) for k in ('lengthCm','widthCm','heightCm')]
    else:
        match=re.fullmatch(r'\s*(\d+(?:\.\d+)?)\s*[x×*]\s*(\d+(?:\.\d+)?)\s*[x×*]\s*(\d+(?:\.\d+)?)\s*cm\s*',str(product.get('packageDimensions') or ''),re.I)
        if not match: raise ValueError('缺少明确包装长宽高cm；不猜折叠尺寸')
        dims=list(match.groups())
    candidates=[]
    rate_root=app_paths.APP/'data/logistics'
    for channel in config.get('preferred_channels',{}).get(market,[]):
        filename,code=channel.split('|',1)
        if Path(filename).name!=filename: raise ValueError('报价路径无效')
        raw=(rate_root/filename).read_bytes();table=json.loads(raw)
        for row in table.get('records',[]):
            if row.get('country_code')!=market or row.get('channel_code')!=code: continue
            result=calculate(config,cost,weight,dims,row.get('first_freight'),row.get('handling_fee'),scenario.get('surcharge_rmb'),scenario.get('other_costs_rmb'))
            grams=(Decimal(result['chargeableKg'])*1000).to_integral_value(rounding=ROUND_CEILING)
            if not number(row.get('start_weight'),'起始档位')<=grams<=number(row.get('end_weight'),'结束档位'): continue
            candidates.append({**result,'channel':channel,'channelName':row.get('channel_name'),
                'sourceRow':row.get('source_row'),'sourceDate':table.get('source_header'),
                'quoteSha256':hashlib.sha256(raw).hexdigest(),'rateRmbKg':str(row['first_freight']),
                'handlingRmb':str(row['handling_fee']),'costRmb':str(cost),
                'weightKg':str(weight),'dimensionsCm':list(map(str,dims)),
                'policy':{k:config[k] for k in ('exchange_rate_cny_per_usd','platform_fee_rate','cost_markup_rate','volumetric_divisor')},
                'scope':'draft_estimate_only','finalPriceVerified':False,
                'assumptions':scenario,'warnings':[
                    '仅按已提供报价表估算，报价日期不代表当前有效期。',
                    '附加费及其他费用按明确的基础情景计算，不代表实际费用为零。',
                    '未证明实际折叠尺寸、渠道尺寸限制、最低计费、进位、税费和燃油费；不是承运或利润保证。']})
    if not candidates: raise ValueError('包装计费重没有匹配已配置普货渠道的报价档位')
    return min(candidates,key=lambda x:(Decimal(x['freightRmb']),x['channel']))
