"""
npc_event_trigger.py — NPC 主动事件提示生成（B-13）

核心概念：
  create_npc_interaction_hint() = 根据 NPC 主动行为生成叙事提示文本。
  只是提示，不直接创建 EventPool 事件。

设计原则：
  - 只生成文本提示，不创建事件。
  - 不修改任何状态。
  - 由未来系统决定是否将提示转化为事件。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

# ──────────────────────────────────────────────
#  主动行为 → 叙事提示映射
# ──────────────────────────────────────────────

_ACTION_HINT_TEMPLATES = {
    "send_warning": [
        "某位旧识托人传来消息，提醒你注意{region}的异常情况。",
        "一位与你交好的修士让人带话：近期{region}不太安宁，务必小心。",
        "你收到一封匿名信笺，上面写着{region}近日有变，建议暂避。",
    ],
    "offer_information": [
        "一位知情者主动找到你，分享了关于{topic}的重要情报。",
        "有人暗中递给你一卷情报，内容涉及{topic}的最新动向。",
        "你偶然从一位旧识口中得知了{topic}的内情。",
    ],
    "avoid_player": [
        "你注意到某些人似乎在刻意回避你。",
        "曾经熟识的几个人见到你便匆匆离去，不愿多言。",
        "有些人对你的态度变得异常冷淡，甚至刻意绕道而行。",
    ],
    "help_player": [
        "一位友人主动伸出援手，为你提供了意想不到的帮助。",
        "有人暗中替你解决了一个麻烦，事后你才知晓。",
        "你得到了一位旧识的慷慨相助，令你颇为感动。",
    ],
    "ignore": [],
}

# ──────────────────────────────────────────────
#  事件提示生成
# ──────────────────────────────────────────────

def create_npc_interaction_hint(
    npc_action: str,
    npc_name: str = "",
    region: str = "附近区域",
    topic: str = "重要事务",
) -> Optional[str]:
    """根据 NPC 主动行为生成叙事提示文本。

    Args:
        npc_action: NPC 主动行为类型（send_warning / offer_information / avoid_player / help_player / ignore）
        npc_name: NPC 名称（可选，若提供则嵌入提示中）
        region: 相关区域
        topic: 相关话题

    Returns:
        叙事提示文本，或 None（如果行为类型不产生提示）
    """
    templates = _ACTION_HINT_TEMPLATES.get(npc_action, [])
    if not templates:
        return None

    # 使用第一个模板（确定性）
    template = templates[0]

    hint = template.format(region=region, topic=topic)

    # 如果提供了 NPC 名称，加入前缀
    if npc_name:
        hint = f"（{npc_name}）" + hint

    return hint
