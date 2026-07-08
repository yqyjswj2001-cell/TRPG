"""
WorldContext NPC life history tests for Phase E.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from world_context import WorldContextBuilder


def test_extract_npc_life_history_reads_recent_entries():
    builder = WorldContextBuilder.__new__(WorldContextBuilder)
    builder.world_dir = Path(".")
    builder.max_chars = 999999

    world_history = [
        {
            "entry_type": "faction_changed",
            "summary": "无关势力变化",
            "cycle": 50,
        },
        {
            "entry_type": "npc_life_changed",
            "npc_id": "李长老",
            "summary": "李长老闭关突破失败，气息大损。",
            "cycle": 200,
        },
        {
            "entry_type": "npc_life_changed",
            "npc_id": "许执事",
            "summary": "许执事受中部灵脉动荡影响，迁往西部避祸。",
            "cycle": 230,
        },
    ]

    result = builder._extract_npc_life_history(world_history)

    assert "近期NPC命运" in result
    assert "李长老闭关突破失败" in result
    assert "许执事" in result
    assert "无关势力变化" not in result


def test_extract_npc_life_history_returns_empty_for_no_entries():
    builder = WorldContextBuilder.__new__(WorldContextBuilder)
    builder.world_dir = Path(".")
    builder.max_chars = 999999

    assert builder._extract_npc_life_history([]) == ""
    assert builder._extract_npc_life_history(
        [{"entry_type": "environment_changed", "summary": "天气变化"}]
    ) == ""


def test_build_includes_npc_life_history_section():
    builder = WorldContextBuilder(Path("."), max_chars=999999)

    world_state = {
        "GLOBAL": {
            "phase": "平稳期",
            "chaos_level": "低",
            "leyline_flow": "平缓",
            "tiandao_activity": "沉寂",
        }
    }
    player_profiles = {
        "PLAYER-A": {
            "IDENTITY_STATE": {"region": "中部", "subregion": "灵溪谷"},
            "CAUSAL_STATE": {},
        }
    }
    campaign = {
        "cycle": 230,
        "world_history": [
            {
                "entry_type": "npc_life_changed",
                "npc_id": "李长老",
                "summary": "李长老闭关突破失败，宗门内气氛骤紧。",
                "cycle": 200,
            }
        ],
    }

    result = builder.build(
        world_state=world_state,
        player_profiles=player_profiles,
        event_log=[],
        campaign=campaign,
        region="中部",
        slot_id="PLAYER-A",
    )

    assert "近期NPC命运" in result
    assert "李长老闭关突破失败" in result


if __name__ == "__main__":
    test_extract_npc_life_history_reads_recent_entries()
    test_extract_npc_life_history_returns_empty_for_no_entries()
    test_build_includes_npc_life_history_section()
    print("PASS: test_world_context_npc_life")
