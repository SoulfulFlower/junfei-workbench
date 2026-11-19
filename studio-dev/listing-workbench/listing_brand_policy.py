"""Brand and mark exclusions for buyer-facing listing text."""
import re


GENERIC_BRANDS = {'', 'generic', 'générique', '无', '其他', '不适用', 'none', 'n/a'}


def excluded_brand_terms(product):
    """Return observed marks that must stay out of copy unless explicitly authorized."""
    product = product if isinstance(product, dict) else {}
    terms = []

    def add(value):
        if isinstance(value, str):
            value = value.strip()
            if value and value.casefold() not in GENERIC_BRANDS and len(value) <= 100:
                terms.append(value)
        elif isinstance(value, (list, tuple, set)):
            for item in value:
                add(item)

    add(product.get('brandExclusions'))
    imported = product.get('sourceImport') if isinstance(product.get('sourceImport'), dict) else {}
    add(imported.get('listingBrandExclusions'))
    supplier = imported.get('supplier') if isinstance(imported.get('supplier'), dict) else {}
    if product.get('brandUseAuthorized') is not True:
        add(product.get('brand'))
    if product.get('manufacturerUseAuthorized') is not True:
        add(product.get('manufacturer'))
    if supplier.get('brandUseAuthorized') is not True:
        add(supplier.get('brand'))
        attrs = supplier.get('attributes') if isinstance(supplier.get('attributes'), dict) else {}
        for key, value in attrs.items():
            if re.search(r'品牌|商标|brand|trademark', str(key), re.I):
                add(value)
    # Adhesive supplier copy may mention a third-party mark outside the brand attribute.
    supplier_text = ' '.join(str(value or '') for value in
        (supplier.get('title'), supplier.get('attributes'), imported.get('supplierNotes')))
    if supplier.get('thirdPartyMarksAuthorized') is not True and re.search(r'(?<![A-Za-z0-9])3M(?![A-Za-z0-9])', supplier_text, re.I):
        add('3M')
    # Amazon reference brands belong to the source listing, not automatically to this product.
    amazon = imported.get('amazon') if isinstance(imported.get('amazon'), dict) else {}
    add(amazon.get('brand'))
    return list(dict.fromkeys(terms))


def find_excluded_brand_terms(value, terms):
    """Find mark mentions with alphanumeric boundaries (e.g. 3M), preserving CJK matching."""
    text = str(value or '')
    found = []
    for term in terms:
        escaped = re.escape(term)
        if re.fullmatch(r'[A-Za-z0-9]+', term):
            pattern = rf'(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])'
        else:
            pattern = escaped
        if re.search(pattern, text, re.I):
            found.append(term)
    return found


def find_in_listing(listing, terms):
    if not terms or not isinstance(listing, dict):
        return []
    keys = ('title', 'highlights', 'bullets', 'description', 'terms', 'zh')
    values = [listing.get(key, '') for key in keys]
    for key in ('translations', 'alternatives'):
        if isinstance(listing.get(key), (dict, list)):
            values.append(listing[key])
    def flatten(value):
        if isinstance(value, dict):
            return ' '.join(flatten(item) for item in value.values())
        if isinstance(value, (list, tuple)):
            return ' '.join(flatten(item) for item in value)
        return str(value or '')
    text = ' '.join(flatten(value) for value in values)
    return find_excluded_brand_terms(text, terms)
