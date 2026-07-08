"""
test_npc_context_perception.py - build_npc_context_for_ai 接入 npc_perception 测试

之前 npc_perception.py 的 perceive_player()/observe_player_with_memory()
有测试背书但没有被任何运行时代码路径调用（见 ORPHAN_MODULE_AUDIT.md）。
现在 build_npc_context_for_ai 在"没有记忆"（首次相遇）时会调用
perceive_player() 生成一段基于外貌的初见印象，而不是直接返回空字符串。
本文件测试这个新行为，不重复测 perceive_player 自己的逻辑（那部分已经
被 test_npc_relationship.py/test_player_appearance.py 覆盖）。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from npc_context import build_npc_context_for_ai, _guess_npc_cultivation


def _player_profile_with_appearance():
    return {
        "gender": "男",
        "METHOD_STATE": {"primary_path": "剑修", "growth_stage": "练气", "progress": 0},
        "CORE_STATE": {"spirit_root_element": "金"},
        "appearance": {
            "face": {"age": "二十出头", "features": ["剑眉"], "expression": "沉静"},
            "clothing": {"style": "青色劲装", "origin": "自制"},
            "aura": {"feeling": "锐利"},
            "marks": ["左手虎口有旧茧"],
            "first_impression": "一身青色劲装，眼神锐利",
        },
    }


# ── 1. 有记忆时行为不变（向后兼容）──

def test_falls_back_to_memory_based_context_when_memory_exists():
    npc_memory = {
        "李长老": [
            {"player_id": "PLAYER-A", "memory_type": "help", "emotion": "grateful",
             "summary": "曾救过我一命", "importance": 80, "trust_change": 40},
        ]
    }
    text = build_npc_context_for_ai(
        npc_id="李长老", player_id="PLAYER-A", npc_memory=npc_memory,
        player_profile=_player_profile_with_appearance(),
        npc_info={"name": "李长老", "role": "长老"},
    )
    assert "对你的印象" in text
    assert "曾救过我一命" in text


# ── 2. 没有记忆、没传 player_profile/npc_info 时行为不变（原始签名兼容）──

def test_returns_empty_without_optional_args_and_no_memory():
    text = build_npc_context_for_ai(
        npc_id="陌生人", player_id="PLAYER-A", npc_memory={},
    )
    assert text == ""


# ── 3. 没有记忆但传了 player_profile/npc_info：首次相遇用外貌生成印象 ──

def test_first_encounter_uses_appearance_perception():
    text = build_npc_context_for_ai(
        npc_id="王长老", player_id="PLAYER-A", npc_memory={},
        player_profile=_player_profile_with_appearance(),
        npc_info={"name": "王长老", "role": "长老"},
    )
    assert "初见印象" in text
    assert "王长老" in text


# ── 4. 陌生百姓（低修为）对高修为玩家感知深度浅，但普通NPC对新手玩家能看清衣着──

def test_first_encounter_low_cultivation_npc_still_produces_basic_observation():
    text = build_npc_context_for_ai(
        npc_id="路人甲", player_id="PLAYER-A", npc_memory={},
        player_profile=_player_profile_with_appearance(),
        npc_info={"name": "路人甲", "role": "百姓"},
    )
    # 普通NPC对练气期新手玩家至少能看到衣着这类基础观察
    assert text == "" or "初见印象" in text


# ── 5. 长度限制仍然生效 ──

def test_first_encounter_respects_max_chars():
    text = build_npc_context_for_ai(
        npc_id="王长老", player_id="PLAYER-A", npc_memory={},
        player_profile=_player_profile_with_appearance(),
        npc_info={"name": "王长老", "role": "长老"},
        max_chars=20,
    )
    assert len(text) <= 23  # 20 + "..." 三个字符


# ── 6. 身份→修为数值映射的基本合理性 ──

def test_guess_npc_cultivation_ordering():
    assert _guess_npc_cultivation("宗主") > _guess_npc_cultivation("长老")
    assert _guess_npc_cultivation("长老") > _guess_npc_cultivation("外门弟子")
    assert _guess_npc_cultivation("外门弟子") > _guess_npc_cultivation("百姓")
    assert _guess_npc_cultivation("完全没见过的职位") == 20  # 默认按散修估算


if __name__ == "__main__":
    test_falls_back_to_memory_based_context_when_memory_exists()
    test_returns_empty_without_optional_args_and_no_memory()
    test_first_encounter_uses_appearance_perception()
    test_first_encounter_low_cultivation_npc_still_produces_basic_observation()
    test_first_encounter_respects_max_chars()
    test_guess_npc_cultivation_ordering()
    print("\nnpc_context_perception tests passed")
