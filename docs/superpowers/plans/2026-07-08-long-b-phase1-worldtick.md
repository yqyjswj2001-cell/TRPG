# LONG-B 第一阶段 WorldTick 升级 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不重写 `WorldState`、不重写 `EventPool`、不破坏 `/dh rollback` 的前提下，把 `WorldTickManager` 升级为带世界时钟、NPC 主动行为接入、显式 Tick 台账的低频世界自主运行入口。

**Architecture:** 以 `world_tick.py` 为编排层，新增挂载在 `campaign[group_id]` 下的 `world_clock`、`tick_ledger`、`npc_world_queue` 三类运行态数据。自然演化仍复用 `WorldEvolutionManager`，NPC 行为仍由 `NPCActionScheduler` 产出候选项而非直接改世界，回滚继续依赖 `main.py` 现有整群快照。

**Tech Stack:** Python 3.x，AstrBot 插件结构，现有 `EventPool` / `WorldEvolutionManager` / `NPCActionScheduler` / 纯 Python 测试脚本。

## Global Constraints

- 复用现有 `WorldTick`、`WorldEvolution`、`WorldEnvironment`、`EventPool`、`WorldEventTrigger`、`WorldNews`、`NPCActionScheduler`、`NPCMemory`
- 禁止重写 `WorldState`
- 禁止重写 `EventPool`
- 禁止破坏 `/dh rollback`
- 所有变化必须代码控制，不能让 AI 直接修改世界
- 所有新增运行态必须挂在现有可快照对象内，优先使用 `campaign[group_id]`
- 所有第一阶段改动必须具备单元测试、存档/兼容测试、rollback 测试、多 group 测试

---

### Task 1: 建立 World Clock 默认结构与推进函数

**Files:**
- Modify: `astrbot_plugin_donghuang/world_tick.py`
- Test: `astrbot_plugin_donghuang/tools/test_world_tick.py`

**Interfaces:**
- Consumes: `campaign: Dict[str, Any]`
- Produces: `WorldTickManager._ensure_world_clock(campaign: Dict[str, Any]) -> Dict[str, Any]`
- Produces: `WorldTickManager._advance_world_clock(campaign: Dict[str, Any]) -> Dict[str, Any]`
- Produces: `result["world_clock"] = {"before": Dict[str, Any], "after": Dict[str, Any], "changed": bool}`

- [ ] **Step 1: Write the failing test**

```python
def test_tick_initializes_world_clock():
    pool = EventPool()
    tm = WorldTickManager(pool)
    campaign = make_campaign(cycle=1)
    result = tm.tick("clock_g1", campaign, [])

    assert "world_clock" in campaign
    assert campaign["world_clock"]["tick_count"] == 1
    assert campaign["world_clock"]["world_day"] == 1
    assert campaign["world_clock"]["time_phase"] == "清晨"
    assert campaign["world_clock"]["season"] == "春"
    assert result["world_clock"]["changed"] is True


def test_world_clock_advances_time_phase():
    pool = EventPool()
    tm = WorldTickManager(pool)
    campaign = make_campaign(cycle=1)
    event_log = []

    phases = []
    for _ in range(5):
        tm.tick("clock_g2", campaign, event_log)
        phases.append(campaign["world_clock"]["time_phase"])

    assert phases[:4] == ["清晨", "白昼", "黄昏", "子夜"]
    assert campaign["world_clock"]["world_day"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python astrbot_plugin_donghuang/tools/test_world_tick.py`
Expected: FAIL with missing `world_clock` assertions

- [ ] **Step 3: Write minimal implementation**

```python
class WorldTickManager:
    _TIME_PHASES = ["子夜", "清晨", "白昼", "黄昏"]
    _SEASONS = ["春", "夏", "秋", "冬"]
    _DAYS_PER_SEASON = 30

    def _ensure_world_clock(self, campaign: Dict[str, Any]) -> Dict[str, Any]:
        clock = campaign.setdefault("world_clock", {})
        clock.setdefault("tick_count", 0)
        clock.setdefault("world_day", 1)
        clock.setdefault("time_phase", "子夜")
        clock.setdefault("season", "春")
        clock["calendar_label"] = self._format_calendar_label(clock)
        return clock

    def _format_calendar_label(self, clock: Dict[str, Any]) -> str:
        return f"东荒历1年{clock['season']}{clock['world_day']}日{clock['time_phase']}"

    def _advance_world_clock(self, campaign: Dict[str, Any]) -> Dict[str, Any]:
        clock = self._ensure_world_clock(campaign)
        before = dict(clock)
        idx = self._TIME_PHASES.index(clock["time_phase"])
        idx = (idx + 1) % len(self._TIME_PHASES)
        clock["time_phase"] = self._TIME_PHASES[idx]
        clock["tick_count"] += 1
        if clock["time_phase"] == "子夜":
            clock["world_day"] += 1
            season_idx = min((clock["world_day"] - 1) // self._DAYS_PER_SEASON, 3)
            clock["season"] = self._SEASONS[season_idx]
        clock["calendar_label"] = self._format_calendar_label(clock)
        return {"before": before, "after": dict(clock), "changed": before != clock}
```

- [ ] **Step 4: Wire world clock into tick result**

```python
result = {
    "cycle_before": campaign.get("cycle", 1),
    "cycle_after": 0,
    "world_clock": {"before": {}, "after": {}, "changed": False},
    "events_progressed": [],
    "stage_changed": [],
    "archived": [],
    "evolution": {...},
}

campaign["cycle"] = campaign.get("cycle", 1) + 1
result["cycle_after"] = campaign["cycle"]
result["world_clock"] = self._advance_world_clock(campaign)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python astrbot_plugin_donghuang/tools/test_world_tick.py`
Expected: existing tests PASS and new world clock tests PASS

- [ ] **Step 6: Commit**

```bash
git add astrbot_plugin_donghuang/world_tick.py astrbot_plugin_donghuang/tools/test_world_tick.py
git commit -m "feat: add world clock to world tick"
```

### Task 2: 把 NPCActionScheduler 接入 Tick 主流程并落地 npc_world_queue

**Files:**
- Modify: `astrbot_plugin_donghuang/world_tick.py`
- Modify: `astrbot_plugin_donghuang/main.py`
- Test: `astrbot_plugin_donghuang/tools/test_world_tick.py`

**Interfaces:**
- Consumes: `campaign["npc_memory"]`, `campaign["npc_action_cooldown"]`, `campaign["npc_action_log"]`
- Consumes: `player_profiles: Dict[str, Any]`
- Consumes: `npc_registry: Any`
- Produces: `result["npc_proactive"]: List[Dict[str, Any]]`
- Produces: `campaign["npc_world_queue"]: List[Dict[str, Any]]`
- Produces: `WorldTickManager.tick(..., player_profiles: Optional[Dict[str, Any]] = None, npc_registry: Any = None) -> Dict[str, Any]`

- [ ] **Step 1: Write the failing test**

```python
class StubNpcRegistry:
    def get_npc(self, npc_id):
        return {"id": npc_id, "name": npc_id, "region": "东部"}


def test_tick_generates_npc_proactive_queue():
    pool = EventPool()
    tm = WorldTickManager(pool)
    campaign = make_campaign(cycle=1)
    campaign["npc_memory"] = {
        "NPC-001": [
            {
                "player_id": "PLAYER-A",
                "importance": 0.9,
                "impression": "positive",
                "tags": ["救助", "信任"],
            }
        ]
    }
    campaign["npc_action_cooldown"] = {}
    campaign["npc_action_log"] = []
    campaign["npc_world_queue"] = []
    profiles = {
        "PLAYER-A": {"IDENTITY_STATE": {"region": "东部"}}
    }

    result = tm.tick(
        "npc_g1",
        campaign,
        [],
        world_state={"GLOBAL": {}, "RESOURCE": {}, "REGION": {}, "FACTION_STATE": {}},
        player_profiles=profiles,
        npc_registry=StubNpcRegistry(),
    )

    assert result["npc_proactive"]
    assert campaign["npc_world_queue"]
    assert campaign["npc_world_queue"][0]["status"] == "pending"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python astrbot_plugin_donghuang/tools/test_world_tick.py`
Expected: FAIL because `tick()` does not accept `player_profiles` / `npc_registry` or does not write queue

- [ ] **Step 3: Write minimal implementation**

```python
try:
    from .npc_action_scheduler import NPCActionScheduler
except ImportError:
    from npc_action_scheduler import NPCActionScheduler


class WorldTickManager:
    def __init__(self, event_pool: EventPool, factions: Optional[Dict[str, Any]] = None):
        ...
        self.npc_action_scheduler = NPCActionScheduler()

    def _ensure_npc_world_queue(self, campaign: Dict[str, Any]) -> List[Dict[str, Any]]:
        return campaign.setdefault("npc_world_queue", [])
```

- [ ] **Step 4: Extend tick signature and queue behavior**

```python
def tick(
    self,
    group_id: str,
    campaign: Dict[str, Any],
    event_log: List[Dict[str, Any]],
    world_state: Optional[Dict[str, Any]] = None,
    player_profiles: Optional[Dict[str, Any]] = None,
    npc_registry: Any = None,
) -> Dict[str, Any]:
    ...
    result["npc_proactive"] = []
    if world_state is not None and player_profiles is not None:
        npc_candidates = self.npc_action_scheduler.check_npc_actions(
            group_id=group_id,
            world_state=world_state,
            player_profiles=player_profiles,
            npc_registry=npc_registry,
            npc_memory=campaign.get("npc_memory", {}),
            campaign=campaign,
        )
        result["npc_proactive"] = npc_candidates
        queue = self._ensure_npc_world_queue(campaign)
        for item in npc_candidates:
            queue.append({
                "npc_id": item["npc_id"],
                "action": item["action"],
                "player_id": item["player_id"],
                "priority": item["priority"],
                "hint": item["hint"],
                "source_cycle": campaign["cycle"],
                "source_tick": campaign["world_clock"]["tick_count"],
                "status": "pending",
            })
```

- [ ] **Step 5: Pass player and NPC context from main.py**

```python
tick_result = self.tick_manager.tick(
    group_id=group_id,
    campaign=campaign,
    event_log=self.event_log.setdefault(group_id, []),
    world_state=self.world_state[group_id],
    player_profiles=self.player_profiles.get(group_id, {}),
    npc_registry=self.npc_registry,
)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `python astrbot_plugin_donghuang/tools/test_world_tick.py`
Expected: NPC proactive test PASS without breaking existing tick tests

- [ ] **Step 7: Commit**

```bash
git add astrbot_plugin_donghuang/world_tick.py astrbot_plugin_donghuang/main.py astrbot_plugin_donghuang/tools/test_world_tick.py
git commit -m "feat: queue npc proactive actions during world tick"
```

### Task 3: 增加 tick_ledger 与 main.py 旧档兼容初始化

**Files:**
- Modify: `astrbot_plugin_donghuang/world_tick.py`
- Modify: `astrbot_plugin_donghuang/main.py`
- Test: `astrbot_plugin_donghuang/tools/test_tick_scheduler.py`
- Test: `astrbot_plugin_donghuang/tools/test_world_tick.py`

**Interfaces:**
- Produces: `campaign["tick_ledger"]`
- Produces: `campaign["tick_ledger"]["last_tick_summary"]`
- Produces: `main.py` group init compatibility via `setdefault`

- [ ] **Step 1: Write the failing test**

```python
def test_tick_records_tick_ledger_summary():
    pool = EventPool()
    tm = WorldTickManager(pool)
    campaign = make_campaign(cycle=1)

    result = tm.tick("ledger_g1", campaign, [], world_state={"GLOBAL": {}, "RESOURCE": {}, "REGION": {}, "FACTION_STATE": {}})

    assert "tick_ledger" in campaign
    summary = campaign["tick_ledger"]["last_tick_summary"]
    assert summary["cycle_after"] == 2
    assert "world_clock_changed" in summary
    assert "faction_changed" in summary
    assert "environment_changed" in summary
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python astrbot_plugin_donghuang/tools/test_world_tick.py`
Expected: FAIL because `tick_ledger` is absent

- [ ] **Step 3: Write minimal implementation**

```python
def _record_tick_ledger(self, campaign: Dict[str, Any], result: Dict[str, Any]) -> None:
    ledger = campaign.setdefault("tick_ledger", {})
    ledger["last_tick_summary"] = {
        "cycle_before": result["cycle_before"],
        "cycle_after": result["cycle_after"],
        "world_clock_changed": result["world_clock"]["changed"],
        "events_progressed": len(result["events_progressed"]),
        "stage_changed": len(result["stage_changed"]),
        "archived": len(result["archived"]),
        "npc_candidates": len(result.get("npc_proactive", [])),
        "faction_changed": len(result["evolution"].get("faction_changed", [])),
        "environment_changed": len(result["evolution"].get("environment_changed", [])),
        "triggered": len(result.get("triggered", [])),
    }
```

- [ ] **Step 4: Call ledger recording before returning from tick**

```python
self._record_tick_ledger(campaign, result)
return result
```

- [ ] **Step 5: Add old-save compatibility in main.py**

```python
self.campaign[group_id].setdefault("tick_state", {
    "last_tick_time": 0.0,
    "last_tick_cycle": 0,
    "tick_count": 0,
})
self.campaign[group_id].setdefault("world_clock", {
    "tick_count": 0,
    "world_day": 1,
    "time_phase": "子夜",
    "season": "春",
    "calendar_label": "东荒历1年春1日子夜",
})
self.campaign[group_id].setdefault("tick_ledger", {})
self.campaign[group_id].setdefault("npc_world_queue", [])
```

- [ ] **Step 6: Run tests to verify it passes**

Run: `python astrbot_plugin_donghuang/tools/test_world_tick.py`
Expected: ledger tests PASS

Run: `python astrbot_plugin_donghuang/tools/test_tick_scheduler.py`
Expected: scheduler compatibility tests still PASS

- [ ] **Step 7: Commit**

```bash
git add astrbot_plugin_donghuang/world_tick.py astrbot_plugin_donghuang/main.py astrbot_plugin_donghuang/tools/test_world_tick.py astrbot_plugin_donghuang/tools/test_tick_scheduler.py
git commit -m "feat: persist tick ledger compatibility state"
```

### Task 4: 补 rollback 与多 group 测试，验证第一阶段不会破坏恢复能力

**Files:**
- Modify: `astrbot_plugin_donghuang/tools/test_world_tick.py`
- Modify: `astrbot_plugin_donghuang/tools/test_rollback_recovery.py`

**Interfaces:**
- Consumes: snapshot structure from `main.py._snapshot_group_state`
- Produces: tests proving `world_clock` / `npc_world_queue` / `tick_ledger` are restored after rollback

- [ ] **Step 1: Write the failing rollback test**

```python
def test_rollback_restores_tick_phase_state():
    pool = EventPool()
    tm = WorldTickManager(pool)
    group_id = "rollback_tick_g1"
    campaign = make_campaign(cycle=3)
    campaign["npc_world_queue"] = []
    campaign["tick_ledger"] = {}
    event_log = []
    world_state = {"GLOBAL": {}, "RESOURCE": {}, "REGION": {}, "FACTION_STATE": {}}

    snapshot = {
        "campaign": json.loads(json.dumps(campaign)),
        "event_pool": json.loads(json.dumps(pool.dump(group_id))),
        "event_log": json.loads(json.dumps(event_log)),
    }

    tm.tick(group_id, campaign, event_log, world_state=world_state)
    assert "world_clock" in campaign

    campaign.clear()
    campaign.update(snapshot["campaign"])
    event_log.clear()
    event_log.extend(snapshot["event_log"])
    pool.clear(group_id)
    pool.load(group_id, snapshot["event_pool"])

    assert "world_clock" not in campaign
    assert campaign.get("npc_world_queue") is None
```

- [ ] **Step 2: Replace the weak rollback assertion with a real restored-state check**

```python
def test_rollback_restores_tick_phase_state():
    ...
    pre_snapshot = {
        "campaign": json.loads(json.dumps(campaign)),
        "event_pool": json.loads(json.dumps(pool.dump(group_id))),
        "event_log": json.loads(json.dumps(event_log)),
    }

    tm.tick(group_id, campaign, event_log, world_state=world_state)

    mutated_clock = json.loads(json.dumps(campaign["world_clock"]))
    mutated_ledger = json.loads(json.dumps(campaign["tick_ledger"]))

    campaign.clear()
    campaign.update(pre_snapshot["campaign"])
    event_log.clear()
    event_log.extend(pre_snapshot["event_log"])
    pool.clear(group_id)
    if pre_snapshot["event_pool"]:
        pool.load(group_id, pre_snapshot["event_pool"])

    assert campaign.get("world_clock") is None
    assert campaign.get("tick_ledger") == {}
    assert campaign.get("npc_world_queue") == []
    assert mutated_clock["tick_count"] == 1
    assert "last_tick_summary" in mutated_ledger
```

- [ ] **Step 3: Add multi-group isolation test for world clock and npc queue**

```python
def test_multi_group_isolation_for_tick_state():
    pool = EventPool()
    tm = WorldTickManager(pool)
    c1 = make_campaign(cycle=1)
    c2 = make_campaign(cycle=10)
    w1 = {"GLOBAL": {}, "RESOURCE": {}, "REGION": {}, "FACTION_STATE": {}}
    w2 = {"GLOBAL": {}, "RESOURCE": {}, "REGION": {}, "FACTION_STATE": {}}

    tm.tick("iso_A", c1, [], world_state=w1)
    assert c1["world_clock"]["tick_count"] == 1
    assert "world_clock" not in c2

    tm.tick("iso_B", c2, [], world_state=w2)
    assert c2["world_clock"]["tick_count"] == 1
    assert c1["cycle"] == 2
    assert c2["cycle"] == 11
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python astrbot_plugin_donghuang/tools/test_world_tick.py`
Expected: PASS with rollback and multi-group assertions

Run: `python astrbot_plugin_donghuang/tools/test_rollback_recovery.py`
Expected: PASS without snapshot compatibility regression

- [ ] **Step 5: Commit**

```bash
git add astrbot_plugin_donghuang/tools/test_world_tick.py astrbot_plugin_donghuang/tools/test_rollback_recovery.py
git commit -m "test: cover world tick rollback and isolation state"
```

### Task 5: 验证第一阶段结果并补文档说明

**Files:**
- Modify: `astrbot_plugin_donghuang/README.md`
- Modify: `astrbot_plugin_donghuang/使用说明.md`
- Modify: `docs/superpowers/specs/2026-07-08-long-b-world-life-design.md`

**Interfaces:**
- Consumes: implemented first-phase behavior
- Produces: updated developer/user docs for world tick behavior

- [ ] **Step 1: Write the doc delta**

```markdown
新增说明：
- 世界 Tick 现在会推进世界时钟
- Tick 会记录最近一次世界运行摘要
- NPC 主动行为会进入待处理队列，不直接修改世界
- rollback 会恢复这些运行态字段
```

- [ ] **Step 2: Update developer README**

Run edit in:
- `astrbot_plugin_donghuang/README.md`

Expected content:
- 第一阶段世界 Tick 数据结构说明
- `world_clock` / `tick_ledger` / `npc_world_queue` 的持久化位置

- [ ] **Step 3: Update user doc**

Run edit in:
- `astrbot_plugin_donghuang/使用说明.md`

Expected content:
- 玩家可感知的表现：世界时间推进、世界动态更稳定
- 强调 NPC 主动行为仍然受系统控制，不会直接篡改状态

- [ ] **Step 4: Run verification commands**

Run: `python astrbot_plugin_donghuang/tools/test_tick_scheduler.py`
Expected: PASS

Run: `python astrbot_plugin_donghuang/tools/test_world_tick.py`
Expected: PASS

Run: `python astrbot_plugin_donghuang/tools/test_rollback_recovery.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add astrbot_plugin_donghuang/README.md astrbot_plugin_donghuang/使用说明.md docs/superpowers/specs/2026-07-08-long-b-world-life-design.md
git commit -m "docs: describe phase1 world tick lifecycle"
```

## Self-Review

### Spec coverage

- 第一阶段 `WorldTickManager` 升级：Task 1-4 覆盖
- 时间推进：Task 1 覆盖
- NPC 行动接入：Task 2 覆盖
- 势力变化、环境变化显式化：Task 3 通过 ledger 和主流程结果覆盖
- 可保存、可恢复、可测试：Task 3-5 覆盖
- rollback 测试、多 group 测试：Task 4 覆盖

### Placeholder scan

- 无 `TODO` / `TBD`
- 每个任务都有具体文件、接口、测试命令

### Type consistency

- 新字段统一挂在 `campaign[group_id]`
- `tick()` 新增参数统一命名为 `player_profiles` 与 `npc_registry`
- `result["world_clock"]` / `result["npc_proactive"]` / `campaign["npc_world_queue"]` 命名前后一致

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-08-long-b-phase1-worldtick.md`. Two execution options:

1. Subagent-Driven (recommended) - I dispatch a fresh subagent per task, review between tasks, fast iteration

2. Inline Execution - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
