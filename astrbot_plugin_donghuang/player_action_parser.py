"""
player_action_parser.py — 玩家行动解析（B-7.2）

把 /dh act 命令的文本参数解析为 PlayerAction。

采用规则解析，不依赖 AI。

支持的行动类型：
  investigate  调查
  assist       协助
  oppose       对抗
  cultivate    修炼
  negotiate    交涉

无法识别时返回 unknown，不修改状态。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

try:
    from .player_action import PlayerAction, ActionType, TargetType, make_action
except ImportError:
    from player_action import PlayerAction, ActionType, TargetType, make_action


# ──────────────────────────────────────────────
#  关键词映射
# ──────────────────────────────────────────────

# 中文关键词 → 行动类型
_KEYWORD_MAP: Dict[str, str] = {
    # 调查
    "调查": ActionType.INVESTIGATE,
    "探查": ActionType.INVESTIGATE,
    "侦查": ActionType.INVESTIGATE,
    "侦察": ActionType.INVESTIGATE,
    "搜索": ActionType.INVESTIGATE,
    "探索": ActionType.INVESTIGATE,
    "检查": ActionType.INVESTIGATE,
    # 协助
    "协助": ActionType.ASSIST,
    "帮助": ActionType.ASSIST,
    "支援": ActionType.ASSIST,
    "支援": ActionType.ASSIST,
    "配合": ActionType.ASSIST,
    "支持": ActionType.ASSIST,
    # 对抗
    "对抗": ActionType.OPPOSE,
    "反对": ActionType.OPPOSE,
    "阻止": ActionType.OPPOSE,
    "抵抗": ActionType.OPPOSE,
    "对抗": ActionType.OPPOSE,
    "阻挠": ActionType.OPPOSE,
    # 修炼
    "修炼": ActionType.CULTIVATE,
    "修行": ActionType.CULTIVATE,
    "修炼": ActionType.CULTIVATE,
    "打坐": ActionType.CULTIVATE,
    "冥想": ActionType.CULTIVATE,
    "练功": ActionType.CULTIVATE,
    # 交涉
    "交涉": ActionType.NEGOTIATE,
    "谈判": ActionType.NEGOTIATE,
    "游说": ActionType.NEGOTIATE,
    "说服": ActionType.NEGOTIATE,
    "协商": ActionType.NEGOTIATE,
    "交涉": ActionType.NEGOTIATE,
}

# 英文别名
_EN_ALIAS: Dict[str, str] = {
    "investigate": ActionType.INVESTIGATE,
    "assist": ActionType.ASSIST,
    "oppose": ActionType.OPPOSE,
    "cultivate": ActionType.CULTIVATE,
    "negotiate": ActionType.NEGOTIATE,
}

# 目标类型推断
_TARGET_TYPE_MAP: Dict[str, str] = {
    "势力": TargetType.FACTION,
    "宗门": TargetType.FACTION,
    "宗": TargetType.FACTION,
    "王朝": TargetType.FACTION,
    "组织": TargetType.FACTION,
    "府": TargetType.FACTION,
    "会": TargetType.FACTION,
    "盟": TargetType.FACTION,
    "事件": TargetType.EVENT,
    "区域": TargetType.REGION,
    "地方": TargetType.REGION,
    "遗迹": TargetType.RESOURCE,
    "灵脉": TargetType.RESOURCE,
    "资源": TargetType.RESOURCE,
    "NPC": TargetType.NPC,
    "人物": TargetType.NPC,
    "角色": TargetType.NPC,
}


class PlayerActionParser:
    """将 /dh act 命令参数解析为 PlayerAction。

    规则解析，不依赖 AI。
    """

    def parse(
        self,
        player_id: str,
        group_id: str,
        cycle: int,
        action_text: str,
        target_text: str = "",
    ) -> PlayerAction:
        """解析行动文本。

        Args:
            player_id: 玩家 slot_id
            group_id: 群号
            cycle: 当前 Cycle
            action_text: 行动关键词（如 "调查"、"assist"）
            target_text: 目标描述（如 "归墟宗"、"西部遗迹"）

        Returns:
            PlayerAction 对象
        """
        # 解析行动类型
        action_type = self._resolve_action_type(action_text)

        # 解析目标类型和 ID
        target_type, target_id = self._resolve_target(target_text)

        # 生成描述
        description = self._generate_description(action_type, target_id, target_text)

        return make_action(
            player_id=player_id,
            group_id=group_id,
            cycle=cycle,
            action_type=action_type,
            target_type=target_type,
            target_id=target_id or target_text,
            description=description,
        )

    def _resolve_action_type(self, text: str) -> str:
        """从文本中解析行动类型。"""
        text = text.strip()

        # 精确匹配英文别名
        lower = text.lower()
        if lower in _EN_ALIAS:
            return _EN_ALIAS[lower]

        # 中文关键词匹配
        for keyword, action_type in _KEYWORD_MAP.items():
            if keyword in text:
                return action_type

        return ActionType.UNKNOWN

    def _resolve_target(self, text: str) -> tuple:
        """从文本中推断目标类型和 ID。"""
        if not text:
            return ("", "")

        text = text.strip()

        # 检查关键词推断目标类型
        for keyword, target_type in _TARGET_TYPE_MAP.items():
            if keyword in text:
                return (target_type, text)

        # 默认：未知目标类型，ID 为文本本身
        return ("", text)

    def _generate_description(self, action_type: str, target_id: str, target_text: str) -> str:
        """生成人类可读的行动描述。"""
        action_names = {
            ActionType.INVESTIGATE: "调查",
            ActionType.ASSIST: "协助",
            ActionType.OPPOSE: "对抗",
            ActionType.CULTIVATE: "修炼",
            ActionType.NEGOTIATE: "交涉",
            ActionType.UNKNOWN: "行动",
        }
        action_name = action_names.get(action_type, "行动")
        target = target_id or target_text or "未知目标"
        # 根据行动类型调整措辞
        if action_type == ActionType.INVESTIGATE:
            return f"{action_name}了{target}，获得了有价值的情报。"
        elif action_type == ActionType.ASSIST:
            return f"{action_name}处理了{target}。"
        elif action_type == ActionType.OPPOSE:
            return f"与{target}发生了对抗。"
        elif action_type == ActionType.CULTIVATE:
            return f"进行了{action_name}，修为有所精进。"
        elif action_type == ActionType.NEGOTIATE:
            return f"与{target}进行了交涉。"
        else:
            return f"执行了一个未识别的{action_name}。"
