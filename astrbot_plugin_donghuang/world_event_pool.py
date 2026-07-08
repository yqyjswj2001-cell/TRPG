"""
world_event_pool.py — 世界事件池（World Event Pool）

整个世界唯一的"正在发生的事件"管理器。

事件池 ≠ EVENT_LOG：
  - EVENT_LOG 是已完成的、不可篡改的历史记录
  - Event Pool 是正在进行的、可查询的活跃事件集合

事件池 ≠ 正式事件系统：
  - 正式事件系统（main.py 中的 turn_lock / _resolve_turn_lock）负责
    多人锁定回合制结算
  - Event Pool 只管"哪些事件正在发生"的数据层面

事件池 ≠ World Tick：
  - 本阶段不实现 Tick，不自动推进事件生命周期

设计约束（本阶段）：
  - 不推进事件
  - 不实现 Tick
  - 不自动结束事件
  - 不改变世界状态
  - 不改变玩家状态
  - 不生成 AI 剧情
  - 不写新闻
  - 不触碰现有正式事件系统
"""

from __future__ import annotations

import json
import logging
import random
import time
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  事件生命周期阶段
# ──────────────────────────────────────────────

class EventStage(str, Enum):
    """事件生命周期阶段。"""
    SPROUT = "萌芽"        # 刚刚出现征兆，尚未扩散
    SPREAD = "扩散"        # 影响范围开始扩大
    ONGOING = "进行中"     # 正在活跃发生
    CLIMAX = "高潮"        # 冲突/影响达到顶峰
    CONVERGE = "收束"      # 开始走向结局
    ENDED = "结束"         # 事件已完结
    ARCHIVED = "归档"      # 已写入 EVENT_LOG，从事件池移除


# 生命周期顺序（用于校验阶段推进的合法性）
_STAGE_ORDER = [
    EventStage.SPROUT,
    EventStage.SPREAD,
    EventStage.ONGOING,
    EventStage.CLIMAX,
    EventStage.CONVERGE,
    EventStage.ENDED,
    EventStage.ARCHIVED,
]

# 可见性
class EventVisibility(str, Enum):
    PUBLIC = "公开"        # 所有人可见
    REGIONAL = "区域"      # 仅同区域角色可见
    HIDDEN = "隐藏"        # 仅 GM 可见

# 事件类别（与 engine_rules.md 六类正式事件对齐，外加"日常"类）
class EventCategory(str, Enum):
    FACTION_CONFLICT = "势力冲突"
    LEYLINE_RESOURCE = "灵脉资源"
    CULTIVATION_BREAKTHROUGH = "修行突破"
    CAUSAL_ECHO = "因果回响"
    CHAOS_ANOMALY = "CHAOS异常"
    RUIN_OPPORTUNITY = "遗迹与机缘"
    DAILY = "日常"          # 非正式事件类：日常运转、市井消息等

# 优先级
class EventPriority(str, Enum):
    LOW = "低"
    MEDIUM = "中"
    HIGH = "高"
    CRITICAL = "紧急"


# ──────────────────────────────────────────────
#  活跃事件数据结构
# ──────────────────────────────────────────────

class ActiveEvent:
    """事件池中的一条活跃事件。"""

    __slots__ = (
        "event_id", "title", "category", "stage", "region", "location",
        "participants", "summary", "progress", "start_time",
        "estimated_end", "priority", "visibility", "player_related",
    )

    def __init__(
        self,
        event_id: str,
        title: str,
        category: str,
        stage: str,
        region: str,
        location: str,
        participants: List[str],
        summary: str,
        progress: float,
        start_time: float,
        estimated_end: Optional[float],
        priority: str,
        visibility: str,
        player_related: bool,
    ):
        self.event_id = event_id
        self.title = title
        self.category = category
        self.stage = stage
        self.region = region
        self.location = location
        self.participants = participants
        self.summary = summary
        self.progress = progress  # 0.0 ~ 1.0
        self.start_time = start_time
        self.estimated_end = estimated_end
        self.priority = priority
        self.visibility = visibility
        self.player_related = player_related

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "title": self.title,
            "category": self.category,
            "stage": self.stage,
            "region": self.region,
            "location": self.location,
            "participants": self.participants,
            "summary": self.summary,
            "progress": self.progress,
            "start_time": self.start_time,
            "estimated_end": self.estimated_end,
            "priority": self.priority,
            "visibility": self.visibility,
            "player_related": self.player_related,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ActiveEvent":
        return cls(
            event_id=d["event_id"],
            title=d["title"],
            category=d["category"],
            stage=d["stage"],
            region=d.get("region", ""),
            location=d.get("location", ""),
            participants=d.get("participants", []),
            summary=d.get("summary", ""),
            progress=d.get("progress", 0.0),
            start_time=d.get("start_time", 0),
            estimated_end=d.get("estimated_end"),
            priority=d.get("priority", "中"),
            visibility=d.get("visibility", "公开"),
            player_related=d.get("player_related", False),
        )

    def format_brief(self) -> str:
        """格式化为简短摘要，用于注入 Prompt 或日志。"""
        player_mark = "⚡" if self.player_related else ""
        return (
            f"[{self.event_id}] [{self.category}]{player_mark} "
            f"{self.title}（{self.stage}，{self.region}·{self.location}，"
            f"进度{int(self.progress * 100)}%，{self.visibility}）"
        )


# ──────────────────────────────────────────────
#  EventPool — 事件池管理器
# ──────────────────────────────────────────────

class EventPool:
    """管理世界中所有正在发生的事件。

    按 group_id 隔离。每个群有独立的事件池。
    """

    # 优先级排序权重（用于查询排序）
    _PRIORITY_WEIGHT = {
        EventPriority.CRITICAL.value: 4,
        EventPriority.HIGH.value: 3,
        EventPriority.MEDIUM.value: 2,
        EventPriority.LOW.value: 1,
    }

    def __init__(self):
        # group_id → {event_id: ActiveEvent}
        self._pools: Dict[str, Dict[str, ActiveEvent]] = {}
        # ID 计数器（每个 group 独立）
        self._id_counters: Dict[str, int] = {}
        # 归档事件记录（group_id → [archive_record, ...]）
        self._archived_events: Dict[str, List[Dict[str, Any]]] = {}

    # ──────────────────────────────────────────────
    #  增：添加事件
    # ──────────────────────────────────────────────

    def add(
        self,
        group_id: str,
        title: str,
        category: str,
        region: str = "",
        location: str = "",
        participants: Optional[List[str]] = None,
        summary: str = "",
        progress: float = 0.0,
        priority: str = EventPriority.MEDIUM.value,
        visibility: str = EventVisibility.PUBLIC.value,
        player_related: bool = False,
        stage: str = EventStage.SPROUT.value,
        start_time: Optional[float] = None,
        estimated_end: Optional[float] = None,
    ) -> ActiveEvent:
        """向事件池添加一条新事件。

        Args:
            group_id: 群号
            title: 事件标题
            category: 事件类别（见 EventCategory）
            region: 所在区域
            location: 具体地点
            participants: 参与者列表（角色/势力/NPC 名称）
            summary: 事件摘要
            progress: 进度 0.0~1.0
            priority: 优先级
            visibility: 可见性
            player_related: 是否与玩家相关
            stage: 初始阶段（默认萌芽）
            start_time: 开始时间戳（默认当前时间）
            estimated_end: 预计结束时间戳

        Returns:
            新创建的 ActiveEvent
        """
        if group_id not in self._pools:
            self._pools[group_id] = {}
            self._id_counters[group_id] = 0

        self._id_counters[group_id] += 1
        event_id = f"EP{self._id_counters[group_id]:04d}"

        event = ActiveEvent(
            event_id=event_id,
            title=title,
            category=category,
            stage=stage,
            region=region,
            location=location,
            participants=participants or [],
            summary=summary,
            progress=max(0.0, min(1.0, progress)),
            start_time=start_time or time.time(),
            estimated_end=estimated_end,
            priority=priority,
            visibility=visibility,
            player_related=player_related,
        )

        self._pools[group_id][event_id] = event
        logger.debug(f"[EventPool] 添加事件 {event_id}「{title}」→ {group_id}")
        return event

    # ──────────────────────────────────────────────
    #  删：移除事件
    # ──────────────────────────────────────────────

    def remove(self, group_id: str, event_id: str) -> Optional[ActiveEvent]:
        """从事件池移除一条事件（不归档，直接删除）。

        Returns:
            被移除的 ActiveEvent，不存在则返回 None
        """
        pool = self._pools.get(group_id, {})
        event = pool.pop(event_id, None)
        if event:
            logger.debug(f"[EventPool] 移除事件 {event_id}「{event.title}」← {group_id}")
        return event

    # ──────────────────────────────────────────────
    #  查：单条查询
    # ──────────────────────────────────────────────

    def get(self, group_id: str, event_id: str) -> Optional[ActiveEvent]:
        """按 ID 查询单条事件。"""
        return self._pools.get(group_id, {}).get(event_id)

    # ──────────────────────────────────────────────
    #  查：全部事件
    # ──────────────────────────────────────────────

    def list_all(self, group_id: str) -> List[ActiveEvent]:
        """列出指定群的所有活跃事件（按优先级降序）。"""
        pool = self._pools.get(group_id, {})
        events = list(pool.values())
        # 排除已归档的
        events = [e for e in events if e.stage != EventStage.ARCHIVED.value]
        events.sort(key=lambda e: self._PRIORITY_WEIGHT.get(e.priority, 0), reverse=True)
        return events

    # ──────────────────────────────────────────────
    #  查：按区域
    # ──────────────────────────────────────────────

    def query_by_region(self, group_id: str, region: str) -> List[ActiveEvent]:
        """查询指定区域的所有活跃事件（按优先级降序）。"""
        events = self.list_all(group_id)
        return [e for e in events if e.region == region]

    # ──────────────────────────────────────────────
    #  查：按优先级
    # ──────────────────────────────────────────────

    def query_by_priority(
        self,
        group_id: str,
        priority: str,
    ) -> List[ActiveEvent]:
        """查询指定优先级的所有活跃事件。"""
        events = self.list_all(group_id)
        return [e for e in events if e.priority == priority]

    # ──────────────────────────────────────────────
    #  查：按玩家相关性
    # ──────────────────────────────────────────────

    def query_player_related(self, group_id: str) -> List[ActiveEvent]:
        """查询所有与玩家相关的活跃事件（按优先级降序）。"""
        events = self.list_all(group_id)
        return [e for e in events if e.player_related]

    # ──────────────────────────────────────────────
    #  查：按类别
    # ──────────────────────────────────────────────

    def query_by_category(
        self,
        group_id: str,
        category: str,
    ) -> List[ActiveEvent]:
        """查询指定类别的所有活跃事件。"""
        events = self.list_all(group_id)
        return [e for e in events if e.category == category]

    # ──────────────────────────────────────────────
    #  查：按可见性过滤
    # ──────────────────────────────────────────────

    def query_visible_to(
        self,
        group_id: str,
        region: Optional[str] = None,
        is_gm: bool = False,
    ) -> List[ActiveEvent]:
        """查询对当前视角可见的事件。

        Args:
            group_id: 群号
            region: 查看者所在区域（区域可见事件只对同区域可见）
            is_gm: 是否 GM（GM 可见所有事件）

        Returns:
            可见事件列表
        """
        events = self.list_all(group_id)
        if is_gm:
            return events
        result = []
        for e in events:
            if e.visibility == EventVisibility.PUBLIC.value:
                result.append(e)
            elif e.visibility == EventVisibility.REGIONAL.value:
                if region and e.region == region:
                    result.append(e)
            # HIDDEN: 非 GM 不可见
        return result

    # ──────────────────────────────────────────────
    #  改：推进事件阶段
    # ──────────────────────────────────────────────

    def advance_stage(
        self,
        group_id: str,
        event_id: str,
        new_stage: str,
    ) -> bool:
        """推进事件到下一阶段。

        校验：只能向前推进（萌芽→扩散→进行中→...），不能倒退。
        已归档的事件不可再推进。

        Returns:
            True 表示推进成功，False 表示推进失败（不存在/非法倒退）
        """
        event = self.get(group_id, event_id)
        if not event:
            return False

        # 校验阶段合法性
        try:
            current_idx = _STAGE_ORDER.index(EventStage(event.stage))
            new_idx = _STAGE_ORDER.index(EventStage(new_stage))
        except ValueError:
            logger.warning(f"[EventPool] 非法阶段：{event.stage} → {new_stage}")
            return False

        if new_idx < current_idx:
            logger.warning(f"[EventPool] 不允许倒退阶段：{event.stage} → {new_stage}")
            return False

        if event.stage == EventStage.ARCHIVED.value:
            logger.warning(f"[EventPool] 已归档事件不可推进：{event_id}")
            return False

        old_stage = event.stage
        event.stage = new_stage
        logger.info(
            f"[EventPool] 事件 {event_id}「{event.title}」"
            f"阶段推进：{old_stage} → {new_stage}"
        )
        return True

    # ──────────────────────────────────────────────
    #  改：更新事件进度
    # ──────────────────────────────────────────────

    def update_progress(
        self,
        group_id: str,
        event_id: str,
        progress: float,
    ) -> bool:
        """更新事件进度（0.0~1.0）。

        Returns:
            True 表示更新成功
        """
        event = self.get(group_id, event_id)
        if not event:
            return False
        event.progress = max(0.0, min(1.0, progress))
        return True

    # ──────────────────────────────────────────────
    #  归档：将已结束的事件转为归档格式
    # ──────────────────────────────────────────────

    def archive(self, group_id: str, event_id: str) -> Optional[Dict[str, Any]]:
        """将一条已结束的事件归档（两阶段提交：先预览再提交）。

        内部调用 preview_archive() + commit_archive()。
        调用方如需保证 EVENT_LOG 写入成功后再删除事件，
        请分别调用 preview_archive() 和 commit_archive()。

        前提：事件阶段必须为"结束"。

        Returns:
            EVENT_LOG 标准结构字典，不符合条件返回 None
        """
        record = self.preview_archive(group_id, event_id)
        if record is None:
            return None
        self.commit_archive(group_id, event_id)
        return record

    def preview_archive(self, group_id: str, event_id: str) -> Optional[Dict[str, Any]]:
        """预览归档：生成 EVENT_LOG 记录，但不删除事件也不修改阶段。

        调用方应在 EVENT_LOG 写入成功后，再调用 commit_archive() 删除事件。
        如果 EVENT_LOG 写入失败，不调用 commit_archive()，事件保留在池中。

        Returns:
            EVENT_LOG 标准结构字典，不符合条件返回 None
        """
        event = self.get(group_id, event_id)
        if not event:
            return None

        if event.stage != EventStage.ENDED.value:
            logger.warning(
                f"[EventPool] 事件 {event_id} 阶段为 {event.stage}，"
                "必须先推进到'结束'才能归档"
            )
            return None

        # 构建 EVENT_LOG 标准结构记录（不修改事件状态）
        end_time = time.time()
        archive_record = {
            # ---- EVENT_LOG 标准字段 ----
            "event_id": event.event_id,
            "cycle": "",  # 由调用方填充
            "category": event.category,
            "participants": event.participants,
            "trigger_source": "event_pool_archive",
            "result": event.summary or event.title,
            "causal_linkage": [],
            "state_before": {},
            "state_after": {},
            "info_tier": "PUBLIC" if event.visibility == "公开" else ("REGIONAL" if event.visibility == "区域" else "GM_ONLY"),
            "irreversible": False,
            "residue": f"[EventPool归档] {event.title}（{event.region}·{event.location}，{event.priority}）",
            "snapshot_ref": None,
            # ---- EventPool 扩展字段（不影响 EVENT_LOG 已有逻辑） ----
            "title": event.title,
            "region": event.region,
            "location": event.location,
            "priority": event.priority,
            "start_time": event.start_time,
            "end_time": end_time,
            "visibility": event.visibility,
            "player_related": event.player_related,
        }

        return archive_record

    def commit_archive(self, group_id: str, event_id: str) -> bool:
        """确认归档：从事件池中删除事件，推进阶段为"归档"。

        必须在 preview_archive() 返回成功且 EVENT_LOG 写入成功后调用。
        如果 EVENT_LOG 写入失败，不要调用此方法，事件将保留在池中。

        Returns:
            True 表示提交成功，False 表示事件不存在或已归档
        """
        event = self.get(group_id, event_id)
        if not event:
            return False

        if event.stage != EventStage.ENDED.value:
            return False

        # 推进到归档
        event.stage = EventStage.ARCHIVED.value

        # 构建简要归档记录存入内存
        summary_record = {
            "id": event.event_id,
            "title": event.title,
            "category": event.category,
            "region": event.region,
            "end_time": time.time(),
        }

        # 从池中移除
        self.remove(group_id, event_id)

        # 存入归档列表
        if group_id not in self._archived_events:
            self._archived_events[group_id] = []
        self._archived_events[group_id].append(summary_record)

        logger.info(f"[EventPool] 事件 {event_id}「{event.title}」归档提交完成")
        return True

    # ──────────────────────────────────────────────
    #  统计
    # ──────────────────────────────────────────────

    def count(self, group_id: str) -> int:
        """统计指定群的活跃事件数量。"""
        return len([e for e in self._pools.get(group_id, {}).values()
                     if e.stage != EventStage.ARCHIVED.value])

    def count_by_stage(self, group_id: str) -> Dict[str, int]:
        """按阶段统计事件数量。"""
        result = {s.value: 0 for s in _STAGE_ORDER if s != EventStage.ARCHIVED}
        for e in self._pools.get(group_id, {}).values():
            if e.stage in result:
                result[e.stage] += 1
        return result

    # ──────────────────────────────────────────────
    #  格式化输出（供 WorldContext 使用）
    # ──────────────────────────────────────────────

    def format_for_context(
        self,
        group_id: str,
        region: Optional[str] = None,
        max_items: int = 5,
        max_chars: int = 300,
        is_gm: bool = False,
    ) -> str:
        """生成格式化的活跃事件摘要，供 WorldContextBuilder 注入 Prompt。

        排序优先级：
          1. player_related=True 的事件
          2. 玩家所在区域匹配的事件
          3. 高优先级事件
          4. 可见性为公开或区域的事件

        Args:
            group_id: 群号
            region: 玩家当前区域
            max_items: 最多展示几条
            max_chars: 段落最大字符数
            is_gm: 是否 GM

        Returns:
            格式化的活跃事件段落文本。没有活跃事件时返回空字符串。
        """
        # 获取可见事件
        visible = self.query_visible_to(group_id, region=region, is_gm=is_gm)
        if not visible:
            return ""

        # 排序：player_related → 同区域 → 优先级
        def _sort_key(e: ActiveEvent) -> tuple:
            player_first = 0 if e.player_related else 1
            region_match = 0 if (region and e.region == region) else 1
            priority_w = self._PRIORITY_WEIGHT.get(e.priority, 0)
            return (player_first, region_match, -priority_w)

        visible.sort(key=_sort_key)

        # 最多 max_items 条
        selected = visible[:max_items]

        # 格式化
        lines = ["【当前活跃事件】"]
        for e in selected:
            # 简短摘要：标题(类型·阶段·地点·优先级)
            affect_mark = "⚡" if e.player_related else ""
            line = (
                f"{affect_mark}{e.title}"
                f"（{e.category}·{e.stage}，{e.region}·{e.location}，{e.priority}）"
            )
            # 如果摘要不长，追加一句
            if e.summary and len(line) + len(e.summary) + 3 < 80:
                line += f"——{e.summary[:30]}"
            lines.append(line)

        text = "\n".join(lines)

        # 超长裁剪
        if len(text) > max_chars:
            # 从末尾删除事件行，直到满足长度
            while len(text) > max_chars and len(lines) > 2:
                lines.pop()
                text = "\n".join(lines)

        return text

    # ──────────────────────────────────────────────
    #  持久化
    # ──────────────────────────────────────────────────────────────

    def dump(self, group_id: str) -> List[Dict[str, Any]]:
        """导出指定群的事件池，用于持久化。"""
        return [e.to_dict() for e in self._pools.get(group_id, {}).values()]

    def load(self, group_id: str, data: List[Dict[str, Any]]) -> None:
        """从持久化数据加载事件池。"""
        self._pools[group_id] = {}
        max_id = 0
        for d in data:
            event = ActiveEvent.from_dict(d)
            self._pools[group_id][event.event_id] = event
            # 恢复 ID 计数器
            try:
                num = int(event.event_id.replace("EP", ""))
                if num > max_id:
                    max_id = num
            except ValueError:
                pass
        self._id_counters[group_id] = max_id

    def clear(self, group_id: str) -> None:
        """清空指定群的事件池。"""
        self._pools.pop(group_id, None)
        self._id_counters.pop(group_id, None)
        self._archived_events.pop(group_id, None)

    # ──────────────────────────────────────────────
    #  推进：批量推进世界事件
    # ──────────────────────────────────────────────

    def advance_world_events(self, group_id: str) -> Dict[str, Any]:
        """手动推进当前群的所有活跃事件。

        遍历所有非归档事件，每条 progress 增加 0.05~0.15，
        根据 progress 判定阶段推进（不允许一次跳多个阶段），
        已结束的事件调用 archive() 归档。

        本阶段不写入 EVENT_LOG。

        Returns:
            推进结果字典：
            {
                "advanced": [{"event_id", "title", "old_progress", "new_progress"}],
                "stage_changed": [{"event_id", "title", "old_stage", "new_stage"}],
                "archived": [{"event_id", "title", "category"}],
            }
        """
        result = {
            "advanced": [],
            "stage_changed": [],
            "archived": [],
            "_archive_event_ids": [],  # 待 commit 的事件 ID（调用方在 EVENT_LOG 写入成功后调用 commit_archive）
        }

        pool = self._pools.get(group_id, {})
        if not pool:
            return result

        # progress → stage 映射
        def _progress_to_stage(p: float) -> str:
            if p >= 1.0:
                return EventStage.ENDED.value
            elif p >= 0.8:
                return EventStage.CONVERGE.value
            elif p >= 0.6:
                return EventStage.CLIMAX.value
            elif p >= 0.4:
                return EventStage.ONGOING.value
            elif p >= 0.2:
                return EventStage.SPREAD.value
            else:
                return EventStage.SPROUT.value

        # 收集需要归档的 event_id（避免遍历时修改 dict）
        to_archive: List[str] = []

        for event_id, event in list(pool.items()):
            # 跳过已归档事件
            if event.stage == EventStage.ARCHIVED.value:
                continue
            # 跳过已结束事件（留给归档流程处理）
            if event.stage == EventStage.ENDED.value:
                to_archive.append(event_id)
                continue

            old_progress = event.progress
            old_stage = event.stage

            # 增加 progress 0.05~0.15
            increment = random.uniform(0.05, 0.15)
            new_progress = min(event.progress + increment, 1.0)
            event.progress = round(new_progress, 4)

            result["advanced"].append({
                "event_id": event.event_id,
                "title": event.title,
                "old_progress": round(old_progress, 4),
                "new_progress": event.progress,
            })

            # 根据 progress 判定目标阶段
            target_stage = _progress_to_stage(event.progress)

            # 不允许一次跳多个阶段：只能推进到当前阶段的下一个
            if target_stage != old_stage:
                try:
                    current_idx = _STAGE_ORDER.index(EventStage(old_stage))
                    target_idx = _STAGE_ORDER.index(EventStage(target_stage))
                except ValueError:
                    # 阶段枚举匹配失败，跳过
                    continue

                # 限制一次只能推进一个阶段
                if target_idx > current_idx + 1:
                    target_stage = _STAGE_ORDER[current_idx + 1].value

                if target_stage != old_stage:
                    event.stage = target_stage
                    result["stage_changed"].append({
                        "event_id": event.event_id,
                        "title": event.title,
                        "old_stage": old_stage,
                        "new_stage": target_stage,
                    })

                # 如果推进到了"结束"，标记归档
                if event.stage == EventStage.ENDED.value:
                    to_archive.append(event_id)

        # 归档已结束的事件（两阶段：先预览，不删除事件）
        for event_id in to_archive:
            record = self.preview_archive(group_id, event_id)
            if record:
                result["archived"].append(record)
                result["_archive_event_ids"].append(event_id)

        logger.info(
            f"[EventPool] advance_world_events({group_id}): "
            f"推进{len(result['advanced'])}条，"
            f"阶段变化{len(result['stage_changed'])}条，"
            f"归档{len(result['archived'])}条"
        )
        return result

    # ──────────────────────────────────────────────
    #  玩家行为推动事件
    # ──────────────────────────────────────────────

    # action_type → 优先推动的事件类别列表
    _ACTION_CATEGORY_MAP: Dict[str, List[str]] = {
        "explore": ["遗迹与机缘"],
        "battle": ["势力冲突", "CHAOS异常"],
        "cultivate": ["灵脉资源"],
        "trade": ["日常"],
        "investigate": ["CHAOS异常", "遗迹与机缘"],
        "join_faction": ["势力冲突"],
        "leave_faction": ["势力冲突"],
        "travel": [],  # travel 特殊处理：进入有事件的区域即可
    }

    def apply_player_action(
        self,
        group_id: str,
        action_type: str,
        region: str,
        location: str = "",
        player_name: str = "",
        optional_target: str = "",
    ) -> Dict[str, Any]:
        """根据玩家行为推动已有活跃事件。

        匹配优先级：同地点 > 同区域 > 同类别。
        如果没有符合条件的事件，不做任何事。
        禁止自动创建事件。

        Args:
            group_id: 群号
            action_type: 行为类型（explore/battle/cultivate/trade/
                         join_faction/leave_faction/investigate/travel）
            region: 玩家所在区域
            location: 玩家所在地点
            player_name: 玩家角色名
            optional_target: 可选目标（如势力名、地点名）

        Returns:
            影响结果字典：
            {
                "affected_event": str | None,  # 受影响事件 ID
                "title": str,                   # 事件标题
                "category": str,                # 事件类别
                "progress_before": float,       # 推进前进度
                "progress_after": float,        # 推进后进度
                "stage_changed": bool,          # 阶段是否变化
                "old_stage": str,               # 变化前阶段
                "new_stage": str,               # 变化后阶段
            }
            无影响时 affected_event 为 None。
        """
        no_effect = {
            "affected_event": None,
            "title": "",
            "category": "",
            "progress_before": 0.0,
            "progress_after": 0.0,
            "stage_changed": False,
            "old_stage": "",
            "new_stage": "",
        }

        pool = self._pools.get(group_id, {})
        if not pool:
            return no_effect

        # travel 特殊处理：进入有事件的区域，所有同区域事件 progress +0.03
        if action_type == "travel":
            return self._apply_travel(group_id, region, pool)

        # 获取该 action_type 优先推动的类别
        preferred_categories = self._ACTION_CATEGORY_MAP.get(action_type, [])
        if not preferred_categories:
            return no_effect

        # 筛选候选事件：排除已结束/归档的
        candidates = [
            e for e in pool.values()
            if e.stage not in (EventStage.ENDED.value, EventStage.ARCHIVED.value)
        ]
        if not candidates:
            return no_effect

        # 匹配优先级：同地点+同类别 > 同区域+同类别 > 同类别
        matched = self._find_best_match(candidates, preferred_categories, region, location)

        if not matched:
            return no_effect

        # 推进匹配到的事件
        return self._push_event(group_id, matched)

    def _apply_travel(
        self,
        group_id: str,
        region: str,
        pool: Dict[str, ActiveEvent],
    ) -> Dict[str, Any]:
        """travel 行为：同区域所有事件 progress +0.03，只报告第一个受影响的。"""
        for event in pool.values():
            if event.stage in (EventStage.ENDED.value, EventStage.ARCHIVED.value):
                continue
            if event.region == region:
                old_progress = event.progress
                new_progress = min(event.progress + 0.03, 1.0)
                self.update_progress(group_id, event.event_id, new_progress)
                # 检查阶段是否变化
                old_stage = event.stage
                self._check_and_advance_stage(group_id, event)
                stage_changed = event.stage != old_stage
                logger.info(
                    f"[EventPool] travel 推动事件 {event.event_id}「{event.title}」"
                    f"：{old_progress:.4f} → {new_progress:.4f}"
                )
                return {
                    "affected_event": event.event_id,
                    "title": event.title,
                    "category": event.category,
                    "progress_before": round(old_progress, 4),
                    "progress_after": round(new_progress, 4),
                    "stage_changed": stage_changed,
                    "old_stage": old_stage,
                    "new_stage": event.stage,
                }
        return {
            "affected_event": None,
            "title": "",
            "category": "",
            "progress_before": 0.0,
            "progress_after": 0.0,
            "stage_changed": False,
            "old_stage": "",
            "new_stage": "",
        }

    def _find_best_match(
        self,
        candidates: List[ActiveEvent],
        preferred_categories: List[str],
        region: str,
        location: str,
    ) -> Optional[ActiveEvent]:
        """按优先级匹配最佳事件：同地点+同类别 > 同区域+同类别 > 同类别。"""
        # 优先级1：同地点 + 同类别
        for cat in preferred_categories:
            for e in candidates:
                if e.category == cat and e.region == region and location and e.location == location:
                    return e

        # 优先级2：同区域 + 同类别
        for cat in preferred_categories:
            for e in candidates:
                if e.category == cat and e.region == region:
                    return e

        # 优先级3：同类别（不限区域）
        for cat in preferred_categories:
            for e in candidates:
                if e.category == cat:
                    return e

        return None

    def _push_event(self, group_id: str, event: ActiveEvent) -> Dict[str, Any]:
        """推动一条事件：progress +0.05~0.15，检查阶段变化。"""
        old_progress = event.progress
        increment = random.uniform(0.05, 0.15)
        new_progress = min(event.progress + increment, 1.0)

        # 调用已有接口更新进度
        self.update_progress(group_id, event.event_id, new_progress)

        # 检查并推进阶段
        old_stage = event.stage
        self._check_and_advance_stage(group_id, event)
        stage_changed = event.stage != old_stage

        logger.info(
            f"[EventPool] 玩家行为推动事件 {event.event_id}「{event.title}」"
            f"：{old_progress:.4f} → {new_progress:.4f}"
            f"{'，阶段变化：' + old_stage + ' → ' + event.stage if stage_changed else ''}"
        )

        return {
            "affected_event": event.event_id,
            "title": event.title,
            "category": event.category,
            "progress_before": round(old_progress, 4),
            "progress_after": round(new_progress, 4),
            "stage_changed": stage_changed,
            "old_stage": old_stage,
            "new_stage": event.stage,
        }

    def _check_and_advance_stage(self, group_id: str, event: ActiveEvent) -> None:
        """根据当前 progress 检查是否需要推进阶段，调用 advance_stage()。

        不允许一次跳多个阶段。
        """
        # progress → stage 映射
        def _progress_to_stage(p: float) -> str:
            if p >= 1.0:
                return EventStage.ENDED.value
            elif p >= 0.8:
                return EventStage.CONVERGE.value
            elif p >= 0.6:
                return EventStage.CLIMAX.value
            elif p >= 0.4:
                return EventStage.ONGOING.value
            elif p >= 0.2:
                return EventStage.SPREAD.value
            else:
                return EventStage.SPROUT.value

        target_stage = _progress_to_stage(event.progress)
        if target_stage == event.stage:
            return

        # 不允许一次跳多个阶段
        try:
            current_idx = _STAGE_ORDER.index(EventStage(event.stage))
            target_idx = _STAGE_ORDER.index(EventStage(target_stage))
        except ValueError:
            return

        if target_idx > current_idx + 1:
            target_stage = _STAGE_ORDER[current_idx + 1].value

        if target_stage != event.stage:
            self.advance_stage(group_id, event.event_id, target_stage)

    # ──────────────────────────────────────────────
    #  开团初始化：注册初始世界事件
    # ──────────────────────────────────────────────

    def seed_initial_events(
        self,
        group_id: str,
        world_state: Dict[str, Any],
        factions: Dict[str, Dict],
        subregions: Dict[str, List[Dict]],
        places: Dict[str, List[Dict]],
    ) -> List[ActiveEvent]:
        """开团时基于 world_state 和势力数据注册 2~3 条初始世界事件。

        事件来源严格基于现有数据（INITIAL_WORLD_STATE + 势力库 + 子区域/地点库），
        不凭空生成。

        Args:
            group_id: 群号
            world_state: 当前世界状态（刚创建的 INITIAL_WORLD_STATE）
            factions: 势力定义（code → faction dict）
            subregions: 五域子区域（region → list）
            places: 五域地点（region → list）

        Returns:
            注册的 ActiveEvent 列表
        """
        # 先清空旧事件（防止重开团时残留）
        self.clear(group_id)

        global_state = world_state.get("GLOBAL", {})
        regions_state = world_state.get("REGION", {})
        causal_state = world_state.get("CAUSAL", {})
        resource_state = world_state.get("RESOURCE", {})

        # 收集候选事件模板（基于 world_state 的实际内容）
        candidates = []

        # ── 候选1：灵脉资源（基于灵气东移 + 东部新生支脉） ──
        leyline_flow = global_state.get("qi_flow") or global_state.get("leyline_flow", "")
        eastern_resource = resource_state.get("东部新生支脉", {})
        east_sub = subregions.get("东部", [])
        east_places = places.get("东部", [])
        if leyline_flow or eastern_resource:
            # 从东部子区域和地点中取一个具体位置
            loc_name = "启阳"
            sub_name = ""
            if east_sub:
                sub = random.choice(east_sub)
                sub_name = sub.get("name", "")
            if east_places:
                loc_name = random.choice(east_places).get("name", "启阳")
            location = f"东部·{sub_name}·{loc_name}" if sub_name else f"东部·{loc_name}"
            candidates.append({
                "title": "灵气东移加速，东部灵脉出现偏转征象",
                "category": EventCategory.LEYLINE_RESOURCE.value,
                "stage": EventStage.SPROUT.value,
                "region": "东部",
                "location": location,
                "participants": ["东部拓展宗门"],
                "summary": f"灵气整体流向{leyline_flow or '东移'}，东部新生支脉状态{eastern_resource.get('state', '活跃')}",
                "progress": 0.15,
                "priority": EventPriority.HIGH.value,
                "visibility": EventVisibility.PUBLIC.value,
                "player_related": False,
            })

        # ── 候选2：势力冲突（基于西部封禁结构接近崩溃） ──
        western_faction = None
        for code, fac in factions.items():
            name = fac.get("name", "")
            if "西部" in name or "封禁" in name or code == "HIDDEN_XB":
                western_faction = fac
                break
        western_resource = resource_state.get("西部遗迹与异常资源", {})
        west_sub = subregions.get("西部", [])
        west_places = places.get("西部", [])
        if western_faction or western_resource:
            fac_name = western_faction.get("name", "西部封禁势力") if western_faction else "西部封禁势力"
            sub_name = ""
            loc_name = "裂川"
            if west_sub:
                sub_name = random.choice(west_sub).get("name", "")
            if west_places:
                loc_name = random.choice(west_places).get("name", "裂川")
            location = f"西部·{sub_name}·{loc_name}" if sub_name else f"西部·{loc_name}"
            candidates.append({
                "title": f"{fac_name}封印松动，西部局势持续恶化",
                "category": EventCategory.FACTION_CONFLICT.value,
                "stage": EventStage.ONGOING.value,
                "region": "西部",
                "location": location,
                "participants": [fac_name],
                "summary": f"封禁结构稳定度：{western_resource.get('state', '高压')}，因果沉积接近临界",
                "progress": 0.45,
                "priority": EventPriority.CRITICAL.value,
                "visibility": EventVisibility.REGIONAL.value,
                "player_related": False,
            })

        # ── 候选3：遗迹与机缘（基于上古战争因果临界） ──
        ancient_war = causal_state.get("上古战争", {})
        ruin_responsibility = causal_state.get("遗迹封闭责任", {})
        central_sub = subregions.get("中部", [])
        central_places = places.get("中部", [])
        if ancient_war.get("tier") in ("临界", "高") or ruin_responsibility:
            sub_name = ""
            loc_name = "祖脉余山"
            if central_sub:
                sub_name = random.choice(central_sub).get("name", "")
            if central_places:
                loc_name = random.choice(central_places).get("name", "祖脉余山")
            location = f"中部·{sub_name}·{loc_name}" if sub_name else f"中部·{loc_name}"
            candidates.append({
                "title": "中部古战场封印出现异常波动",
                "category": EventCategory.RUIN_OPPORTUNITY.value,
                "stage": EventStage.SPROUT.value,
                "region": "中部",
                "location": location,
                "participants": ["中部守成宗门"],
                "summary": "上古战争因果临界，遗迹封印松动迹象，守成宗门已加强巡查",
                "progress": 0.1,
                "priority": EventPriority.MEDIUM.value,
                "visibility": EventVisibility.REGIONAL.value,
                "player_related": False,
            })

        # ── 候选4：CHAOS异常（基于 CHAOS 活跃度） ──
        chaos_level = global_state.get("chaos_level", "")
        if chaos_level and chaos_level not in ("沉寂", "未知"):
            west_sub2 = subregions.get("西部", [])
            sub_name2 = random.choice(west_sub2).get("name", "") if west_sub2 else ""
            location2 = f"西部·{sub_name2}" if sub_name2 else "西部"
            candidates.append({
                "title": "西部CHAOS异常活跃，时空裂缝频繁闪现",
                "category": EventCategory.CHAOS_ANOMALY.value,
                "stage": EventStage.SPREAD.value,
                "region": "西部",
                "location": location2,
                "participants": [],
                "summary": f"CHAOS活跃度{chaos_level}，西部封禁区域异常频发",
                "progress": 0.3,
                "priority": EventPriority.HIGH.value,
                "visibility": EventVisibility.PUBLIC.value,
                "player_related": False,
            })

        # ── 候选5：日常（基于南部承载压力） ──
        southern_carry = causal_state.get("南部承载", {})
        south_resource = resource_state.get("南部资源网络", {})
        if southern_carry.get("tier") in ("高", "临界") or south_resource:
            south_sub = subregions.get("南部", [])
            sub_name3 = random.choice(south_sub).get("name", "") if south_sub else ""
            location3 = f"南部·{sub_name3}" if sub_name3 else "南部"
            candidates.append({
                "title": "南部供给紧张，各地坊市物资紧缺",
                "category": EventCategory.DAILY.value,
                "stage": EventStage.ONGOING.value,
                "region": "南部",
                "location": location3,
                "participants": ["南部水土维护结构"],
                "summary": "承载压力持续上升，资源网络趋紧，各地物价上涨",
                "progress": 0.5,
                "priority": EventPriority.LOW.value,
                "visibility": EventVisibility.PUBLIC.value,
                "player_related": False,
            })

        # 从候选中选择 2~3 条，确保：
        # - 至少 1 条公开事件
        # - 至少 1 条区域事件
        # - 不生成隐藏事件
        selected = self._select_initial_candidates(candidates)

        # 注册到事件池
        registered = []
        for c in selected:
            event = self.add(group_id=group_id, **c)
            registered.append(event)

        return registered

    def _select_initial_candidates(self, candidates: List[Dict]) -> List[Dict]:
        """从候选事件中选择 2~3 条，确保至少1条公开、1条区域。

        选择策略：
        1. 优先保证公开+区域的覆盖
        2. 按优先级从高到低填充
        3. 总数 2~3 条
        """
        if not candidates:
            return []

        public = [c for c in candidates if c["visibility"] == EventVisibility.PUBLIC.value]
        regional = [c for c in candidates if c["visibility"] == EventVisibility.REGIONAL.value]

        selected: List[Dict] = []

        # 第一条：必须有一条公开事件
        if public:
            # 优先级最高的公开事件
            public.sort(key=lambda c: self._PRIORITY_WEIGHT.get(c["priority"], 0), reverse=True)
            selected.append(public[0])
        elif candidates:
            selected.append(candidates[0])

        # 第二条：必须有一条区域事件
        if regional:
            regional.sort(key=lambda c: self._PRIORITY_WEIGHT.get(c["priority"], 0), reverse=True)
            # 避免跟已选的完全相同
            for r in regional:
                if r["title"] != selected[0]["title"]:
                    selected.append(r)
                    break
            else:
                if len(selected) < 2:
                    selected.append(regional[0])

        # 第三条：如果候选够多，再补一条不同区域的
        if len(candidates) >= 3 and len(selected) < 3:
            used_regions = {c["region"] for c in selected}
            different_region = [c for c in candidates if c["region"] not in used_regions and c["title"] not in {s["title"] for s in selected}]
            if different_region:
                different_region.sort(key=lambda c: self._PRIORITY_WEIGHT.get(c["priority"], 0), reverse=True)
                selected.append(different_region[0])

        return selected
