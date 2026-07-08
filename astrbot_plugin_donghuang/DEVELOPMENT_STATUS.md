# DEVELOPMENT_STATUS.md — 开发状态清单

快照时间：**2026-07-08 19:20 左右**（C-1 任务）。

**⚠️ 重要声明：这是一个快照，不是稳定描述。** 审计过程中亲眼看到这个仓库
被并行开发以分钟为单位持续修改——`npc_life_manager.py`、
`world_tick.py`、`main.py`、LONG-A 六个模块的接入，都是在本次审计
进行期间实时发生的（详见 `LONG_A_AUDIT.md`、`NPC_LIFE_AUDIT.md`）。
**读者使用本文档前，应该先用下面"如何验证本文档仍然准确"一节里的命令
重新核实一遍，而不是直接相信表格。**

## 如何验证本文档仍然准确

```
py -m py_compile main.py                      # 确认还能编译
py tools\test_full_regression.py              # 确认回归测试当前通过率
```
再对照下表"关键判定依据"那一列里点出的具体文件/行号，看是否已经变化。

---

## 状态定义

| 状态 | 含义 |
|---|---|
| `DONE` | 功能完整、已接入运行时、测试通过、暂无已知大缺口 |
| `INTEGRATED` | 已接入运行时主线并实际工作，但存在已知的、非阻塞性的缺口或仍在扩展 |
| `PARTIAL` | 只有部分子功能接入/工作，另一部分明确未完成或未接入 |
| `UNCONNECTED` | 代码存在，但完全没有被运行时主线（main.py 命令路径 / world_tick 循环）调用 |
| `EXPERIMENTAL` | 仅接口/占位设计，无实现，或刚起步、正确性未经任何测试验证 |

---

## 系统状态表

| 系统 | 文件位置 | 状态 | 关键判定依据 |
|---|---|---|---|
| 玩家系统（行动解析/结算） | `player_action.py`、`player_action_parser.py`、`player_action_resolver.py` | **INTEGRATED** | `main.py` 顶层 import（[main.py:201-203](main.py:201)），`/dh act` 命令实际调用 |
| 角色外观 | `player_appearance.py`、`appearance_modifier.py` | **INTEGRATED** | `main.py` 角色生成流程调用 `AppearanceGenerator`；旧档 `appearance` 字段有启动时自愈（[main.py:1575](main.py:1575)） |
| 玩家行动结算（Outcome 落地） | `outcome_applier.py`、`event_outcome.py`、`event_outcome_resolver.py` | **INTEGRATED** | 两条路径都在跑：`main.py._apply_state_delta` → `OutcomeApplier`（STATE_DELTA自由文本）；`world_tick.py` → `EventOutcomeResolver`（结构化世界事件）。两条路径共用 `OutcomeApplier`，上游结构不统一（见 `SYSTEM_ARCHITECTURE.md` 第2节） |
| NPC记忆 | `npc_memory.py`、`npc_memory_manager.py` | **DONE** | `main.py` 直接 import 并在多处调用；`npc_life_manager.py` 也复用它写"NPC生命事件记忆"，测试全绿 |
| NPC关系 | `npc_relationship.py` | **DONE** | 被 `npc_behavior`/`npc_context`/`npc_action_generator`/`npc_action_scheduler`/`npc_interaction`/`main.py` 广泛复用，是事实上的单一实现，测试全绿 |
| NPC行为 | `npc_behavior.py` | **DONE** | 同上，广泛复用，测试全绿 |
| NPC主动行为 | `npc_action_scheduler.py`、`npc_action_generator.py`、`npc_event_trigger.py` | **INTEGRATED** | `main.py` 直接 import `NPCActionScheduler`；world_tick 的 `npc_world_queue` 依赖这条链；测试全绿 |
| **NPC生命周期** | `npc_life_manager.py` | **PARTIAL** | `world_tick.py` 已 import 并实例化 `NPCLifeManager`、写入 `result["npc_life_actions"]`（[world_tick.py:78](world_tick.py:78)、[world_tick.py:627-635](world_tick.py:627)）——**已接入，但功能不完整**：本次审计运行时 `test_npc_life_manager.py` 和 `test_world_tick.py` 的"跨区域迁移候选"/"闭关后突破候选"两个新测试仍在失败（AssertionError，非崩溃），是明确的 TDD 红灯阶段。详见 `NPC_LIFE_AUDIT.md` |
| 势力系统 | `faction_ai_manager.py` + `world_state["FACTION_STATE"]` + `data/factions.json` | **INTEGRATED** | `world_tick.py` 调用 `FactionAIManager.generate_candidates`；`main.py` 有 `/dh faction`、`/dh join_faction`、`/dh leave_faction`；测试全绿（5个 faction 测试文件） |
| 世界Tick | `world_tick.py`、`world_tick_scheduler.py` | **DONE** | 全系统的编排核心，17项以上子测试全绿（含 chain candidate、faction proposal、npc life 前两项），是目前测试覆盖最完整的模块 |
| 世界环境 | `world_environment.py`、`world_environment_manager.py`、`world_evolution.py` | **DONE** | `main.py` 有 `/dh environment`/`/dh weather`；`world_tick` 调用 `WorldEvolutionManager`；测试全绿 |
| 事件链 | `world_event_pool.py`、`world_event_trigger.py`、`world_chain_manager.py` | **DONE** | `EventPool` 是全系统事件单一数据源；`world_tick` 完整跑通"触发→链候选→消费"全流程；测试全绿 |
| **修炼系统（旧）** | `main.py` 内联的 `_REALMS`/`_adjust_cultivation_progress`/`_apply_breakthrough` | **INTEGRATED**（但即将被下面的新系统部分覆盖） | 一直是唯一在跑的修炼实现，突破检定/HP成长/六维精进都在这条路径上，测试通过（间接覆盖于 world_tick/faction 测试） |
| **修炼系统（LONG-A 新）** | `cultivation_state.py`/`cultivation_technique.py`/`spiritual_root.py`/`breakthrough_manager.py`/`cultivation_ability.py`/`sect_interface.py` | **PARTIAL**（本次审计期间从 UNCONNECTED 变为 PARTIAL） | `main.py` 现在会 import 全部六个模块（[main.py:116-157](main.py:116)，`try/except` + `_LONG_A_AVAILABLE` 标志位保护），**但目前只有"角色创建时生成初始灵根"一条调用路径真正被执行**（[main.py:3023](main.py:3023) 的 `_generate_initial_spiritual_root`）；`BreakthroughManager`/`TechniqueManager`/`AbilityManager`/`SectInterface` 均只被 import，未见任何实际调用点。零测试覆盖。详见 `LONG_A_AUDIT.md` |
| 战斗系统 | `main.py` 内联（`_resolve_combat_round` 等，无独立模块文件） | **INTEGRATED** | `/dh combat` 命令可用，先攻/命中/伤害由代码摇骰，AI 只叙事；未模块化，仍是 `main.py` 巨型化的一部分（见 `SYSTEM_ARCHITECTURE.md` 第6.6节），无独立单元测试，只能通过端到端手测/间接测试覆盖 |

---

## 一句话总结

- **最成熟**：世界Tick、事件链、世界环境、NPC记忆/关系/行为——测试覆盖好，
  接入完整，本次审计没有发现新问题。
- **进行中，需要关注**：NPC生命周期（刚接入，功能未完工）、
  LONG-A 修炼系统（刚开始接入，只接了一条路径，其余五个模块的类都还
  是摆件）。这两个是当前最活跃的战场，也是最容易在半接线状态下被
  误判为"已完成"或"完全没做"的两个系统——本文档存在的意义就是把
  这个中间状态钉住。
- **技术债但稳定**：战斗系统和旧修炼系统仍是 `main.py` 内联实现，
  没有模块化、没有独立测试，但功能完整、正在生产使用，不属于本次
  "废弃/未接入"风险范畴，只是架构技术债（见 `SYSTEM_ARCHITECTURE.md`）。
