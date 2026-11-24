"""Preflight checks for gallery direction, independent of paid rendering."""
import re
import unicodedata
from collections import defaultdict
from itertools import combinations

from ivyea_render_core import _layout_family


SCENE_FIELDS = {
    'pose': ('姿势', {
        'standing': '站立', 'walking': '迈步', 'seated': '坐姿',
        'reaching': '伸手取物', 'bending': '弯身', 'in use': '正在操作商品',
        'stationary object': '商品静置',
    }),
    'angle': ('镜头角度', {
        'front-on': '正面', 'three-quarter': '三分之四侧前方', 'profile': '正侧面',
        'from above': '俯拍', 'from below': '仰拍', 'overhead': '正上方俯视',
    }),
    'framing': ('景别', {
        'environmental wide shot': '环境远景', 'full-length shot': '全身',
        'three-quarter-length shot': '四分之三身', 'medium shot': '中景', 'close shot': '近景',
    }),
    'composition': ('构图', {
        'centered symmetry': '居中对称', 'subject on the left with space on the right': '主体左侧，右侧留白',
        'subject on the right with space on the left': '主体右侧，左侧留白',
        'diagonal leading lines': '对角线引导', 'layered foreground and background': '前后景层次',
    }),
}


def is_scene(image):
    return (image.get('shot_type') == 'lifestyle'
            or image.get('product_presence') == 'environmental'
            or _layout_family(image) in ('human_context', 'scenario_mosaic'))


def _normalized(text):
    return re.sub(r'[\W_]+', '', unicodedata.normalize('NFKC', str(text or '')).casefold())


def gallery_issues(images, *, shared_verified_angle=False, seven_policy=False):
    issues = []
    layouts = defaultdict(list)
    scenes = []
    seen = {}
    for number, image in enumerate(images, 1):
        layouts[_layout_family(image)].append(number)
        for key, label in (('visual_concept', '视觉概念'), ('camera_direction', '镜头描述')):
            value = _normalized(image.get(key))
            if not value:
                continue
            first = seen.setdefault((key, value), number)
            if first != number:
                issues.append(f'第 {first}、{number} 张的{label}重复。')
        if is_scene(image):
            scenes.append((number, image.get('scene_direction') or {}))

    for layout, numbers in layouts.items():
        if len(numbers) > (3 if seven_policy and layout=='human_context' else 2):
            positions = '、'.join(map(str, numbers))
            issues.append(f'第 {positions} 张使用同一类版式（{layout}），最多两张。')

    if len(scenes) > 1:
        for number, direction in scenes:
            missing = [label for key, (label, options) in SCENE_FIELDS.items()
                       if not isinstance(direction, dict) or direction.get(key) not in tuple(options)]
            if missing:
                issues.append(f'第 {number} 张场景图请补齐：{"、".join(missing)}。')
        for (first, left), (second, right) in combinations(scenes, 2):
            if not isinstance(left, dict) or not isinstance(right, dict):
                continue
            repeated = [label for key, (label, options) in SCENE_FIELDS.items()
                        if left.get(key) in tuple(options) and left[key] == right.get(key)]
            if shared_verified_angle:
                changed=[key for key in ('pose','framing','composition') if left.get(key)!=right.get(key)]
                if 'pose' not in changed or len(changed)<2:
                    issues.append(f'第 {first}、{second} 张场景图须改变姿势，并至少改变景别或构图；不要求虚构未核实的角度。')
            elif repeated:
                issues.append(f'第 {first}、{second} 张场景图的{"、".join(repeated)}重复，换背景不能通过。')
    return issues
