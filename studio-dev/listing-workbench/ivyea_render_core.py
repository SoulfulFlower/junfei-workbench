"""IvyeaOps original deterministic artwork compiler, adapted under AGPL-3.0.
Source: server/app/routers/listing/visuals.py @ 51f5141b475e64b67638f396451d887531caa761.
The original functions are preserved; the product/auth/provider adapter lives separately.
"""
import re
import json

def _clean_text(value):
    return str(value or '').strip()

_PRESENCE_SCALE = {"hero": 0.65, "supporting": 0.32, "environmental": 0.10, "absent": 0.0}

_LAYOUT_FAMILIES = {
    "white_main", "poster_hero", "result_showcase", "split_compare", "spec_grid",
    "scenario_mosaic", "human_context", "in_box_flatlay", "detail_macro", "trust_close",
}

_LAYOUT_DEFAULT_BY_TYPE = {
    "white_main": "white_main", "hero_feature": "poster_hero", "lifestyle": "human_context",
    "detail": "detail_macro", "comparison": "split_compare", "specs": "spec_grid",
    "in_box": "in_box_flatlay", "trust": "trust_close", "aplus_banner": "poster_hero",
}

_TYPE_ZONES = {
    "top-left", "top-center", "top-right", "center-left", "center-right",
    "bottom-left", "bottom-center", "bottom-right",
}
_LAYOUT_STYLES = {
    "editorial": "Use a restrained editorial hierarchy and deliberate negative space.",
    "minimal": "Set the type directly on a calm part of the image, without a title box.",
    "split": "Separate type and subject with a quiet, aligned division in the visual hierarchy.",
    "proof": "Use a restrained typographic emphasis only for evidence supplied in the artwork copy.",
    "grid": "Align the supplied information on a consistent grid with readable spacing.",
}

_LAYOUT_PROMPTS = {
    "white_main": (
        "Pure #FFFFFF seamless Amazon main image. The complete product fills 80-90% of the frame, "
        "with neutral studio lighting. No text, no graphics, no props."
    ),
    "poster_hero": (
        "Premium brand poster layout: a clean title band across the {text_zone} area holds the headline in large "
        "confident type with the subline beneath it in one quiet line{big_number_clause}. The remaining canvas is a "
        "single striking commercial visual for this selling point{presence_clause}. Deliberate negative space, "
        "one clear focal point, editorial balance — designed like a top-tier consumer electronics brand page."
    ),
    "result_showcase": (
        "Outcome-first layout: the canvas is dominated by a beautiful, realistic example of what this product "
        "category delivers ({scene}), presented like professionally captured content{big_number_clause}. Title band "
        "in the {text_zone} area with the headline and subline. The physical product itself stays out of frame — "
        "the result is the hero."
    ),
    "split_compare": (
        "Two-panel comparison layout: the canvas splits into two equal side-by-side panels showing the same subject "
        "under the two contrasted conditions, with a small rounded corner tag on each panel and a subtle divider"
        "{big_number_clause}. Headline and subline sit in a title band across the {text_zone} area. Both panels are "
        "realistic photographic content, identical framing, only the contrasted condition differs."
    ),
    "spec_grid": (
        "Dark premium spec-panel layout: a 2x2 (or 1+2) grid of rounded rectangular panels on a deep neutral "
        "background. Each panel pairs one oversized statistic in bold type with a short caption; one panel may hold "
        "a small angled product render{big_number_clause}. Headline across the {text_zone} area. Clean, technical, "
        "high-contrast — like a flagship electronics brand's spec sheet."
    ),
    "scenario_mosaic": (
        "Use-case mosaic layout: one wide primary panel plus two smaller panels beneath it, each a realistic "
        "photograph of a different real usage scenario ({scene}), each with a tiny corner label chip. Headline and "
        "subline in a title band across the {text_zone} area{presence_clause}."
    ),
    "human_context": (
        "Authentic in-use photograph: a real person naturally using the product in {scene}. The environment and the "
        "human moment dominate the frame{presence_clause}; believable posture, natural light, honest scale. Title "
        "band with headline and subline in the {text_zone} area kept visually calm."
    ),
    "in_box_flatlay": (
        "What's-in-the-box flat lay: every included item arranged neatly on a clean seamless background with even "
        "spacing and soft shadows, the main unit largest{presence_clause}. Small caption under each item is allowed "
        "only if listed in the copy contract. Headline across the {text_zone} area."
    ),
    "detail_macro": (
        "Macro craftsmanship shot: an extreme close crop of the real product detail that proves this selling point, "
        "shallow depth of field, tactile material realism{presence_clause}{big_number_clause}. Headline and subline "
        "in the {text_zone} area over calm negative space."
    ),
    "trust_close": (
        "Trust closing layout: a warm, reassuring real-life scene ({scene}) that summarises the ownership "
        "experience{presence_clause}, with a restrained row of small outlined badges only for claims present in the "
        "copy contract. Headline and subline in the {text_zone} area."
    ),
}

def _ground_render_prompt(value: str) -> str:
    """Remove known prompt habits that systematically create synthetic ad art."""
    text = str(value or "").strip()
    replacements = {
        r"\bno neon(?: light trails?)?\b": "avoid stylized lighting",
        r"\bno floating (?:glass )?panels?\b": "avoid decorative overlays",
        r"\bneon light trails?\b": "subtle practical light",
        r"\bneon\b": "stylized colored lighting",
        r"\blight trails?\b": "natural motion blur",
        r"\bcyber(?:punk)?\b": "contemporary",
        r"\bsci[- ]?fi\b": "contemporary",
        r"\bfloating (?:glass )?panels?\b": "clean negative space",
        r"\bhologra(?:m|phic)\w*\b": "subtle graphic depth",
        r"\bfuturistic platform\b": "simple real surface",
        r"\bepic cinematic\b": "natural editorial",
        r"\bhyperreal fantasy\b": "realistic photography",
        r"\b(?:a )?\$?10,?000 commercial photoshoot\b": "restrained ecommerce photography",
        r"\bnational geographic style\b": "documentary photography",
    }
    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text, flags=re.I)
    return re.sub(r"\s{2,}", " ", text).strip()

def _remove_legacy_textless_directions(value: str) -> str:
    """Remove obsolete 'generate a blank plate' instructions before compiling
    an exact-text final-artwork prompt.

    Existing projects and the deterministic fallback can contain these phrases.
    Keeping them beside the new copy contract gives the image model mutually
    exclusive instructions and is a major source of missing or garbled type.
    """
    text = str(value or "")
    patterns = (
        r"[^.\n]*(?:typography|copy|text)\s+(?:is|will be)\s+(?:added|typeset)\s+(?:later|separately)[^.\n]*[.\n]?",
        r"[^.\n]*(?:reserve|keep)\s+[^.\n]*(?:for later typography|for separately typeset copy)[^.\n]*[.\n]?",
        r"[^.\n]*render\s+no\s+(?:added\s+marketing\s+)?(?:copy|text|words|letters)[^.\n]*[.\n]?",
        r"[^.\n]*\bno\s+(?:added\s+)?(?:text|words|letters|marketing copy)\b[^.\n]*[.\n]?",
        r"[^.\n]*no\s+words,?\s+no\s+icons[^.\n]*[.\n]?",
    )
    for pattern in patterns:
        text = re.sub(pattern, " ", text, flags=re.I)
    return re.sub(r"\s{2,}", " ", text).strip()

def _clamped_float(value, default: float, low: float, high: float) -> float:
    try:
        return max(low, min(float(value), high))
    except (TypeError, ValueError):
        return default

def _readable_accent(value: str) -> str:
    text = str(value or "#67C95B").strip().lstrip("#")
    if len(text) != 6 or not re.fullmatch(r"[0-9a-fA-F]{6}", text):
        return "#67C95B"
    rgb = [int(text[index:index + 2], 16) for index in (0, 2, 4)]
    peak = max(rgb)
    if peak < 150:
        factor = 185 / max(1, peak)
        rgb = [min(230, round(channel * factor)) for channel in rgb]
    return "#" + "".join(f"{channel:02X}" for channel in rgb)

_DEFAULT_SET_PALETTES = {
    "soft_goods": ["#F4F0E8", "#D8C7B5", "#8A6F56", "#4E5B4B", "#282622"],
    "spatial_gear": ["#E9E3D6", "#A7AD8C", "#667151", "#B97645", "#252A23"],
    "rigid_device": ["#EEF1F3", "#C8D0D6", "#657581", "#6E8D72", "#22292E"],
    "category_specific": ["#F2EFE9", "#D7D0C5", "#8A7967", "#66736B", "#292A28"],
}

def _normalise_set_style(style: dict, product_profile: dict) -> dict:
    """Create one concrete, reusable colour grammar for the whole set."""
    source = dict(style) if isinstance(style, dict) else {}
    behaviour = _clean_text(product_profile.get("object_behavior")) or "category_specific"
    requested = " ".join(str(source.get(key) or "") for key in ("palette", "direction"))
    profile_palette = product_profile.get("supporting_palette") or []
    requested += " " + " ".join(str(value) for value in profile_palette)
    colours: list[str] = []
    for value in re.findall(r"#[0-9a-fA-F]{6}\b", requested):
        upper = value.upper()
        if upper not in colours:
            colours.append(upper)
    defaults = _DEFAULT_SET_PALETTES.get(behaviour, _DEFAULT_SET_PALETTES["category_specific"])
    for value in defaults:
        if len(colours) >= 5:
            break
        if value not in colours:
            colours.append(value)
    colours = colours[:5]
    product_colours = [
        _clean_text(value) for value in (product_profile.get("product_colours") or [])
        if _clean_text(value)
    ][:5]
    source.update({
        "direction": _clean_text(source.get("direction")) or (
            f"Product-led {behaviour.replace('_', ' ')} commercial photography with realistic materials"
        ),
        "palette": (
            f"background {colours[0]}; surface {colours[1]}; supporting tone {colours[2]}; "
            f"brand accent {colours[3]}; deep neutral {colours[4]}"
        ),
        "palette_hex": colours,
        "product_colours": product_colours,
        "lighting": _clean_text(source.get("lighting")) or "soft directional key light with consistent neutral white balance",
        "materials": _clean_text(source.get("materials")) or "real category-appropriate materials with restrained supporting props",
        "type_system": _clean_text(source.get("type_system")) or "clean high-contrast ecommerce typography",
        "accent_color": _readable_accent(source.get("accent_color") or colours[3]),
    })
    return source

def _replace_prompt_section(prompt: str, name: str, content: str) -> str:
    """Replace a canonical prompt section so repeated saves never grow prompts."""
    pattern = rf"\s*\[{re.escape(name)}\].*?\[/{re.escape(name)}\]\s*"
    base = re.sub(pattern, " ", str(prompt or ""), flags=re.I | re.S).strip()
    return _ground_render_prompt(f"{base}\n[{name}] {content.strip()} [/{name}]")

def _set_colour_prompt(style: dict, shot_type: str) -> str:
    palette = str(style.get("palette") or "")
    product_colours = ", ".join(style.get("product_colours") or []) or "the exact colours visible in the reference"
    if shot_type == "white_main":
        return f"Keep the pure #FFFFFF background neutral and preserve the exact reference product colours ({product_colours})."
    return (
        f"One locked colour system for the entire image set: {palette}. Lighting: {style.get('lighting')}. "
        f"Product colours are immutable ({product_colours}) and are not replaced by the set palette. "
        "Use these colours across the background, supporting surfaces, ambient grade and typography. "
        "Preserve the same white balance and visual family without making the set look templated."
    )

def _presence_clause(presence: str, product_scale: float) -> str:
    if presence == "hero":
        return (
            "; the exact reference product is the dominant subject, shown complete and "
            "entirely within the frame — the whole product is visible and never cropped by "
            f"the canvas edges — filling roughly {int(product_scale * 100)}% of the frame"
        )
    if presence == "supporting":
        return (
            "; the exact reference product appears clearly but shares the stage, shown "
            "complete and entirely within the frame — the whole product is visible and never "
            f"cropped by the canvas edges — occupying roughly {int(product_scale * 100)}% of the frame"
        )
    if presence == "environmental":
        return (
            "; the exact reference product appears small and natural within the scene, "
            f"around {max(5, int(product_scale * 100))}% of the frame — the story is the environment, not the device"
        )
    return ""

def _is_wide_banner(image: dict) -> bool:
    """成图是否为明显宽幅（宽高比≥1.9，如高级 A+ 1464×600）。方形画廊/主图恒为 False。"""
    try:
        width, height = (int(part) for part in str(image.get("size") or "").lower().split("x")[:2])
    except (ValueError, TypeError):
        return False
    return bool(height) and width / height >= 1.9

def _layout_family(image: dict) -> str:
    layout = str(image.get("layout") or "")
    if layout in _LAYOUT_FAMILIES:
        return layout
    return _LAYOUT_DEFAULT_BY_TYPE.get(str(image.get("shot_type") or ""), "poster_hero")


def _is_detail_crop(image: dict) -> bool:
    return _layout_family(image) == "detail_macro" and not _is_wide_banner(image)


def _wide_banner_clause(image: dict) -> str:
    """宽幅 A+ 横幅（如高级 A+ 1464×600）的横向编排指令。

    版式模板（poster_hero 等）都是照 1600×1600 近方形画布写的——"顶部标题带 + 下方主视觉"。
    放到 600px 高的宽横幅上没有纵向空间，模型只能塌缩成一条"贴上去"的字幕条，还常把主标题
    整条丢掉（画廊图效果好正是因为方形画布放得下完整版式）。此子句仅在明显宽幅（宽高比≥1.9）
    时追加，方形画廊图完全不受影响。"""
    if not _is_wide_banner(image):
        return ""
    geometry = (
        "WIDE BANNER FORMAT: deliver a full-bleed 1464x600 horizontal module. Use the chosen shot direction. "
        "A reference may have neutral carrier margins to establish the input aspect ratio. Only its photographed "
        "region establishes product identity; carrier margins are not an output panel or layout requirement. "
        "If the service paints on a taller canvas, compose the complete horizontal banner in the central band. "
        "The top and bottom may be cropped: keep the focal product detail and all required text within the band "
        "that remains at 2.44:1, with safe margins inside it. Extend the background to every edge."
    )
    if not image.get("text_on_image"):
        return geometry
    return (
        geometry + " Follow this module's planned composition and shared type system. "
        "Let the product photograph or measurement table lead. Keep headings restrained and copy readable. "
        "Text may sit on any planned calm area, with room around it. Do not force every module into the same "
        "opposing image-and-headline split or enlarge a short heading to fill unused space. "
        "Respect the shot's planned crop; do not expand a torso or three-quarter crop into a full-body view. "
        "Keep the product details required by that crop, all table cells and every required string inside the safe delivery band."
    )

def _compile_layout_section(image: dict, custom_direction: str = "") -> str:
    if image.get("size_chart"):
        return (
            "Layout family: spec_grid. Make a readable measurement table with one row per size and no oversized "
            "statistic or promotional badge. Use the real product in Reference Image 1 as the visible background "
            "photo, with the table in a contrasting light panel. Preserve product colour and visible construction. "
            "Copy the column labels, units and measurements exactly from the artwork copy. Do not use any product "
            "illustration from the measurement source."
        ) + " " + _wide_banner_clause(image)
    layout = _layout_family(image)
    presence = str(image.get("product_presence") or "supporting")
    scale = _clamped_float(image.get("product_scale"), _PRESENCE_SCALE.get(presence, 0.32), 0.04, 0.9)
    big_number = _clean_text(image.get("big_number"))
    concept = _clean_text(image.get("visual_concept"))
    camera = _clean_text(image.get("camera_direction"))
    scene = _clean_text(image.get("scene"))
    direction = image.get("scene_direction")
    has_scene_direction = isinstance(direction, dict) and all(
        isinstance(direction.get(key), str) and direction[key]
        for key in ("pose", "angle", "framing", "composition")
    )
    if layout != "white_main" and (custom_direction or camera or has_scene_direction):
        # Keep the editorial type treatment without injecting the layout's default
        # crop or subject scale over a directed shot.
        parts = [f"Layout family: {layout}."]
        if has_scene_direction:
            parts.append(f"Required scene direction: {direction['pose']}; camera {direction['angle']}; "
                         f"{direction['framing']}; {direction['composition']}.")
        if scene:
            parts.append(f"Setting: {scene.rstrip('.')}.")
        if concept and concept not in (camera, custom_direction):
            parts.append(f"Creative concept: {concept.rstrip('.')}.")
        if camera and camera != custom_direction:
            parts.append(f"Camera and composition: {camera.rstrip('.')}.")
        if image.get("text_on_image"):
            zone = image.get("text_zone")
            if zone not in _TYPE_ZONES:
                zone = "top-center"
            style = _LAYOUT_STYLES.get(image.get("layout_style"), _LAYOUT_STYLES["editorial"])
            parts.append(f"Integrate the typography in the {zone} area using the planned negative space. {style}")
        banner = _wide_banner_clause(image)
        if banner:
            parts.append(banner)
        return " ".join(parts)
    template = _LAYOUT_PROMPTS.get(layout, _LAYOUT_PROMPTS["poster_hero"])
    body = template.format(
        text_zone=str(image.get("text_zone") or "top-center"),
        scene=_clean_text(image.get("scene")) or "a realistic category-appropriate setting",
        presence_clause="" if _is_detail_crop(image) else _presence_clause(presence, scale),
        big_number_clause=(
            f", anchored by the oversized statistic \"{big_number}\" as a bold graphic element"
            if big_number else ""
        ),
    )
    extras = []
    concept = _clean_text(image.get("visual_concept"))
    if concept:
        extras.append(f"Creative concept: {concept}.")
    camera = _clean_text(image.get("camera_direction"))
    if camera:
        extras.append(f"Camera and composition: {camera}.")
    banner = _wide_banner_clause(image)
    if banner:
        extras.append(banner)
    return f"Layout family: {layout}. {body} " + " ".join(extras)

def _compile_presence_section(image: dict, product_profile: dict, product_lock: str) -> str:
    presence = str(image.get("product_presence") or "supporting")
    anchors = ", ".join(
        _clean_text(v) for v in (product_profile.get("fidelity_anchors") or []) if _clean_text(v)
    ) or "silhouette, proportions, colour, material, visible construction, markings"
    behaviour = _clean_text(product_profile.get("object_behavior")) or "category-specific physical behaviour"
    lock = _clean_text(product_lock).rstrip(". ")
    if presence == "absent":
        return (
            "The physical product does NOT appear in this image. Do not sneak the device, its packaging or its "
            "accessories into the frame. This image shows the outcome, comparison, scenario or information the "
            "buyer cares about — a standard practice on premium listings. Keep every visual physically plausible."
        )
    accessory_rule = (
        "Include every item that belongs to the purchased set, arranged deliberately."
        if str(image.get("shot_type")) == "in_box" else
        "Show ONLY the primary product itself. Do NOT carry packaging, memory cards, cables, manuals or any "
        "loose accessory items from the reference photo into this scene — the reference may be a bundle shot; "
        "everything except the main unit is reference noise here."
    )
    treatment = _clean_text(image.get("product_treatment"))
    treatment_rule = f"Product treatment: {treatment}. " if treatment else ""
    framing_rule = (
        "Use one continuous photograph of the specified visible detail. The product may extend past the frame. "
        "Do not add a full-product inset, split view, grid or collage. "
        if _is_detail_crop(image) else
        "Show the complete visible product with margin around the frame. "
        if image.get("shot_type") == "white_main" else
        "Preserve the visible product within the framing specified for this card. "
    )
    direction = image.get("scene_direction")
    if isinstance(direction, dict) and direction.get("framing") in ("medium shot", "close shot", "three-quarter-length shot"):
        framing_rule = "Use the planned scene framing and preserve the visible product exactly. "
    return (
        "REFERENCE IMAGE 1 is the only immutable product truth. "
        + (f"{lock}. " if lock else "")
        + f"Preserve exactly: {anchors.rstrip('. ')}. Physical behaviour: {behaviour}. {treatment_rule}{accessory_rule} "
        f"{framing_rule}Change only the environment, camera, composition, lighting and supporting design. "
        "If a creative direction conflicts with the reference, preserve the product. "
        "Reproduce the visible finish without inferring unverified material composition or hidden construction. "
        "Do not redesign, recolour, relabel, simplify or add parts. Existing logos, labels and printed markings on "
        "the product must remain unchanged."
    )

def _compile_copy_section(image: dict, plan_style: dict) -> str:
    if not image.get("text_on_image"):
        return (
            "This artwork intentionally contains no added marketing copy. Do not render headlines, captions, "
            "letters, numbers, badges, icons, diagrams, app UI or watermarks."
        )
    exact_copy = {
        key: value for key, value in (
            ("eyebrow", image.get("eyebrow")), ("headline", image.get("headline")),
            ("subline", image.get("subline")), ("callout", image.get("callout")),
            ("supporting_text", image.get("supporting_text")),
            ("big_number", image.get("big_number")), ("proof", image.get("proof")),
        ) if _clean_text(value)
    }
    chart = image.get("measurement_table")
    if chart:
        exact_copy.pop("supporting_text", None)
    contract = json.dumps(exact_copy, ensure_ascii=False)
    table_rule = (
        f" Verified measurement table: {json.dumps(chart, ensure_ascii=False)}. Render the columns and rows "
        "as one aligned table, with a single header row and unit label. Do not print JSON, pipe separators "
        "or an extra summary of the same headings or measurements."
    ) if chart else ""
    hierarchy=(
        'Hierarchy: the complete measurement table is the dominant information, with large readable cells and units. '
        'Keep the heading small and leave most of the canvas for the table. The actual garment photograph remains '
        'visible as context without squeezing the table into a narrow column. '
        if image.get('photo_led_typography') and image.get('size_chart') else
        'Hierarchy: the actual garment photograph and useful visible detail lead the composition. Keep the headline '
        'restrained and subordinate to the photograph, with one quiet factual subline. Use the planned calm negative '
        'space; do not enlarge type to fill it, obscure the garment feature, or turn numbers into a decorative poster. '
        if image.get('photo_led_typography') else
        "Hierarchy: follow the shared type system; a restrained heading, a quiet supporting line and readable "
        "table labels. Photography or the measurement table carries the visual emphasis. "
        if _is_wide_banner(image) else
        "Hierarchy: headline dominant, subline one quiet line beneath it, big_number oversized as a graphic anchor "
        "when present, other strings small. "
    )
    return (
        f"This is final pixel artwork. Render every string in this JSON exactly once and character-for-character: "
        f"{contract}. Do not translate, paraphrase, abbreviate, add, omit or repeat any character. "
        f"Type system: {plan_style.get('type_system')}. "+hierarchy+"Keep all type "
        "inside an 8% safe margin, high contrast, unobstructed, readable at mobile thumbnail size. The typography "
        "is part of the designed composition, never a pasted caption." + table_rule
    )

def _compile_render_prompt(image: dict, plan_style: dict, product_profile: dict,
                           plan: dict, deliverable: str) -> str:
    """从结构字段确定性编译最终生图提示词。

    先写商品真值，再写版式参考用途和自定义描述。旧的生成区块按当前字段重编译。
    """
    existing = str(image.get("render_prompt") or "")
    base = existing
    for name in ("SHOT DESIGN", "CANVAS", "PRODUCT IDENTITY LOCK", "PRODUCT PRESENCE", "REFERENCE ROLES", "SET COLOR SYSTEM",
                 "USER CREATIVE DIRECTION", "FINAL ARTWORK COPY", "OUTPUT SAFETY"):
        base = re.sub(rf"\s*\[{re.escape(name)}\].*?\[/{re.escape(name)}\]\s*", " ", base, flags=re.I | re.S)
    base = _ground_render_prompt(base)
    custom_direction = base
    if not base:
        size = str(image.get("size") or ("1464x600" if deliverable == "aplus" else "1600x1600"))
        base = (
            f"Create one finished, commercially polished Amazon {'A+ module' if deliverable == 'aplus' else 'listing image'} "
            f"on a {size} canvas. Photorealistic materials, believable light and physics, restrained premium design."
        )
    creative_brief = _clean_text(plan.get("creative_brief"))
    language = _clean_text(plan.get("language")) or "en"
    prompt = _replace_prompt_section(
        "", "PRODUCT PRESENCE",
        _compile_presence_section(image, product_profile, str(plan.get("product_lock") or "")),
    ).strip()
    if image.get("template_url"):
        prompt = _replace_prompt_section(
            prompt, "REFERENCE ROLES",
            "REFERENCE IMAGE 2 is a layout template only. Use its framing, subject scale, negative space and "
            "information hierarchy. Do not reproduce its product, brand, text, person, or exact pixels.",
        )
    if deliverable == "gallery" and image.get("shot_type") != "white_main":
        prompt = _replace_prompt_section(
            prompt, "CANVAS",
            "Compose for the actual output canvas. Fill all four edges with the photograph or the intended "
            "design surface. Keep the focal detail and typography inside the safe area. No blank outer strips, "
            "letterboxing, pillarboxing, or a smaller photograph pasted onto a plain surround. A wide scene "
            "describes the lens and subject distance, not a different canvas aspect ratio. For square delivery, "
            "keep headlines and required garment details clear of the outer 17% on all sides so they survive "
            "a square center crop if the service returns a taller or wider native image. Keep the chosen type zone "
            "within that safe area.",
        )
    prompt += "\n" + base
    prompt = _replace_prompt_section(prompt, "SHOT DESIGN", _compile_layout_section(image, custom_direction))
    prompt = _replace_prompt_section(
        prompt, "SET COLOR SYSTEM", _set_colour_prompt(plan_style, str(image.get("shot_type") or "")),
    )
    prompt = _replace_prompt_section(
        prompt, "USER CREATIVE DIRECTION",
        (
            "Set-wide planning context follows. It may describe other modules or an earlier storyboard draft. "
            "Use it only for audience, mood, exclusions and design character compatible with the current card. "
            "The current SHOT DESIGN and this card's creative direction control pose, camera, crop, subject scale, "
            "composition and text placement; do not replace them with directions from this context. "
            f"Planning context: {creative_brief}. "
            if creative_brief else
            "No additional manual creative requirement was supplied; follow the product-specific set direction. "
        ) + f"The requested language for added artwork copy is {language}.",
    )
    if image.get("text_on_image"):
        prompt = _remove_legacy_textless_directions(prompt)
    prompt = _replace_prompt_section(prompt, "FINAL ARTWORK COPY", _compile_copy_section(image, plan_style))
    prompt = _replace_prompt_section(
        prompt, "OUTPUT SAFETY",
        "Do not invent additional copy, claims, certifications, logos, labels, icons, badges, diagrams, app UI or "
        "watermarks. The exact public copy in FINAL ARTWORK COPY is the only added text allowed. Product labels "
        "already visible on the reference product are part of the product and must remain unchanged.",
    )
    return prompt


def planning_prompt(*, deliverable, count_rule, product_context, approved, product_profile_text, img_sp, template_text, narrative_text, deliverable_rules, body, color_directive):
    return f"""You are a senior ecommerce creative director planning a commercially usable Amazon {deliverable} set. {count_rule}

Study how flagship 3C brands (DJI / Anker level) build galleries: only 1-2 images show the product as the dominant
subject. The rest rotate the spotlight — outcome showcases, A/B comparisons, oversized spec numbers, real humans in
real scenes, use-case mosaics — under ONE consistent title band, type system and palette. Plan that calibre of set.

## PRODUCT INFO
{product_context}

## APPROVED LISTING COPY (the only source for exact on-image text and numbers)
{approved or "(none — derive concise phrases from the bullets/selling points above; never invent numbers)"}

## PRODUCT VISUAL IDENTITY
{product_profile_text}

## VISUAL ANALYSIS OF COLLECTED IMAGES
{img_sp or "(not available)"}
{template_text}

## RECOMMENDED NARRATIVE SKELETON (adapt to the facts; reorder/replace when justified)
{narrative_text}

## FIELD RULES
- product_presence: hero (product dominant, ≤2 per set incl. the white main) | supporting (25-40% of frame) |
  environmental (small in a real scene) | absent (product not in frame — outcome/comparison/spec panels).
  At least one image must be absent or environmental. {deliverable_rules}
- layout: white_main | poster_hero | result_showcase | split_compare | spec_grid | scenario_mosaic |
  human_context | in_box_flatlay | detail_macro | trust_close. Do not use the same layout more than twice.
- headline: a COMPLETE punchy phrase of 2-5 words (like "Stunning Low-Light Performance"). Never a truncated
  sentence fragment. subline: one supporting line ≤14 words. big_number: an exact spec anchor from the approved
  copy (e.g. "0.1s", "36MP", "IP66") or empty. proof: optional short public numeric fact.
- evidence: the exact product fact this image relies on. Do not plan images whose claims have no supporting fact.
- scene / visual_concept / camera_direction: ≤20 words each, concrete and different for every image.
- text_zone: top-left|top-center|top-right|center-left|center-right|bottom-left|bottom-center|bottom-right.
- layout_style: editorial|minimal|split|proof|grid. Choose a treatment that suits the shot and its actual artwork copy.
- Tone requested: {body.visual_tone}. Manual requirement (highest priority after facts): {body.brief or "none"}.
  Artwork language: {body.language}.
{color_directive}

## OUTPUT — return ONLY this JSON, no commentary. Keep every string SHORT; do not write long render prompts —
the rendering pipeline compiles final image prompts from these fields.
{{"style":{{"direction":"...","palette":"background #RRGGBB; surface #RRGGBB; supporting tone #RRGGBB; brand accent #RRGGBB; deep neutral #RRGGBB","lighting":"...","type_system":"...","accent_color":"#RRGGBB"}},
 "story":"one sentence sales narrative",
 "product_lock":"strict appearance description of the sellable product",
 "images":[
   {{"slot":"...","role":"...","shot_type":"...","product_presence":"hero|supporting|environmental|absent",
    "layout":"...","buyer_question":"...","selling_point":"...","evidence":"...",
    "headline":"...","subline":"...","big_number":"...","proof":"",
    "scene":"...","visual_concept":"...","camera_direction":"...","text_zone":"top-center","layout_style":"editorial"}}
 ]}}"""
