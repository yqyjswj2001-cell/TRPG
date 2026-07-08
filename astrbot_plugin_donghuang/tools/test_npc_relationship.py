"""
test_npc_relationship.py — B-10 NPC认知与关系反馈系统 测试

覆盖：
  1. memory计算relationship_state
  2. 帮助提升关系
  3. 冲突降低关系
  4. NPC只能看到自己的memory
  5. NPC context长度限制
  6. AI context注入成功
  7. 旧存档兼容
  8. 多NPC隔离
  9. 特殊记忆触发检测
  10. observe_player_with_memory返回NPCPerceptionResult
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from npc_memory import NPCMemory, create_memory, MEMORY_IMPORTANCE_THRESHOLD
from npc_memory_manager import NPCMemoryManager
from npc_relationship import (
    calculate_relationship, calculate_relationship_from_objects,
    detect_special_memories, REL_UNKNOWN, REL_FAMILIAR, REL_FRIENDLY,
    REL_RESPECTFUL, REL_SUSPICIOUS, REL_HOSTILE, REL_LABELS,
    SPECIAL_MEMORY_TAGS, SPECIAL_MEMORY_NARRATIVE,
)
from npc_context import build_npc_context, build_npc_context_for_ai
from npc_perception import observe_player_with_memory, NPCPerceptionResult


# ──────────────────────────────────────────────
#  测试1：memory计算relationship_state
# ──────────────────────────────────────────────

def test_b101_memory_calculates_relationship():
    """根据 memory 列表正确计算关系状态。"""
    # 无记忆 → unknown
    assert calculate_relationship([]) == REL_UNKNOWN

    # trust_change = 0 但有记忆 → familiar
    memories = [{"memory_type": "encounter", "trust_change": 0, "importance": 50}]
    assert calculate_relationship(memories) == REL_FAMILIAR

    # trust_change >= 30 → friendly
    memories = [{"memory_type": "help", "trust_change": 35, "importance": 60}]
    assert calculate_relationship(memories) == REL_FRIENDLY

    # trust_change >= 60 → respectful
    memories = [{"memory_type": "help", "trust_change": 65, "importance": 70}]
    assert calculate_relationship(memories) == REL_RESPECTFUL

    # trust_change <= -30 → suspicious
    memories = [{"memory_type": "conflict", "trust_change": -35, "importance": 65}]
    assert calculate_relationship(memories) == REL_SUSPICIOUS

    # trust_change <= -60 → hostile
    memories = [{"memory_type": "conflict", "trust_change": -65, "importance": 75}]
    assert calculate_relationship(memories) == REL_HOSTILE

    print("✅ B-10 测试1通过：memory计算relationship_state")


# ──────────────────────────────────────────────
#  测试2：帮助提升关系
# ──────────────────────────────────────────────

def test_b102_help_improves_relationship():
    """帮助行为生成 grateful 记忆 → 关系提升。"""
    # 单次帮助 trust=10 → familiar（10 > 0 但 < 30）
    memories = [{"memory_type": "help", "trust_change": 10, "emotion": "grateful", "importance": 60}]
    assert calculate_relationship(memories) == REL_FAMILIAR

    # 多次帮助 trust_total >= 30 → friendly
    memories = [
        {"memory_type": "help", "trust_change": 15, "emotion": "grateful", "importance": 55},
        {"memory_type": "help", "trust_change": 20, "emotion": "grateful", "importance": 60},
    ]
    assert calculate_relationship(memories) == REL_FRIENDLY

    # 大量帮助 trust_total >= 60 → respectful
    memories = [
        {"memory_type": "help", "trust_change": 25, "emotion": "grateful", "importance": 60},
        {"memory_type": "rescue", "trust_change": 20, "emotion": "grateful", "importance": 80},
        {"memory_type": "help", "trust_change": 20, "emotion": "grateful", "importance": 55},
    ]
    assert calculate_relationship(memories) == REL_RESPECTFUL

    print("✅ B-10 测试2通过：帮助提升关系")


# ──────────────────────────────────────────────
#  测试3：冲突降低关系
# ──────────────────────────────────────────────

def test_b103_conflict_worsens_relationship():
    """冲突行为生成 hostile 记忆 → 关系下降。"""
    # 单次冲突 trust=-15 → familiar（有负面但不够suspicious）
    memories = [{"memory_type": "conflict", "trust_change": -15, "emotion": "hostile", "importance": 65}]
    assert calculate_relationship(memories) == REL_FAMILIAR

    # 多次冲突 trust_total <= -30 → suspicious
    memories = [
        {"memory_type": "conflict", "trust_change": -15, "emotion": "hostile", "importance": 65},
        {"memory_type": "conflict", "trust_change": -20, "emotion": "hostile", "importance": 55},
    ]
    assert calculate_relationship(memories) == REL_SUSPICIOUS

    # 严重冲突 trust_total <= -60 → hostile
    memories = [
        {"memory_type": "conflict", "trust_change": -30, "emotion": "hostile", "importance": 75},
        {"memory_type": "betrayal", "trust_change": -30, "emotion": "hostile", "importance": 90},
    ]
    assert calculate_relationship(memories) == REL_HOSTILE

    print("✅ B-10 测试3通过：冲突降低关系")


# ──────────────────────────────────────────────
#  测试4：NPC只能看到自己的memory
# ──────────────────────────────────────────────

def test_b104_npc_sees_own_memories_only():
    """NPC 只能看到自己的记忆，不读取其他 NPC 的记忆。"""
    manager = NPCMemoryManager()
    campaign = {}

    # NPC-A 帮助记忆
    manager.add_memory(campaign, "GROUP-1", "NPC-A", "PLAYER-A",
                       "help", "帮过我。", 60, "grateful")
    # NPC-B 冲突记忆
    manager.add_memory(campaign, "GROUP-1", "NPC-B", "PLAYER-A",
                       "conflict", "吵过架。", 65, "hostile")

    # NPC-A 看到友好记忆
    rel_a = calculate_relationship(
        [m.to_dict() for m in manager.get_memories(campaign, "NPC-A", player_id="PLAYER-A")]
    )
    assert rel_a in (REL_FAMILIAR, REL_FRIENDLY)

    # NPC-B 看到敌对记忆
    rel_b = calculate_relationship(
        [m.to_dict() for m in manager.get_memories(campaign, "NPC-B", player_id="PLAYER-A")]
    )
    assert rel_b in (REL_FAMILIAR, REL_SUSPICIOUS)

    # NPC-C 没有任何记忆 → unknown
    rel_c = calculate_relationship(
        [m.to_dict() for m in manager.get_memories(campaign, "NPC-C", player_id="PLAYER-A")]
    )
    assert rel_c == REL_UNKNOWN

    print("✅ B-10 测试4通过：NPC只能看到自己的memory")


# ──────────────────────────────────────────────
#  测试5：NPC context长度限制
# ──────────────────────────────────────────────

def test_b105_npc_context_length_limit():
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

    # max_memories=5
    ctx = build_npc_context("NPC-A", "PLAYER-A", npc_memory, max_memories=5, max_chars=500)
    assert ctx.startswith("【NPC-A对你的印象】")
    # 应最多5条记忆
    memory_lines = [l for l in ctx.split("\n") if l.startswith("- ")]
    assert len(memory_lines) <= 5

    # max_chars=50 极短限制
    ctx_short = build_npc_context("NPC-A", "PLAYER-A", npc_memory, max_memories=5, max_chars=50)
    assert len(ctx_short) <= 53  # 50 + "..." 最多53

    print("✅ B-10 测试5通过：NPC context长度限制")


# ──────────────────────────────────────────────
#  测试6：AI context注入成功
# ──────────────────────────────────────────────

def test_b106_ai_context_injection():
    """build_npc_context_for_ai 生成合法的 AI 上下文文本。"""
    npc_memory = {
        "归墟宗弟子": [
            {
                "memory_id": "MEM0001",
                "npc_id": "归墟宗弟子",
                "player_id": "PLAYER-A",
                "group_id": "GROUP-1",
                "cycle": 5,
                "memory_type": "help",
                "summary": "曾帮助处理灵脉异常。",
                "importance": 60,
                "emotion": "grateful",
                "trust_change": 10,
                "source": "player_action",
            },
        ],
    }

    ctx = build_npc_context_for_ai(
        npc_id="归墟宗弟子",
        player_id="PLAYER-A",
        npc_memory=npc_memory,
    )

    assert "归墟宗弟子" in ctx, f"NPC ID 应出现在上下文中，实际：{ctx}"
    assert "当前态度" in ctx or "态度" in ctx, f"上下文应包含态度信息，实际：{ctx}"
    assert "曾帮助处理灵脉异常" in ctx, f"上下文应包含记忆摘要，实际：{ctx}"

    # 无记忆时返回空
    ctx_empty = build_npc_context_for_ai("NPC-X", "PLAYER-A", npc_memory)
    assert ctx_empty == ""

    print("✅ B-10 测试6通过：AI context注入成功")


# ──────────────────────────────────────────────
#  测试7：旧存档兼容
# ──────────────────────────────────────────────

def test_b107_old_save_compatibility():
    """旧存档没有 npc_memory 字段时正常计算关系。"""
    old_campaign = {
        "state": "running",
        "cycle": 5,
        "slots": {},
    }

    # 不存在 npc_memory → 空字典
    npc_memory = old_campaign.get("npc_memory", {})
    relationship = calculate_relationship([])
    assert relationship == REL_UNKNOWN

    # build_npc_context 不崩溃
    ctx = build_npc_context("NPC-A", "PLAYER-A", npc_memory)
    assert ctx == ""

    print("✅ B-10 测试7通过：旧存档兼容")


# ──────────────────────────────────────────────
#  测试8：多NPC隔离
# ──────────────────────────────────────────────

def test_b108_multi_npc_isolation():
    """不同 NPC 的关系状态互不影响。"""
    campaign_a = {}
    campaign_b = {}

    manager = NPCMemoryManager()

    # NPC-A 友好
    manager.add_memory(campaign_a, "GROUP-1", "NPC-A", "PLAYER-X",
                       "help", "帮过我。", 60, "grateful", trust_change=35)
    # NPC-B 敌对
    manager.add_memory(campaign_b, "GROUP-1", "NPC-B", "PLAYER-X",
                       "conflict", "冲突。", 65, "hostile", trust_change=-40)

    rel_a = calculate_relationship(campaign_a.get("npc_memory", {}).get("NPC-A", []))
    rel_b = calculate_relationship(campaign_b.get("npc_memory", {}).get("NPC-B", []))

    assert rel_a == REL_FRIENDLY, f"NPC-A 应为 friendly，实际：{rel_a}"
    assert rel_b == REL_SUSPICIOUS, f"NPC-B 应为 suspicious，实际：{rel_b}"

    # 交叉查询应为 unknown
    cross_a = calculate_relationship(campaign_a.get("npc_memory", {}).get("NPC-B", []))
    assert cross_a == REL_UNKNOWN

    print("✅ B-10 测试8通过：多NPC隔离")


# ──────────────────────────────────────────────
#  测试9：特殊记忆触发检测
# ──────────────────────────────────────────────

def test_b109_special_memory_trigger():
    """rescue/major_event/betrayal 记忆触发特殊叙事标签。"""
    # rescue 触发
    memories = [{"memory_type": "rescue", "trust_change": 20, "importance": 80}]
    tags = detect_special_memories(memories)
    assert "RESCUE_MEMORY" in tags

    # major_event 触发
    memories = [{"memory_type": "major_event", "trust_change": 0, "importance": 75}]
    tags = detect_special_memories(memories)
    assert "MAJOR_EVENT_MEMORY" in tags

    # betrayal 触发
    memories = [{"memory_type": "betrayal", "trust_change": -30, "importance": 90}]
    tags = detect_special_memories(memories)
    assert "BETRAYAL_MEMORY" in tags

    # 普通帮助不触发
    memories = [{"memory_type": "help", "trust_change": 10, "importance": 60}]
    tags = detect_special_memories(memories)
    assert len(tags) == 0

    # 多种特殊记忆同时存在
    memories = [
        {"memory_type": "rescue", "trust_change": 20, "importance": 80},
        {"memory_type": "betrayal", "trust_change": -30, "importance": 90},
    ]
    tags = detect_special_memories(memories)
    assert "RESCUE_MEMORY" in tags
    assert "BETRAYAL_MEMORY" in tags

    print("✅ B-10 测试9通过：特殊记忆触发检测")


# ──────────────────────────────────────────────
#  测试10：observe_player_with_memory返回NPCPerceptionResult
# ──────────────────────────────────────────────

def test_b1010_observe_with_memory_returns_result():
    """observe_player_with_memory 返回带 relationship_state 的 NPCPerceptionResult。"""
    player_profile = {
        "name": "沈砚",
        "gender": "男",
        "CORE_STATE": {"spirit_root_tier": 1, "spirit_root_element": "金"},
        "METHOD_STATE": {"primary_path": "剑修", "growth_stage": "练气"},
    }

    npc_info = {"name": "归墟宗弟子", "cultivation": 10, "type": "外门弟子"}

    memories = [
        {
            "memory_id": "MEM0001",
            "npc_id": "归墟宗弟子",
            "player_id": "PLAYER-A",
            "group_id": "GROUP-1",
            "cycle": 5,
            "memory_type": "help",
            "summary": "曾帮助我处理灵脉异常。",
            "importance": 60,
            "emotion": "grateful",
            "trust_change": 10,
            "source": "player_action",
        },
    ]

    result = observe_player_with_memory(player_profile, npc_info, memories)

    # 返回类型应为 NPCPerceptionResult
    assert isinstance(result, NPCPerceptionResult), f"应返回 NPCPerceptionResult，实际：{type(result)}"

    # relationship_state 应被设置
    assert result.relationship_state != "unknown", \
        f"有记忆时 relationship_state 不应为 unknown，实际：{result.relationship_state}"

    # 应有观察内容
    assert len(result.observations) > 0, "应有观察内容"

    # 无记忆时返回 unknown
    result_empty = observe_player_with_memory(player_profile, npc_info, [])
    assert result_empty.relationship_state == "unknown"

    print("✅ B-10 测试10通过：observe_player_with_memory返回NPCPerceptionResult")


# ──────────────────────────────────────────────
#  测试11：特殊记忆影响关系判定
# ──────────────────────────────────────────────

def test_b1011_special_memory_affects_relationship():
    """rescue/betrayal 记忆对关系有最低保证。"""
    # rescue + 总信任为0 → 至少 friendly
    memories = [
        {"memory_type": "rescue", "trust_change": 20, "importance": 80},
        {"memory_type": "conflict", "trust_change": -20, "importance": 50},
    ]
    rel = calculate_relationship(memories)
    assert rel == REL_FRIENDLY, f"rescue 应保证至少 friendly，实际：{rel}"

    # betrayal + 总信任为0 → 至少 suspicious
    memories = [
        {"memory_type": "betrayal", "trust_change": -10, "importance": 90},
        {"memory_type": "help", "trust_change": 10, "importance": 60},
    ]
    rel = calculate_relationship(memories)
    assert rel == REL_SUSPICIOUS, f"betrayal 应保证至少 suspicious，实际：{rel}"

    # major_event + 无其他记忆 → 至少 familiar
    memories = [
        {"memory_type": "major_event", "trust_change": 0, "importance": 75},
    ]
    rel = calculate_relationship(memories)
    assert rel == REL_FAMILIAR, f"major_event 应保证至少 familiar，实际：{rel}"

    print("✅ B-10 测试11通过：特殊记忆影响关系判定")


# ──────────────────────────────────────────────
#  运行全部测试
# ──────────────────────────────────────────────

if __name__ == "__main__":
    test_b101_memory_calculates_relationship()
    test_b102_help_improves_relationship()
    test_b103_conflict_worsens_relationship()
    test_b104_npc_sees_own_memories_only()
    test_b105_npc_context_length_limit()
    test_b106_ai_context_injection()
    test_b107_old_save_compatibility()
    test_b108_multi_npc_isolation()
    test_b109_special_memory_trigger()
    test_b1010_observe_with_memory_returns_result()
    test_b1011_special_memory_affects_relationship()
    print("\n🎉 B-10 全部 11 项测试通过！")
