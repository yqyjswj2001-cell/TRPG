# LONG-B 世界生命模拟系统设计

## 1. 目标

LONG-B 的目标不是重写世界系统，而是在 `astrbot_plugin_donghuang` 现有框架上，把东荒世界从“主要由玩家推动”升级为“世界可低频、自主、可回滚地运行”。

必须遵守的硬约束：

- 复用现有 `WorldTick`、`WorldEvolution`、`WorldEnvironment`、`EventPool`、`WorldEventTrigger`、`WorldNews`、`NPCActionScheduler`、`NPCMemory`
- 不重写 `WorldState`
- 不重写 `EventPool`
- 不破坏 `/dh rollback`
- 所有变化必须代码控制，不能让 AI 直接改世界
- 所有新增系统必须可保存、可恢复、可测试

## 2. 当前代码基线

### 2.1 已存在的主干

- `world_tick.py`
  - 已负责 `cycle += 1`
  - 已推进 `EventPool` 活跃事件进度
  - 已对结束事件生成 `Outcome` 并通过 `OutcomeApplier` 写回状态
  - 已调用 `WorldEvolutionManager`
  - 已调用 `WorldEventTrigger`
  - 已预留 `npc_proactive` 字段，但仍是空列表
- `world_tick_scheduler.py`
  - 已提供低频 Tick 触发门控
  - 已持久化 `tick_state`
  - 已提供 `reset()` 供 rollback 后恢复
- `world_evolution.py`
  - 已覆盖天气、灵气流向、资源、势力运行态、区域环境
  - 已具备 `ensure_faction_state()`
- `npc_action_scheduler.py`
  - 已能基于记忆、关系、行为倾向生成 NPC 主动行为候选
  - 明确不直接修改 `world_state / EventPool / EVENT_LOG`
- `npc_action_generator.py`
  - 目前还是“提示级”动作生成，目标较窄，尚不足以承载“生存/修炼/交易/探索/复仇/结交”
- `world_news.py`
  - 已支持从 `EventPool` 和世界状态生成新闻
  - 仍有较大比例依赖模板随机补全
- `main.py`
  - 现有快照覆盖 `world_state / player_profiles / event_log / campaign / event_pool`
  - rollback 已按群完整恢复上述结构

### 2.2 现阶段缺口

- `WorldTickManager` 的“时间推进”还只是 `cycle` 自增，没有世界时钟语义
- NPC 主动行为还没真正进入 Tick 主流程
- NPC 行动结果目前主要是“提示”，不是标准化 `Outcome` / `Event` 生产线
- 势力演化已有运行态，但缺少长期战略层字段
- 事件生态仍以单事件为主，缺少因果链结构
- 新闻系统虽能引用状态，但尚未统一绑定“来源对象”
- 历史系统尚不存在

## 3. 总体设计原则

### 3.1 不新增平行真相源

所有 LONG-B 数据必须附着在现有可快照对象内：

- 世界级状态放入 `world_state[group_id]`
- 团务运行态放入 `campaign[group_id]`
- 事件继续留在 `EventPool`
- 审计与历史记录继续基于 `event_log`，新增长期历史使用独立字段挂在 `world_state`

这样可以直接继承：

- 现有 JSON 存档
- 现有初始化逻辑
- 现有 `/dh rollback`
- 现有多 group 隔离

### 3.2 Tick 只编排，不越权

`WorldTickManager` 继续做“编排层”，不直接在 Tick 里硬编码大量世界变更规则：

- 世界自然变化仍由 `WorldEvolutionManager` 执行
- NPC 自主行动必须只产出 `Outcome` 或 `Event`
- 势力变化优先通过 `WorldEvolutionManager` 和 `EventPool` 触发
- 新闻只读状态，不写状态

### 3.3 分层推进

LONG-B 按三层递进：

1. `Tick orchestration`
   - 让世界自主运行的节拍成立
2. `State producers`
   - NPC、势力、环境、事件链生成可审计变化
3. `Narrative consumers`
   - 新闻、历史、玩家体验读取世界状态并叙事化

## 4. LONG-B 分阶段实现映射

### 阶段一：WorldTick 升级

目标：

- 为 Tick 增加真正的世界时间语义
- 接入 NPC 主动行为检查
- 稳定串联势力变化、环境变化、事件触发
- 保持低频、可控、可回滚

落点：

- `world_tick.py`
- `world_tick_scheduler.py`
- `main.py`
- 新增 `world_clock` 或等价轻量结构

### 阶段二：NPC 自主生命

目标：

- 扩展 `npc_action_generator`
- 让 NPC 目标由关系、人格、环境、事件共同决定
- 输出标准化 `Outcome` 或 `Event`

落点：

- `npc_action_generator.py`
- `npc_action_scheduler.py`
- 新增 NPC 目标评估与结果封装模块

### 阶段三：势力演化

目标：

- 在 `FACTION_STATE` 基础上增加声望、资源、战略目标、内部变化

落点：

- `world_evolution.py`
- `world_state["FACTION_STATE"]`

### 阶段四：世界事件生态

目标：

- 在不重写 `EventPool` 的前提下，给事件增加因果链元数据

落点：

- `world_event_pool.py`
- `world_event_trigger.py`
- 事件 outcome / archive 结构

### 阶段五：新闻生态

目标：

- 新闻来源必须可追溯到事件、NPC、势力、环境状态

落点：

- `world_news.py`
- `campaign[group_id]["news_log"]` 或 `WorldNewsBuilder` 现有日志

### 阶段六：区域生态

目标：

- 统一区域的资源、天气、危险、势力、NPC 差异

落点：

- `world_state["REGION"]`
- `world_environment_manager.py`
- NPC / faction / event 查询上下文

### 阶段七：历史系统

目标：

- 记录重大事件、势力兴衰、传奇人物

落点：

- 新增 `world_history.py`
- `world_state[group_id]["HISTORY"]`

### 阶段八：世界观自演化

目标：

- 让状态变化反向影响事件、NPC、新闻、玩家体验
- 但仍只允许代码控制，不允许 AI 直接写世界

落点：

- Tick 编排层
- 状态生产层的联动规则
- Prompt 注入只读化

## 5. 第一阶段详细设计：WorldTick 升级

### 5.1 设计目标

第一阶段不追求完整生命模拟，只建立一个可扩展的世界自主运行骨架。

成功标准：

- 每次 Tick 不只是 `cycle+1`，还会推进一个受控世界时钟
- Tick 结果中包含明确的子步骤产物
- NPC 主动行为进入 Tick 流程，但仍不允许直接改世界
- 所有新增字段天然被现有 snapshot 覆盖

### 5.2 新增数据结构

#### `campaign[group_id]["world_clock"]`

建议结构：

```python
{
    "tick_count": 0,
    "world_day": 1,
    "time_phase": "子夜",   # 子夜 / 清晨 / 白昼 / 黄昏
    "season": "春",
    "calendar_label": "东荒历1年春1日子夜"
}
```

用途：

- 给世界变化提供时间语义
- 给新闻、历史、NPC 行动提供上下文
- 不替代 `cycle`，而是建立在 `cycle` 之上

#### `campaign[group_id]["tick_ledger"]`

建议结构：

```python
{
    "last_tick_summary": {
        "world_clock_changed": True,
        "npc_candidates": 2,
        "npc_events_created": 1,
        "faction_changed": 3,
        "environment_changed": 2
    }
}
```

用途：

- 方便调试与测试
- 不承担唯一状态职责

#### `campaign[group_id]["npc_world_queue"]`

建议结构：

```python
[
    {
        "npc_id": "NPC-001",
        "action": "offer_information",
        "player_id": "PLAYER-A",
        "priority": "medium",
        "source_cycle": 42,
        "source_tick": 8,
        "status": "pending"
    }
]
```

用途：

- 把 NPC 主动行为从“即时提示”升级为“可控待处理项”
- 仍不直接写 `world_state`

### 5.3 Tick 主流程改造

建议将 `WorldTickManager.tick()` 明确为七步：

1. 推进 `cycle`
2. 推进 `world_clock`
3. 推进活跃事件进度
4. 对结束事件产出 `Outcome` 并归档
5. 执行 `WorldEvolution`
6. 执行 `NPCActionScheduler`，只产出候选行为 / 待处理项
7. 将世界变化送入 `WorldEventTrigger`

其中关键变化如下。

#### A. 世界时钟推进

新增私有方法：

- `_advance_world_clock(campaign) -> dict`

职责：

- 若无 `world_clock` 则初始化
- 每个 Tick 推进一个 `time_phase`
- `time_phase` 轮转一周后 `world_day += 1`
- 每若干天推进季节
- 返回 `from/to` 差异供测试与输出

这样避免直接依赖真实时间，仍保持 deterministic enough 的代码控制。

#### B. NPC 行为接入 Tick

现有 `world_tick.py` 里的 `npc_proactive = []` 应升级为真实结果：

- 从 `campaign[group_id]["npc_memory"]` 读取 NPC 记忆
- 调用 `NPCActionScheduler.check_npc_actions()`
- 把结果写入 `result["npc_proactive"]`
- 同时写入 `campaign["npc_world_queue"]`

重要约束：

- 不在 Tick 中直接执行 NPC 行为
- 不在 Tick 中直接改玩家属性
- 不在 Tick 中直接写 `EventPool`，除非动作已被升级成标准 `Event`

#### C. 势力 / 环境变化结果显式透出

`WorldEvolutionManager.evolve()` 已返回：

- `faction_changed`
- `environment_changed`

第一阶段不重写其逻辑，只要求：

- `WorldTickManager.tick()` 结构化保留这些结果
- `main.py` 的 Tick 输出摘要可以展示这些变化
- 测试覆盖这些结果在多 group 下隔离

### 5.4 与 rollback 的兼容方式

第一阶段新增数据只放在：

- `campaign[group_id]["world_clock"]`
- `campaign[group_id]["tick_ledger"]`
- `campaign[group_id]["npc_world_queue"]`

因为 `_snapshot_group_state()` 已整体深拷贝 `campaign[group_id]`，所以：

- 不需要新增 snapshot 入口
- 不需要修改 rollback 核心逻辑
- 只需要补测试验证 rollback 后这些字段恢复

### 5.5 与存档的兼容方式

需要在 `main.py` 的群初始化逻辑里补旧档兼容：

- `world_clock`
- `tick_ledger`
- `npc_world_queue`

兼容原则：

- 没有就补默认值
- 有但字段不全就 `setdefault`
- 不迁移旧结构，不引入一次性升级脚本

## 6. 后续阶段的结构预埋

### 6.1 NPC 自主生命如何不破坏现有系统

后续 NPC 系统不应直接把“复仇/交易/探索”等动作写死在 `scheduler` 内。

推荐拆分：

- `npc_action_generator.py`
  - 负责目标与动作候选计算
- `npc_action_scheduler.py`
  - 负责时机、冷却、筛选
- 新增 `npc_world_outcome.py`
  - 把候选行为封装为 `Outcome` 或 `EventDraft`

这样第二阶段能扩展目标模型，但不会把 Tick 编排层变成巨型规则文件。

### 6.2 事件链如何在不重写 EventPool 前提下实现

推荐仅给事件增加元数据，不改 `EventPool` 主体行为模型：

```python
{
    "cause_event_id": "E000123",
    "chain_id": "CHAIN-0007",
    "chain_role": "cause",   # cause / escalation / consequence
    "source_system": "world_tick"
}
```

这样：

- 旧事件仍可正常使用
- 新事件链只是在 archive、news、history 层增强可读性

### 6.3 历史系统如何避免重复记账

`world_history` 不应重复保存整条 `event_log`。

建议只记录“历史摘要条目”：

```python
{
    "history_id": "H00001",
    "cycle": 120,
    "calendar_label": "东荒历1年夏12日黄昏",
    "type": "faction_rise",
    "title": "青岚宗吞并西岭坊市",
    "related_event_ids": ["E001201", "E001202"],
    "region": "西部",
    "actors": ["CULT-03"]
}
```

## 7. 测试设计

LONG-B 每个模块都要求：

- 单元测试
- 存档测试
- rollback 测试
- 多 group 测试

第一阶段至少补以下测试：

### 7.1 WorldTick 单元测试

- `world_clock` 初始化与推进
- `time_phase` 轮转
- `npc_proactive` 非空时正确写入结果
- `npc_world_queue` 正确落入 `campaign`

### 7.2 存档测试

- 新字段在 `_save_campaign()` 后可重载
- 旧存档缺少这些字段时可自动补全

### 7.3 rollback 测试

- Tick 后的 `world_clock`
- `npc_world_queue`
- `tick_ledger`

都能在 snapshot 恢复后回到 Tick 前状态

### 7.4 多 group 测试

- A 群推进 Tick 不影响 B 群世界时钟
- A 群 NPC 队列不污染 B 群

## 8. 推荐实施顺序

推荐先做第一阶段，拆成四个小步：

1. 新增 `world_clock` 默认结构与推进函数
2. 将 `world_clock` 挂入 `WorldTickManager.tick()` 返回值和 `campaign`
3. 将 `NPCActionScheduler` 真正接入 Tick，落地 `npc_world_queue`
4. 为新增字段补测试、存档兼容、rollback 测试

完成后再进入第二阶段，而不是一口气同时改 NPC / 势力 / 新闻 / 历史。

## 9. 本轮结论

当前代码基础足够支撑 LONG-B，但正确路线不是“推翻重做”，而是：

- 以 `WorldTickManager` 为统一编排入口
- 以 `campaign` / `world_state` 为唯一持久化容器
- 以 `Outcome` / `Event` 为唯一可审计世界变化出口
- 以现有 snapshot 体系兜住 rollback

第一阶段的核心就是把“世界时钟 + NPC 主动行为接入 + 结果显式化”做扎实。只要这一层建立起来，后面的事件链、新闻来源、历史沉淀都能自然叠加。
