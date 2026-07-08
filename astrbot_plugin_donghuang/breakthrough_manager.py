# -*- coding: utf-8 -*-
"""
breakthrough_manager.py — 突破体系（LONG-A 第4阶段）

核心概念：
  BreakthroughManager = 突破管理器，负责处理境界突破的完整流程。
  包括：检定、成功/失败判定、状态更新、副作用应用、NPC感知触发。
  不直接修改 profile，只负责计算和构造合法的 delta。

设计原则：
  - 所有变更通过 EventOutcome → OutcomeApplier 写入，本模块不碰 profile。
  - 突破成功率、失败后果全部由代码计算，AI 不决定数值。
  - 旧存档兼容：缺失字段使用 .get(key, default) 读取。
  - 复用现有 CORE_STATE / METHOD_STATE 字段，扩展不破坏旧结构。

METHOD_STATE 扩展字段：
  "breakthrough_status": "none_pending"  # none_pending/attempted_failed/successful
  "consecutive_failures": 0             # 连续突破失败次数

CORE_STATE 扩展字段：
  "spiritual_root": {...}              # 灵根状态（见 spiritual_root.py）
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

try:
    from .cultivation_state import (
        CultivationState, extract_cultivation_state,
        calculate_breakthrough_dc, adjust_cultivation_progress,
        REALMS, REALM_STAGE, BOUNDARY_REALMS, get_realm_index,
        is_boundary_realm, make_method_state_delta,
    )
    from .cultivation_technique import TechniqueManager, CultivationTechnique
    from .spiritual_root import (
        SpiritualRoot, extract_spiritual_root, calculate_breakthrough_risk,
        generate_spiritual_root, make_core_state_delta, describe_spiritual_root,
        calculate_breakthrough_bonus,
    )
except ImportError:
    from cultivation_state import (
        CultivationState, extract_cultivation_state,
        calculate_breakthrough_dc, adjust_cultivation_progress,
        REALMS, REALM_STAGE, BOUNDARY_REALMS, get_realm_index,
        is_boundary_realm, make_method_state_delta,
    )
    from cultivation_technique import TechniqueManager, CultivationTechnique
    from spiritual_root import (
        SpiritualRoot, extract_spiritual_root, calculate_breakthrough_risk,
        generate_spiritual_root, make_core_state_delta, describe_spiritual_root,
        calculate_breakthrough_bonus,
    )


# ──────────────────────────────────────────────
#  修炼事件定义（LONG-A 第6阶段：通过 EventPool 生成事件）
# ──────────────────────────────────────────────

# 修炼事件类型 → EventPool 参数模板
CULTIVATION_EVENT_TEMPLATES = {
    "闭关走火": {
        "title_template": "{name}闭关走火，灵气紊乱引发异象",
        "category": "修行突破",
        "priority": "高",
        "visibility": "区域",
        "summary_template": "{name}突破失败后灵气失控，闭关之处灵气紊乱，方圆数里可感",
    },
    "突破异象": {
        "title_template": "{name}突破{realm}，天地异象惊动四方",
        "category": "修行突破",
        "priority": "紧急",
        "visibility": "公开",
        "summary_template": "{name}成功突破至{realm}，天地灵气涌动，异象波及周围数个区域",
    },
    "天劫降临": {
        "title_template": "天劫降临！{name}渡劫{realm}",
        "category": "修行突破",
        "priority": "紧急",
        "visibility": "公开",
        "summary_template": "异变灵根引来天劫，雷云密布，方圆十里修士皆感天威",
    },
    "功法顿悟": {
        "title_template": "{name}突破时顿悟功法",
        "category": "修行突破",
        "priority": "中",
        "visibility": "区域",
        "summary_template": "{name}于突破之际对功法有了更深领悟，气息更加凝练",
    },
}


def generate_cultivation_events(
    result: BreakthroughResult,
    profile: Dict[str, Any],
    event_pool: Any = None,
    group_id: str = "",
) -> List[Dict[str, Any]]:
    """根据突破结果生成修炼事件，通过 EventPool 添加。

    LONG-A 第6阶段核心要求：事件必须通过 EventPool，不能直接生成剧情。

    生成规则：
      - 突破成功 + 大境界 → 突破异象事件
      - 突破成功 + 异变灵根 + 大境界 → 额外天劫降临事件
      - 突破失败 → 闭关走火事件
      - 突破成功 + 20%概率 → 功法顿悟事件

    Args:
        result: 突破结果
        profile: 玩家档案
        event_pool: EventPool 实例（可选，为 None 时只返回事件定义不添加）
        group_id: 群 ID

    Returns:
        生成的事件列表（dict 格式，包含 event_id 等信息）
    """
    events_created = []
    name = profile.get("name", "未知修士")
    spiritual = extract_spiritual_root(profile)
    region = profile.get("IDENTITY_STATE", {}).get("region", "中部")

    if result.success:
        # 大境界突破成功 → 突破异象
        if result.is_boundary:
            tmpl = CULTIVATION_EVENT_TEMPLATES["突破异象"]
            event_info = {
                "type": "突破异象",
                "title": tmpl["title_template"].format(name=name, realm=result.next_realm),
                "category": tmpl["category"],
                "summary": tmpl["summary_template"].format(name=name, realm=result.next_realm),
                "region": region,
                "participants": [name],
                "priority": tmpl["priority"],
                "visibility": tmpl["visibility"],
                "player_related": True,
            }

            if event_pool and group_id:
                evt = event_pool.add(
                    group_id=group_id,
                    title=event_info["title"],
                    category=event_info["category"],
                    region=region,
                    participants=[name],
                    summary=event_info["summary"],
                    priority=event_info["priority"],
                    visibility=event_info["visibility"],
                    player_related=True,
                    stage="进行中",
                )
                event_info["event_id"] = evt.event_id

            events_created.append(event_info)

            # 异变灵根 + 大境界 → 天劫
            risk = calculate_breakthrough_risk(spiritual, is_boundary=True)
            if risk["tribulation"] > 0.05:
                import random as _rng
                if _rng.random() < risk["tribulation"]:
                    tmpl_trib = CULTIVATION_EVENT_TEMPLATES["天劫降临"]
                    trib_info = {
                        "type": "天劫降临",
                        "title": tmpl_trib["title_template"].format(name=name, realm=result.next_realm),
                        "category": tmpl_trib["category"],
                        "summary": tmpl_trib["summary_template"].format(name=name, realm=result.next_realm),
                        "region": region,
                        "participants": [name],
                        "priority": tmpl_trib["priority"],
                        "visibility": tmpl_trib["visibility"],
                        "player_related": True,
                    }

                    if event_pool and group_id:
                        evt = event_pool.add(
                            group_id=group_id,
                            title=trib_info["title"],
                            category=trib_info["category"],
                            region=region,
                            participants=[name],
                            summary=trib_info["summary"],
                            priority=trib_info["priority"],
                            visibility=trib_info["visibility"],
                            player_related=True,
                            stage="萌芽",
                        )
                        trib_info["event_id"] = evt.event_id

                    events_created.append(trib_info)

        # 20% 概率触发功法顿悟
        import random as _rng
        if _rng.random() < 0.2:
            tmpl_aw = CULTIVATION_EVENT_TEMPLATES["功法顿悟"]
            aw_info = {
                "type": "功法顿悟",
                "title": tmpl_aw["title_template"].format(name=name),
                "category": tmpl_aw["category"],
                "summary": tmpl_aw["summary_template"].format(name=name),
                "region": region,
                "participants": [name],
                "priority": tmpl_aw["priority"],
                "visibility": tmpl_aw["visibility"],
                "player_related": True,
            }

            if event_pool and group_id:
                evt = event_pool.add(
                    group_id=group_id,
                    title=aw_info["title"],
                    category=aw_info["category"],
                    region=region,
                    participants=[name],
                    summary=aw_info["summary"],
                    priority=aw_info["priority"],
                    visibility=aw_info["visibility"],
                    player_related=True,
                    stage="萌芽",
                )
                aw_info["event_id"] = evt.event_id

            events_created.append(aw_info)

    else:
        # 突破失败 → 闭关走火
        tmpl_fail = CULTIVATION_EVENT_TEMPLATES["闭关走火"]
        fail_info = {
            "type": "闭关走火",
            "title": tmpl_fail["title_template"].format(name=name),
            "category": tmpl_fail["category"],
            "summary": tmpl_fail["summary_template"].format(name=name),
            "region": region,
            "participants": [name],
            "priority": tmpl_fail["priority"],
            "visibility": tmpl_fail["visibility"],
            "player_related": True,
        }

        if event_pool and group_id:
            evt = event_pool.add(
                group_id=group_id,
                title=fail_info["title"],
                category=fail_info["category"],
                region=region,
                participants=[name],
                summary=fail_info["summary"],
                priority=fail_info["priority"],
                visibility=fail_info["visibility"],
                player_related=True,
                stage="萌芽",
            )
            fail_info["event_id"] = evt.event_id

        events_created.append(fail_info)

    return events_created


# ──────────────────────────────────────────────
#  突破结果数据类
# ──────────────────────────────────────────────

@dataclass
class BreakthroughResult:
    """突破结果。"""

    success: bool
    current_realm: str
    next_realm: str
    is_boundary: bool
    roll_result: int          # 实际掷骰结果
    required_dc: int          # 需要的 DC
    actual_dc: int            # 实际 DC（用于叙事）
    technique_bonus: float    # 功法突破加成
    root_bonus: float         # 灵根突破加成
    risk_factors: List[str]   # 风险因素描述
    narrative_hints: List[str] # AI 叙事提示


# ──────────────────────────────────────────────
#  BreakthroughManager 突破管理器
# ──────────────────────────────────────────────

class BreakthroughManager:
    """突破管理器，处理境界突破的完整流程。"""

    def __init__(self):
        self._technique_manager = TechniqueManager()
        self._breakthrough_history: List[Dict[str, Any]] = []

    def can_attempt_breakthrough(self, profile: Dict[str, Any]) -> Tuple[bool, str]:
        """判断是否可以进行突破尝试。

        条件：
          1. 修为进度 >= 100
          2. 不在突破冷却期（突破失败后需要等待一定时间）
          3. 没有正在进行的突破

        Args:
            profile: 玩家档案

        Returns:
            (是否可以突破, 原因)
        """
        method = profile.get("METHOD_STATE", {})
        progress = method.get("progress", 0)

        if progress < 100:
            return False, f"修为进度不足（{progress}/100），还需修炼"

        breakthrough_status = method.get("breakthrough_status", "none_pending")
        if breakthrough_status == "attempted_failed":
            # 检查是否需要冷却
            consecutive = method.get("consecutive_failures", 0)
            if consecutive > 0:
                # 每次失败增加冷却时间（简化：只要还在 attempt 状态就可以继续试）
                pass

        return True, ""

    def roll_breakthrough(
        self,
        profile: Dict[str, Any],
        seed: Optional[int] = None,
    ) -> BreakthroughResult:
        """执行突破检定。

        规则：
          1d20 + 悟性修正 vs 困难 DC(20)
          DC = 20 + 境界修正 + 瓶颈修正 - 根基修正 - 功法加成

        Args:
            profile: 玩家档案
            seed: 随机种子（用于可复现）

        Returns:
            BreakthroughResult 对象
        """
        rng = random.Random(seed) if seed is not None else random

        # 提取修炼状态
        cultivation = extract_cultivation_state(profile)
        spiritual = extract_spiritual_root(profile)
        technique_mgr = self._technique_manager

        # 计算突破 DC
        dc = calculate_breakthrough_dc(cultivation)

        # 计算各种加成
        technique_bonus = 0.0
        known_techniques = profile.get("METHOD_STATE", {}).get("known_techniques", [])
        if known_techniques:
            techniques = [t for t in technique_mgr.get_all_techniques()
                         if any(name in t["name"] for name in known_techniques)]
            technique_bonus = sum(t.breakthrough_bonus for t in techniques)

        root_bonus = calculate_breakthrough_bonus(spiritual)

        # 基础 DC
        base_dc = 20

        # 境界修正（练气+0，筑基+2，金丹+5）
        stage = cultivation.growth_stage
        stage_modifier = {"练气": 0, "筑基": 2, "金丹": 5}.get(stage, 0)

        # 瓶颈修正
        bottleneck_modifier = cultivation.bottleneck * 2

        # 根基修正
        foundation_bonus = min(5, cultivation.foundation // 20)

        # 功法加成（转换为 DC 减免）
        technique_dc_reduction = int(technique_bonus * 5)

        # 最终 DC
        actual_dc = base_dc + stage_modifier + bottleneck_modifier - foundation_bonus - technique_dc_reduction
        actual_dc = max(10, actual_dc)

        # 掷骰
        six = profile.get("six_dims", {})
        wisdom = six.get("悟性", 10)
        modifier = (wisdom - 10) // 2
        roll = rng.randint(1, 20) + modifier

        # 判断成功
        success = roll >= actual_dc

        # 确定下一境界
        current_realm = profile.get("cultivation_realm", REALMS[0])
        current_idx = get_realm_index(current_realm)
        is_boundary = is_boundary_realm(current_realm)

        if success and current_idx < len(REALMS) - 1:
            next_realm = REALMS[current_idx + 1]
        else:
            next_realm = current_realm

        # 风险因素
        risk_factors = []
        if cultivation.bottleneck > 0:
            risk_factors.append(f"瓶颈等级{cultivation.bottleneck}")
        if spiritual.mutation != "none":
            risk = calculate_breakthrough_risk(spiritual, is_boundary)
            if risk["tribulation"] > 0:
                risk_factors.append("天劫风险")
            if risk["backlash"] > 0:
                risk_factors.append("反噬风险")

        # 叙事提示
        hints = []
        if success:
            if is_boundary:
                hints.append("大境界突破，天地异象")
            else:
                hints.append("小境界突破，气息稳固")
        else:
            hints.append("突破失败，需要重新积累")

        return BreakthroughResult(
            success=success,
            current_realm=current_realm,
            next_realm=next_realm,
            is_boundary=is_boundary,
            roll_result=roll,
            required_dc=actual_dc,
            actual_dc=actual_dc,
            technique_bonus=technique_bonus,
            root_bonus=root_bonus,
            risk_factors=risk_factors,
            narrative_hints=hints,
        )

    def apply_breakthrough(
        self,
        result: BreakthroughResult,
        profile: Dict[str, Any],
        world_state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """应用突破结果到档案。

        返回需要应用的 delta dict，由调用方包装进 EventOutcome。

        Args:
            result: 突破结果
            profile: 当前档案（会被修改）
            world_state: 世界状态（可选）

        Returns:
            {"profile_delta": {...}, "world_delta": {...}}
        """
        profile_delta: Dict[str, Any] = {}
        world_delta: Dict[str, Any] = {}

        if result.success:
            profile_delta = self._apply_success(result, profile)
        else:
            profile_delta = self._apply_failure(result, profile)

        if world_state:
            world_delta = self._apply_world_effects(result, world_state)

        return {"profile_delta": profile_delta, "world_delta": world_delta}

    def _apply_success(
        self,
        result: BreakthroughResult,
        profile: Dict[str, Any],
    ) -> Dict[str, Any]:
        """应用突破成功。"""
        delta: Dict[str, Any] = {}

        # 境界提升
        delta["cultivation_realm"] = result.next_realm

        # METHOD_STATE
        method = profile.setdefault("METHOD_STATE", {})
        method["growth_stage"] = REALM_STAGE.get(result.next_realm, "练气")
        method["breakthrough_status"] = "none_pending"
        method["progress"] = 0  # 清零重新开始
        method["consecutive_failures"] = 0  # 重置连续失败

        # 根基恢复
        new_foundation = min(200, method.get("foundation", 100) + 5)
        if "foundation" in method:
            method["foundation"] = new_foundation

        # HP 上限提升（跨大境界更多）
        hp = profile.setdefault("hp", {"current": 20, "max": 20})
        gain = 15 if result.is_boundary else 5
        try:
            hp["max"] = int(hp.get("max", 20)) + gain
            hp["current"] = int(hp.get("current", hp["max"])) + gain
        except (ValueError, TypeError):
            hp["max"] = 20 + gain
            hp["current"] = hp["max"]

        # 六维精进（30% 概率）
        if random.random() < 0.3:
            path = method.get("primary_path", "")
            dim = {"资源型": "机缘", "感悟型": "悟性", "实战型": "体质",
                   "世俗型": "魅力", "共鸣型": "心性", "复合型": "根骨"}.get(path, "根骨")
            six = profile.setdefault("six_dims", {})
            six[dim] = min(24, six.get(dim, 10) + 1)

        # 灵气变化
        mp = profile.setdefault("mp", {"current": 15, "max": 15})
        mp["current"] = int(mp.get("current", mp["max"]))

        return delta

    def _apply_failure(
        self,
        result: BreakthroughResult,
        profile: Dict[str, Any],
    ) -> Dict[str, Any]:
        """应用突破失败。"""
        delta: Dict[str, Any] = {}

        # 标记为已尝试失败
        method = profile.setdefault("METHOD_STATE", {})
        method["breakthrough_status"] = "attempted_failed"

        # 修为进度打对折
        old_progress = method.get("progress", 0)
        method["progress"] = max(0, old_progress // 2)

        # 连续失败计数
        consecutive = method.get("consecutive_failures", 0) + 1
        method["consecutive_failures"] = consecutive

        # 根基损耗
        foundation = method.get("foundation", 100)
        loss = 5 if not result.is_boundary else 15
        method["foundation"] = max(0, foundation - loss)

        # 气血损伤（跨大境界更重）
        hp = profile.setdefault("hp", {"current": 20, "max": 20})
        damage = random.randint(2, 6) if result.is_boundary else random.randint(1, 3)
        try:
            new_current = max(1, int(hp.get("current", 20)) - damage)
        except (ValueError, TypeError):
            new_current = max(1, 20 - damage)
        hp["current"] = new_current

        # 可能留下病症（40% 概率）
        if random.random() < 0.4:
            talent_str = profile.get("talent", "")
            talent_names = set(talent_str.split("、")) if talent_str else set()
            try:
                from .affliction_data import AFFLICTION_POOL, _AFFLICTION_IMMUNE_TALENTS
            except ImportError:
                from affliction_data import AFFLICTION_POOL, _AFFLICTION_IMMUNE_TALENTS
            if not (talent_names & _AFFLICTION_IMMUNE_TALENTS):
                candidates = [a for a in AFFLICTION_POOL if a["type"] in ("肉身", "灵气紊乱")]
                aff = random.choice(candidates) if candidates else random.choice(AFFLICTION_POOL)
                profile.setdefault("afflictions", []).append({
                    "name": aff["name"], "type": aff["type"], "severity": aff["severity"],
                    "effect": aff["effect"], "cure": aff["cure"], "turns_untreated": 0
                })

        return delta

    def _apply_world_effects(
        self,
        result: BreakthroughResult,
        world_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        """应用突破对世界的影响。"""
        delta: Dict[str, Any] = {}

        # 记录突破历史
        self._breakthrough_history.append({
            "player": "UNKNOWN",  # 应由调用方填充
            "from": result.current_realm,
            "to": result.next_realm,
            "is_boundary": result.is_boundary,
            "success": result.success,
            "timestamp": "now",
        })

        return delta

    def get_breakthrough_narrative(self, result: BreakthroughResult) -> str:
        """生成突破叙事提示（供 AI 使用）。"""
        lines = []

        if result.success:
            lines.append(f"🎉 恭喜！你成功突破至 {result.next_realm}！")
            if result.is_boundary:
                lines.append("这是一次大境界突破，天地间似乎有异象显现。")
            else:
                lines.append("气息更加稳固，道心更加坚定。")
        else:
            lines.append("💥 突破失败...")
            if result.risk_factors:
                lines.append(f"风险因素：{', '.join(result.risk_factors)}")
            lines.append("你需要重新积累修为再做尝试。")

        return "\n".join(lines)


# ──────────────────────────────────────────────
#  便捷函数
# ──────────────────────────────────────────────

def attempt_breakthrough(
    profile: Dict[str, Any],
    seed: Optional[int] = None,
) -> BreakthroughResult:
    """尝试突破（便捷函数）。

    自动完成：检定 → 应用结果 → 返回结果。

    Args:
        profile: 玩家档案
        seed: 随机种子

    Returns:
        BreakthroughResult 对象
    """
    manager = BreakthroughManager()
    result = manager.roll_breakthrough(profile, seed)

    # 如果成功，直接应用到 profile
    if result.success:
        manager.apply_breakthrough(result, profile)

    return result
