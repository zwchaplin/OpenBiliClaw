"""LLM-based xiaohongshu-style keyword generator.

Rewrites SoulProfile interest tags into xhs-flavored search queries —
concrete, lifestyle-oriented, long-tail — so the extension's background
dispatcher can search xhs in a way that matches how real users browse.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from openbiliclaw.llm.json_utils import parse_llm_json_tolerant

if TYPE_CHECKING:
    from openbiliclaw.llm.service import LLMService
    from openbiliclaw.soul.profile import OnionProfile, SoulProfile

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = """你是小红书内容策略师。给你一个用户的兴趣画像（B 站等平台归纳的），\
请把它改写成 N 个"小红书风格"的搜索关键词。

小红书风格的关键词特征：
- 生活化、具象、带场景（而不是宽泛的学科/品类词）
- 偏长尾、偏体验分享（"教程/攻略/vlog/踩坑/真实体验"等尾词常见）
- 口语化，2~8 个字为主，必要时可稍长
- 避免只给单字类目词（"科技"、"游戏"），要加限定
- 避免和 bilibili 完全相同的写法

只返回 JSON，不要任何解释文字。格式：
{"keywords": ["...", "..."]}"""


def _build_user_prompt(interest_tags: list[tuple[str, str, float]], count: int) -> str:
    lines = ["用户兴趣画像（name | category | weight）："]
    for name, category, weight in interest_tags[:15]:
        cat = category or "-"
        lines.append(f"- {name} | {cat} | {weight:.2f}")
    lines.append(f"\n请输出 {count} 个小红书风格关键词。")
    return "\n".join(lines)


async def generate_xhs_keywords(
    llm_service: LLMService,
    profile: SoulProfile | OnionProfile,
    *,
    count: int = 5,
) -> list[str]:
    """Generate up to ``count`` xhs-style search keywords from *profile*.

    Returns an empty list when the profile has no usable interests or the
    LLM call fails — the caller should treat empty as "nothing to enqueue
    this cycle" and try again next interval.
    """
    interests = list(profile.preferences.interests)
    if not interests:
        return []

    interests.sort(key=lambda t: t.weight, reverse=True)
    interest_tuples = [(t.name, t.category, t.weight) for t in interests if t.name]
    if not interest_tuples:
        return []

    try:
        response = await llm_service.complete_structured_task(
            system_instruction=_SYSTEM_PROMPT,
            user_input=_build_user_prompt(interest_tuples, count),
            temperature=0.8,
            max_tokens=512,
        )
    except Exception as exc:
        logger.warning("xhs keyword LLM call failed: %s", exc)
        return []

    content = response.content.strip()
    payload = parse_llm_json_tolerant(content)
    if payload is None:
        try:
            payload = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            logger.warning("xhs keyword LLM returned non-JSON: %r", content[:200])
            return []

    if not isinstance(payload, dict):
        return []

    raw_keywords = payload.get("keywords", [])
    if not isinstance(raw_keywords, list):
        return []

    seen: set[str] = set()
    keywords: list[str] = []
    for item in raw_keywords:
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        keywords.append(text)
        if len(keywords) >= count:
            break
    return keywords
