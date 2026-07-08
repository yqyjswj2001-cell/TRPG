"""
npc_action_scheduler.py — NPC 主动行为调度器（B-14）

核心概念：
  NPCActionScheduler = 决定什么时候检查 NPC 主动行为。
  不直接执行——只返回候选行为列表供调用方处理。

设计原则：
  - NPC 主动行为不能替代玩家行动。
  - 只产生消息/提醒/小事件提示。
  - 不直接修改 world_state / EventPool / EVENT_LOG。
  - 如果未来产生影响，必须通过 EventOutcome → OutcomeApplier。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from .npc_behavior import calculate_behavior, apply_identity_modifier, NPCBehaviorProfile
    from .npc_relationship import (
        calculate_relationship, REL_FRIENDLY, REL_RESPECTFUL,
        REL_SUSPICIOUS, REL_HOSTILE, REL_FAMILIAR, REL_UNKNOWN,
    )
    from .npc_action_generator import evaluate_npc_opportunity, plan_npc_action
    from .npc_event_trigger import create_npc_interaction_hint
except ImportError:
    from npc_behavior import calculate_behavior, apply_identity_modifier, NPCBehaviorProfile
    from npc_relationship import (
        calculate_relationship, REL_FRIENDLY, REL_RESPECTFUL,
        REL_SUSPICIOUS, REL_HOSTILE, REL_FAMILIAR, REL_UNKNOWN,
    )
    from npc_action_generator import evaluate_npc_opportunity, plan_npc_action
    from npc_event_trigger import create_npc_interaction_hint


# ──────────────────────────────────────────────
#  冷却配置
# ──────────────────────────────────────────────

NPC_ACTION_COOLDOWN_CYCLES = 10  # 同一 NPC 10 个 Cycle 内最多主动一次


# ──────────────────────────────────────────────
#  NPCActionScheduler
# ──────────────────────────────────────────────

class NPCActionScheduler:
    """NPC 主动行为调度器。

    职责：决定什么时候检查 NPC 主动行为。
    不直接执行——只返回候选行为列表。
    """

    def check_npc_actions(
        self,
        group_id: str,
        world_state: Dict[str, Any],
        player_profiles: Dict[str, Any],
        npc_registry: Any,
        npc_memory: Dict[str, Any],
        campaign: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """检查所有 NPC 的主动行为机会。

        Args:
            group_id: 群组 ID
            world_state: 世界状态
            player_profiles: 玩家档案
            npc_registry: NPCRegistry 实例
            npc_memory: campaign[group_id]["npc_memory"] 数据
            campaign: 团队状态（含 cycle, npc_action_cooldown, npc_action_log）

        Returns:
            候选行为列表：[{"npc_id", "action", "priority", "hint"}]
        """
        results = []
        cycle = campaign.get("cycle", 1)
        cooldown = campaign.get("npc_action_cooldown", {})
        action_log = campaign.get("npc_action_log", [])

        # 已消费的提示不再重复
        consumed_hints = {
            entry.get("hint", "") for entry in action_log
            if entry.get("consumed", False)
        }

        for npc_id, mem_list in npc_memory.items():
            if not isinstance(mem_list, list):
                continue

            # 检查冷却
            npc_cd = cooldown.get(npc_id, {})
            last_cycle = npc_cd.get("last_action_cycle", -999)
            if cycle - last_cycle < NPC_ACTION_COOLDOWN_CYCLES:
                continue

            # 查找 NPC 信息
            npc_dict = npc_registry.get_npc(npc_id) if npc_registry else None
            npc_info = {}
            npc_region = ""
            if npc_dict:
                npc_info = npc_dict
                npc_region = npc_dict.get("region", "")
            else:
                npc_info = {"name": npc_id}

            # 收集该 NPC 对所有玩家的记忆
            # 找到最相关的玩家（有记忆的）
            player_memories = {}
            for mem in mem_list:
                if isinstance(mem, dict):
                    pid = mem.get("player_id", "")
                    if pid:
                        player_memories.setdefault(pid, []).append(mem)

            if not player_memories:
                continue

            # 对每个有记忆的玩家检查
            for player_id, memories in player_memories.items():
                # 计算关系和行为
                relationship = calculate_relationship(memories)
                behavior = calculate_behavior(memories)
                if npc_dict:
                    behavior = apply_identity_modifier(behavior, npc_dict)

                # 检查触发条件
                action_plan = self._check_trigger(
                    relationship, behavior, npc_info, player_id,
                    player_profiles, npc_region, world_state, memories,
                )

                if action_plan is None:
                    continue
                action = action_plan["primary_action"]

                # 生成提示
                player_region = ""
                if player_id in player_profiles:
                    player_region = player_profiles[player_id].get("IDENTITY_STATE", {}).get("region", "")

                hint = create_npc_interaction_hint(
                    npc_action=action,
                    npc_name=npc_id,
                    region=player_region or npc_region or "附近区域",
                )

                if hint and hint not in consumed_hints:
                    # 确定优先级
                    priority = self._determine_priority(relationship, action)

                    results.append({
                        "npc_id": npc_id,
                        "action": action,
                        "priority": priority,
                        "hint": hint,
                        "player_id": player_id,
                        "goal": action_plan.get("goal", ""),
                        "reason_tags": list(action_plan.get("reason_tags", [])),
                        "relationship": action_plan.get("relationship", relationship),
                        "candidates": list(action_plan.get("candidates", [])),
                    })

        # 按优先级排序
        priority_order = {"high": 0, "medium": 1, "low": 2}
        results.sort(key=lambda r: priority_order.get(r["priority"], 3))

        return results

    def _check_trigger(
        self,
        relationship: str,
        behavior: NPCBehaviorProfile,
        npc_info: Dict[str, Any],
        player_id: str,
        player_profiles: Dict[str, Any],
        npc_region: str,
        world_state: Dict[str, Any],
        memories: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        """检查单个 NPC-玩家对的主动行为触发条件。

        规则：
          - friendly/respectful + help_probability >= 0.6 + 同区域 → send_warning / offer_information / help_player
          - suspicious/hostile + 玩家最近影响 NPC → avoid_player / send_warning
          - familiar/unknown → 不主动
        """
        if relationship in (REL_FRIENDLY, REL_RESPECTFUL):
            # 友善 NPC：帮助概率足够高时可能主动
            if behavior.help_probability >= 0.6:
                # 检查是否同区域
                player_region = ""
                if player_id in player_profiles:
                    player_region = player_profiles[player_id].get("IDENTITY_STATE", {}).get("region", "")

                # 同区域时才主动（或NPC区域为空时允许）
                if not npc_region or not player_region or npc_region == player_region:
                    action = evaluate_npc_opportunity(npc_info, world_state, player_profiles, memories)
                    if action is None:
                        return None
                    return plan_npc_action(
                        npc_info=npc_info,
                        memories=memories or [],
                        world_state=world_state,
                        current_region=npc_region,
                    )

            return None

        elif relationship in (REL_SUSPICIOUS, REL_HOSTILE):
            # 敌对 NPC：可能回避或警告
            action = evaluate_npc_opportunity(npc_info, world_state, player_profiles, memories)
            if action is None:
                return None
            return plan_npc_action(
                npc_info=npc_info,
                memories=memories or [],
                world_state=world_state,
                current_region=npc_region,
            )

        else:
            # familiar / unknown：不主动
            return None

    def _determine_priority(self, relationship: str, action: str) -> str:
        """确定主动行为的优先级。"""
        if relationship == REL_RESPECTFUL:
            return "high"
        elif relationship == REL_FRIENDLY:
            return "medium"
        elif relationship in (REL_SUSPICIOUS, REL_HOSTILE):
            return "medium"
        else:
            return "low"

    def apply_cooldown(self, campaign: Dict[str, Any], npc_id: str) -> None:
        """应用冷却：记录 NPC 最后主动行为的 Cycle。"""
        cooldown = campaign.setdefault("npc_action_cooldown", {})
        cooldown.setdefault(npc_id, {})["last_action_cycle"] = campaign.get("cycle", 1)

    def log_action(
        self,
        campaign: Dict[str, Any],
        npc_id: str,
        player_id: str,
        action: str,
        hint: str,
    ) -> None:
        """记录 NPC 主动行为到 npc_action_log。"""
        log = campaign.setdefault("npc_action_log", [])
        log.append({
            "type": "npc_action",
            "npc_id": npc_id,
            "player_id": player_id,
            "cycle": campaign.get("cycle", 1),
            "action": action,
            "hint": hint,
            "consumed": False,
        })

    def mark_consumed(self, campaign: Dict[str, Any], indices: List[int]) -> None:
        """标记指定的 npc_action_log 条目为已消费。"""
        log = campaign.get("npc_action_log", [])
        for idx in indices:
            if 0 <= idx < len(log):
                log[idx]["consumed"] = True
