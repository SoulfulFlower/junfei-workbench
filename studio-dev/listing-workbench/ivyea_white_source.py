"""IvyeaOps white-source classifier from listing/common.py, AGPL-3.0.
Source revision: 51f5141b475e64b67638f396451d887531caa761. See SOURCE-NOTICE.md.
"""
import io

def _white_metrics_ready(metrics: dict, *, allow_legacy_bundle: bool = False) -> bool:
    """Return whether measured pixels describe a usable white ecommerce source.

    A normal product photo leaves a mostly-white border.  Large bundles are a
    legitimate second shape: the items can touch one canvas edge and occupy most
    of the frame while the white background is still one continuous region that
    spans the other three sides.  Keeping these as separate acceptance paths
    avoids lowering the normal white-border threshold for bright lifestyle art.
    """
    border = float(metrics.get("border_white") or 0)
    overall = float(metrics.get("overall_white") or 0)
    connected = float(metrics.get("edge_connected_white") or 0)
    white_sides = int(metrics.get("white_sides") or 0)
    sides = [float(v) for v in (metrics.get("side_white") or []) if isinstance(v, (int, float))]
    classic_white_main = border >= .62 and overall >= .30
    connected_bundle = overall >= .34 and connected >= .30 and white_sides >= 3
    # Tightly cropped white mains are a third legitimate shape: the product
    # fills nearly the whole canvas, so total white is small (可低至 ~17%)
    # and even the border band is mostly product. Their unmistakable signature
    # is that every canvas edge LINE is almost entirely strict-white and that
    # white forms one edge-connected sweep (lifestyle photos never light all
    # four edges pure #F8+ white). Validated against 138 real workspace images
    # with zero false accepts.
    tight_white_main = (
        len(sides) == 4 and min(sides) >= .80
        and connected >= .12 and overall > 0 and connected >= overall * .8
    )
    # Reports written before edge-connectivity was introduced cannot be
    # re-scored without downloading the image again.  Only the first scraped
    # gallery image may use this narrow migration path; callers control that
    # condition with allow_legacy_bundle.
    legacy_bundle = (
        allow_legacy_bundle and "edge_connected_white" not in metrics
        and border >= .30 and overall >= .35
    )
    return classic_white_main or connected_bundle or tight_white_main or legacy_bundle


def _white_background_score(raw: bytes) -> dict:
    """Identify a white-background ecommerce source, including dense bundles."""
    from PIL import Image
    try:
        image = Image.open(io.BytesIO(raw)).convert("RGB")
        image.thumbnail((240, 240))
    except Exception:
        return {"ready": False, "score": 0, "border_white": 0, "overall_white": 0}
    width, height = image.size
    if width < 20 or height < 20:
        return {"ready": False, "score": 0, "border_white": 0, "overall_white": 0}
    pixels = image.load()
    margin_x, margin_y = max(2, width // 12), max(2, height // 12)

    def is_white(pixel) -> bool:
        return min(pixel) >= 238 and max(pixel) - min(pixel) <= 16

    total = white = border_total = border_white = 0
    white_mask = bytearray(width * height)
    for y in range(height):
        for x in range(width):
            value = pixels[x, y]
            pixel_white = is_white(value)
            white_mask[y * width + x] = int(pixel_white)
            total += 1
            white += int(pixel_white)
            if x < margin_x or x >= width - margin_x or y < margin_y or y >= height - margin_y:
                border_total += 1
                border_white += int(pixel_white)
    overall_ratio = white / max(1, total)
    border_ratio = border_white / max(1, border_total)

    # Count the strict-white region connected to the outside of the canvas.
    # This distinguishes a genuine white sweep surrounding a dense bundle from
    # disconnected pale labels, screens, clouds or highlights inside a scene.
    seen = bytearray(total)
    stack: list[int] = []

    def seed(index: int) -> None:
        if white_mask[index] and not seen[index]:
            seen[index] = 1
            stack.append(index)

    for x in range(width):
        seed(x)
        seed((height - 1) * width + x)
    for y in range(height):
        seed(y * width)
        seed(y * width + width - 1)
    connected_white = 0
    while stack:
        index = stack.pop()
        connected_white += 1
        x = index % width
        for neighbor in (
            index - width if index >= width else -1,
            index + width if index < total - width else -1,
            index - 1 if x else -1,
            index + 1 if x < width - 1 else -1,
        ):
            if neighbor >= 0 and white_mask[neighbor] and not seen[neighbor]:
                seen[neighbor] = 1
                stack.append(neighbor)
    connected_ratio = connected_white / max(1, total)
    side_ratios = (
        sum(white_mask[x] for x in range(width)) / width,
        sum(white_mask[(height - 1) * width + x] for x in range(width)) / width,
        sum(white_mask[y * width] for y in range(height)) / height,
        sum(white_mask[y * width + width - 1] for y in range(height)) / height,
    )
    white_sides = sum(ratio >= .55 for ratio in side_ratios)
    legacy_score = (border_ratio * .68 + overall_ratio * .32) * 100
    connected_score = (connected_ratio * .55 + (white_sides / 4) * .45) * 100
    metrics = {
        "score": round(max(legacy_score, connected_score)),
        "border_white": round(border_ratio, 3),
        "overall_white": round(overall_ratio, 3),
        "edge_connected_white": round(connected_ratio, 3),
        "white_sides": white_sides,
        "side_white": [round(ratio, 3) for ratio in side_ratios],
    }
    return {
        "ready": _white_metrics_ready(metrics),
        **metrics,
    }
