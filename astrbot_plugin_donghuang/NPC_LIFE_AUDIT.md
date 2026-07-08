# NPC_LIFE_AUDIT.md — NPC 生命周期系统审计

审计日期：2026-07-08（C-1 任务第三节）

**⚠️ 同样需要先说明状态漂移**：审计开始时 `npc_life_manager.py` 还不
存在，审计过程中该文件被（并行开发）创建并**当场接入了 `world_tick.py`**。
本文档基于审计完成时刻的真实状态。

---

## 1. `npc_life_manager.py` 现状总结

- 单一类 `NPCLifeManager`，构造参数只需要 `EventPool`。
- 核心方法：`generate_candidates()`（只读生成候选，不改状态）、
  `record_candidate()`（把选中的候选落到 `campaign["npc_life_state"]`/
  `campaign["npc_life_log"]`，并调用 `NPCMemoryManager` 写一条 NPC 记忆）。
- 明确遵守"只生成候选，不直接改 world_state / EventPool"的边界
  （风格上跟 `faction_ai_manager.py` 是同一套设计约定，两者应该是
  同一个人/同一轮设计出来的姊妹模块）。

## 2. `world_tick.py` 接入情况

**已接入，非本次会话所为，审计期间发现：**

- `world_tick.py` 顶部 import `NPCLifeManager`（[world_tick.py:28](world_tick.py:28)）
- `__init__` 里实例化 `self.npc_life_manager = NPCLifeManager(event_pool)`
  （[world_tick.py:78](world_tick.py:78)）
- `tick()` 流程里调用 `generate_candidates()` 并把结果写入
  `result["npc_life_actions"]`（[world_tick.py:627-635](world_tick.py:627)），
  同时 `result` 的默认结构里也预先声明了 `"npc_life_actions": []`
  （[world_tick.py:433](main.py:433)）——说明这次接入**不是临时拍上去的**，
  而是跟其他 tick 结果字段（`faction_changed`/`environment_changed`）
  用了完全一致的写法。

**结论：已经是"接入运行时主线"，不是"孤儿模块"，但功能不完整**（见第4节）。

## 3. 是否存在生命周期各环节

任务要求确认"出生/成长/移动/死亡/突破/事件"，逐项核对
`_build_candidate_for_npc()` 当前的分支实现（[npc_life_manager.py:152](npc_life_manager.py:152)）
和测试文件 `tools/test_npc_life_manager.py` 里断言的完整清单两者的差集：

| 环节 | 对应 action | 是否已实现 | 依据 |
|---|---|---|---|
| 出生 | — | ❌ 不存在 | 代码里没有任何"NPC 新生"相关分支；`npc_life_state` 只在已有 NPC 身上 setdefault，不创建新 NPC 个体 |
| 成长/闭关修炼 | `seclusion` | ✅ 已实现 | 灵脉资源事件触发闭关候选，`test_generate_seclusion_candidate_from_leyline_signal` 通过 |
| 移动/迁移 | `relocate` | ❌ **未实现（红灯）** | `_build_candidate_for_npc` 没有对应分支；`test_generate_relocate_candidate_from_cross_region_ruin` 断言失败（`AssertionError`，`relocate` 列表为空） |
| 死亡 | `death` | ✅ 已实现（需要因果链佐证才触发） | 势力冲突事件+因果链同时存在才生成，`test_death_requires_cause_chain` 通过 |
| 突破 | `breakthrough` | ❌ **未实现（红灯）** | 没有对应分支；`test_generate_breakthrough_candidate_from_existing_seclusion` 断言失败 |
| 消失（CHAOS异常相关，介于死亡和转移之间的第三种"退场"） | `disappear` | ⚠️ 未验证 | 代码没有对应分支，测试文件里有 `test_disappear_requires_cause_chain`，但由于同一测试脚本前面的 `relocate`/`breakthrough` 测试先失败并让脚本整体中断，**这个测试连跑都没跑到**，处于"未知"而不是"确认失败"状态 |
| 加入事件/参与事件 | `join`（推测名，来自 `test_generate_join_event_candidate_from_local_conflict`） | ⚠️ 未验证 | 同上，因脚本提前中断，实际是否实现未知 |

**总结**：生命周期六个环节里，"出生"完全没有设计痕迹（不确定是否在
路线图内，还是这套系统本来就只管"存量 NPC 的后续人生"，不管"新增
NPC"）；"成长/闭关"和"死亡"两个分支已实现且测试通过；"移动"和
"突破"分支确认未实现（有断言、有失败，是明确的 TDD 红灯）；
"消失"和"加入事件"两个分支因为测试脚本提前中断，**处于未验证状态**，
不能归类为"失败"，只能归类为"未知"。

## 4. 是否与既有系统重复

**未发现功能性重复，边界划分清晰：**

- `NPCRegistry.get_all_npcs()`（[npc_registry.py:148](npc_registry.py:148)）
  被 `NPCLifeManager.generate_candidates()` 直接调用（鸭子类型传参，
  不要求真实类型），**没有重新实现一套 NPC 名录**，是正确的复用。
- `NPCMemoryManager`（`npc_memory_manager.py`）被 `record_candidate()`
  直接调用来写"NPC 生命事件"记忆，**没有另起一套记忆存储**。
- `NPCActionScheduler`（`npc_action_scheduler.py`）负责的是"高频、
  日常"的 NPC 主动互动线索；`NPCLifeManager` 负责的是"低频、影响NPC
  存在状态本身"的生命事件（死亡/闭关/迁移等）——两者的触发频率、
  影响范围、写入的字段（`npc_action_log` vs `npc_life_log`/
  `npc_life_state`）都是分开的，没有交叉写同一份状态，不构成重复。

## 5. 风险与建议（仅报告，未做任何接线/实现/删除）

1. **`relocate`/`breakthrough` 两个分支确认缺失**——如果这两个功能
   本来计划要在这一轮完成，需要开发者继续实现；如果这一轮只打算做
   "seclusion+death"两种，测试文件里其余几个测试函数应该被跳过/
   标记为"暂缓"，而不是留着让 `test_full_regression.py` 一直报红——
   现在的状态会导致"回归测试常年有红灯"，久而久之团队容易对红灯
   脱敏，这是本次审计想特别提醒的工程习惯风险。
2. **"出生"环节完全没有设计**：需要向开发者确认这是不是故意的范围
   划分（这套系统只管理存量 NPC，不负责生成全新 NPC 个体）。
3. `disappear`/`join` 两个分支的真实完成度目前无法确认，建议下次
   审计前先单独执行这两个测试函数（而不是跑整个文件),以获得准确
   状态，不要被"脚本提前中断"误导成"完全没做"或"看起来还行"。
4. 目前 `npc_life_manager.py` 和 `faction_ai_manager.py` 结构高度相似
   （都是"只生成候选，交给 world_tick 统一持久化"），如果后续还会有
   第三个"低频候选生成器"，值得考虑要不要抽一个共享的基类/协议
   （但这是"值不值得"的架构决策，不在本次审计范围内，只作为观察记录）。
