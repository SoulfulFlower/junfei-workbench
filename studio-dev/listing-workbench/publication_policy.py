"""Default US-to-UK follow-up rules for the explicit publication executor.

These helpers describe new-task defaults and validate recorded identities. They
never open a browser, copy a product, submit a listing or change existing jobs.
"""
import json
from pathlib import Path
import re


CONFIG = Path(__file__).resolve().parent.parent / 'automation' / 'config.json'
COPY_STATUSES = ('publishing', 'accepted')


def _configuration():
    try:
        return json.loads(CONFIG.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as error:
        raise ValueError('无法读取默认跨站发布规则，请检查配置') from error


def default_followup(market, *, config=None):
    """Return new-task defaults; reading this policy never starts execution.

    ``config`` is an optional full config dictionary for isolated checks. Old
    tasks are not migrated by reading this rule, and UK is not chained again.
    """
    if market != 'US':
        return None
    settings = _configuration() if config is None else config
    if not isinstance(settings, dict) or not isinstance(settings.get('publishing', {}), dict):
        raise ValueError('默认跨站发布配置格式无效')
    policy = settings.get('publishing', {}).get('cross_marketplace_followup')
    if policy is None:
        return None
    if not isinstance(policy, dict):
        raise ValueError('默认跨站发布配置格式无效')
    if policy.get('enabled') is not True:
        return None
    if policy.get('source_marketplace') != 'US' or policy.get('target_marketplace') != 'UK':
        raise ValueError('当前默认跨站流程仅支持美国站到英国站')
    if policy.get('trigger') != 'publishing':
        raise ValueError('英国复制须以美国真实发布任务进入发布中为前置')
    required = ('preserve_parent_sku', 'preserve_child_skus', 'require_target_store_match',
                'require_gtin_exemption', 'require_shipping_template', 'require_parent_child_sku_readback')
    if any(policy.get(key, True) is not True for key in required):
        raise ValueError('跨站复制必须保留父子SKU并核对目标店铺、豁免、运输模板和SKU回读')
    if policy.get('pricing', 'recalculate_target_currency') != 'recalculate_target_currency':
        raise ValueError('英国售价须按目标币种重新核算，不能直接沿用美元数值')
    if policy.get('unknown_result_policy', 'reconcile_existing_record') != 'reconcile_existing_record':
        raise ValueError('未知复制或发布结果必须先核对原记录，不能自动重发')
    if policy.get('apply_to_existing_products', False) is not False:
        raise ValueError('此默认流程仅应用于新任务，不自动处理现有产品')
    return {
        'enabled': True,
        'sourceMarketplace': 'US', 'targetMarketplace': 'UK', 'trigger': 'publishing',
        'acceptedStatuses': list(COPY_STATUSES), 'requiresPublishId': True,
        'preserveParentSku': True, 'preserveChildSkus': True,
        'requireTargetStoreMatch': True, 'requireGtinExemption': True,
        'requireShippingTemplate': True, 'requireParentChildSkuReadback': True,
        'pricing': 'recalculate_target_currency',
        'unknownResultPolicy': 'reconcile_existing_record',
        'applyToExistingProducts': False,
        'executorAvailable': True,
        'entryPoint': '/api/publication/start',
        'summary': '通过正式发布入口提交美国站，取得真实发布中任务后自动接续英国；父子SKU保持不变。ERP草稿采集入口仍只保存草稿。',
    }


def _publish_id(value):
    return (type(value) is int and value > 0 or
            isinstance(value, str) and re.fullmatch(r'[1-9][0-9]*', value) is not None)


def ready_for_copy(publication):
    """Check the shape of a saved US publishing observation, not online status.

    The caller still owns account/store/draft and variant evidence checks. A
    positive result neither proves an external state nor authorizes execution.
    """
    return bool(isinstance(publication, dict)
        and publication.get('sourceMarketplace') == 'US'
        and publication.get('status') in COPY_STATUSES
        and _publish_id(publication.get('publishId'))
        and not publication.get('errors')
        and not any(publication.get(key) for key in
                    ('resultUnknown', 'submissionUnknown', 'requiresReconciliation', 'unknown')))


def _child_skus(value, label):
    if (not isinstance(value, (list, tuple)) or not value
            or any(not isinstance(sku, str) or not sku.strip() for sku in value)):
        raise ValueError(label + '子SKU须为非空的原始字符串列表')
    if len(set(value)) != len(value):
        raise ValueError(label + '子SKU重复，须先核对真实变体映射')
    return value


def validate_copy_skus(source_parent, source_children, target_parent, target_children):
    """Require exact SKU strings; ERP row ordering may change during copying.

    No trimming, case folding, country suffixes or renumbering is performed.
    Colour/size mapping is a separate readback check at the execution boundary.
    """
    if any(not isinstance(sku, str) or not sku.strip() for sku in (source_parent, target_parent)):
        raise ValueError('源和目标父SKU须为非空原始字符串')
    if source_parent != target_parent:
        raise ValueError('英国父SKU必须与美国原SKU完全一致，不能添加后缀或重新编号')
    source = _child_skus(source_children, '美国')
    target = _child_skus(target_children, '英国')
    if len(source) != len(target) or set(source) != set(target):
        raise ValueError('英国全部子SKU必须与美国逐条完全一致，数量不变，不添加后缀或重新编号')
    return True
