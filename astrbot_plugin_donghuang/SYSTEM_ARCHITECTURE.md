# SYSTEM_ARCHITECTURE.md — 东荒修仙 TRPG 系统地图

维护者角色：架构维护与质量工程（对抗性审查），不负责新增大型玩法。
本文档描述**代码实际连到哪里**，不是文档"应该"是什么样子——凡是本文档
和 `README.md` / `使用说明.md` 描述不一致的地方，以本文档为准（并应在
发现的当下同步修正三者）。

最后核实日期：2026-07-08（基于当时的 import 关系与命令列表核实，非静态推测）。
每次对模块边界/数据流做出实质性改动后，必须回来更新本文件。

---

## 1. 顶层入口

- `main.py` —— 单文件承载 `DonghuangPlugin` 类，是唯一的 AstrBot 插件入口
  （`@register()`，`PLUGIN_NAME` 见 `metadata.yaml`）。
- 体量：约 5400+ 行源码等级的巨型类（139 个方法级别，43 个 `/dh` 子命令，
  经 `@filter.command_group("dh")` 注册）。
- **main.py 承担的职责远超"指令入口"**：世界规则文件加载、AI 提示词组装、
  STATE_DELTA 解析写入、回合锁定、战斗结算、角色生成、存档回滚、诊断指令，
  全部堆在这一个类里。这是当前最大的架构风险来源（见第 6 节）。

### 1.1 命令面（`/dh <sub>`，来自 `main.py` 里 `@dh.command(...)` 的真实清单）

```
help ask doctor bestiary why join exit testfill start end export status
advance eventtest tick roster world weather environment history eventlog
replay rollback mycard causal act profile memories interact npc npc_events
join_faction leave_faction faction items logout autopilot play kick
blacklist unblacklist combat decree force stop save stabilize confirmdeath
rejectdeath recap
```

（`recap` 是本次会话新修复的——见下方说明与第 8 节。）

（`recap` 曾是个已知坑：`dh_recap` 函数体完整存在，但缺少
`@dh.command("recap")` 装饰器，导致指令从未真正注册——本次核实时发现并
已修复，见第 8 节"本次会话变更记录"。）

### 1.2 main.py 内最大的几个函数（架构风险信号，非功能清单）

- `_generate_character_panels_batch`、`__init__`、`_resolve_turn_lock`、
  `_build_system_prompt`、`on_group_message`、`_resolve_combat_round`、
  `_apply_state_delta`、`_reactive_narrate`
- 这些函数正是"指令层/规则层/AI提示词层/状态机"混在一起的具体体现。
  拆分方向见第 6 节，**但按现有约束（见"禁止事项"）不要现在重写它们**，
  只在新增校验/测试/隔离时touch。

---

## 2. 数据流（一次典型的"正式事件"回合）

```
玩家群消息
  ↓
on_group_message()（main.py）——判断是否轮到该玩家、是否托管、是否在黑名单
  ↓
PlayerActionParser（player_action_parser.py）——把自然语言解析成结构化 PlayerAction
  ↓
PlayerActionResolver（player_action_resolver.py）——结合 player_action.py 的
  PlayerAction/ActionType/TargetType，判定行动合法性、目标解析
  ↓
_resolve_turn_lock（main.py）——收集本轮所有玩家行动，判断是否满足结算条件
  ↓
_build_system_prompt（main.py）——拼装 AI 提示词：world/engine_rules.md（常驻）
  + world/death_protocol.md（濒死时）+ region_lore/faction_index（world/
  lore_dossier.md、world/faction_resource_entity.md 解析后的分段索引）
  + 当前 WorldContext + 当前事件 + 玩家状态
  ↓
LLM 生成叙事 + STATE_DELTA 文本
  ↓
_apply_state_delta（main.py）——解析 STATE_DELTA 自由文本路径 DSL，
  调用 OutcomeApplier（outcome_applier.py）做实际的 dict 树写入
  （world_state / player_profile / faction 三类合并，含数值 clamp）
  ↓
状态变化落盘（world_state / campaign / player_profiles / event_log，
  经 main.py 里的 _save_*() 直接整体覆盖写文件，无 group 级锁，见第6.4节）
  ↓
EventPool.advance_stage / update_progress（world_event_pool.py）——
  事件本身按 EventStage 推进
  ↓
下一次 /dh tick 或 /dh advance 触发 WorldTickManager.tick()（world_tick.py）
  ↓
世界演化：WorldEvolutionManager（world_evolution.py，天气/环境类演化）+
  WorldEnvironmentManager（world_environment_manager.py）+
  WorldChainManager / WorldEventTrigger / EventOutcomeResolver
  （world_tick.py 内部按需 import，生成事件链候选、触发新事件、
  结算 tick 生成事件的 outcome）
```

**两条不同的"outcome 结算路径"，不要混淆：**

1. 玩家在正式事件里的行动结果 —— 走 `_apply_state_delta` → `OutcomeApplier`
   （outcome_applier.py），处理的是 LLM 自由文本 STATE_DELTA。
2. World Tick 自动推进产生的世界事件结果 —— 走
   `EventOutcomeResolver`（event_outcome_resolver.py，只在
   `world_tick.py` 内部被 import 使用），处理的是结构化的
   `EventOutcome`（event_outcome.py）。

这两条路径目前是分开实现的，没有共用一套 schema/校验层——第 6.2 节详述风险。

---

## 3. 模块清单（按子系统分组）

### 3.1 核心引擎 / 编排

| 模块 | 职责 | 被谁引用 |
|---|---|---|
| `main.py` | 唯一插件入口，指令层+提示词层+状态机 | AstrBot 框架 |
| `world_tick_scheduler.py` (`TickScheduler`) | 定时/条件触发 tick 的调度封装 | main.py |
| `world_tick.py` (`WorldTickManager`) | 每次 tick：推进世界时钟、NPC主动队列、事件进度、势力/环境变化记录、事件链候选生成与消费、`commit_archives` | main.py；内部依赖 world_event_pool / world_event_trigger / world_chain_manager / event_outcome_resolver |

### 3.2 事件系统

| 模块 | 职责 |
|---|---|
| `world_event_pool.py` (`EventPool`, `ActiveEvent`, `EventStage`, `EventCategory`, `EventVisibility`, `EventPriority`) | 事件池的增删查、按 group_id 隔离、`advance_world_events`、`apply_player_action`、`seed_initial_events`、归档（`archive`/`preview_archive`/`commit_archive`） |
| `world_event_trigger.py` (`WorldEventTrigger`) | 由环境/势力/灵脉等状态变化触发新事件候选，被 `world_tick.py` 使用 |
| `world_chain_manager.py` (`WorldChainManager`) | 事件链（连续因果）候选的构建与消费，被 `world_tick.py` 使用 |
| `event_outcome.py` / `event_outcome_resolver.py` | 结构化 `EventOutcome` 定义 + 结算器；`event_outcome_resolver.py` 只在 `world_tick.py` 内使用 |
| `faction_ai_manager.py` (`FactionAIManager`，C-0 审计新确认) | 为每个势力生成低频、可解释的 `faction_action` 候选；只读 `FACTION_STATE`/`factions`/`EventPool`/`world_history`，不直接改 world_state、不直接写 EventPool、不直接调 OutcomeApplier——候选交给 `world_tick.py` 统一持久化。被 `world_tick.py` import 使用（`self.faction_ai_manager`）。|

### 3.3 世界模拟

| 模块 | 职责 |
|---|---|
| `world_context.py` (`WorldContextBuilder`) | 组装喂给 AI 的"当前世界上下文"文本/结构，是 Prompt 工程的核心入口 |
| `world_evolution.py` (`WorldEvolutionManager`) | 天气/环境相邻状态转移等演化规则 |
| `world_environment.py` (`EnvironmentState`, `EFFECT_DESCRIPTIONS`) + `world_environment_manager.py` (`WorldEnvironmentManager`) | 区域环境状态建模与管理 |
| `world_news.py` (`WorldNewsBuilder`) | 把 world_history 里的事件/提案生成"世界新闻"叙事片段 |
| `weather_data.py` | 天气生成的数据/规则表 |

### 3.4 玩家行动

| 模块 | 职责 |
|---|---|
| `player_action.py` (`PlayerAction`, `ActionType`, `TargetType`, `make_action`) | 玩家行动的结构化数据定义，被 `player_action_parser.py` / `player_action_resolver.py` 使用 |
| `player_action_parser.py` (`PlayerActionParser`) | 自然语言 → `PlayerAction` |
| `player_action_resolver.py` (`PlayerActionResolver`) | 行动合法性/目标解析 |
| `player_appearance.py` (`AppearanceGenerator`) + `appearance_modifier.py` | 角色外观生成与后天修饰（伤疤/异变等） |
| `cultivation_state.py` + `cultivation_technique.py` + `spiritual_root.py` + `breakthrough_manager.py` + `cultivation_ability.py` | "LONG-A" 五阶段修炼子系统重写（根基/瓶颈/灵根/功法/突破/技能），`breakthrough_manager.py` 把前三者串起来，`cultivation_ability.py` 目前连子系统内部都还没被引用。**五个文件均未被 main.py/world_tick.py 等任何已接入运行时的模块 import，也没有任何测试覆盖**——是正在进行中、尚未接线的并行开发，跟 main.py 现有的 `_REALMS`/`_adjust_cultivation_progress` 是两套平行实现。详见 `ORPHAN_MODULE_AUDIT.md` 与 `DEPENDENCY_MAP.md` 第3节。|

### 3.5 NPC 系统

| 模块 | 职责 |
|---|---|
| `npc_registry.py` (`NPCRegistry`) | NPC 名录：注册/查询 |
| `npc_context.py` (`build_npc_context_for_ai`) | 组装喂给 AI 的 NPC 上下文 |
| `npc_memory.py` (`NPCMemory`, `create_memory`, `MEMORY_IMPORTANCE_THRESHOLD`) + `npc_memory_manager.py` (`NPCMemoryManager`) | NPC 记忆的数据结构与增删/衰减管理 |
| `npc_behavior.py` (`calculate_behavior`, `NPCBehaviorProfile`) | 由心性/属性推导行为倾向 |
| `npc_relationship.py` (`calculate_relationship`, `REL_LABELS`) | NPC↔玩家/NPC↔NPC 关系值计算 |
| `npc_interaction.py` + `npc_interaction_executor.py` (`execute_interaction`) | 互动定义与执行；`npc_interaction_executor.py` 是 main.py 实际 import 的入口，内部再调用 `npc_interaction.py` |
| `npc_event_trigger.py` (`create_npc_interaction_hint`) | 由事件生成 NPC 互动线索 |
| `npc_action_scheduler.py` (`NPCActionScheduler`) | NPC 主动行为的调度（world tick 里"NPC主动队列"的来源） |
| `npc_action_generator.py` | NPC 主动行为的具体生成逻辑 |
| `npc_perception.py` | NPC 感知模型 —— **截至本次核实，同样未被任何运行时模块 import**，风险同 `cultivation_state.py`（见第 6.3 节）|
| `npc_attribute_roller.py` | NPC 属性摇点 —— **同上，未接入运行时**（见第 6.3 节）|

### 3.6 势力/资源/状态写入

| 模块 | 职责 |
|---|---|
| `outcome_applier.py` (`OutcomeApplier`) | STATE_DELTA 解析后的实际落地：`_apply_world_delta` / `_apply_faction_delta` / `_apply_profile_delta`，含 `_merge_dict` 系列的数值 clamp。是当前"自由文本路径 DSL 写状态树"的最终执行点，也是最该优先加白名单校验的地方（见第 6.2 节）|

### 3.7 静态资产与生成器

| 模块 | 职责 |
|---|---|
| `asset_loader.py` | 通用资产加载封装 |
| `bazi.py` | 八字计算与属性映射 |
| `name_data.py` | 姓名库 |
| `talent_data.py` | 约1000条天赋 + 100条缺陷数据表 |
| `background_data.py` | 家世背景/人生事件/社会关系/个人驱动力数据表 |
| `affliction_data.py` | 持续性负面状态（病症等）数据表 |
| `bestiary_generator.py` / `ecosystem_generator.py` / `flora_generator.py` / `item_generator.py` / `technique_generator.py` / `place_generator.py` / `generate_timeline.py` / `gen_techniques_v2.py` | **均为离线资产生成脚本**，用于产出 `data/*.jsonl` / `data/*.json`，不是运行时被 `main.py` 调用的模块——它们的角色类似"数据编译工具"，跟服务运行时无关。改动这些脚本前应先确认目的是"重新生成资产"还是"运行时逻辑"，不要误当成热路径代码去改。|

### 3.8 世界规则文档（`world/*.md`，喂给 LLM 的规则文本）

**已核实真实加载情况**（`main.py` 初始化时的 `self._read_text(...)` / `self._parse_sections(...)` 调用）：

| 文件 | 是否真的被加载进提示词 | 加载方式 |
|---|---|---|
| `engine_rules.md` | ✅ 常驻 | 每次调用固定加载全文 |
| `death_protocol.md` | ✅ 常驻 | 固定加载全文（濒死判定时引用） |
| `campaign_seed.md` | ✅ | `/dh start` 开团时加载 |
| `lore_dossier.md` | ✅ | `_parse_sections` 按区域分段索引 |
| `faction_resource_entity.md` | ✅ | `_parse_sections` 按势力分段索引 |
| `economy_rules.md` | ❌ 未接入 | 仅在源码注释里被引用（"详见 economy_rules.md"），没有任何 `_read_text`/`_parse_sections` 调用加载它 |
| `combat_rules.md` | ❌ 未接入 | 同上，只是注释引用，不在真实提示词装配链里 |

这个结论和 `README.md` 目前的描述不一致（README 声称这两个文件会在
交易/战斗时加载）——**文档漂移仍未修复，是遗留的已知问题**，不是本次
新发现（上一轮审计 `AUDIT_HANDOFF_2026-07-06.md` 5.4 节已记录）。

---

## 4. 存档结构（按 group_id 隔离）

运行时数据路径经 `StarTools.get_data_dir(PLUGIN_NAME)` 获取（不硬编码），
核心状态包括：

- `campaign`（含 `cycle`、`world_clock`、`world_history`、
  `npc_world_queue`、`world_action_proposals` 等）
- `world_state`
- `event_log`
- `player_profiles`
- `output_log`

写入路径目前是"读入内存 dict → 多处直接修改 → 整体覆盖写文件"，
**没有 group 级并发锁**（见第 6.4 节，遗留风险，未修复）。

---

## 5. 已有测试基础设施

`tools/` 下已有 25 个 standalone 回归测试脚本（`test_*.py`），覆盖
faction / npc / world_tick / event / rollback / appearance 等子系统。
运行约定：每个脚本 `assert` 失败即抛异常，进程退出码非 0；全部通过
则打印 `🎉 全部 XXX 测试通过！`。

新增 `tools/test_full_regression.py` 作为一键聚合入口：

```
py tools/test_full_regression.py            # 跑全部
py tools/test_full_regression.py -k npc      # 只跑文件名含 npc 的
py tools/test_full_regression.py --list      # 只列出会跑哪些文件
```

**踩过的坑，记录一下**：这些测试脚本大量使用 emoji（✅ 📌 🧪）做输出标记。
当 stdout 没有连接到真实控制台（比如被子进程捕获、被管道重定向）时，
Windows 上 Python 会退回系统 ANSI 代码页（如 gbk），打印 emoji 直接抛
`UnicodeEncodeError`，**即使测试逻辑完全正确也会以非零退出码"假失败"**。
`test_full_regression.py` 已经在子进程 env 里强制
`PYTHONIOENCODING=utf-8` + `PYTHONUTF8=1` 来规避，但如果后续 CI 或其他
自动化脚本用别的方式调用这些测试文件，同样的坑会再踩一次——**任何新的
自动化调用点都要注意这一点**，不要归因成"测试写错了"。

---

## 6. 已知风险清单（本次核实仍然成立，尚未修复）

以下问题在 `AUDIT_HANDOFF_2026-07-06.md` 中已被记录，本次核实确认
**截至目前仍未修复**，按风险等级排列：

### 6.1 数据资产 BOM 问题（高，未修复）
1499 个 `.jsonl` 中约 1460 个带 UTF-8 BOM，代码里大量 `encoding="utf-8"`
直接读取会报错或被 `except: continue` 静默吞掉。尚未核实是否已建立
统一的 `utf-8-sig` 读取层——下一次审查应优先复核这一项是否仍然存在。

### 6.2 STATE_DELTA 自由文本路径 DSL（中，已部分修复——用户明确授权后处理）
`_apply_state_delta`（这条路径跟 `OutcomeApplier`/`EventOutcome` 是两套
独立机制，`_apply_state_delta` 只服务 STATE_DELTA 这种自由文本代码块，
没有改到 Outcome 结构本身）现在加了**模块级白名单**：
- `world_state.<模块>.xxx`：`<模块>` 必须是 `INITIAL_WORLD_STATE` 的
  已知顶层 key（直接引用该常量的 `.keys()`，不需要手动维护第二份清单，
  以后新增/删除世界状态模块时白名单自动跟着变）。
- `player_profile.<模块>.<字段>`：`<模块>` 必须是角色创建时那份 profile
  字典的已知顶层 key（`_PROFILE_MODULE_WHITELIST`，跟 `dh_start` 里角色
  面板构造代码手动对齐维护）。

**没有做的**：字段级别（`<字段>` 本身）依然是自由文本，没有对每个模块
内部收紧到具体字段清单——那需要逐一枚举 `engine_rules.md` 里每个
模块允许 AI 写哪些字段，风险和工作量都大得多，且原有的
`_PROFILE_PROTECTED_TOP_FIELDS`/`_PROFILE_PROTECTED_NESTED_FIELDS`
黑名单已经挡住了最危险的那几个字段（修为/六维/生存状态等）。这次拦住
的是"AI 编一个全新的、从未设计过的模块名"这个最容易"静默长出新结构"
的失败模式，是防御深度的加强，不是把开放式 DSL 彻底改造成严格白名单。
测试见 tools/test_state_delta_whitelist.py（6项，含合法路径回归验证）。

### 6.3 三个模块未接入运行时（本次审查新确认，中）
`cultivation_state.py`、`npc_perception.py`、`npc_attribute_roller.py`
在整个插件目录内搜索不到任何运行时 import（只有测试文件引用它们）。
可能性有两种：
  - (a) 确实是"做了一半、还没接线"的半成品，测试先行但功能未上线；
  - (b) 命名重复/功能已被其他模块（如 `bazi.py` 的属性计算、
    `npc_behavior.py` 的行为计算）取代，成了应删除的遗留代码。
**在没有跟开发者确认之前不要擅自删除或强行接入**——这不是本角色能
单方面判断的产品决策，只负责把这个事实亮出来。

### 6.4 无 group 级并发锁（中，已修复——用户明确授权后处理）
`DonghuangPlugin._get_group_lock(group_id)` 惰性创建每个群一把
`asyncio.Lock`。`on_group_message`/`dh_start`/`dh_decree` 这三个"会
await LLM 调用、期间又会读写共享 campaign/profile 状态"的高风险入口
改成"薄包装函数持锁 + `_xxx_locked` 版本做实际逻辑"模式，同一个群的
处理严格串行，不同群互不阻塞。测试见 tools/test_group_lock.py（5项，
含一个真实复现"更新丢失"场景的并发测试）。

**没有覆盖的范围（有意为之，不是漏做）**：main.py 里还有约 50 个
`/dh` 指令，大部分是同步的、读完立刻写、中间没有 `await` 的操作
（比如 `/dh kick`），Python asyncio 是协作式单线程调度，两个协程只在
`await` 点才会交错——没有 `await` 的代码块本身就是原子的，不需要锁。
真正有竞态窗口的只有"读状态 → await（LLM/IO）→ 写状态"这个模式，本次
覆盖了三个最高频/影响面最大的入口，其余包含 `await self._call_llm`
的角色创建子函数（`_generate_character_panels_batch` 等）都在
`dh_start` 的锁范围内，已经间接覆盖。

### 6.5 文档漂移（中，未修复，见 3.8 节）
`economy_rules.md` / `combat_rules.md` 文档承诺加载，代码未加载。

### 6.6 main.py 巨型化（中，架构层面，短期不打算重写）
按"禁止事项"约束，本角色不重写已有模块、不做大拆分，但每次新增校验/
测试时应尽量新增独立文件而不是继续往 main.py 里堆函数，为将来的
拆分留出空间。

---

## 7. 更新纪律

- 任何一次改动，只要触及：新增/删除模块、改变某模块的 import 关系、
  改变 `world/*.md` 的加载方式、改变存档字段结构——都必须回来同步本文档。
- 本文档不是"这个系统应该长成什么样"的理想蓝图，是"现在到底长什么样"
  的核对结果。如果发现本文档和代码不一致，以代码为准，并立刻修正文档。

---

## 8. 本次会话变更记录（2026-07-08）

1. 修改文件：
   - `astrbot_plugin_donghuang/.gitignore` —— 移除 `data/`，不再让插件
     核心世界资产被忽略（上一轮审计 5.2 节记录的遗留问题，本次修复）。
   - `astrbot_plugin_donghuang/main.py` —— 给 `dh_recap` 补上缺失的
     `@dh.command("recap")` 装饰器（原本函数体完整、文档也承诺存在，
     但从未真正注册为可用指令）。
2. 新增文件：
   - `astrbot_plugin_donghuang/SYSTEM_ARCHITECTURE.md`（本文件）。
   - `astrbot_plugin_donghuang/tools/test_full_regression.py` —— 聚合
     运行 `tools/` 下全部 25 个 `test_*.py`，子进程环境强制
     `PYTHONIOENCODING=utf-8`/`PYTHONUTF8=1` 规避 Windows 下的假失败。
3. 修复问题：
   - `.gitignore` 数据丢失风险（见上）。
   - `/dh recap` 指令未注册（见上）。
   - 回归测试在非交互式/子进程环境下因 emoji 输出全体假失败
     （运行 25/25 从 0/25 变为 25/25，但这是"测试跑法"层面的修复，
     不是业务逻辑变化——运行到真实控制台里之前这些测试本来就是通过的）。
4. 测试结果：
   - `py -m py_compile main.py` 通过。
   - `py tools/test_full_regression.py`：25/25 通过（用时约 1.6s）。
5. 性能变化：无（本次未涉及热路径逻辑改动）。
6. 发现的风险（详见第 6 节，多数为上一轮审计已记录、本次核实仍未修复）：
   - JSONL 资产 BOM 读取问题是否已修复——本次未复核，下次应优先确认。
   - `STATE_DELTA` 自由文本路径 DSL 仍无白名单校验。
   - `cultivation_state.py` / `npc_perception.py` / `npc_attribute_roller.py`
     三个模块在运行时代码里搜不到任何 import，疑似未接入或已废弃
     （本次审查新确认的事实，需要跟开发者确认意图，不擅自处理）。
   - 无 group 级 `asyncio.Lock`，并发覆盖写风险仍在。
   - `economy_rules.md` / `combat_rules.md` 文档与实际加载不一致。
7. 建议下一步（按风险/收益排序）：
   - 复核 JSONL BOM 读取问题的当前真实状态（上次审计给出的建议是否已落地）。
   - 针对第 6.3 节三个"孤儿模块"，直接问开发者：是预留半成品还是废弃代码。
   - 建立 `tools/save_validator.py`（对应任务书第三阶段），先从"打开
     现有存档、检查缺失字段、试跑一次自动补全"做起，不动 EventPool/
     Outcome 核心结构。
   - 建立 `tools/world_consistency_checker.py`（第六阶段），优先做
     "事件引用的地点/NPC/势力是否存在"这类纯读校验，风险最低、收益直接。
