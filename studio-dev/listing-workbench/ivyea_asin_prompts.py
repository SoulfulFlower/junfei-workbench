"""Original IvyeaOps ASIN analysis prompts, AGPL-3.0-only. See SOURCE-NOTICE.md."""


def image_batch(lo, hi, total):
    return (
        f"这是某亚马逊产品的第 {lo}-{hi} 张图片（共 {total} 张）。请逐张分析并提取：\n"
        "① 体现的核心卖点 / 功能点；② 视觉风格 / 构图 / 配色；"
        "③ 使用场景 / 目标人群；④ 可直接复用到文案与图片提示词的要点。\n"
        "用简洁中文分点输出，每张图前标注其序号。"
    )


def image_summary(combined):
    return (
        "以下是对一组产品图片逐批的视觉分析。请汇总成一份『图片卖点清单』："
        "去重合并、按重要度排序，明确列出可用于 Listing 文案与图片提示词的"
        "卖点、视觉风格与使用场景。\n\n" + combined
    )


def product_analysis(skill_knowledge, product_context, image_insights):
    return f"""你是Amazon产品分析专家。基于以下专业知识和产品信息，进行深度分析。

## 专业知识参考
{skill_knowledge[:4000]}

## 产品信息
{product_context}

## 产品图片视觉分析（采集 + 上传的全部图片）
{image_insights or "（未配置视觉模型或暂无图片）"}


请输出结构化分析（JSON格式）：
{{
  "usp": ["核心卖点1", "核心卖点2", "核心卖点3"],
  "target_audience": "目标受众描述",
  "scenarios": ["使用场景1", "使用场景2", "使用场景3"],
  "keywords": ["关键词1", "关键词2", ...最多15个],
  "image_strategy": {{
    "main": "主图策略建议",
    "sub1": "副图1策略(USP概览)",
    "sub2": "副图2策略(对比图)",
    "sub3": "副图3策略(场景图)",
    "sub4": "副图4策略(技术/细节)",
    "sub5": "副图5策略(效果展示)",
    "sub6": "副图6策略(包装/配件)"
  }},
  "cosmo_score": "基于分析的COSMO评分估计(0-100)",
  "optimization_suggestions": ["建议1", "建议2", "建议3"]
}}

直接输出JSON，不要其他文字。"""


def text_task(prompt, *, web_search=True):
    task_prompt = (
        "你正在作为 Listing 生成板块的纯文本生成引擎。"
        "禁止执行命令、禁止读写文件、禁止修改系统、禁止调用工具；只根据提示词内容返回最终文本。\n\n"
        + prompt
    )
    if not web_search:
        task_prompt = "不要联网搜索，不要调用工具，只基于下面提供的信息回答。\n\n" + task_prompt
    task_prompt = (
        f"{task_prompt}\n\n"
        "输出要求：直接输出最终内容，不要解释调用过程，不要添加 Markdown 代码块。"
    )
    return task_prompt


SKILL_KNOWLEDGE = (
    '[LISTING CREATIVE STRATEGY]\n'
    '## When to use\n'
    '\n'
    'Load this skill whenever the task touches:\n'
    '\n'
    '- Designing or critiquing Amazon product images (main image, secondary images 2-7)\n'
    '- Writing or rewriting bullet points / title\n'
    '- Diagnosing why a listing has low CTR on search results or low CVR on the detail page\n'
    '- Producing image briefs for a designer, Midjourney, 即梦, or other AI tools\n'
    '\n'
    '## Hard compliance rules (do not violate)\n'
    '\n'
    'These are Amazon policy. Violations can cause suppression or take-down.\n'
    '\n'
    '### Main image (slot 1)\n'
    '\n'
    '- **Pure white background — exactly `#FFFFFF`**, no gradients, no tint, no off-white\n'
    '- **Product must fill ≥ 85%** of the frame\n'
    '- **NO text, NO logos, NO watermarks, NO promotional badges** on the image itself\n'
    '  - This includes "NEW", "BEST SELLER", "NO MONTHLY FEE", sale stickers, brand name overlays\n'
    '  - Amazon\'s own "Amazon\'s Choice" / "Prime" badges are injected by Amazon, not by you\n'
    '- **NO additional props, accessories, or models** that are not part of what the buyer receives\n'
    '- **NO borders, mascots, or decorative elements**\n'
    '- Real photograph preferred; pure AI-generated product renders risk "inaccurate representation" complaints\n'
    '- Allowed exception: very small, neutral "NEW" badge is tolerated in some categories but risky — default to no text\n'
    '\n'
    '**Common self-correction pitfall**: It is tempting to say "add a small \'NO MONTHLY FEE\' angle badge to the main image to beat competitors." **This is wrong.** All USP/promotional text goes on secondary images (slots 2-7). Double-check before suggesting any text on slot 1.\n'
    '\n'
    '### Secondary images (slots 2-7)\n'
    '\n'
    '- Free to include: scene/lifestyle photos, infographics, comparison charts, text overlays, size charts, feature callouts, before/after shots, packaging layouts\n'
    '- Still must be accurate — no fake night-vision samples, no staged features that the product does not actually have\n'
    '- Recommended resolution: 2000×2000 square, RGB, JPG or PNG\n'
    '\n'
    '### Product video (slot 8, optional)\n'
    '\n'
    '- ≤ 30 seconds is the sweet spot\n'
    '- Demonstrates actual product use, not just still images animated\n'
    '\n'
    '## The 7-slot CVR strategy\n'
    '\n'
    'Each image slot has a distinct job. Use this grid when briefing or critiquing:\n'
    '\n'
    '| Slot | Job | What goes in it |\n'
    '|------|-----|-----------------|\n'
    "| 1 Main | Win the CTR on search results | Pure white bg, 45° hero angle, max clarity on the product's differentiator (e.g., visible solar panel on top) |\n"
    '| 2 USP overview | Convince buyer to keep scrolling | Infographic with 4 core USPs as icon+headline+one-line benefit |\n'
    '| 3 Comparison | Kill competitive doubt | Us vs "typical product" side-by-side; red ❌ on generic, green ✓ on ours; do NOT name competitor brands |\n'
    '| 4 In-context / scene | Make it feel real | Product installed/used in the real environment (forest, kitchen, gym, etc.) |\n'
    '| 5 App / tech / integration | Answer the "will it actually work?" fear | Phone UI mockup, connectivity diagram, signal coverage, etc. |\n'
    '| 6 Effect sample | Show what the output looks like | Real sample output (photo/video/result). **Must be real**\n'
    '\n'
    '[ASIN AUDIT METHODOLOGY]\n'
    '# Amazon ASIN COSMO + Rufus Audit\n'
    '\n'
    '## Purpose\n'
    '\n'
    '把单个 Amazon ASIN 的问题拆成一份可执行的审计结果，而不是泛泛点评。\n'
    '\n'
    '本技能默认回答 4 个核心问题：\n'
    '1. 当前更像是哪里失分：曝光、点击、转化，还是预期错配\n'
    '2. 这些问题的证据是什么\n'
    '3. 优先应该先改什么，为什么\n'
    '4. 改完以后标题、Bullet、Q&A、Backend Search Terms、图片卖点、A+ 应该怎么写\n'
    '\n'
    '## Trigger Conditions\n'
    '\n'
    '用户出现下列表达时，优先触发本技能：\n'
    '- 分析这个 ASIN\n'
    '- 看下这个 listing 为什么卖不好\n'
    '- 做 COSMO 审计\n'
    '- 做 Rufus 审计\n'
    '- 帮我重写亚马逊标题 / 五点 / 描述\n'
    '- 帮我补 Q&A / Backend Search Terms / 图片卖点 / A+\n'
    '- 这个产品为什么 AI 搜索不容易搜到\n'
    '- 这个 listing 是曝光差还是转化差\n'
    '\n'
    '## When Not To Use\n'
    '\n'
    '不要硬套本技能到这些场景：\n'
    '- 用户只是在问 Amazon 平台规则、代码、命令、文档用法\n'
    '- 用户没有给 ASIN，也不是在讨论 ASIN 审计工作流\n'
    '- 用户要的是纯广告投放执行，不需要 Listing / 评论 / 页面证据分析\n'
    '- 用户只想润色一句文案，不需要完整诊断逻辑\n'
    '\n'
    '## Required Inputs\n'
    '\n'
    '默认输入：\n'
    '- 1 个 ASIN\n'
    '\n'
    '可选输入：\n'
    '- 站点（默认 `US`）\n'
    '- 用户已有证据：评论截图、旧标题、旧 Bullet、Q&A、竞品链接、竞品文案、广告表现摘要\n'
    '- 用户偏好：是否要完整 10 板块报告，是否要只给改写稿\n'
    '\n'
    '如果缺少 ASIN：\n'
    '- 直接追问，不猜\n'
    '\n'
    '## Prerequisites\n'
    '\n'
    '### Primary workflow\n'
    '本技能默认工作流是：\n'
    '- **Claude Code** 作为主执行环境\n'
    '- **sorftime** MCP 提供产品详情、评论、竞品关键词与竞品表达\n'
    '- **sif-mcp** 提供广告、流量、趋势、经营侧证据\n'
    '\n'
    '### What to verify first\n'
    '开始前先确认：\n'
    '1. `cla'
)
