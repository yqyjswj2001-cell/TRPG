"""
test_world_news.py - WorldNews tests based on world_history
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from world_news import WorldNewsBuilder


def make_world_state():
    return {
        "GLOBAL": {},
        "RESOURCE": {},
        "REGION": {},
        "FACTION_STATE": {},
    }


def make_campaign():
    return {
        "world_history": [],
    }


def test_generate_news_from_world_history_spawned():
    builder = WorldNewsBuilder(Path(__file__).resolve().parent.parent / "data", max_per_generation=3)
    campaign = make_campaign()
    campaign["world_history"] = [{
        "entry_type": "proposal_spawned",
        "proposal_id": "NPCP-001",
        "event_id": "EP0001",
        "category": "遗迹与机缘",
        "region": "east",
        "cycle": 3,
        "tick_count": 6,
    }]

    items = builder.generate(
        group_id="g_news_history_1",
        world_state=make_world_state(),
        player_profiles={},
        event_log=[],
        campaign=campaign,
        factions={},
        subregions={},
        places={},
        timeline_index=None,
        region="east",
    )

    assert items
    assert any(item.news_type == "铁墟发现" or item.news_type == "灵墟发现" or item.news_type == "遗迹与机缘" or item.news_type == "灵墟发现" for item in items) or any("遗迹" in item.title or "机缘" in item.title for item in items)


def test_generate_news_from_world_history_archived():
    builder = WorldNewsBuilder(Path(__file__).resolve().parent.parent / "data", max_per_generation=2)
    campaign = make_campaign()
    campaign["world_history"] = [{
        "entry_type": "event_archived",
        "event_id": "EP0999",
        "title": "sect conflict settled",
        "category": "势力冲突",
        "outcome_type": "resolved",
        "cycle": 10,
        "tick_count": 12,
    }]

    items = builder.generate(
        group_id="g_news_history_2",
        world_state=make_world_state(),
        player_profiles={},
        event_log=[],
        campaign=campaign,
        factions={},
        subregions={},
        places={},
        timeline_index=None,
        region="central",
    )

    assert items
    assert any(item.news_type == "势力动向" for item in items)


def test_generate_news_from_world_history_faction_changed():
    builder = WorldNewsBuilder(Path(__file__).resolve().parent.parent / "data", max_per_generation=2)
    campaign = make_campaign()
    campaign["world_history"] = [{
        "entry_type": "faction_changed",
        "code": "STATE-01",
        "faction_name": "Xuandu Court",
        "field": "active_goal",
        "from": "maintain order",
        "to": "tighten defense",
        "region": "central",
        "cycle": 11,
        "tick_count": 7,
    }]

    items = builder.generate(
        group_id="g_news_history_2_1",
        world_state=make_world_state(),
        player_profiles={},
        event_log=[],
        campaign=campaign,
        factions={},
        subregions={},
        places={},
        timeline_index=None,
        region="central",
    )

    assert items
    assert any(item.news_type == "势力动向" for item in items)
    assert any("Xuandu Court" in item.title or "Xuandu Court" in item.content for item in items)


def test_generate_news_from_world_history_environment_changed():
    builder = WorldNewsBuilder(Path(__file__).resolve().parent.parent / "data", max_per_generation=2)
    campaign = make_campaign()
    campaign["world_history"] = [{
        "entry_type": "environment_changed",
        "region": "central",
        "physical_weather": "storm",
        "spiritual_weather": "chaotic",
        "celestial_phenomenon": "blood moon",
        "anomaly_environment": "space tear",
        "effects": ["spirit flow reversal"],
        "cycle": 12,
        "tick_count": 8,
    }]

    items = builder.generate(
        group_id="g_news_history_2_2",
        world_state=make_world_state(),
        player_profiles={},
        event_log=[],
        campaign=campaign,
        factions={},
        subregions={},
        places={},
        timeline_index=None,
        region="central",
    )

    assert items
    assert any(item.news_type in ("异常征兆", "灵脉异动") for item in items)


def test_generate_news_from_world_history_npc_life_changed():
    builder = WorldNewsBuilder(Path(__file__).resolve().parent.parent / "data", max_per_generation=2)
    campaign = make_campaign()
    campaign["world_history"] = [{
        "entry_type": "npc_life_changed",
        "npc_id": "Li Elder",
        "goal": "cultivate",
        "action": "breakthrough",
        "region": "central",
        "identity": "elder",
        "cause_category": "修行突破",
        "source_refs": ["event:EP0100"],
        "summary": "Li Elder used the central leyline tide to attempt a breakthrough.",
        "cycle": 15,
        "tick_count": 4,
    }]

    items = builder.generate(
        group_id="g_news_history_2_3",
        world_state=make_world_state(),
        player_profiles={},
        event_log=[],
        campaign=campaign,
        factions={},
        subregions={},
        places={},
        timeline_index=None,
        region="central",
    )

    assert items
    assert any(item.news_type == "修士传闻" for item in items)
    assert any("Li Elder" in item.title or "Li Elder" in item.content for item in items)


def test_news_log_isolated_between_groups():
    builder = WorldNewsBuilder(Path(__file__).resolve().parent.parent / "data", max_per_generation=1)
    campaign_a = make_campaign()
    campaign_b = make_campaign()
    campaign_a["world_history"] = [{
        "entry_type": "proposal_spawned",
        "proposal_id": "A-1",
        "event_id": "EP0001",
        "category": "遗迹与机缘",
        "region": "east",
        "cycle": 1,
        "tick_count": 1,
    }]
    campaign_b["world_history"] = [{
        "entry_type": "event_archived",
        "event_id": "EP0002",
        "title": "border anomaly",
        "category": "CHAOS异常",
        "outcome_type": "partial",
        "cycle": 2,
        "tick_count": 2,
    }]

    builder.generate("group_A", make_world_state(), {}, [], campaign_a, {}, {}, {}, None, region="east")
    builder.generate("group_B", make_world_state(), {}, [], campaign_b, {}, {}, {}, None, region="west")

    recent_a = builder.get_recent("group_A", 1)
    recent_b = builder.get_recent("group_B", 1)
    assert recent_a and recent_b
    assert recent_a[0].title != recent_b[0].title


if __name__ == "__main__":
    test_generate_news_from_world_history_spawned()
    test_generate_news_from_world_history_archived()
    test_generate_news_from_world_history_faction_changed()
    test_generate_news_from_world_history_environment_changed()
    test_generate_news_from_world_history_npc_life_changed()
    test_news_log_isolated_between_groups()
    print("\nWorldNews tests passed")
