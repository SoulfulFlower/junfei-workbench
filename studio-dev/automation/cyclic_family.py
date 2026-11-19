"""Read observed Amazon children without adding colour/size combinations."""

def observed_family(fields):
    dimensions = fields['dimensions'][0]
    if dimensions.count('color_name') != 1 or any(d not in {'color_name', 'size_name'} for d in dimensions):
        raise ValueError('Unsupported variation dimensions; review actual source')
    if dimensions.count('size_name') > 1:
        raise ValueError('Duplicate size dimension')
    ci = dimensions.index('color_name')
    si = dimensions.index('size_name') if 'size_name' in dimensions else None
    values = fields['variationValues'][0]
    rows = []
    for asin, attributes in fields['dimensionValuesDisplayData'][0].items():
        if len(attributes) != len(dimensions):
            raise ValueError('Incomplete observed child attributes')
        color = attributes[ci]
        size = attributes[si] if si is not None else ''
        if color not in values['color_name'] or (si is not None and size not in values['size_name']):
            raise ValueError('Child value missing from declared dimension values')
        rows.append({'asin': asin, 'color': color, 'size': size})
    if not rows:
        raise ValueError('No observed children')
    colors = [c for c in values['color_name'] if any(r['color'] == c for r in rows)]
    sizes = [s for s in values.get('size_name', []) if any(r['size'] == s for r in rows)] if si is not None else []
    return {'dimensions': dimensions, 'variants': rows, 'colors': colors, 'sizes': sizes, 'size_dimension_present': si is not None}
