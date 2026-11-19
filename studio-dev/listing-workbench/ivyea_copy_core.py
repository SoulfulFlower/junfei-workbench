"""IvyeaOps copy pipeline source adapter, AGPL-3.0. See SOURCE-NOTICE.md."""
import json

_AMAZON_LISTING_RULES = """# Amazon Listing Generation Rules

## Output Goal
The final deliverable must include:
- 1 generation plan/rationale
- 5 compliant Amazon titles
- 1 Product Highlights string (NEW Amazon field, effective 2026-07-27)
- 2 bullet point sets, each with exactly 5 bullet points
- 2 backend search term strings
- A compliance checklist

## Title Rules (Amazon policy effective 2026-07-27)
- Generate exactly 5 title options.
- Target the marketplace language. For US, write titles in English.
- Length: Every title MUST NOT exceed 75 characters INCLUDING spaces. This is the single hard limit for ALL categories. Count spaces.
- Mobile Optimization: Front-load the product type and 1-2 primary keywords within the first ~60 characters.
- Do NOT keyword-stuff or list specs in the title. Move secondary keywords/attributes to Product Highlights and bullets instead.
- Put "what the product IS" in the title; "what advantages it has" go in Product Highlights.
- Use title case. Do not use ALL CAPS.
- Forbidden Words: "Gift", "Free", "Bonus", "Warranty", "Hot Item", "Best Seller", "No.1", price/delivery promises.
- Do not include unsupported claims, medical claims, or subjective claims such as "best" or "top-rated".

## Product Highlights Rules (NEW field, effective 2026-07-27)
- Generate exactly 1 highlights string.
- Length: MUST NOT exceed 125 characters INCLUDING spaces.
- Use short, benefit/feature-driven PHRASES, NOT full sentences. Separate phrases with ", " (comma + space).
- Cover the most decisive of: material, core function, usage scenario, compatibility/fit, key spec.
  Example: "Non-stick, Food Grade, Heat Resistant 220°C, Fits Ninja Crispi, 100 PCS".
- This field IS searchable: naturally embed core keywords that are NOT already in the title (avoid duplication).
- It only displays on the storefront when the title is under 75 characters, so make it information-dense.

## Bullet Point Rules
- Generate exactly 2 bullet point sets.
- Set A (Conversion Focus): Focus on emotional benefits, usage scenarios, and persuasion. Use [Bold Header] for each bullet.
- Set B (Rufus/QA Focus): Focus on factual specifications, technical details, and answering shopper questions.
- Each set must contain exactly 5 bullets.
- Cover material/structure, core function, usage scenario, gift/audience fit, and risk-reducing details.
- Explicit Attributes: State key attributes in "[Attribute]: [Detail]" format.
- Avoid prohibited terms: medical claims, guaranteed outcomes, competitor attacks, prices, promotions, URLs.

## Search Term Rules
- Generate exactly 2 backend search term strings.
- Length Limit: Each string MUST be under 249 bytes. Use lowercase, space-separated terms. No commas.
- Do not repeat keywords already in the title. Prefer synonyms, spelling variants, use cases, long-tail terms.

## Output Format (JSON)
Return a JSON object with these fields:
{
  "rationale": "Strategy explanation",
  "titles": ["Title 1 (<=75 chars incl spaces)", "Title 2", "Title 3", "Title 4", "Title 5"],
  "highlights": "phrase1, phrase2, phrase3, ... (single string, <=125 chars incl spaces)",
  "bullets_a": ["Bullet 1", "Bullet 2", "Bullet 3", "Bullet 4", "Bullet 5"],
  "bullets_b": ["Bullet 1", "Bullet 2", "Bullet 3", "Bullet 4", "Bullet 5"],
  "search_terms": ["string 1 under 249 chars", "string 2 under 249 chars"],
  "compliance_notes": ["any compliance issues or notes"]
}"""

def _build_listing_prompt(
    marketplace: str,
    product_type: str,
    product_notes: str,
    vision_result: dict,
    competitor_result: dict,
) -> str:
    parts = [
        "You are an Amazon listing copywriting expert.",
        f"Marketplace: {marketplace}",
        f"Product Type: {product_type}",
        "",
    ]

    if product_notes:
        parts.append(f"Seller Notes (product specs/features):\n{product_notes}")
        parts.append("")

    if vision_result.get("mode") == "vision":
        features = vision_result.get("features", [])
        if features:
            parts.append("Image Analysis - Observed Features:\n" + "\n".join(f"- {f}" for f in features[:20]))
        materials = vision_result.get("materials", "")
        if materials:
            parts.append(f"Materials: {materials}")
        scenarios = vision_result.get("scenarios", [])
        if scenarios:
            parts.append(f"Visible Use Scenarios: {', '.join(scenarios[:5])}")
        parts.append("")

    if competitor_result.get("available"):
        comp_data = competitor_result.get("data", {})
        parts.append("Competitor Data (from market research):")
        parts.append(json.dumps(comp_data, ensure_ascii=False)[:3000])
        parts.append("")

    parts.append(_AMAZON_LISTING_RULES)
    parts.append("")
    parts.append("Now generate the listing copy. Return ONLY valid JSON, no other text.")

    return "\n".join(parts)


def production_writing_rules():
    """Keep IvyeaOps writing guidance and apply the workbench's output contract."""
    rules = _AMAZON_LISTING_RULES.split('## Title Rules', 1)[1].split('## Output Format', 1)[0]
    rules = '## Title Rules' + rules
    rules = rules.replace('Generate exactly 5 title options.', 'Generate exactly one title.')
    rules = rules.replace(
        '- Generate exactly 2 bullet point sets.\n'
        '- Set A (Conversion Focus): Focus on emotional benefits, usage scenarios, and persuasion. Use [Bold Header] for each bullet.\n'
        '- Set B (Rufus/QA Focus): Focus on factual specifications, technical details, and answering shopper questions.\n'
        '- Each set must contain exactly 5 bullets.',
        '- Generate exactly one set of five bullets. Combine practical buyer benefits with factual answers to '
        'shopper questions. Use a short bracketed heading. Each bullet must have 250–500 characters including spaces.',
    )
    rules = rules.replace('gift/audience fit', 'audience fit')
    rules = rules.replace(
        '- Generate exactly 2 backend search term strings.\n'
        '- Length Limit: Each string MUST be under 249 bytes. Use lowercase, space-separated terms. No commas.',
        '- Generate one backend search term string of 200–250 characters including spaces after deduplication. '
        'Maximum 249 UTF-8 bytes. Use lowercase, space-separated terms. No commas.',
    )
    return '# IvyeaOps Listing Writing Rules\n\n' + rules.strip()
