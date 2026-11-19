"""Resolve image colours against the product's recorded child variants."""
import supplier_variants
import asin_reference


def observed_children(product):
    return product.get('sourceImport', {}).get('amazon', {}).get('variants')


def colour_key(value):
    return supplier_variants._colour(value)


def amazon_colour_references(product, children):
    source = product.get('sourceImport') or {}
    captured = product.get('editorAsinReference')
    market = source.get('market') or product.get('market')
    if not isinstance(captured, dict) or captured.get('market') != market or market not in asin_reference.importer.MARKET_DOMAINS:
        return
    actual = {(row.get('asin'), colour_key(row.get('color_name'))) for row in children if row.get('asin')}
    captured_children = {(row.get('asin'), colour_key(row.get('color')))
                         for row in captured.get('variants') or [] if isinstance(row, dict)}
    linked_colours = {key for _, key in actual & captured_children}
    for row in captured.get('colors') or []:
        if not isinstance(row, dict) or not isinstance(image := row.get('mainImage'), dict):
            continue
        key = colour_key(row.get('color'))
        asin = image.get('sourceAsin')
        if (key not in linked_colours or not isinstance(asin, str) or not asin_reference.ASIN.fullmatch(asin)
                or (asin, key) not in captured_children or not asin_reference.media_key(image.get('url'))
                or image.get('sourceUrl') != asin_reference.product_url(market, asin) or not image.get('checkedAt')):
            continue
        yield key, {'url':image['url'], 'aliases':[row['color']], 'referenceType':'amazon_variant_main',
                    'sourceAsin':asin, 'sourceUrl':image['sourceUrl']}


def catalog(product, *, include_excluded=False):
    groups = {}
    children = observed_children(product)
    if not isinstance(children, list):
        return groups
    amazon = product['sourceImport']['amazon']
    eligible = amazon.get('listingEligibleVariants')
    eligible_asins = {row['asin'] for row in eligible if isinstance(row, dict) and isinstance(row.get('asin'), str)} \
        if isinstance(eligible, list) else None
    children = [{**row, 'color_name':row.get('color_name') or row.get('color'),
                 'size_name':row.get('size_name') or row.get('size')} for row in children
                if isinstance(row, dict) and (include_excluded or eligible_asins is None or row.get('asin') in eligible_asins)]
    bindings = product.get('assetColorBindings') or {}
    for row in children:
        if not isinstance(row, dict):
            continue
        key = colour_key(row.get('color_name'))
        if not key:
            continue
        group = groups.setdefault(key, {'key':key, 'color':row['color_name'].strip(),
                                         'children':[], 'references':[], 'issues':[]})
        group['children'].append({'sku':row.get('sku'), 'size':row.get('size_name'), 'asin':row.get('asin')})

    references = [*product.get('supplierColorReferences', []), *product.get('assets', []),
                  *({'url':url} for url in bindings)]
    for ref in references:
        url = ref.get('url')
        if not isinstance(url, str) or not url.startswith(('/uploads/', 'https://')):
            continue
        names = [bindings.get(url), ref.get('color'), ref.get('english')]
        explicit = colour_key(bindings.get(url))
        matches = {colour_key(name) for name in names} & groups.keys()
        if explicit in groups:
            matches = {explicit}
        if len(matches) != 1:
            continue
        key = next(iter(matches))
        group = groups[key]
        if not any(item['url'] == url for item in group['references']):
            group['references'].append({'url':url, 'aliases':list(filter(None,names)),
                'referenceType':ref.get('referenceType') or 'supplier_product_image'})

    for key, ref in amazon_colour_references(product, children):
        if not any(item['url'] == ref['url'] for item in groups[key]['references']):
            groups[key]['references'].append(ref)

    all_skus = [child['sku'] for group in groups.values() for child in group['children']
                if isinstance(child['sku'], str) and child['sku'].strip()]
    reference_urls = [ref['url'] for group in groups.values() for ref in group['references']]
    for key,group in groups.items():
        group['references'] = [ref for ref in group['references']
                               if reference_urls.count(ref['url']) == 1
                               and ref['referenceType'] != 'supplier_ai_preview']
        rows = [row for row in children if isinstance(row,dict) and colour_key(row.get('color_name'))==key]
        scoped = {**product, 'sourceImport':{**product['sourceImport'], 'amazon':{**amazon,'variants':rows}}}
        # A one-size colour still needs supplier evidence if the product has multiple children.
        if len(children)>1 and 'supplierVariantCoverage' not in scoped:
            scoped['supplierVariantCoverage'] = {}
        group['issues'].extend(supplier_variants.inspect(scoped)['issues'])
        sizes = [supplier_variants._size(child['size']) for child in group['children']]
        if not all(sizes) or len(set(sizes)) != len(sizes):
            group['issues'].append('该颜色的尺码缺失或重复')
        if any(not isinstance(child['sku'],str) or not child['sku'].strip() or all_skus.count(child['sku'])!=1
               for child in group['children']):
            group['issues'].append('该颜色的子 SKU 缺失或重复')
        if not group['references']:
            group['issues'].append('缺少关联的同色参考图')
        group['ready'] = not group['issues']
    return groups


def display_catalog(product):
    """Show excluded colours and their evidence without enabling production."""
    groups = catalog(product)
    for group in groups.values():
        group['listingEligible'] = True
    excluded = product.get('sourceImport', {}).get('amazon', {}).get('excludedVariants') or []
    for key, group in catalog(product, include_excluded=True).items():
        if key in groups:
            continue
        asins = {child['asin'] for child in group['children']}
        reasons = list(dict.fromkeys(row['reason'].strip() for row in excluded
                       if isinstance(row, dict) and row.get('asin') in asins
                       and isinstance(row.get('reason'), str) and row['reason'].strip()))
        reasons = reasons or ['该颜色尚未纳入可刊登变体']
        group.update(listingEligible=False, exclusionReasons=reasons, ready=False)
        group['issues'] = list(dict.fromkeys([*group['issues'], *reasons]))
        _, checked = reinstatement_candidate(product, key)
        group['canReinstate'] = checked['ready']
        group['reinstatementIssues'] = checked['issues']
        groups[key] = group
    return groups


def reinstatement_candidate(product, key):
    """Compatibility entry point; validation lives in colour_rules."""
    from colour_rules import reinstatement_candidate as validate
    return validate(product, key)


def reinstate(product, data, actor):
    """Compatibility entry point; product updates live in colour_associations."""
    from colour_associations import reinstate as update
    return update(product, data, actor)


def confirmed_master(product, key):
    """Compatibility entry point; validation lives in colour_rules."""
    from colour_rules import confirmed_master as validate
    return validate(product, key)


def set_master(product, data, actor):
    """Compatibility entry point; product updates live in colour_associations."""
    from colour_associations import set_master as update
    return update(product, data, actor)


def validate_master_changes(previous, current):
    """Keep legacy whole-workspace saves under the same master validation."""
    from colour_rules import validate_master_changes as validate
    return validate(previous, current)


def resolve(groups, label):
    key = colour_key(label)
    if key in groups:
        return key
    matches = [group['key'] for group in groups.values() if any(
        key == colour_key(alias) for ref in group['references'] for alias in ref['aliases'])]
    return matches[0] if key and len(matches) == 1 else ''


def has_reference(group, reference):
    return bool(group and reference and any(ref['url'] == reference for ref in group['references']))
