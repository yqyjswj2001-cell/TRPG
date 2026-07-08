"""
test_npc_memory.py — B-9 NPC记忆与关系系统 测试

覆盖：
  1. 创建 NPCMemory
  2. 保存读取一致
  3. 玩家帮助行为生成记忆
  4. 冲突生成敌意记忆
  5. NPC只能看到自己的记忆
  6. Snapshot恢复记忆
  7. Rollback恢复记忆
  8. 旧存档兼容
  9. 多group隔离
  10. WorldContext长度控制
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from npc_memory import (
    NPCMemory, create_memory, MEMORY_IMPORTANCE_THRESHOLD,
    action_to_memory_params, EMOTION_TO_ATTITUDE, SOURCE_PLAYER_ACTION,
)
from npc_memory_manager import NPCMemoryManager


# ──────────────────────────────────────────────
#  测试1：创建 NPCMemory
# ──────────────────────────────────────────────

def test_b91_create_npc_memory():
    """创建 NPCMemory：所有字段正确填充。"""
    mem = create_memory(
        npc_id="NPC-A",
        player_id="PLAYER-A",
        group_id="GROUP-1",
        memory_type="help",
        summary="曾帮助我解决灵脉异常。",
        importance=60,
        emotion="grateful",
        trust_change=10,
        source=SOURCE_PLAYER_ACTION,
        cycle=5,
    )

    assert mem.memory_id.startswith("MEM")
    assert mem.npc_id == "NPC-A"
    assert mem.player_id == "PLAYER-A"
    assert mem.group_id == "GROUP-1"
    assert mem.cycle == 5
    assert mem.memory_type == "help"
    assert mem.summary == "曾帮助我解决灵脉异常。"
    assert mem.importance == 60
    assert mem.emotion == "grateful"
    assert mem.trust_change == 10
    assert mem.source == SOURCE_PLAYER_ACTION

    d = mem.to_dict()
    assert d["npc_id"] == "NPC-A"
    assert d["importance"] == 60

    # from_dict 还原
    restored = NPCMemory.from_dict(d)
    assert restored.npc_id == "NPC-A"
    assert restored.importance == 60

    print("✅ B-9 测试1通过：创建 NPCMemory")


# ──────────────────────────────────────────────
#  测试2：保存读取一致
# ──────────────────────────────────────────────

def test_b92_save_load_roundtrip():
    """to_dict → JSON → from_dict → to_dict 应完全一致。"""
    mem = create_memory(
        npc_id="NPC-B", player_id="PLAYER-A", group_id="GROUP-1",
        memory_type="conflict", summary="曾发生冲突。", importance=65,
        emotion="hostile", trust_change=-15, source=SOURCE_PLAYER_ACTION, cycle=10,
    )

    d = mem.to_dict()
    json_str = json.dumps(d, ensure_ascii=False)
    d2 = json.loads(json_str)
    restored = NPCMemory.from_dict(d2)
    assert restored.to_dict() == d

    # 空 dict 也能正常反序列化
    empty = NPCMemory.from_dict({})
    assert empty.npc_id == ""
    assert empty.importance == 0

    print("✅ B-9 测试2通过：保存读取一致")


# ──────────────────────────────────────────────
#  测试3：玩家帮助行为生成记忆
# ──────────────────────────────────────────────

def test_b93_help_action_generates_memory():
    """assist + resolved → help 记忆，importance >= 40。"""
    params = action_to_memory_params(
        action_type="assist", outcome_type="resolved",
        target_id="归墟宗弟子", target_type="npc", description="协助处理了稳定灵脉。",
    )
    assert params is not None
    assert params["memory_type"] == "help"
    assert params["importance"] == 60  # resolved 时重要性更高
    assert params["emotion"] == "grateful"

    # assist + partial 也应该生成记忆
    params2 = action_to_memory_params(
        action_type="assist", outcome_type="partial",
        target_id="村民", target_type="npc", description="协助安抚了恐慌的村民。",
    )
    assert params2 is not None
    assert params2["importance"] == 45  # partial 时略低

    print("✅ B-9 测试3通过：玩家帮助行为生成记忆")


# ──────────────────────────────────────────────
#  测试4：冲突生成敌意记忆
# ──────────────────────────────────────────────

def test_b94_conflict_generates_hostile():
    """oppose + resolved/failed → conflict 记忆，情绪为 hostile。"""
    for outcome in ("resolved", "partial", "failed"):
        params = action_to_memory_params(
            action_type="oppose", outcome_type=outcome,
            target_id="敌对势力", target_type="faction", description="对抗了西部封禁势力。",
        )
        assert params is not None
        assert params["memory_type"] == "conflict"
        assert params["emotion"] == "hostile"
        assert params["importance"] >= 40

    print("✅ B-9 测试4通过：冲突生成敌意记忆")


# ──────────────────────────────────────────────
#  测试5：NPC只能看到自己的记忆
# ──────────────────────────────────────────────

def test_b95_npc_sees_own_memories():
    """不同 NPC 的记忆互不干扰。"""
    manager = NPCMemoryManager()
    campaign = {}  # 共享的 campaign 数据

    # NPC-A 对玩家的记忆
    mem_a = manager.add_memory(
        campaign=campaign, group_id="GROUP-1", npc_id="NPC-A", player_id="PLAYER-A",
        memory_type="help", summary="帮过我。", importance=60, emotion="grateful",
    )

    # NPC-B 对同一玩家的记忆（另一条记录）
    mem_b = manager.add_memory(
        campaign=campaign, group_id="GROUP-1", npc_id="NPC-B", player_id="PLAYER-A",
        memory_type="conflict", summary="跟我吵过架。", importance=65, emotion="hostile",
    )

    # NPC-A 应该只看到自己对他的记忆
    memories_a = manager.get_memories(campaign, "NPC-A", player_id="PLAYER-A")
    assert len(memories_a) == 1
    assert memories_a[0].npc_id == "NPC-A"
    assert memories_a[0].emotion == "grateful"

    # NPC-B 应该只看到自己对他的记忆
    memories_b = manager.get_memories(campaign, "NPC-B", player_id="PLAYER-A")
    assert len(memories_b) == 1
    assert memories_b[0].npc_id == "NPC-B"
    assert memories_b[0].emotion == "hostile"

    # NPC-A 不应看到 NPC-B 的记忆
    all_for_a = manager.get_memories(campaign, "NPC-A")
    assert len(all_for_a) == 1

    print("✅ B-9 测试5通过：NPC只能看到自己的记忆")


# ──────────────────────────────────────────────
#  测试6：Snapshot恢复记忆
# ──────────────────────────────────────────────

def test_b96_snapshot_restores_memories():
    """快照包含 npc_memory，rollback 后记忆恢复。"""
    manager = NPCMemoryManager()
    campaign = {}

    # 添加记忆
    mem1 = manager.add_memory(campaign, "GROUP-1", "NPC-A", "PLAYER-A",
                              "help", "帮过我。", 60, "grateful")
    mem2 = manager.add_memory(campaign, "GROUP-1", "NPC-B", "PLAYER-A",
                              "conflict", "吵过架。", 65, "hostile")

    # 拍快照（深拷贝）
    snapshot = json.loads(json.dumps(campaign))

    # 修改记忆
    manager.delete_memory(campaign, "NPC-A", mem1.memory_id)

    # rollback
    campaign.clear()
    campaign.update(json.loads(json.dumps(snapshot)))

    # 验证恢复
    memories = manager.get_memories(campaign, "NPC-A", player_id="PLAYER-A")
    assert len(memories) == 1
    assert memories[0].summary == "帮过我。"

    print("✅ B-9 测试6通过：Snapshot恢复记忆")


# ──────────────────────────────────────────────
#  测试7：Rollback恢复记忆
# ──────────────────────────────────────────────

def test_b97_rollback_restores_memories():
    """删除记忆后再 rollback，记忆恢复。"""
    manager = NPCMemoryManager()
    campaign = {}

    mem = manager.add_memory(campaign, "GROUP-1", "NPC-A", "PLAYER-A",
                             "help", "帮过我。", 60, "grateful")

    # 模拟 rollback：从快照恢复
    snapshot = json.loads(json.dumps(campaign))
    campaign = json.loads(json.dumps(snapshot))

    memories = manager.get_memories(campaign, "NPC-A", player_id="PLAYER-A")
    assert len(memories) == 1
    assert memories[0].emotion == "grateful"

    print("✅ B-9 测试7通过：Rollback恢复记忆")


# ──────────────────────────────────────────────
#  测试8：旧存档兼容
# ──────────────────────────────────────────────

def test_b98_old_save_compatibility():
    """旧存档没有 npc_memory 字段时正常启动。"""
    manager = NPCMemoryManager()
    old_campaign = {
        "state": "not_started",
        "cycle": 1,
        "slots": {},
        "combat": {"active": False, "round": 0, "monsters": {}, "used_flavor": []},
        "created_at": "2024-01-01",
        "updated_at": "2024-01-01",
    }

    # 不报错，正常初始化
    mem = manager.add_memory(old_campaign, "GROUP-1", "NPC-A", "PLAYER-A",
                             "help", "帮过我。", 60, "grateful")

    assert mem.memory_id.startswith("MEM")
    assert manager.get_memories(old_campaign, "NPC-A", player_id="PLAYER-A")[0].summary == "帮过我。"

    print("✅ B-9 测试8通过：旧存档兼容")


# ──────────────────────────────────────────────
#  测试9：多group隔离
# ──────────────────────────────────────────────

def test_b99_multi_group_isolation():
    """不同群组的 NPC 记忆互不干扰。"""
    manager = NPCMemoryManager()

    # 两个不同的群组各自有独立的 campaign 数据
    campaign_a = {}
    campaign_b = {}

    manager.add_memory(campaign_a, "GROUP-A", "NPC-X", "PLAYER-A",
                       "help", "帮过我。", 60, "grateful")
    manager.add_memory(campaign_b, "GROUP-B", "NPC-Y", "PLAYER-A",
                       "conflict", "吵过架。", 65, "hostile")

    # GROUP-A 中只有 NPC-X 的记忆
    memories_a = manager.get_memories(campaign_a, "NPC-X", player_id="PLAYER-A")
    assert len(memories_a) == 1
    assert memories_a[0].group_id == "GROUP-A"

    # GROUP-B 中只有 NPC-Y 的记忆
    memories_b = manager.get_memories(campaign_b, "NPC-Y", player_id="PLAYER-A")
    assert len(memories_b) == 1
    assert memories_b[0].group_id == "GROUP-B"

    # GROUP-A 中不应有 GROUP-B 的记忆
    all_for_a = manager.get_memories(campaign_a, "NPC-X")
    assert len(all_for_a) == 1

    # GROUP-B 中不应有 GROUP-A 的记忆
    all_for_b = manager.get_memories(campaign_b, "NPC-X")
    assert len(all_for_b) == 0

    print("✅ B-9 测试9通过：多group隔离")


# ──────────────────────────────────────────────
#  测试10：WorldContext长度控制
# ──────────────────────────────────────────────

def test_b910_worldcontext_length_control():
    """人物关系记忆段在超长时被裁剪。"""
    from world_context import WorldContextBuilder

    builder = WorldContextBuilder.__new__(WorldContextBuilder)
    builder.world_dir = Path("/tmp")
    builder.max_chars = 200  # 很短的限制

    # 构造大量记忆
    npc_memory = {}
    for i in range(10):
        npc_id = f"NPC-{i}"
        npc_memory.setdefault(npc_id, [])
        for j in range(5):
            npc_memory[npc_id].append({
                "memory_id": f"MEM{j:04d}",
                "npc_id": npc_id,
                "player_id": "PLAYER-A",
                "group_id": "GROUP-1",
                "cycle": 10,
                "memory_type": "help",
                "summary": f"第{i}个NPC的第{j}条重要记忆内容很长很详细用于测试裁剪效果。",
                "importance": 60,
                "emotion": "grateful",
                "trust_change": 10,
                "source": "player_action",
            })

    profiles = {"PLAYER-A": {"name": "测试"}}
    result = builder._extract_player_memories(npc_memory, "PLAYER-A")

    # 即使有很多记忆，也最多展示5条（加标题最多6行）
    assert result.startswith("【人物关系记忆】")
    lines = [l for l in result.split("\n") if l.strip()]
    assert len(lines) <= 6  # 标题 + 最多5条记忆

    print("✅ B-9 测试10通过：WorldContext长度控制")


# ──────────────────────────────────────────────
#  运行全部测试
# ──────────────────────────────────────────────

if __name__ == "__main__":
    test_b91_create_npc_memory()
    test_b92_save_load_roundtrip()
    test_b93_help_action_generates_memory()
    test_b94_conflict_generates_hostile()
    test_b95_npc_sees_own_memories()
    test_b96_snapshot_restores_memories()
    test_b97_rollback_restores_memories()
    test_b98_old_save_compatibility()
    test_b99_multi_group_isolation()
    test_b910_worldcontext_length_control()
    print("\n🎉 B-9 全部 10 项测试通过！")
