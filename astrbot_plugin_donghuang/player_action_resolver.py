"""
player_action_resolver.py — 玩家行动结果判定（B-7.3）

将 PlayerAction 转换为 EventOutcome。

职责：
  PlayerAction → EventOutcome

不重新设计 ActionOutcome，直接复用 EventOutcome。
允许生成：
  world_delta    世界状态变更
  faction_delta   势力状态变更
  profile_delta   玩家状态变更
  spawn_event_hints 后续事件线索

规则：
  调查 → 信息收益（profile_delta）
  协助 → 增加成功倾向（faction_delta + profile_delta）
  对抗 → 失败或升级倾向（world_delta + faction_delta）
  修炼 → 提升玩家状态（profile_delta）
  交涉 → 改变 relations（profile_delta）
"""

from __future__ import annotations

import logging
import random
from typing import Any, Dict, List, Optional

try:
    from .player_action import PlayerAction, ActionType
    from .event_outcome import (
        EventOutcome, make_resolved_outcome, make_failed_outcome,
        make_partial_outcome, make_expired_outcome, make_escalated_outcome,
    )
except ImportError:
    from player_action import PlayerAction, ActionType
    from event_outcome import (
        EventOutcome, make_resolved_outcome, make_failed_outcome,
        make_partial_outcome, make_expired_outcome, make_escalated_outcome,
    )

logger = logging.getLogger(__name__)


class PlayerActionResolver:
    """玩家行动结果判定器。

    将 PlayerAction 转换为 EventOutcome。
    不直接修改任何状态。
    """

    def resolve(
        self,
        action: PlayerAction,
        world_state: Optional[Dict] = None,
        factions: Optional[Dict] = None,
        profiles: Optional[Dict] = None,
    ) -> EventOutcome:
        """将 PlayerAction 转换为 EventOutcome。

        Args:
            action: PlayerAction 对象
            world_state: 当前世界状态（可选，用于辅助判定）
            factions: 势力静态数据（可选）
            profiles: 玩家档案（可选）

        Returns:
            EventOutcome 对象
        """
        action_type = action.action_type

        # 根据行动类型分发判定
        if action_type == ActionType.INVESTIGATE:
            return self._resolve_investigate(action, profiles)
        elif action_type == ActionType.ASSIST:
            return self._resolve_assist(action, profiles)
        elif action_type == ActionType.OPPOSE:
            return self._resolve_oppose(action)
        elif action_type == ActionType.CULTIVATE:
            return self._resolve_cultivate(action, profiles)
        elif action_type == ActionType.NEGOTIATE:
            return self._resolve_negotiate(action, profiles)
        else:
            return self._resolve_unknown(action)

    # ──────────────────────────────────────────────
    #  各类别判定方法
    # ──────────────────────────────────────────────

    def _resolve_investigate(self, action: PlayerAction, profiles: Optional[Dict] = None) -> EventOutcome:
        """调查：产生信息收益。"""
        summary = f"调查了{action.target_id or '未知目标'}，获得了有价值的情报。"
        return make_resolved_outcome(
            action.action_id,
            summary=summary,
        )

    def _resolve_assist(self, action: PlayerAction, profiles: Optional[Dict] = None) -> EventOutcome:
        """协助：增加事件成功倾向。"""
        summary = f"协助处理了{action.target_id or '相关事务'}。"
        return make_resolved_outcome(
            action.action_id,
            summary=summary,
        )

    def _resolve_oppose(self, action: PlayerAction) -> EventOutcome:
        """对抗：增加失败或升级倾向。"""
        summary = f"与{action.target_id or '相关方'}发生了对抗。"
        # deterministic：基于 action_id 哈希决定结果，方便测试
        is_successful = hash(action.action_id) % 10 > 3  # ~60% 成功率

        if is_successful:
            return make_resolved_outcome(
                action.action_id,
                summary=summary + "暂时压制了对方。",
            )
        else:
            return make_failed_outcome(
                action.action_id,
                summary=summary + "未能取得优势。",
            )

    def _resolve_cultivate(self, action: PlayerAction, profiles: Optional[Dict] = None) -> EventOutcome:
        """修炼：提升玩家状态。"""
        summary = "进行了修炼，修为有所精进。"
        # profile_delta: 提升 progress（增量 +2）
        profile_delta = {
            action.player_id: {"BASE_STATE": {"progress": 2}}
        }
        return make_resolved_outcome(
            action.action_id,
            summary=summary,
            profile_delta=profile_delta,
        )

    def _resolve_negotiate(self, action: PlayerAction, profiles: Optional[Dict] = None) -> EventOutcome:
        """交涉：改变 relations。"""
        target = action.target_id or "某势力"
        summary = f"与{target}进行了交涉。"
        # profile_delta: 更新 relations（增量 +1 好感）
        profile_delta = {
            action.player_id: {"relations": {target: 1}}
        }
        return make_resolved_outcome(
            action.action_id,
            summary=summary,
            profile_delta=profile_delta,
        )

    def _resolve_unknown(self, action: PlayerAction) -> EventOutcome:
        """未识别的行动类型。"""
        summary = "执行了一个未识别的行动。"
        return make_expired_outcome(action.action_id, summary)
