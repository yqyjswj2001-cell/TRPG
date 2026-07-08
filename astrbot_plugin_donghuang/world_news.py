"""
world_news.py - lightweight world news builder
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional


_EVENT_CATEGORY_TO_NEWS_TYPE = {
    "势力冲突": "势力动向",
    "灵脉资源": "灵脉异动",
    "修行突破": "修士传闻",
    "因果回响": "异常征兆",
    "CHAOS异常": "异常征兆",
    "遗迹与机缘": "灵墟发现",
    "日常": "市井消息",
}


class NewsItem:
    __slots__ = ("title", "news_type", "location", "content", "credibility", "may_affect_player", "timestamp")

    def __init__(
        self,
        title: str,
        news_type: str,
        location: str,
        content: str,
        credibility: str,
        may_affect_player: bool,
        timestamp: float,
    ):
        self.title = title
        self.news_type = news_type
        self.location = location
        self.content = content
        self.credibility = credibility
        self.may_affect_player = may_affect_player
        self.timestamp = timestamp

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "type": self.news_type,
            "location": self.location,
            "content": self.content,
            "credibility": self.credibility,
            "may_affect_player": self.may_affect_player,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "NewsItem":
        return cls(
            title=d["title"],
            news_type=d["type"],
            location=d["location"],
            content=d["content"],
            credibility=d["credibility"],
            may_affect_player=d.get("may_affect_player", False),
            timestamp=d.get("timestamp", 0),
        )

    def format_brief(self) -> str:
        affect_mark = "*" if self.may_affect_player else ""
        return f"[{self.news_type}]{affect_mark} {self.title} ({self.location}, {self.credibility})"


class WorldNewsBuilder:
    """Build lightweight news items from current world state and world history."""

    def __init__(
        self,
        data_dir: Path,
        max_per_generation: int = 3,
        event_pool: Optional[Any] = None,
    ):
        self.data_dir = data_dir
        self.max_per_generation = max_per_generation
        self.event_pool = event_pool
        self._news_log: Dict[str, List[NewsItem]] = {}

    def generate(
        self,
        group_id: str,
        world_state: Dict[str, Any],
        player_profiles: Dict[str, Any],
        event_log: List[Dict[str, Any]],
        campaign: Dict[str, Any],
        factions: Dict[str, Dict],
        subregions: Dict[str, List[Dict]],
        places: Dict[str, List[Dict]],
        timeline_index: Optional[Dict],
        region: Optional[str] = None,
        slot_id: Optional[str] = None,
    ) -> List[NewsItem]:
        _ = (world_state, player_profiles, event_log, factions, subregions, places, timeline_index, slot_id)
        now = time.time()
        items = self._generate_from_world_history(group_id, campaign, region, now)
        self._news_log.setdefault(group_id, []).extend(items)
        if len(self._news_log[group_id]) > 30:
            self._news_log[group_id] = self._news_log[group_id][-30:]
        return items

    def get_recent(self, group_id: str, n: int = 3) -> List[NewsItem]:
        return self._news_log.get(group_id, [])[-n:]

    def get_recent_formatted(self, group_id: str, n: int = 3) -> str:
        items = self.get_recent(group_id, n)
        if not items:
            return ""
        return "\n".join(["【东荒见闻】"] + [item.format_brief() for item in items])

    def load_log(self, group_id: str, data: List[Dict[str, Any]]) -> None:
        self._news_log[group_id] = [NewsItem.from_dict(d) for d in data]

    def dump_log(self, group_id: str) -> List[Dict[str, Any]]:
        return [item.to_dict() for item in self._news_log.get(group_id, [])]

    def build_news_from_history(
        self,
        entry: Dict[str, Any],
        timestamp: Optional[float] = None,
    ) -> Optional[NewsItem]:
        entry_type = entry.get("entry_type", "")
        region = entry.get("region", "") or "东荒"
        ts = timestamp or time.time()

        if entry_type == "proposal_spawned":
            category = entry.get("category", "日常")
            news_type = _EVENT_CATEGORY_TO_NEWS_TYPE.get(category, "市井消息")
            title = f"{region}有新动向化为{category}"
            content = f"据传一条世界动向已在{region}落成{category}事件，编号为{entry.get('event_id', 'UNKNOWN')}。"
        elif entry_type == "event_archived":
            category = entry.get("category", "日常")
            news_type = _EVENT_CATEGORY_TO_NEWS_TYPE.get(category, "市井消息")
            title = entry.get("title", f"{category}告一段落")
            content = f"{title}已被记入世界历史，结果为{entry.get('outcome_type', 'unknown')}。"
        elif entry_type == "faction_changed":
            faction_name = entry.get("faction_name", entry.get("code", "未知势力"))
            field = entry.get("field", "状态")
            news_type = "势力动向"
            title = f"{faction_name}{field}发生变化"
            content = f"{faction_name}在{region}的{field}已由{entry.get('from', '未知')}转为{entry.get('to', '未知')}。"
        elif entry_type == "environment_changed":
            spiritual = entry.get("spiritual_weather", "平稳")
            celestial = entry.get("celestial_phenomenon", "")
            anomaly = entry.get("anomaly_environment", "")
            if celestial and celestial != "无":
                news_type = "异常征兆"
                title = f"{region}{celestial}异象显现"
                content = f"{region}近日出现{celestial}，灵象转为{spiritual}。"
            elif anomaly and anomaly != "无":
                news_type = "异常征兆"
                title = f"{region}{anomaly}引发异变"
                content = f"{region}环境异常已显化为{anomaly}，灵象转为{spiritual}。"
            else:
                news_type = "灵脉异动"
                title = f"{region}灵象转为{spiritual}"
                content = f"{region}环境变化持续扩散，当前灵象为{spiritual}。"
            effects = entry.get("effects", [])
            if effects:
                content += " 已知影响包括：" + "、".join(str(effect) for effect in effects) + "。"
        elif entry_type == "npc_life_changed":
            npc_id = entry.get("npc_id", "某NPC")
            action = entry.get("action", "activity")
            summary = entry.get("summary", "")
            action_labels = {
                "seclusion": "闭关",
                "breakthrough": "突破",
                "trade": "交易",
                "join_event": "卷入争端",
                "relocate": "远行迁移",
                "disappear": "失踪",
                "death": "陨落",
            }
            action_label = action_labels.get(action, action)
            news_type = "修士传闻"
            title = f"{npc_id}{action_label}之事在{region}传开"
            content = summary or f"{npc_id}在{region}的{action_label}之事已被修士与坊间广泛议论。"
        else:
            return None

        return NewsItem(
            title=title,
            news_type=news_type,
            location=region,
            content=content,
            credibility="确有其事",
            may_affect_player=True,
            timestamp=ts,
        )

    def _generate_from_world_history(
        self,
        group_id: str,
        campaign: Dict[str, Any],
        region: Optional[str],
        now: float,
    ) -> List[NewsItem]:
        _ = group_id
        history = campaign.get("world_history", [])
        if not history:
            return []

        items: List[NewsItem] = []
        for entry in reversed(history):
            entry_region = entry.get("region", "")
            if region and entry_region and entry_region != region:
                continue
            item = self.build_news_from_history(entry, timestamp=now)
            if item is None:
                continue
            items.append(item)
            if len(items) >= self.max_per_generation:
                break
        return items
