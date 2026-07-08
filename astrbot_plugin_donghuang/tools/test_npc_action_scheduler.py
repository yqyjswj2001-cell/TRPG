"""
test_npc_action_scheduler.py — B-14 NPC主动行为与世界交互闭环系统 测试

覆盖：
  1. 友善NPC生成主动帮助
  2. 敌对NPC生成警告/回避
  3. 未知NPC不触发
  4. 区域限制正确
  5. 冷却机制正确
  6. Tick调用成功
  7. 旧存档兼容
  8. Rollback恢复
  9. 多玩家隔离
  10. 不修改world_state
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from npc_action_scheduler import NPCActionScheduler, NPC_ACTION_COOLDOWN_CYCLES
from npc_behavior import calculate_behavior
from npc_relationship import (
    calculate_relationship, REL_FRIENDLY, REL_RESPECTFUL,
    REL_SUSPICIOUS, REL_HOSTILE, REL_FAMILIAR, REL_UNKNOWN,
)
from npc_event_trigger import create_npc_interaction_hint


# ──────────────────────────────────────────────
#  辅助函数
# ──────────────────────────────────────────────

def _make_campaign(cycle=10, npc_memory=None, cooldown=None, action_log=None):
    """构造测试用 campaign 数据。"""
    campaign = {
        "cycle": cycle,
        "npc_action_cooldown": cooldown or {},
        "npc_action_log": action_log or [],
        "npc_memory": npc_memory or {},
    }
    return campaign

def _make_profiles(player_id="PLAYER-A", region="中部"):
    """构造测试用 player_profiles。"""
    return {
        player_id: {
            "name": "玩家",
            "IDENTITY_STATE": {"region": region},
        }
    }

class _FakeRegistry:
    """模拟 NPCRegistry。"""
    def __init__(self, npcs=None):
        self._npcs = npcs or {}
    def get_npc(self, npc_id):
        return self._npcs.get(npc_id)


# ──────────────────────────────────────────────
#  测试1：友善NPC生成主动帮助
# ──────────────────────────────────────────────

def test_b141_friendly_npc_proactive():
    """友善NPC（help_probability >= 0.6）可能主动帮助。"""
    scheduler = NPCActionScheduler()

    npc_memory = {
        "李长老": [
            {"memory_type": "help", "trust_change": 40, "importance": 60,
             "player_id": "PLAYER-A", "npc_id": "李长老"},
        ]
    }

    npc_registry = _FakeRegistry({
        "李长老": {"name": "李长老", "role": "长老", "region": "中部", "faction_code": "CULT-01"},
    })

    campaign = _make_campaign(cycle=20, npc_memory=npc_memory)
    profiles = _make_profiles(region="中部")

    results = scheduler.check_npc_actions(
        group_id="GROUP-1",
        world_state={},
        player_profiles=profiles,
        npc_registry=npc_registry,
        npc_memory=npc_memory,
        campaign=campaign,
    )

    # 友善NPC应有主动行为
    assert len(results) > 0, "友善NPC应生成主动行为"
    assert results[0]["npc_id"] == "李长老"
    assert results[0]["action"] in ("send_warning", "offer_information", "help_player")
    assert results[0]["hint"] != ""

    print("✅ B-14 测试1通过：友善NPC生成主动帮助")


# ──────────────────────────────────────────────
#  测试2：敌对NPC生成警告/回避
# ──────────────────────────────────────────────

def test_b142_hostile_npc_avoid():
    """敌对NPC可能主动回避。"""
    scheduler = NPCActionScheduler()

    npc_memory = {
        "敌对散修": [
            {"memory_type": "conflict", "trust_change": -65, "importance": 75,
             "player_id": "PLAYER-A", "npc_id": "敌对散修"},
        ]
    }

    npc_registry = _FakeRegistry({
        "敌对散修": {"name": "敌对散修", "role": "散修", "region": "中部"},
    })

    campaign = _make_campaign(cycle=20, npc_memory=npc_memory)
    profiles = _make_profiles(region="中部")

    results = scheduler.check_npc_actions(
        group_id="GROUP-1",
        world_state={},
        player_profiles=profiles,
        npc_registry=npc_registry,
        npc_memory=npc_memory,
        campaign=campaign,
    )

    # 敌对NPC应有主动行为
    assert len(results) > 0, "敌对NPC应生成主动行为"
    assert results[0]["action"] == "avoid_player"

    print("✅ B-14 测试2通过：敌对NPC生成警告/回避")


# ──────────────────────────────────────────────
#  测试3：未知NPC不触发
# ──────────────────────────────────────────────
def test_b143_unknown_npc_no_action():
    """未知NPC（无记忆）不产生主动行为。"""
    scheduler = NPCActionScheduler()

    npc_memory = {}  # 无记忆
    npc_registry = _FakeRegistry({
        "路人": {"name": "路人", "role": "百姓", "region": "中部"},
    })

    campaign = _make_campaign(cycle=20, npc_memory=npc_memory)
    profiles = _make_profiles()

    results = scheduler.check_npc_actions(
        group_id="GROUP-1",
        world_state={},
        player_profiles=profiles,
        npc_registry=npc_registry,
        npc_memory=npc_memory,
        campaign=campaign,
    )

    assert len(results) == 0, "未知NPC不应产生主动行为"

    print("✅ B-14 测试3通过：未知NPC不触发")


# ──────────────────────────────────────────────
#  测试4：区域限制正确
# ──────────────────────────────────────────────

def test_b144_region_restriction():
    """NPC和玩家不在同一区域时，友善NPC不会主动帮助。"""
    scheduler = NPCActionScheduler()

    npc_memory = {
        "西部长老": [
            {"memory_type": "help", "trust_change": 40, "importance": 60,
             "player_id": "PLAYER-A", "npc_id": "西部长老"},
        ]
    }

    npc_registry = _FakeRegistry({
        "西部长老": {"name": "西部长老", "role": "长老", "region": "西部", "faction_code": "CULT-01"},
    })

    # 玩家在中部，NPC在西部
    campaign = _make_campaign(cycle=20, npc_memory=npc_memory)
    profiles = _make_profiles(region="中部")

    results = scheduler.check_npc_actions(
        group_id="GROUP-1",
        world_state={},
        player_profiles=profiles,
        npc_registry=npc_registry,
        npc_memory=npc_memory,
        campaign=campaign,
    )

    # 不同区域时，友善NPC不应触发（除非 help_probability 很高且无区域限制）
    # 由于NPC在西部、玩家在中部，应不触发
    assert len(results) == 0, "不同区域时友善NPC不应主动触发"

    print("✅ B-14 测试4通过：区域限制正确")


# ──────────────────────────────────────────────
#  测试5：冷却机制正确
# ──────────────────────────────────────────────

def test_b145_cooldown():
    """同一NPC在10个Cycle内不会再次主动。"""
    scheduler = NPCActionScheduler()

    npc_memory = {
        "李长老": [
            {"memory_type": "help", "trust_change": 40, "importance": 60,
             "player_id": "PLAYER-A", "npc_id": "李长老"},
        ]
    }

    npc_registry = _FakeRegistry({
        "李长老": {"name": "李长老", "role": "长老", "region": "中部", "faction_code": "CULT-01"},
    })

    # Cycle 10时已触发过
    cooldown = {"李长老": {"last_action_cycle": 10}}

    # Cycle 15（5个Cycle后）不应触发
    campaign = _make_campaign(cycle=15, npc_memory=npc_memory, cooldown=cooldown)
    profiles = _make_profiles(region="中部")

    results = scheduler.check_npc_actions(
        group_id="GROUP-1",
        world_state={},
        player_profiles=profiles,
        npc_registry=npc_registry,
        npc_memory=npc_memory,
        campaign=campaign,
    )
    assert len(results) == 0, "冷却期内不应触发"

    # Cycle 21（11个Cycle后）应触发
    campaign2 = _make_campaign(cycle=21, npc_memory=npc_memory, cooldown=cooldown)
    results2 = scheduler.check_npc_actions(
        group_id="GROUP-1",
        world_state={},
        player_profiles=profiles,
        npc_registry=npc_registry,
        npc_memory=npc_memory,
        campaign=campaign2,
    )
    assert len(results2) > 0, "冷却期后应可触发"

    print("✅ B-14 测试5通过：冷却机制正确")


# ──────────────────────────────────────────────
#  测试6：Tick调用成功
# ──────────────────────────────────────────────

def test_b146_tick_integration():
    """world_tick 返回结果中包含 npc_proactive 字段。"""
    from world_tick import WorldTickManager
    from world_event_pool import EventPool

    tick = WorldTickManager(EventPool())
    campaign = {
        "cycle": 1, "slots": {}, "state": "running",
        "npc_action_cooldown": {}, "npc_action_log": [],
        "combat": {"active": False, "round": 0, "monsters": {}, "used_flavor": []},
    }

    # world_state=None 时 npc_proactive 不在 if 块内
    result = tick.tick(
        group_id="GROUP-1",
        campaign=campaign,
        event_log=[],
        world_state=None,
    )

    # 结果可能没有 npc_proactive（因为没有 world_state）
    # 但不应崩溃
    assert "cycle_after" in result  # 验证 tick 基本功能

    # 有 world_state 时应包含 npc_proactive
    campaign2 = {
        "cycle": 1, "slots": {}, "state": "running",
        "npc_action_cooldown": {}, "npc_action_log": [],
        "combat": {"active": False, "round": 0, "monsters": {}, "used_flavor": []},
    }
    result2 = tick.tick(
        group_id="GROUP-1",
        campaign=campaign2,
        event_log=[],
        world_state={"GLOBAL": {}},
    )
    assert "npc_proactive" in result2, "有 world_state 时 tick 结果应包含 npc_proactive"

    print("✅ B-14 测试6通过：Tick调用成功")


# ──────────────────────────────────────────────
#  测试7：旧存档兼容
# ──────────────────────────────────────────────

def test_b147_old_save_compatible():
    """旧存档没有 npc_action_cooldown/npc_action_log 字段时正常运行。"""
    scheduler = NPCActionScheduler()

    old_campaign = {
        "cycle": 10,
        "state": "running",
        # 没有 npc_action_cooldown 和 npc_action_log
    }

    npc_memory = {}
    npc_registry = _FakeRegistry()
    profiles = _make_profiles()

    # 不崩溃
    results = scheduler.check_npc_actions(
        group_id="GROUP-1",
        world_state={},
        player_profiles=profiles,
        npc_registry=npc_registry,
        npc_memory=npc_memory,
        campaign=old_campaign,
    )
    assert isinstance(results, list)

    # log_action 应自动创建字段
    scheduler.log_action(old_campaign, "NPC-A", "PLAYER-A", "send_warning", "提示")
    assert "npc_action_log" in old_campaign
    assert len(old_campaign["npc_action_log"]) == 1

    # apply_cooldown 应自动创建字段
    scheduler.apply_cooldown(old_campaign, "NPC-A")
    assert "npc_action_cooldown" in old_campaign
    assert old_campaign["npc_action_cooldown"]["NPC-A"]["last_action_cycle"] == 10

    print("✅ B-14 测试7通过：旧存档兼容")


# ──────────────────────────────────────────────
#  测试8：Rollback恢复
# ──────────────────────────────────────────────

def test_b148_rollback_restores():
    """Snapshot/Rollback 可恢复 npc_action_log 和 npc_action_cooldown。"""
    scheduler = NPCActionScheduler()

    campaign = _make_campaign(cycle=10)
    scheduler.log_action(campaign, "NPC-A", "PLAYER-A", "send_warning", "提示1")
    scheduler.apply_cooldown(campaign, "NPC-A")

    assert len(campaign["npc_action_log"]) == 1
    assert campaign["npc_action_cooldown"]["NPC-A"]["last_action_cycle"] == 10

    # 拍快照
    snapshot = json.loads(json.dumps(campaign))

    # 继续修改
    scheduler.log_action(campaign, "NPC-B", "PLAYER-A", "offer_information", "提示2")
    assert len(campaign["npc_action_log"]) == 2

    # Rollback
    campaign.clear()
    campaign.update(json.loads(json.dumps(snapshot)))
    assert len(campaign["npc_action_log"]) == 1
    assert campaign["npc_action_log"][0]["npc_id"] == "NPC-A"

    print("✅ B-14 测试8通过：Rollback恢复")


# ──────────────────────────────────────────────
#  测试9：多玩家隔离
# ──────────────────────────────────────────────

def test_b149_multi_player_isolation():
    """不同玩家的 NPC 主动行为互不干扰。"""
    scheduler = NPCActionScheduler()

    npc_memory = {
        "李长老": [
            {"memory_type": "help", "trust_change": 40, "importance": 60,
             "player_id": "PLAYER-A", "npc_id": "李长老"},
            {"memory_type": "conflict", "trust_change": -40, "importance": 65,
             "player_id": "PLAYER-B", "npc_id": "李长老"},
        ]
    }

    npc_registry = _FakeRegistry({
        "李长老": {"name": "李长老", "role": "长老", "region": "中部", "faction_code": "CULT-01"},
    })

    profiles = {
        "PLAYER-A": {"name": "玩家A", "IDENTITY_STATE": {"region": "中部"}},
        "PLAYER-B": {"name": "玩家B", "IDENTITY_STATE": {"region": "中部"}},
    }

    campaign = _make_campaign(cycle=20, npc_memory=npc_memory)

    results = scheduler.check_npc_actions(
        group_id="GROUP-1",
        world_state={},
        player_profiles=profiles,
        npc_registry=npc_registry,
        npc_memory=npc_memory,
        campaign=campaign,
    )

    # 两个玩家都有记忆，应各自生成行为
    # PLAYER-A 是 friendly → 可能帮助/提醒
    # PLAYER-B 是 suspicious → 可能回避
    player_a_actions = [r for r in results if r.get("player_id") == "PLAYER-A"]
    player_b_actions = [r for r in results if r.get("player_id") == "PLAYER-B"]

    # 友善玩家应得到友好行为
    if player_a_actions:
        assert player_a_actions[0]["action"] in ("send_warning", "offer_information", "help_player")

    # 敌对玩家应得到回避行为
    if player_b_actions:
        assert player_b_actions[0]["action"] == "avoid_player"

    print("✅ B-14 测试9通过：多玩家隔离")


# ──────────────────────────────────────────────
#  测试10：不修改world_state
# ──────────────────────────────────────────────

def test_b1410_no_world_state_modification():
    """check_npc_actions 不直接修改 world_state。"""
    scheduler = NPCActionScheduler()

    npc_memory = {
        "李长老": [
            {"memory_type": "help", "trust_change": 40, "importance": 60,
             "player_id": "PLAYER-A", "npc_id": "李长老"},
        ]
    }

    npc_registry = _FakeRegistry({
        "李长老": {"name": "李长老", "role": "长老", "region": "中部", "faction_code": "CULT-01"},
    })

    original_ws = {"GLOBAL": {"chaos_level": "低"}}
    ws_copy = json.loads(json.dumps(original_ws))

    campaign = _make_campaign(cycle=20, npc_memory=npc_memory)
    profiles = _make_profiles(region="中部")

    results = scheduler.check_npc_actions(
        group_id="GROUP-1",
        world_state=ws_copy,
        player_profiles=profiles,
        npc_registry=npc_registry,
        npc_memory=npc_memory,
        campaign=campaign,
    )

    # world_state 未被修改
    assert ws_copy == original_ws, "check_npc_actions 不应修改 world_state"

    # 返回结果只是建议，不是执行
    for r in results:
        assert "npc_id" in r
        assert "action" in r
        assert "hint" in r

    print("✅ B-14 测试10通过：不修改world_state")


# ──────────────────────────────────────────────
#  测试11：WorldContext读取npc_action_log
# ──────────────────────────────────────────────

def test_b1411_worldcontext_reads_action_log():
    """WorldContext 可以读取 npc_action_log 并生成【近期人物动向】。"""
    from world_context import WorldContextBuilder

    builder = WorldContextBuilder.__new__(WorldContextBuilder)
    builder.world_dir = Path("/tmp")
    builder.max_chars = 999999

    action_log = [
        {"type": "npc_action", "npc_id": "李长老", "player_id": "PLAYER-A",
         "cycle": 10, "action": "send_warning",
         "hint": "李长老提醒你注意西部异常。", "consumed": False},
        {"type": "npc_action", "npc_id": "商会掌柜", "player_id": "PLAYER-A",
         "cycle": 11, "action": "offer_information",
         "hint": "商会掌柜希望与你再次交易。", "consumed": False},
    ]

    result = builder._extract_npc_action_log(action_log, "PLAYER-A")

    assert "【近期人物动向】" in result
    assert "李长老" in result or "西部" in result
    assert "商会" in result or "交易" in result

    # 空日志
    result_empty = builder._extract_npc_action_log([], "PLAYER-A")
    assert result_empty == ""

    # 已消费的条目不显示
    consumed_log = [
        {"type": "npc_action", "npc_id": "李长老", "player_id": "PLAYER-A",
         "cycle": 10, "action": "send_warning", "hint": "提示", "consumed": True},
    ]
    result_consumed = builder._extract_npc_action_log(consumed_log, "PLAYER-A")
    assert result_consumed == ""

    print("✅ B-14 测试11通过：WorldContext读取npc_action_log")


# ──────────────────────────────────────────────
#  运行全部测试
# ──────────────────────────────────────────────

if __name__ == "__main__":
    test_b141_friendly_npc_proactive()
    test_b142_hostile_npc_avoid()
    test_b143_unknown_npc_no_action()
    test_b144_region_restriction()
    test_b145_cooldown()
    test_b146_tick_integration()
    test_b147_old_save_compatible()
    test_b148_rollback_restores()
    test_b149_multi_player_isolation()
    test_b1410_no_world_state_modification()
    test_b1411_worldcontext_reads_action_log()
    print("\n🎉 B-14 全部 11 项测试通过！")
