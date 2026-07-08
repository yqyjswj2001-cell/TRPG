# DEPENDENCY_MAP.md — 模块依赖检查

审计日期：2026-07-08（C-0 任务第五节）
方法：对仓库内全部 `astrbot_plugin_donghuang/*.py` 做 `import` 关系静态
提取（含模块顶层 `from .xxx import` / `from xxx import` 两种写法，以及
函数体内的延迟导入），手工核对是否成环、是否有重复实现、是否有明显
废弃 import。

**结论先行：**
- **未发现循环依赖。** 整个依赖图可以画成一张有向无环图（DAG），分层
  清晰（见第 1 节）。
- **发现一条新的"未接线子系统"，比孤儿模块审计阶段掌握的范围更大**——
  审计过程中这个仓库同一天内新增了 `cultivation_technique.py`、
  `spiritual_root.py`、`breakthrough_manager.py`、`cultivation_ability.py`
  四个文件，跟已经在 `ORPHAN_MODULE_AUDIT.md` 里记录过的
  `cultivation_state.py` 组成一条完整的 "LONG-A" 五阶段修炼子系统开发链，
  互相之间没有循环依赖，但**整条链没有一个文件被 main.py 或任何已接入
  运行时的模块引用**（见第 3 节）。已同步更新 `ORPHAN_MODULE_AUDIT.md`。
- **重复实现**：确认一处（`main.py` 自带的境界/修炼逻辑 vs
  `cultivation_state.py`/`cultivation_technique.py`/`spiritual_root.py`
  这条新链），性质是"新旧两代设计并存、旧的仍在跑"，不是意外重复代码。
- **疑似废弃 import**：用一个基于 AST 的粗筛脚本扫了一遍未使用的顶层
  import（第 4 节），有信号但噪音也不低，已标注哪些可信、哪些需要人工
  复核，不建议直接照单清理。

---

## 1. 依赖分层图（自底向上，箭头表示"上层 import 下层"）

```
Layer 0（纯叶子，只依赖标准库/dataclass）
  player_action.py
  event_outcome.py
  npc_relationship.py
  world_event_pool.py（EventPool/ActiveEvent/EventStage/EventCategory 等定义本体）
  world_environment.py
  asset_loader.py
  npc_memory.py
  bazi.py / name_data.py / weather_data.py / background_data.py /
    affliction_data.py / talent_data.py（纯数据表/计算，互不依赖）
  player_appearance.py / appearance_modifier.py
  cultivation_state.py（孤立子系统 L0，见第3节）
  cultivation_technique.py（孤立子系统 L0，见第3节）
  spiritual_root.py（孤立子系统 L0，见第3节）
  cultivation_ability.py（孤立子系统 L0，见第3节，且连子系统内部都还没人 import 它）
  npc_perception.py（孤立子系统，B-8）
  npc_attribute_roller.py（一次性生成工具，非运行时依赖）

Layer 1（依赖 L0）
  npc_behavior.py            → npc_relationship
  npc_registry.py            → asset_loader
  npc_context.py             → npc_relationship, npc_memory
  npc_memory_manager.py      → npc_memory
  npc_interaction.py         → npc_behavior, npc_relationship
  npc_action_generator.py    → npc_behavior, npc_relationship
  player_action_parser.py    → player_action
  player_action_resolver.py  → player_action, event_outcome
  outcome_applier.py         → event_outcome
  event_outcome_resolver.py  → event_outcome
  world_event_trigger.py     → world_event_pool
  world_chain_manager.py     → world_event_pool
  faction_ai_manager.py      → world_event_pool
  world_environment_manager.py → world_environment
  world_context.py           → asset_loader（+ 延迟 import world_environment/npc_behavior/npc_relationship）
  world_news.py              → asset_loader
  breakthrough_manager.py    → cultivation_state, cultivation_technique, spiritual_root（孤立子系统 L1）

Layer 2（依赖 L1）
  npc_interaction_executor.py → npc_interaction, npc_behavior, event_outcome, npc_memory
  npc_action_scheduler.py     → npc_behavior, npc_relationship, npc_action_generator, npc_event_trigger
  world_evolution.py         → world_environment_manager（延迟 import）

Layer 3（依赖 L2）
  world_tick.py → world_event_pool, world_evolution, world_event_trigger,
                  world_chain_manager, event_outcome, event_outcome_resolver,
                  outcome_applier, npc_action_scheduler, faction_ai_manager

Layer 4（顶层入口）
  main.py → bazi, world_context, world_news, world_event_pool, world_evolution,
            world_tick, world_tick_scheduler, player_action_parser,
            player_action_resolver, outcome_applier, player_appearance,
            npc_memory, npc_memory_manager, npc_context, npc_relationship,
            npc_interaction_executor, npc_registry, npc_behavior,
            npc_event_trigger, npc_action_scheduler, world_environment,
            world_environment_manager, asset_loader, talent_data, name_data,
            background_data, affliction_data, weather_data
```

**核心模块重点关系（任务要求特别关注的五个）：**

- `main.py` 是唯一顶层入口，不被任何模块反向 import（符合预期，AstrBot
  插件入口本来就不该被别的模块依赖）。
- `WorldTick`（`world_tick.py`）是 Layer 3 里唯一一个把 `EventPool`、
  `WorldEvolutionManager`、`OutcomeApplier`、`EventOutcomeResolver`、
  `NPCActionScheduler`、`FactionAIManager` 全部串起来的编排点——它比
  `main.py` 更接近"世界模拟内核"的角色，`main.py` 只是把它当一个子系统
  调用。
- `WorldContext`（`world_context.py`）只依赖 `asset_loader` 和（延迟）
  `world_environment`/`npc_behavior`/`npc_relationship`，本身不依赖
  `EventPool`/`OutcomeApplier`——它是纯粹的"读取/组装展示层"，不参与
  状态写入，边界很干净。
- `EventPool`（`world_event_pool.py`）是 Layer 0，被 `world_event_trigger`/
  `world_chain_manager`/`faction_ai_manager`/`world_tick` 共同依赖，是
  事实上的"事件系统单一数据源"，没有第二个模块定义等价的事件池结构。
- `OutcomeApplier`（`outcome_applier.py`）只依赖 `event_outcome.py`，
  被 `main.py`（STATE_DELTA 落地）和 `world_tick.py`（world tick 结果
  落地）两条路径共用——这也印证了 `SYSTEM_ARCHITECTURE.md` 第2节提到的
  "两条 outcome 结算路径共用同一个落地执行器，但上游结构不统一"这个
  已知设计现状。

---

## 2. 循环依赖检查

**未发现循环依赖。** 依赖图严格分层（Layer 0 → 4 单向流动），没有出现
"A import B，B（直接或间接）又 import A"的情况。这对一个 5400+ 行的
`main.py` 加上 45+ 个支撑模块的项目来说是一个健康信号——说明模块拆分
虽然细碎，但边界意识是有的，没有出现"互相缠绕"的典型坏味道。

延迟导入（函数体内 import，而不是文件顶部）出现在多处（如
`world_context.py`、`npc_perception.py`、`main.py` 部分方法内），
这是一种常见的"避免潜在循环 / 按需加载"手法，本次检查未发现任何一处
延迟导入实际上是在掩盖一个本该在顶部就会报错的真实循环——都是可以
安全提到顶部的，只是保留了现状（未做无必要的改动）。

---

## 3. "LONG-A" 修炼子系统：完整的未接线依赖链

```
cultivation_state.py       （阶段1，叶子，无内部依赖）
        ↑
breakthrough_manager.py    （阶段4）→ 同时依赖 ↓
        ↑                              cultivation_technique.py（阶段2，叶子）
        |                              spiritual_root.py      （阶段3，叶子）
        |
   （没有任何模块 import breakthrough_manager.py）

cultivation_ability.py     （阶段5，叶子，连子系统内部都还没被引用）
```

- 五个文件全部在 `main.py`/`world_tick.py`/`outcome_applier.py` 等任何
  已接入运行时的模块里**零引用**。
- 子系统内部依赖关系正确（`breakthrough_manager.py` 正确地把阶段1/2/3
  串起来），说明这不是几个互不相干的草稿，而是**一条有意设计、正在
  推进中的完整链路**。
- `cultivation_ability.py`（阶段5）目前连子系统内部都还没人引用它，
  是这条链里进度最靠后的一环。
- **跟 `main.py` 现有的 `_REALMS`/`_adjust_cultivation_progress`/
  `_apply_breakthrough` 逻辑是平行的两套实现**（`main.py` 那套更简单，
  没有 `spiritual_root`/`cultivation_technique`/`foundation`/`bottleneck`
  这些概念）。这不算"重复劳动"意义上的坏味道，更像是"重写替代版本
  开发到一半，还没做切换"——切换是产品决策，不是本审计能替开发者
  做的判断。
- **无测试覆盖**：`tools/` 下没有任何测试文件引用这五个文件中的任何
  一个（用 grep 全文确认过）。如果这条链条还要继续往前推进，强烈建议
  尽早补至少纯函数级测试（这些模块基本都是无副作用计算函数 + dataclass，
  测试成本很低），否则等到真正接线那天出错，debug 成本会因为链路已经
  有 5 层而显著放大。

---

## 4. 重复实现 / 疑似废弃 import

### 4.1 重复实现（已确认）
`main.py` 的 `_REALMS`/`_adjust_cultivation_progress`/`_apply_breakthrough`
与"LONG-A"链路是同一个问题域的两套实现——详见第 3 节和
`ORPHAN_MODULE_AUDIT.md` 第 1 节。不在本次处理范围（禁止修改
EventPool/Outcome/Combat/NPC逻辑，这条链目前还没碰到这些边界，但切换
到新系统会实质性改动 `main.py` 的修炼相关代码，属于产品/架构决策）。

### 4.2 疑似废弃 import（AST 粗筛结果，需人工复核，未直接清理）
用一个基于 `ast` 的脚本扫了每个文件顶层 import 的名字是否在文件内被
`ast.Name` 引用过。**这个方法噪音较高**（比如某些名字只在字符串类型
注解、`__all__`、或者只被同名的类属性/参数遮蔽时会误判成"未使用"），
所以这里只列出扫描结果里看起来比较可信、值得人工确认的几条，完整
输出更长，本次不全部照单处理：

- `main.py` 第968行一带：`FLAW_TIERS`、`FLAW_WEIGHTS` 从 `talent_data`
  导入后疑似未直接引用（可能是通过其他聚合变量间接使用，需要人工确认
  再决定是否清理）。
- `main.py` 第205-212行一带：`NPCMemory`、`create_memory`、
  `action_to_memory_params`、`NPCBehaviorProfile`、`clamp_probability`、
  `create_npc_interaction_hint` 疑似未直接引用——**这几个大概率是假
  阳性**，因为它们的类型经常只出现在类型注解或者被间接调用链使用，
  本次没有逐一跟踪确认，标记为"低置信度，需要人工用 IDE 的
  'find usages' 复核"，不建议直接删。
- `outcome_applier.py`：`copy` 模块导入但未见直接 `copy.xxx()` 调用
  （用的是 `_merge_dict`/`_merge_dict_no_clamp` 自己实现的深合并逻辑，
  值得确认 `copy` 是否已经是历史遗留）。
- `world_context.py`：`json` 导入但未见直接调用——如果确认属实，
  是个成本很低的清理项。

**本次不直接删除任何 import**（禁止事项要求"只允许审计"），以上作为
下一轮"代码卫生"任务的候选清单，处理前建议用比这个粗糙脚本更可靠的
工具（比如真正装上 `pyflakes`/`ruff` 跑一遍，本机环境目前没装，
执行 `py -m pyflakes .` 会报 `No module named pyflakes`）。
