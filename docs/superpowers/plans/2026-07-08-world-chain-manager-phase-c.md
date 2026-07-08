# WorldChainManager Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Phase C `WorldChainManager` so Donghuang can persist, delay, consume, expire, and depth-limit world causal chains without bypassing `EventPool`, `OutcomeApplier`, `WorldTick`, or rollback.

**Architecture:** Add a dedicated `WorldChainManager` module that stores chain candidates in `campaign["world_history"]`, uses `WorldTickManager` as the only time driver, and converts eligible pending chains into formal `EventPool` events on later ticks. `WorldTickManager` will delegate chain creation/consumption/expiry to the manager, while `EventPool` remains the only formal event entry.

**Tech Stack:** Python, existing `EventPool`, `WorldTickManager`, `world_history`, snapshot/rollback through existing campaign + event pool persistence.

## Global Constraints

- Do not rewrite `WorldState`.
- Do not rewrite `EventPool`.
- `EventPool` remains the only formal event entry.
- `OutcomeApplier` remains the only state mutation entry.
- `WorldTick` remains the world time entry.
- Snapshot/Rollback must remain valid.
- No second character/event/state system.
- All new data must be persistent through existing campaign/event snapshots.
- All behavior must support multi-group isolation.
- Only implement Phase C in this slice; do not pull in later phases.

---

### Task 1: Add `WorldChainManager` module

**Files:**
- Create: `astrbot_plugin_donghuang/world_chain_manager.py`
- Test: `astrbot_plugin_donghuang/tools/test_world_chain_manager.py`

**Interfaces:**
- Consumes: `EventPool`, `campaign["world_history"]`, `world_clock`, `factions`
- Produces:
  - `WorldChainManager.create_chain_candidates(group_id: str, campaign: Dict[str, Any], environment_changes: List[Dict[str, Any]]) -> List[Dict[str, Any]]`
  - `WorldChainManager.consume_pending_chains(group_id: str, campaign: Dict[str, Any]) -> List[Dict[str, Any]]`
  - `WorldChainManager.expire_pending_chains(campaign: Dict[str, Any]) -> List[Dict[str, Any]]`

- [ ] **Step 1: Write the failing test**

```python
def test_create_chain_candidate_with_required_metadata():
    pool = EventPool()
    factions = {
        "CULT-01": {"code": "CULT-01", "name": "归墟宗", "type": "宗门", "region": "中部"},
        "CULT-02": {"code": "CULT-02", "name": "青岚门", "type": "宗门", "region": "中部"},
    }
    manager = WorldChainManager(pool, factions=factions)
    campaign = {
        "cycle": 12,
        "world_clock": {"tick_count": 8},
        "world_history": [],
    }
    pool.add(group_id="g1", title="中部灵脉异常", category=EventCategory.LEYLINE_RESOURCE.value, region="中部")

    created = manager.create_chain_candidates(
        group_id="g1",
        campaign=campaign,
        environment_changes=[{
            "region": "中部",
            "spiritual_weather": "紊乱",
            "celestial_phenomenon": "血月映空",
            "anomaly_environment": "无",
            "effects": ["灵气逆流"],
        }],
    )

    assert len(created) == 1
    candidate = created[0]
    assert candidate["entry_type"] == "chain_candidate"
    assert candidate["parent_chain_id"] == ""
    assert candidate["chain_depth"] == 1
    assert candidate["cause_category"] == EventCategory.LEYLINE_RESOURCE.value
    assert candidate["source_refs"]
    assert candidate["trigger_conditions"]["requires_environment_change"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python astrbot_plugin_donghuang/tools/test_world_chain_manager.py`
Expected: FAIL with `ImportError` or missing `WorldChainManager`

- [ ] **Step 3: Write minimal implementation**

```python
class WorldChainManager:
    MAX_CHAIN_DEPTH = 3
    CHAIN_TTL_TICKS = 3

    def __init__(self, event_pool, factions=None):
        self.event_pool = event_pool
        self.factions = factions or {}

    def create_chain_candidates(self, group_id, campaign, environment_changes):
        ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python astrbot_plugin_donghuang/tools/test_world_chain_manager.py`
Expected: the metadata creation test passes

- [ ] **Step 5: Commit**

```bash
git add astrbot_plugin_donghuang/world_chain_manager.py astrbot_plugin_donghuang/tools/test_world_chain_manager.py
git commit -m "feat: add world chain manager core"
```

### Task 2: Add chain consumption and expiry safeguards

**Files:**
- Modify: `astrbot_plugin_donghuang/world_chain_manager.py`
- Test: `astrbot_plugin_donghuang/tools/test_world_chain_manager.py`

**Interfaces:**
- Consumes: `chain_candidate` history entries with `status == "pending"`
- Produces:
  - spawned history entries `chain_candidate_spawned`
  - expired history entries `chain_candidate_expired`
  - updated `chain_candidate.status`

- [ ] **Step 1: Write the failing tests**

```python
def test_consume_pending_chain_spawns_formal_event():
    pool = EventPool()
    manager = WorldChainManager(pool, factions={
        "CULT-01": {"code": "CULT-01", "name": "归墟宗", "type": "宗门", "region": "中部"},
        "CULT-02": {"code": "CULT-02", "name": "青岚门", "type": "宗门", "region": "中部"},
    })
    campaign = {
        "cycle": 13,
        "world_clock": {"tick_count": 9},
        "world_history": [{
            "entry_type": "chain_candidate",
            "chain_id": "CHAIN-1",
            "chain_type": "leyline_anomaly_to_faction_conflict",
            "parent_chain_id": "",
            "chain_depth": 1,
            "cause_category": EventCategory.LEYLINE_RESOURCE.value,
            "source_refs": ["event:EP0001", "history:environment_changed:中部:12:8"],
            "trigger_conditions": {"requires_environment_change": True, "requires_leyline_event": True},
            "region": "中部",
            "target_event_category": EventCategory.FACTION_CONFLICT.value,
            "target_event_title": "中部宗门争夺灵脉",
            "status": "pending",
            "created_cycle": 12,
            "created_tick": 8,
        }],
    }

    spawned = manager.consume_pending_chains("g1", campaign)

    assert len(spawned) == 1
    assert campaign["world_history"][0]["status"] == "spawned"
    assert pool.query_by_category("g1", EventCategory.FACTION_CONFLICT.value)


def test_expire_old_pending_chain():
    pool = EventPool()
    manager = WorldChainManager(pool)
    campaign = {
        "cycle": 20,
        "world_clock": {"tick_count": 12},
        "world_history": [{
            "entry_type": "chain_candidate",
            "chain_id": "CHAIN-OLD",
            "chain_type": "leyline_anomaly_to_faction_conflict",
            "parent_chain_id": "",
            "chain_depth": 1,
            "cause_category": EventCategory.LEYLINE_RESOURCE.value,
            "source_refs": ["event:EP0001"],
            "trigger_conditions": {},
            "region": "中部",
            "target_event_category": EventCategory.FACTION_CONFLICT.value,
            "target_event_title": "中部宗门争夺灵脉",
            "status": "pending",
            "created_cycle": 18,
            "created_tick": 1,
        }],
    }

    expired = manager.expire_pending_chains(campaign)

    assert len(expired) == 1
    assert campaign["world_history"][0]["status"] == "expired"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python astrbot_plugin_donghuang/tools/test_world_chain_manager.py`
Expected: FAIL on missing consume/expire behavior

- [ ] **Step 3: Write minimal implementation**

```python
def consume_pending_chains(self, group_id, campaign):
    ...

def expire_pending_chains(self, campaign):
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python astrbot_plugin_donghuang/tools/test_world_chain_manager.py`
Expected: consume and expiry tests pass

- [ ] **Step 5: Commit**

```bash
git add astrbot_plugin_donghuang/world_chain_manager.py astrbot_plugin_donghuang/tools/test_world_chain_manager.py
git commit -m "feat: add chain consume and expiry guards"
```

### Task 3: Add depth-limit and loop-prevention behavior

**Files:**
- Modify: `astrbot_plugin_donghuang/world_chain_manager.py`
- Test: `astrbot_plugin_donghuang/tools/test_world_chain_manager.py`

**Interfaces:**
- Consumes: `parent_chain_id`, `chain_depth`
- Produces: skipped history entries or skipped statuses when depth is above the limit

- [ ] **Step 1: Write the failing test**

```python
def test_prevent_infinite_loop_when_chain_depth_exceeds_limit():
    pool = EventPool()
    manager = WorldChainManager(pool)
    campaign = {
        "cycle": 30,
        "world_clock": {"tick_count": 5},
        "world_history": [],
    }
    pool.add(group_id="g1", title="中部灵脉异常", category=EventCategory.LEYLINE_RESOURCE.value, region="中部")

    created = manager.create_chain_candidates(
        group_id="g1",
        campaign=campaign,
        environment_changes=[{
            "region": "中部",
            "spiritual_weather": "紊乱",
            "celestial_phenomenon": "血月映空",
            "anomaly_environment": "无",
            "effects": [],
            "parent_chain_id": "CHAIN-PARENT",
            "chain_depth": 3,
        }],
    )

    assert created == []
    assert any(entry.get("entry_type") == "chain_candidate_skipped" for entry in campaign["world_history"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python astrbot_plugin_donghuang/tools/test_world_chain_manager.py`
Expected: FAIL because depth limit is not enforced

- [ ] **Step 3: Write minimal implementation**

```python
if parent_depth >= self.MAX_CHAIN_DEPTH:
    history.append({... "entry_type": "chain_candidate_skipped", "skip_reason": "max_depth_reached"})
    continue
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python astrbot_plugin_donghuang/tools/test_world_chain_manager.py`
Expected: PASS with no new pending chain created

- [ ] **Step 5: Commit**

```bash
git add astrbot_plugin_donghuang/world_chain_manager.py astrbot_plugin_donghuang/tools/test_world_chain_manager.py
git commit -m "feat: guard world chains against infinite depth"
```

### Task 4: Integrate `WorldChainManager` into `WorldTickManager`

**Files:**
- Modify: `astrbot_plugin_donghuang/world_tick.py`
- Test: `astrbot_plugin_donghuang/tools/test_world_tick.py`

**Interfaces:**
- Consumes:
  - `WorldChainManager.create_chain_candidates(...)`
  - `WorldChainManager.consume_pending_chains(...)`
  - `WorldChainManager.expire_pending_chains(...)`
- Produces:
  - `result["chain_events_spawned"]`
  - `result["chain_candidates_created"]`
  - history entries created through the manager

- [ ] **Step 1: Write the failing integration tests**

```python
def test_tick_delegates_chain_candidate_creation_and_consumption():
    ...

def test_tick_rollback_restores_chain_history():
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python astrbot_plugin_donghuang/tools/test_world_tick.py`
Expected: FAIL because `WorldTickManager` is still using inline chain logic

- [ ] **Step 3: Write minimal implementation**

```python
from .world_chain_manager import WorldChainManager

self.chain_manager = WorldChainManager(event_pool, factions=factions)
...
created = self.chain_manager.create_chain_candidates(...)
expired = self.chain_manager.expire_pending_chains(campaign)
spawned = self.chain_manager.consume_pending_chains(group_id, campaign)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python astrbot_plugin_donghuang/tools/test_world_tick.py`
Expected: PASS with chain creation and next-tick spawning preserved

- [ ] **Step 5: Commit**

```bash
git add astrbot_plugin_donghuang/world_tick.py astrbot_plugin_donghuang/tools/test_world_tick.py
git commit -m "feat: integrate world chain manager into world tick"
```

### Task 5: Run Phase C regression coverage

**Files:**
- Test: `astrbot_plugin_donghuang/tools/test_world_chain_manager.py`
- Test: `astrbot_plugin_donghuang/tools/test_world_tick.py`
- Test: `astrbot_plugin_donghuang/tools/test_world_news.py`
- Test: `astrbot_plugin_donghuang/tools/test_rollback_recovery.py`
- Test: `astrbot_plugin_donghuang/tools/test_npc_action_scheduler.py`

**Interfaces:**
- Consumes: all chain/tick/news/rollback behaviors
- Produces: regression evidence that Phase C does not break existing systems

- [ ] **Step 1: Run focused Phase C chain tests**

Run: `python astrbot_plugin_donghuang/tools/test_world_chain_manager.py`
Expected: all chain manager tests PASS

- [ ] **Step 2: Run tick integration tests**

Run: `python astrbot_plugin_donghuang/tools/test_world_tick.py`
Expected: all WorldTick tests PASS

- [ ] **Step 3: Run rollback/news/NPC regressions**

Run: `python astrbot_plugin_donghuang/tools/test_world_news.py`
Run: `python astrbot_plugin_donghuang/tools/test_rollback_recovery.py`
Run: `python astrbot_plugin_donghuang/tools/test_npc_action_scheduler.py`
Expected: all PASS

- [ ] **Step 4: Commit regression-proven Phase C slice**

```bash
git add astrbot_plugin_donghuang/world_chain_manager.py astrbot_plugin_donghuang/world_tick.py astrbot_plugin_donghuang/tools/test_world_chain_manager.py astrbot_plugin_donghuang/tools/test_world_tick.py docs/superpowers/plans/2026-07-08-world-chain-manager-phase-c.md
git commit -m "feat: add phase c world chain manager"
```

## Self-Review

- Spec coverage: this plan only covers Phase C and deliberately does not implement D–J.
- Placeholder scan: no TODO/TBD placeholders remain.
- Type consistency: `chain_candidate` uses `parent_chain_id`, `chain_depth`, `cause_category`, `source_refs`, and `trigger_conditions` consistently across manager and tick integration tasks.

