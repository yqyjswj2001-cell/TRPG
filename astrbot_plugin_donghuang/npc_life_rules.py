"""
npc_life_rules.py - Phase E-2 NPC 生命周期因果约束规则

只读校验函数：判断某个 NPC 生命周期候选是否满足触发条件，以及某次变化
是否重大到需要额外写入 EVENT_LOG。不修改任何状态，不生成候选，不调用
NPCRegistry/NPCMemory/EventPool 等其它系统——只做布尔判断。

设计原则（对应 ARCHITECTURE_RULES.md）：
  - 这不是第二套 NPC 系统，只是把 npc_life_manager.py 里原本散落在
    if 分支中的隐式条件抽成有名字、可单测的函数，行为不变。
  - 普通 NPC 不允许随机突破/死亡：每个 validate_* 函数都要求"事件 +
    身份/关系"等多重条件同时成立，缺一不可。
"""

from __future__ import annotations

from typing import Tuple

try:
    from .npc_relationship import (
        REL_FRIENDLY,
        REL_HOSTILE,
        REL_RESPECTFUL,
        REL_SUSPICIOUS,
        REL_UNKNOWN,
    )
except ImportError:
    from npc_relationship import (
        REL_FRIENDLY,
        REL_HOSTILE,
        REL_RESPECTFUL,
        REL_SUSPICIOUS,
        REL_UNKNOWN,
    )

# ── 常量 ──

FRAGILE_ROLES = ("执事", "弟子", "散修", "deacon", "disciple", "rogue cultivator")
BREAKTHROUGH_HELP_PROBABILITY_MIN = 0.25
MAJOR_NPC_ID_PREFIX = "MAJ-"
SIGNIFICANT_ACTIONS_FOR_EVENT_LOG = ("death", "breakthrough", "disappear", "npc_join_faction", "npc_leave_faction")


def validate_breakthrough(
    life_status: str,
    has_leyline_event: bool,
    help_probability: float,
) -> Tuple[bool, str]:
    """突破需要：处于闭关状态 + 存在灵脉资源事件 + 天时（help_probability）达标。

    禁止：普通 NPC 在没有闭关、没有灵脉事件支撑的情况下随机突破。
    """
    if life_status != "seclusion":
        return False, "未处于闭关状态，不能突破"
    if not has_leyline_event:
        return False, "缺少灵脉资源事件支撑，不能突破"
    if help_probability < BREAKTHROUGH_HELP_PROBABILITY_MIN:
        return False, (
            f"天时不足（help_probability={help_probability:.2f} < "
            f"{BREAKTHROUGH_HELP_PROBABILITY_MIN}）"
        )
    return True, "闭关期满，灵脉资源具足，可尝试突破"


def validate_death(
    has_conflict_event: bool,
    has_cause_chain: bool,
    role: str,
    relationship: str,
) -> Tuple[bool, str]:
    """死亡需要：存在冲突/战斗事件 + 有因果链佐证 + 角色身份脆弱 + 关系非友善。

    禁止：没有事件原因、没有因果链佐证的随机死亡；也禁止显赫身份或
    友善关系的 NPC 无端死亡。
    """
    if not has_conflict_event:
        return False, "缺少冲突/战斗事件，不能死亡"
    if not has_cause_chain:
        return False, "缺少因果链佐证，不能死亡"
    if not any(flag in role for flag in FRAGILE_ROLES):
        return False, f"身份（{role}）不属于易损角色，不能轻易死亡"
    if relationship not in (REL_HOSTILE, REL_SUSPICIOUS, REL_UNKNOWN):
        return False, f"关系（{relationship}）过于友善，缺少死亡动机"
    return True, "冲突已生因果链，且身份脆弱、关系敌对，死亡风险成立"


def validate_disappear(
    has_chaos_event: bool,
    has_cause_chain: bool,
) -> Tuple[bool, str]:
    """失踪需要：区域存在异常事件 + 有因果链佐证。

    禁止：没有区域异常事件时的随机失踪。
    """
    if not has_chaos_event:
        return False, "缺少区域异常事件，不能失踪"
    if not has_cause_chain:
        return False, "缺少因果链佐证，不能失踪"
    return True, "区域异常且因果链成立，失踪风险成立"


def validate_relocate(
    has_cross_region_event: bool,
    relationship: str,
) -> Tuple[bool, str]:
    """迁移需要：目标区域存在跨区域机缘事件 + 关系非敌对。

    禁止：没有目标区域事件牵引的随机迁移。
    """
    if not has_cross_region_event:
        return False, "缺少跨区域机缘事件，不能迁移"
    if relationship in (REL_HOSTILE, REL_SUSPICIOUS):
        return False, f"关系（{relationship}）敌对，缺乏迁移动机"
    return True, "跨区域机缘事件存在且关系非敌对，迁移动机成立"


def validate_npc_join_faction(
    relationship: str,
    has_diplomacy_event: bool,
    already_affiliated: bool,
) -> Tuple[bool, str]:
    """加入势力需要：外交/因果回响类事件牵线 + 关系友善/敬重 + 当前未挂靠
    任何势力（散修才谈得上"加入"，已经隶属某势力的 NPC 不会再"加入"一次）。

    禁止：没有事件牵线、或关系冷淡/敌对时凭空加入。

    注意：这是 NPC 被动生命周期变化，跟 main.py 里玩家主动执行的
    `/dh join_faction` 指令（改玩家 profile.FACTION_STATE.affiliation）
    是两套完全独立的系统，只是概念相似——action 字符串特意加了 npc_ 前缀
    （npc_join_faction/npc_leave_faction）避免和玩家指令名混淆。
    """
    if already_affiliated:
        return False, "已隶属某势力，不适用加入"
    if not has_diplomacy_event:
        return False, "缺少外交/因果回响事件牵线，不能加入势力"
    if relationship not in (REL_FRIENDLY, REL_RESPECTFUL):
        return False, f"关系（{relationship}）不足以主动加入"
    return True, "有事件牵线且关系友善，加入势力的动机成立"


def validate_npc_leave_faction(
    relationship: str,
    has_conflict_event: bool,
    has_cause_chain: bool,
    currently_affiliated: bool,
) -> Tuple[bool, str]:
    """离开势力需要：当前确实隶属某势力 + 冲突事件 + 因果链佐证 + 关系恶化。

    禁止：没有隶属关系、或没有冲突因果支撑时凭空离开。
    """
    if not currently_affiliated:
        return False, "当前未隶属任何势力，不适用离开"
    if not has_conflict_event:
        return False, "缺少冲突事件，不能离开势力"
    if not has_cause_chain:
        return False, "缺少因果链佐证，不能离开势力"
    if relationship not in (REL_HOSTILE, REL_SUSPICIOUS):
        return False, f"关系（{relationship}）不足以促成离开"
    return True, "冲突因果链成立且关系恶化，离开势力的动机成立"


def is_major_npc_event(registry_id: str, action: str) -> bool:
    """判断该 NPC 生命周期变化是否需要额外写入 EVENT_LOG。

    只有"重要 NPC"（registry_id 以 MAJ- 开头，即来自 major_npcs.json，
    如宗门长老、势力首脑）发生"重大变化"（死亡/突破/失踪）时才算。
    普通 NPC（MIN- 开头）或非重大变化（迁移/闭关/交易等）只留在
    world_history 里，不写入 EVENT_LOG，避免 EVENT_LOG 被淹没。
    """
    if not registry_id or not str(registry_id).startswith(MAJOR_NPC_ID_PREFIX):
        return False
    return action in SIGNIFICANT_ACTIONS_FOR_EVENT_LOG
