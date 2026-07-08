"""
test_npc_behavior.py — B-11 NPC行为倾向与关系反馈系统 测试

覆盖：
  1. 无记忆 NPC 行为正常
  2. 友善关系提升帮助倾向
  3. 敬重关系提高信息提供倾向
  4. 警惕关系降低合作倾向
  5. 敌对关系拒绝互动
  6. 不同 NPC 记忆隔离
  7. NPC Context 长度限制
  8. 旧存档兼容
  9. 不修改任何状态
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from npc_memory import create_memory, MEMORY_IMPORTANCE_THRESHOLD
from npc_relationship import (
    calculate_relationship, REL_UNKNOWN, REL_FAMILIAR, REL_FRIENDLY,
    REL_RESPECTFUL, REL_SUSPICIOUS, REL_HOSTILE,
)
from npc_behavior import (
    calculate_behavior, NPCBehaviorProfile,
    HELP_BASELINE, HELP_FRIENDLY, HELP_RESPECTFUL, HELP_FAMILIAR,
    SECRET_BASELINE, SECRET_FRIENDLY, SECRET_RESPECTFUL, SECRET_FAMILIAR,
    PRICE_BASELINE, PRICE_FRIENDLY, PRICE_RESPECTFUL, PRICE_FAMILIAR,
    RISK_CAUTIOUS, RISK_BOLD, RISK_NEUTRAL,
)
from npc_interaction import resolve_npc_interaction, InteractionResult
from npc_action_generator import generate_npc_action, plan_npc_action
from npc_context import build_npc_context, build_npc_context_for_ai


# ──────────────────────────────────────────────
#  测试1：无记忆 NPC 行为正常
# ──────────────────────────────────────────────

def test_b111_no_memory_npc_normal():
    """无记忆时，NPC 行为倾向为默认值。"""
    behavior = calculate_behavior([])

    assert behavior.relationship == REL_UNKNOWN
    assert behavior.help_probability == HELP_BASELINE
    assert behavior.secret_probability == SECRET_BASELINE
    assert behavior.price_bias == PRICE_BASELINE
    assert behavior.risk_attitude == RISK_NEUTRAL

    print("✅ B-11 测试1通过：无记忆 NPC 行为正常")


# ──────────────────────────────────────────────
#  测试2：友善关系提升帮助倾向
# ──────────────────────────────────────────────

def test_b112_friendly_increases_help():
    """友善关系 → 高帮助概率、优惠价格、大胆态度。"""
    memories = [{"memory_type": "help", "trust_change": 35, "importance": 60}]
    behavior = calculate_behavior(memories)

    assert behavior.relationship == REL_FRIENDLY
    assert behavior.help_probability > HELP_FAMILIAR
    assert behavior.price_bias >= PRICE_FAMILIAR
    assert behavior.risk_attitude in (RISK_BOLD, RISK_NEUTRAL)

    # 多次帮助 → respectful (trust >= 60)
    memories2 = [
        {"memory_type": "help", "trust_change": 30, "importance": 60},
        {"memory_type": "rescue", "trust_change": 35, "importance": 80},
    ]
    behavior2 = calculate_behavior(memories2)
    assert behavior2.relationship == REL_RESPECTFUL
    assert behavior2.help_probability > behavior.help_probability

    print("✅ B-11 测试2通过：友善关系提升帮助倾向")


# ──────────────────────────────────────────────
#  测试3：敬重关系提高信息提供倾向
# ──────────────────────────────────────────────

def test_b113_respectful_increases_info_openness():
    """敬重关系 → 最高帮助率、高信息开放、最大优惠。"""
    memories = [
        {"memory_type": "help", "trust_change": 65, "importance": 70},
        {"memory_type": "major_event", "trust_change": 0, "importance": 75},
    ]
    behavior = calculate_behavior(memories)

    assert behavior.relationship == REL_RESPECTFUL
    assert behavior.help_probability >= 0.80
    assert behavior.secret_probability >= 0.40
    assert behavior.price_bias >= 0.15
    assert behavior.risk_attitude == RISK_BOLD

    print("✅ B-11 测试3通过：敬重关系提高信息提供倾向")


# ──────────────────────────────────────────────
#  测试4：警惕关系降低合作倾向
# ──────────────────────────────────────────────

def test_b114_suspicious_reduces_cooperation():
    """警惕关系 → 低帮助率、低信息开放、谨慎态度。"""
    # trust_change = -25 → familiar（略负面但有记忆）
    # betrayal 特殊规则 → 至少 suspicious
    memories = [
        {"memory_type": "betrayal", "trust_change": -15, "importance": 90},
        {"memory_type": "encounter", "trust_change": 5, "importance": 30},
    ]
    behavior = calculate_behavior(memories)

    assert behavior.relationship == REL_SUSPICIOUS
    assert behavior.help_probability < HELP_FAMILIAR
    assert behavior.secret_probability < SECRET_FAMILIAR
    assert behavior.price_bias <= 0.0
    assert behavior.risk_attitude == RISK_CAUTIOUS

    print("✅ B-11 测试4通过：警惕关系降低合作倾向")


# ──────────────────────────────────────────────
#  测试5：敌对关系拒绝互动
# ──────────────────────────────────────────────

def test_b115_hostile_refuses_interaction():
    """敌对关系 → 极低帮助率、极低信息开放、不利价格。"""
    memories = [
        {"memory_type": "conflict", "trust_change": -65, "importance": 75},
    ]
    behavior = calculate_behavior(memories)

    assert behavior.relationship == REL_HOSTILE
    assert behavior.help_probability <= 0.10
    assert behavior.secret_probability <= 0.05
    assert behavior.price_bias <= PRICE_FAMILIAR  # 敌对时价格不利
    assert behavior.risk_attitude == RISK_CAUTIOUS

    print("✅ B-11 测试5通过：敌对关系拒绝互动")


# ──────────────────────────────────────────────
#  测试6：不同 NPC 记忆隔离
# ──────────────────────────────────────────────

def test_b116_different_npcs_isolated():
    """不同 NPC 的记忆互不影响对方的行为倾向。"""
    # NPC-A 记忆：友好
    mem_a = [{"memory_type": "help", "trust_change": 35, "importance": 60}]
    # NPC-B 记忆：敌对
    mem_b = [{"memory_type": "conflict", "trust_change": -40, "importance": 65}]

    behavior_a = calculate_behavior(mem_a)
    behavior_b = calculate_behavior(mem_b)

    assert behavior_a.relationship == REL_FRIENDLY
    assert behavior_b.relationship == REL_SUSPICIOUS

    # 空 NPC 的行为应为 unknown
    behavior_empty = calculate_behavior([])
    assert behavior_empty.relationship == REL_UNKNOWN

    print("✅ B-11 测试6通过：不同 NPC 记忆隔离")


# ──────────────────────────────────────────────
#  测试7：NPC Context 长度限制
# ──────────────────────────────────────────────

def test_b117_npc_context_length_limit():
    """NPC context 在超长时被裁剪。"""
    npc_memory = {}
    for i in range(20):
        npc_memory.setdefault("NPC-A", [])
        npc_memory["NPC-A"].append({
            "memory_id": f"MEM{i:04d}",
            "npc_id": "NPC-A",
            "player_id": "PLAYER-A",
            "group_id": "GROUP-1",
            "cycle": 10,
            "memory_type": "help",
            "summary": f"第{i}条非常长的记忆摘要用于测试裁剪效果和长度控制机制是否正常工作。",
            "importance": 60 + i,
            "emotion": "grateful",
            "trust_change": 10,
            "source": "player_action",
        })

    ctx = build_npc_context("NPC-A", "PLAYER-A", npc_memory, max_memories=5, max_chars=500)
    assert ctx.startswith("【NPC-A对你的印象】")
    # 只计算以 "- " 开头的记忆条目行
    memory_lines = [l for l in ctx.split("\n") if l.strip().startswith("- ")]
    assert len(memory_lines) <= 5

    ctx_short = build_npc_context("NPC-A", "PLAYER-A", npc_memory, max_memories=5, max_chars=50)
    assert len(ctx_short) <= 53

    print("✅ B-11 测试7通过：NPC Context 长度限制")


# ──────────────────────────────────────────────
#  测试8：旧存档兼容
# ──────────────────────────────────────────────

def test_b118_old_save_compatibility():
    """旧存档没有 npc_memory 字段时正常计算行为。"""
    old_campaign = {
        "state": "running",
        "cycle": 5,
        "slots": {},
    }

    npc_memory = old_campaign.get("npc_memory", {})
    behavior = calculate_behavior(list(npc_memory.values()))

    assert behavior.relationship == REL_UNKNOWN
    assert behavior.help_probability == HELP_BASELINE

    ctx = build_npc_context("NPC-A", "PLAYER-A", npc_memory)
    assert ctx == ""

    print("✅ B-11 测试8通过：旧存档兼容")


# ──────────────────────────────────────────────
#  测试9：不修改任何状态
# ──────────────────────────────────────────────

def test_b119_no_state_modification():
    """calculate_behavior 只读取输入，不修改任何状态。"""
    memories = [
        {"memory_type": "help", "trust_change": 35, "importance": 60},
        {"memory_type": "trade", "trust_change": 5, "importance": 40},
    ]

    original_memories = list(memories)  # 保存原始引用

    behavior = calculate_behavior(memories)

    # 验证返回了新对象，不是原地修改
    assert isinstance(behavior, NPCBehaviorProfile)
    assert behavior.relationship != ""

    # 原始列表未被修改
    assert len(original_memories) == 2
    assert original_memories[0]["memory_type"] == "help"

    print("✅ B-11 测试9通过：不修改任何状态")


def test_b1110_plan_revenge_goal_from_hostility():
    """结构化决策：敌对关系和冲突记忆应导向复仇目标。"""
    npc_info = {"name": "厉锋", "role": "散修", "personality": "多疑"}
    memories = [
        {"memory_type": "betrayal", "trust_change": -40, "importance": 90},
        {"memory_type": "conflict", "trust_change": -35, "importance": 80},
    ]

    plan = plan_npc_action(
        npc_info=npc_info,
        memories=memories,
        world_state={"REGION": {"东部": {"environment": {"anomaly_environment": "无"}}}},
        current_region="东部",
        current_events=[{"category": "势力冲突", "title": "旧仇未了"}],
    )

    assert plan["goal"] == "revenge"
    assert "relationship_hostile" in plan["reason_tags"]
    assert "event_conflict" in plan["reason_tags"]
    assert plan["primary_action"] in ("avoid_player", "send_warning")

    print("✅ B-11 测试10通过：敌对关系会导向 revenge 目标")


def test_b1111_plan_trade_goal_from_merchant_context():
    """结构化决策：商人型 NPC 在稳定环境下应优先交易目标。"""
    npc_info = {"name": "钱掌柜", "role": "商人", "personality": "豪爽"}
    memories = [{"memory_type": "help", "trust_change": 35, "importance": 60}]

    plan = plan_npc_action(
        npc_info=npc_info,
        memories=memories,
        world_state={
            "REGION": {"中部": {"environment": {"anomaly_environment": "无"}}},
            "RESOURCE": {"中部主脉残核": {"value": 72}},
        },
        current_region="中部",
        current_events=[],
    )

    assert plan["goal"] == "trade"
    assert "role_merchant" in plan["reason_tags"]
    assert "personality_bold" in plan["reason_tags"]
    assert plan["primary_action"] in ("help_player", "offer_information", "send_warning")

    print("✅ B-11 测试11通过：商人语境会导向 trade 目标")


def test_b1112_plan_survive_goal_from_anomaly_pressure():
    """结构化决策：异常环境优先触发生存目标。"""
    npc_info = {"name": "沈隐", "role": "散修", "personality": "谨慎"}
    memories = [{"memory_type": "encounter", "trust_change": 5, "importance": 20}]

    plan = plan_npc_action(
        npc_info=npc_info,
        memories=memories,
        world_state={"REGION": {"西部": {"environment": {"anomaly_environment": "空间裂隙"}}}},
        current_region="西部",
        current_events=[{"category": "CHAOS异常", "title": "裂隙扩张"}],
    )

    assert plan["goal"] == "survive"
    assert "environment_danger" in plan["reason_tags"]
    assert "personality_cautious" in plan["reason_tags"]
    assert plan["primary_action"] == "avoid_player"

    print("✅ B-11 测试12通过：异常环境会导向 survive 目标")


# ──────────────────────────────────────────────
#  运行全部测试
# ──────────────────────────────────────────────

if __name__ == "__main__":
    test_b111_no_memory_npc_normal()
    test_b112_friendly_increases_help()
    test_b113_respectful_increases_info_openness()
    test_b114_suspicious_reduces_cooperation()
    test_b115_hostile_refuses_interaction()
    test_b116_different_npcs_isolated()
    test_b117_npc_context_length_limit()
    test_b118_old_save_compatibility()
    test_b119_no_state_modification()
    test_b1110_plan_revenge_goal_from_hostility()
    test_b1111_plan_trade_goal_from_merchant_context()
    test_b1112_plan_survive_goal_from_anomaly_pressure()
    print("\n🎉 B-11 全部 9 项测试通过！")
