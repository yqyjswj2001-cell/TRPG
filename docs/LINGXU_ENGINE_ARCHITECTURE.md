# LingXu Engine v1 架构设计

> 本文档是灵墟界项目的工程宪法。所有开发决策以本文档为准。
> 文档冲突时，以本文档覆盖任何旧文档。

---

## 1. 定位

LingXu Engine 是一个持续运行的 AI 修仙世界模拟器。

世界独立于任何客户端。玩家只是进入世界。世界不围绕玩家运行。

AstrBot 是第一个客户端。未来可接入 Web、Discord、Steam、CLI。

---

## 2. 最终目录树

```
lingxu/
├── docs/                              # 文档（不参与运行时）
│   └── LINGXU_ENGINE_ARCHITECTURE.md  # 本文件
│
├── src/                               # 引擎核心（纯 Python，零平台依赖）
│   ├── core/                          # 引擎核心层
│   │   ├── world.py                   # World State 管理
│   │   ├── tick.py                    # 世界 Tick / 事件循环
│   │   ├── event.py                   # Event Engine
│   │   ├── memory.py                  # Memory Engine
│   │   ├── actor.py                   # Actor 抽象基类
│   │   ├── causality.py              # 因果网络
│   │   └── chaos.py                   # CHAOS 异常系统
│   │
│   ├── systems/                       # 子系统模块
│   │   ├── cultivation.py             # 修行体系
│   │   ├── combat.py                  # 战斗系统
│   │   ├── economy.py                 # 经济系统
│   │   ├── faction.py                 # 势力系统
│   │   ├── exploration.py             # 探索系统
│   │   └── lore.py                    # 叙事系统
│   │
│   ├── ai/                            # AI 适配层
│   │   ├── adapter.py                 # AIAdapter 抽象基类
│   │   ├── prompts.py                 # Prompt 模板构建
│   │   ├── interpreter.py             # STATE_DELTA 解析器
│   │   └── resolver.py                # 编剧敕令处理器
│   │
│   ├── storage/                       # 持久化层
│   │   ├── manager.py                 # StorageManager 统一入口
│   │   ├── json_store.py              # JSON 文件存储（原子写入）
│   │   ├── cache.py                   # 内存缓存
│   │   └── migrations/               # 数据迁移脚本
│   │
│   ├── data/                          # 只读资产数据
│   │   ├── techniques/                # 功法库
│   │   ├── items/                     # 法宝/武器/丹药/灵材
│   │   ├── bestiary/                  # 生灵数据库
│   │   ├── ecosystem/                 # 生态圈
│   │   ├── flora/                     # 植物
│   │   ├── timeline/                  # 千年时间线
│   │   ├── factions/                  # 势力定义
│   │   ├── npcs/                      # NPC 定义
│   │   ├── places/                    # 地点定义
│   │   └── schemas/                   # JSON Schema 校验器
│   │
│   └── utils/                         # 工具函数
│       ├── random.py                  # 骰子/随机抽取
│       ├── validation.py              # 硬校验
│       └── logging.py                 # 日志
│
├── clients/                           # 客户端适配器（每个平台一个目录）
│   ├── astrbot/                       # AstrBot QQ 群客户端
│   │   ├── plugin.py                  # 插件壳（仅注册/路由/发送）
│   │   ├── commands.py                # 指令注册表
│   │   ├── handlers.py                # 消息处理器
│   │   └── events.py                  # 事件监听
│   │
│   ├── discord/                       # Discord 客户端
│   ├── web/                           # Web 客户端
│   └── cli/                           # CLI 客户端
│
├── tools/                             # 工程工具（非运行时）
│   ├── generate_data.py               # 数据生成器
│   ├── validate_assets.py             # 资产校验
│   └── run_tick.py                    # 测试用 Tick 运行器
│
├── tests/                             # 测试套件
│   ├── unit/
│   ├── integration/
│   └── fixtures/
│
└── config/                            # 配置文件
    ├── default.yaml
    └── schemas/                       # 运行时状态 JSON Schema
```

---

## 3. 每个目录职责

| 目录 | 职责 | 依赖方向 |
|---|---|---|
| `src/core/` | 世界引擎核心：状态管理、Tick 循环、事件调度、记忆、因果、异常 | 不依赖任何外部模块 |
| `src/systems/` | 六个业务子系统：修行、战斗、经济、势力、探索、叙事 | 依赖 `core/`，被 `core/` 调度 |
| `src/ai/` | AI 适配层：Prompt 构建、AI 输出解析、敕令处理 | 依赖 `core/`（读取状态、写入变化），不依赖任何客户端 |
| `src/storage/` | 持久化层：统一读写、原子写入、缓存、迁移 | 依赖 `core/`（序列化 World State），不依赖任何客户端 |
| `src/data/` | 只读资产数据。有 JSON Schema 校验。运行时不被修改 | 被所有模块读取，不被任何模块写入 |
| `src/utils/` | 通用工具：骰子、校验、日志 | 不依赖任何模块 |
| `clients/` | 每个平台一个子目录。只做：接收输入 → 调引擎 API → 返回结果 | 依赖 `src/`，不被 `src/` 依赖 |
| `tools/` | 一次性脚本和校验工具。不进入生产运行时 | 依赖 `src/data/` |
| `tests/` | 测试。核心引擎必须有单元测试 | 依赖 `src/` |
| `config/` | 配置和 Schema 定义 | 被运行时读取 |

**依赖铁律**：

```
clients/ → src/ → 无外部依赖
src/ 内部：systems/ → core/，ai/ → core/，storage/ → core/
core/ 不依赖 systems/、ai/、storage/ 之外的任何模块
data/ 只被读取，永远不被写入
```

---

## 4. 世界引擎模块

### 4.1 核心层（src/core/）

| 模块 | 职责 |
|---|---|
| `world.py` | World State 管理。持有全局状态快照。提供按层级读写、快照、回滚接口。内部按 GLOBAL / REGION / ACTOR / FACTION / ENTITY / CAUSAL / CHAOS / EVENT 组织。 |
| `tick.py` | 世界 Tick 循环。驱动世界自主演化。每 tick：推进时间 → 自动修炼 → 被动演化 → 事件队列检查 → 持久化。即使无玩家也持续运行。 |
| `event.py` | Event Engine。六类事件注册、触发检测、排队、结算。区分反应式叙事（即时反馈）和正式事件（多人锁定回合制）。 |
| `memory.py` | Memory Engine。玩家档案、因果链、历史记录、决策日志。跨会话持久化。详见第 9 节。 |
| `actor.py` | Actor 抽象基类。角色、势力、NPC、灵体——所有"能做事的实体"统一接口。提供行动能力、资源持有、关系网络。 |
| `causality.py` | 因果网络。因果债追踪、回响触发、承接判定。关联到具体实体和事件。 |
| `chaos.py` | CHAOS 异常系统。异常范围分级（局部/区域/世界级）、状态流转（沉寂→潜伏→活跃→高压→临界→收敛）、天道修正。 |

### 4.2 子系统层（src/systems/）

| 模块 | 职责 | 修改的 World State 区域 |
|---|---|---|
| `cultivation.py` | 修行体系：突破检定、修为进度、灵根跃迁、日常修炼增益 | `actor.method_state`、`actor.core_state` |
| `combat.py` | 战斗系统：回合制流程、先攻/命中/伤害/状态效果、濒死判定 | `actor.hp`、`actor.mp`、`actor.combat_status` |
| `economy.py` | 经济系统：货币波动钳制、物价判断、交易模拟 | `actor.resource_state.currency`、`faction.resources` |
| `faction.py` | 势力系统：扩张/收缩、联盟/敌对、灵脉控制 | `region.factions`、`global.power_balance` |
| `exploration.py` | 探索系统：地点发现、秘境开启、遗迹激活、灵墟形成 | `entity.locations`、`chaos.anomalies` |
| `lore.py` | 叙事系统：故事生成提示词、传说传播、历史格式化 | 不修改 World State（纯输出），可写入 `event_log` |

---

## 5. AstrBot 只作为客户端适配器

AstrBot 插件只负责三件事：

1. **接收输入**：监听群消息，匹配指令，提取参数
2. **调用引擎**：将用户意图翻译为引擎 API 调用
3. **返回结果**：将引擎输出格式化为 QQ 消息发送

**AstrBot 不包含的任何逻辑**：

- 世界规则判断和运算
- 事件触发和结算
- 战斗摇骰和状态计算
- 存档和回滚
- STATE_DELTA 解析
- 提示词构建
- 因果网络计算
- 任何业务逻辑

---

## 6. 代码归属：搬出 DonghuangPlugin 的部分

以下逻辑属于引擎，不属于任何客户端。当前它们嵌在 `DonghuangPlugin` 中，未来必须迁入 `src/`。

| 逻辑 | 目标模块 |
|---|---|
| 骰子/检定/随机抽取 | `src/utils/random.py` |
| 硬校验（最高约束检查） | `src/utils/validation.py` |
| 病症/功法/物品/关系池的读取和抽取 | `src/data/`（资产文件）+ 对应 `systems/` 模块 |
| 角色生成（八字→灵根/六维/区域/身份） | `src/core/actor.py` + `src/systems/cultivation.py` |
| 突破检定/修为进度/灵根跃迁 | `src/systems/cultivation.py` |
| 战斗结算（先攻/命中/伤害/状态效果） | `src/systems/combat.py` |
| 回合锁定/事件结算 | `src/core/event.py` |
| 因果债追踪/回响触发 | `src/core/causality.py` |
| CHAOS 异常检测/天道修正 | `src/core/chaos.py` |
| STATE_DELTA 解析 | `src/ai/interpreter.py` |
| 提示词构建 | `src/ai/prompts.py` |
| 编剧敕令处理 | `src/ai/resolver.py` |
| 存档/回滚/快照 | `src/storage/manager.py` |
| 诊断逻辑 | `src/core/` 内部方法 |
| 数据生成器（15 个 generate_*.py） | `tools/generate_data.py` |
| 静态数据池（affliction_data / background_data / talent_data / weather_data 等） | `src/data/`（转为 JSONL/JSON 文件） |

---

## 7. 代码归属：必须留在插件的部分

只有两类代码永远留在客户端层：

**平台适配代码**：

| 内容 | 理由 |
|---|---|
| `@register(PLUGIN_NAME, ...)` 插件注册 | AstrBot 框架要求，换平台即失效 |
| `class DonghugPlugin(Star)` 类定义 | Star 是 AstrBot 基类 |
| `on_group_message` 事件回调 | AstrBot 事件钩子 |
| `filter.command_group("dh")` 指令分组 | AstrBot 指令注册语法 |
| LLM 提供商调用方式 | 不同平台接入方式不同 |
| `StarTools.get_data_dir()` 数据目录获取 | AstrBot 特有 API |
| `event.is_admin()` 权限判断 | 平台身份判断 |

**客户端专属逻辑**：

| 内容 | 理由 |
|---|---|
| QQ @提及 处理 | 其他平台无此机制 |
| QQ 群号作为 group_id | 每个平台群标识符格式不同 |
| 消息格式转换 | 不同平台消息对象结构不同 |
| 指令前缀约定（`/dh`） | 使用层约定，非引擎逻辑 |

**原则**：凡涉及"怎么跟某个聊天平台通信"的代码，都属于客户端层。

---

## 8. 世界 Tick 设计

### 8.1 理念

世界是一个持续运行的时钟。即使没有玩家行动，世界也在演化。

### 8.2 Tick 周期

| 周期类型 | 间隔 | 执行内容 |
|---|---|---|
| 微观 Tick | 秒级 | 事件队列检查、玩家行动响应 |
| 修炼 Tick | 分钟级 | 托管角色自动修炼、修为进度增长 |
| 势力 Tick | 小时级 | 势力自动演化（小规模变动）、经济调整 |
| 世界 Tick | 日级 | CHAOS 潜伏度检查、天道修正评估、灵气流向更新 |

### 8.3 单次 Tick 流程

```
1. advance_time(delta)
   → CycleTime 递增
   → 季节/天气可能变化

2. tick_autopilot()
   → 托管角色自动修炼（固定小额修为增益）
   → 托管角色在正式事件中自动提交保守行动

3. tick_passive_evolution()
   → 势力自动演化（扩张/收缩/联盟变化）
   → 经济自动调整（供需/物价）
   → CHAOS 潜伏度递增检查
   → 灵气流向微调

4. tick_event_queue()
   → 检查是否有事件满足触发条件
   → 满足则入队，按优先级处理

5. persist()
   → 将最新状态 flush 到磁盘
   → 追加 EVENT_LOG 条目
```

### 8.4 优先级

```
玩家行动 > 微观 Tick > 修炼 Tick > 势力 Tick > 世界 Tick
```

玩家输入在任何时候打断当前 Tick 流程，走"玩家输入 → 引擎判断 → 响应"路径。Tick 只在无人行动时默默运转。

### 8.5 与当前实现的差异

当前实现是"触发式"——玩家发言才推进世界。Tick 机制引入后，世界自主运转，玩家只是介入点。这是从"跑团机器人"到"世界模拟器"的根本转变。

---

## 9. World State 设计

### 9.1 理念

World State 是世界的当前快照。树形分层，高层覆盖低层。

### 9.2 层级结构

```
WorldState
│
├── meta
│   ├── seed                    # 世界种子
│   ├── cycle_time              # 当前周期
│   ├── version                 # 状态格式版本
│   └── created_at
│
├── global
│   ├── phase                   # 世界阶段（动荡/稳定/崩解/重组）
│   ├── chaos_level             # CHAOS 活跃度
│   ├── tiandao_activity        # 天道调节强度
│   └── leyline_flow            # 灵气主流向
│
├── regions[5]
│   └── {region_name}
│       ├── phase               # 区域阶段
│       ├── subregions[]        # 子区域列表
│       ├── leyline_state       # 灵脉状态
│       ├── spirit_density      # 灵气浓度
│       └── weather             # 当前天气
│
├── actors[]
│   ├── characters[]            # 玩家角色
│   │   └── {slot_id}
│   │       ├── identity        # IDENTITY_STATE
│   │       ├── core            # CORE_STATE（灵根/天赋/缺陷）
│   │       ├── method          # METHOD_STATE（路径/进度/突破）
│   │       ├── resource        # RESOURCE_STATE（持有/货币）
│   │       ├── causal          # CAUSAL_STATE（因果债/回响）
│   │       ├── faction         # FACTION_STATE（所属/关系）
│   │       ├── hp              # {current, max}
│   │       ├── mp              # {current, max}
│   │       ├── afflictions[]   # 持续病症
│   │       └── combat_status[] # 战斗临时状态
│   │
│   └── npcs[]
│       └── {npc_id}
│           ├── name
│           ├── role
│           ├── location
│           └── relationships[]
│
├── factions[]
│   └── {faction_id}
│       ├── name
│       ├── origin
│       ├── territory
│       ├── resources[]
│       ├── goals
│       └── relations[]
│
├── entities[]
│   ├── locations[]
│   │   └── {location_id}
│   │       ├── name, region, type, state
│   │       └── features[]
│   │
│   └── anomalies[]
│       └── {anomaly_id}
│           ├── type, scope, state, source
│           └── convergence_path
│
├── causal
│   ├── links[]                 # 因果链接
│   │   └── {link_id}
│   │       ├── from_event, to_event
│   │       ├── debt_amount
│   │       ├── status          # untriggered/bound/resonating/completed/residual
│   │       └── resolution[]
│   │
│   └── resonances[]            # 因果回响
│       └── {resonance_id}
│           ├── trigger_event
│           ├── reference_debts[]
│           └── effect
│
└── event_log[]                 # 事件历史（只增不改）
    └── {event_id}
        ├── timestamp, type
        ├── participants[]
        ├── result
        ├── state_changes[]
        ├── causal_links[]
        └── residuals[]
```

### 9.3 设计约束

| 约束 | 说明 |
|---|---|
| 高层覆盖低层 | 优先级：META > GLOBAL > REGION > ACTOR > FACTION > ENTITY > CAUSAL > CHAOS > EVENT_LOG |
| 事件历史只增不改 | EVENT_LOG 不可删除、修改、覆盖。新发现只能通过新条目或附注实现 |
| 状态更新原子提交 | 一次事件的所有状态变化要么全部生效，要么全部无效 |
| 快照可回滚 | 每次正式事件结算前拍快照，支持整体回退到任意快照点 |
| 保护字段不可篡改 | AI 通过 STATE_DELTA 写入时，保护字段（六维/修为进度/生存状态等）由代码钳制，AI 不能自由修改 |

---

## 10. Event Engine 设计

### 10.1 理念

Event Engine 是世界的触发器和结算器。它决定"什么时候发生什么事"，以及"发生后世界怎么变"。

### 10.2 事件分类

只有六类正式事件，不得新增第七类：

| 类型 | 触发条件 | 涉及模块 |
|---|---|---|
| 势力冲突 | 势力目标冲突 + 资源争夺 + 关系恶化 | faction + resource + entity |
| 灵脉资源 | 灵气流向变化 + 灵脉状态变化 + 资源枯竭 | resource + region + chaos |
| 修行突破 | 修为进度满 + 突破检定触发 | cultivation + core + causal |
| 因果回响 | 因果债累积到阈值 + 事件触发时概率回响 | causal + event + chaos |
| CHAOS 异常 | CHAOS 潜伏度超阈值 + 天道修正延迟 | chaos + region + entity |
| 遗迹与机缘 | 地点状态变化 + 探索触发 + 因果承载 | exploration + entity + causal |

### 10.3 事件生命周期

```
潜伏 → 显现 → 扩展 → 分化 → 临界 → 收敛/崩解/重组 → 结束 → 残留
```

每个阶段至少有一个玩家可介入的节点。不得在同一轮跳过玩家可介入节点完成整条事件链。

### 10.4 事件触发方式

| 触发源 | 说明 |
|---|---|
| 玩家行动 | 玩家发言被判定为触发正式事件 |
| Tick 自动 | 势力 Tick / 世界 Tick 检测到条件满足 |
| 因果回响 | 因果债累积触发回响事件 |
| CHAOS 临界 | 异常状态推进到临界 |
| 编剧敕令 | GM 通过 decree 指定事件发生 |

### 10.5 事件结算流程

```
1. 触发检测
   → 判定事件类型
   → 确定参与角色

2. 行动收集
   → 反应式叙事：即时反馈，无需等待
   → 正式事件：多人锁定回合制，等待所有参与者提交行动
   → 超时处理：托管角色自动提交保守行动，或 GM 强制结算

3. 统一结算
   → 代码摇骰/查表决定客观结果
   → AI 将客观结果写成叙事
   → STATE_DELTA 解析并写入状态

4. 状态同步
   → 更新 World State 所有受影响区域
   → 追加 EVENT_LOG
   → 推进因果链
   → 检查天道响应

5. 输出
   → 按对话协议输出叙事
   → 停在互动点
```

### 10.6 反应式叙事 vs 正式事件

| 维度 | 反应式叙事 | 正式事件 |
|---|---|---|
| 触发 | 玩家日常发言 | 玩家行动命中六类事件 / Tick 自动触发 |
| 等待 | 不等待，即时反馈 | 等待所有参与者提交行动 |
| 状态变化 | 微小或无 | 显著，必须同步 World State |
| EVENT_LOG | 可选记录 | 必须记录 |
| 回合锁定 | 无 | 有 |

---

## 11. Memory Engine 设计

### 11.1 理念

Memory Engine 是世界的长期记忆。它不是数据库，是因果链 + 历史记录 + 角色档案的统一管理器。

### 11.2 记忆分层

| 层 | 内容 | 持久性 | 修改规则 |
|---|---|---|---|
| 世界记忆 | EVENT_LOG（事件历史） | 永久 | 只增不改 |
| 因果记忆 | 因果链（债务/回响/承接） | 永久 | 状态可流转，但记录不可删除 |
| 角色记忆 | 玩家档案（PROFILE） | 永久 | 按规则修改，保护字段受限 |
| 势力记忆 | 势力关系/目标/历史 | 永久 | 动态演化 |
| 决策记忆 | 决策日志（GM/系统决策） | 永久 | 只增不改 |
| 会话记忆 | 当前回合锁定状态/战斗状态 | 临时 | 团结束时归档或清空 |

### 11.3 核心接口

| 接口 | 说明 |
|---|---|
| `record_event(event)` | 追加一条事件到 EVENT_LOG。不可删除。 |
| `query_events(filter)` | 按类型/时间/参与者/区域查询事件。 |
| `get_profile(actor_id)` | 获取角色完整档案。 |
| `update_profile(actor_id, delta)` | 更新角色档案。走保护字段校验。 |
| `add_causal_debt(source, target, amount)` | 新增一笔因果债。 |
| `surface_causal_debt(actor_id)` | 检查并触发到期因果债的回响。 |
| `snapshot()` | 拍摄当前完整状态快照（用于回滚）。 |
| `rollback(snapshot_id)` | 回退到指定快照。整体性回退，不可部分撤销。 |
| `get_decision_log(group_id, date)` | 获取决策日志。 |

### 11.4 快照与回滚

| 规则 | 说明 |
|---|---|
| 快照时机 | 每次正式事件结算前、每次 AI 输出前、每次 decree 执行前 |
| 快照内容 | World State + 所有 Actor Profile + EVENT_LOG + Campaign 状态的深拷贝 |
| 保留数量 | 最近 N 条（默认 50），更早的自动丢弃 |
| 回滚范围 | 整体性：世界状态/角色档案/团史/管理操作一并回退 |
| 回滚限制 | 战斗中的逐回合叙事不产生独立快照（MVP 阶段） |
| EVENT_LOG 一致性 | 正常游戏不回滚 EVENT_LOG；管理员主动 rollback 时，回滚点之后的事件记录一并清除 |

---

## 12. AI Adapter 设计

### 12.1 理念

AI 是世界的解释器，不是世界的运行者。

真正运行世界的是 LingXu Engine 的代码（骰子、校验、状态机、因果网络）。AI 只负责两件事：

1. **将代码的客观结果写成人类可读的叙事**
2. **在代码留出的自由度内做出合理判断**（比如"这次行动该不该让 NPC 关系变化"）

### 12.2 模块职责

| 模块 | 职责 |
|---|---|
| `adapter.py` | AIAdapter 抽象基类。定义 `call(prompt) → response` 接口。具体实现由客户端注入（AstrBot 的 LLM 提供商、OpenAI API、本地 Ollama 等）。引擎不关心 AI 是谁。 |
| `prompts.py` | Prompt 模板构建。将世界规则 + 当前状态 + 玩家行动组装成 LLM 输入。按场景动态装配：常驻规则（engine_rules）+ 区域档案（lore_dossier）+ 按需规则（combat/economy/death）+ 当前状态摘要。 |
| `interpreter.py` | STATE_DELTA 解析器。从 AI 回复中提取结构化状态变化。白名单操作 + 类型校验 + 保护字段拦截。这是 AI 文本→游戏状态的唯一通道。 |
| `resolver.py` | 编剧敕令处理器。接收 GM 指定的结果，要求 AI 安排合理来源，然后走正常 STATE_DELTA 路径。decree 不走特殊路径，它就是一条特殊的 STATE_DELTA。 |

### 12.3 "代码管数字，AI 管叙事"原则

| 领域 | 代码负责 | AI 负责 |
|---|---|---|
| 运气检定 | 1d20+(机缘-10) 摇骰，六档判定 | 根据档位写叙事方向（顺利/出岔子） |
| 突破检定 | 1d20+悟性 vs DC20 摇骰 | 写突破成功/失败的叙事 |
| 战斗结算 | 先攻/命中/伤害/状态效果全部摇骰 | 写战斗叙事 |
| 修为进度 | 按行动类型代码定增减量 | 写修炼感受 |
| 货币波动 | 代码钳制幅度（灵石±50/贡献点±20） | 判断该涨还是该跌 |
| NPC 关系 | 代码定幅度（±1/±2） | 判断是否涉及社交、涉及哪个 NPC |
| 死亡判定 | 代码计数死亡豁免次数 | 不得自行判定死亡，必须人类确认 |
| 病症恶化 | 代码计数未治疗轮数 | 判断是否引入/治愈病症 |

### 12.4 STATE_DELTA 协议

AI 输出中的状态变化必须以 `STATE_DELTA` 代码块标记。解析器按白名单操作处理：

| 操作 | 说明 | 校验规则 |
|---|---|---|
| `append_event` | 追加事件到 EVENT_LOG | 必须是六类之一，必须有参与者和结果 |
| `adjust_currency` | 调整灵石/贡献点 | 代码钳制幅度，不可为负 |
| `append_known_technique` | 角色学会新功法 | 功法必须存在于资产库 |
| `set_relation_delta` | NPC 关系变化 | 幅度由代码定（±1/±2） |
| `add_affliction` | 新增持续病症 | 必须来自病症池 |
| `cure_affliction` | 治愈病症 | 必须是已有病症 |
| `adjust_hp` | HP 变化 | 不可超过 max，归零走死亡协议 |
| `adjust_progress` | 修为进度变化 | 0~100 范围，代码定增减量 |
| `add_causal_debt` | 新增因果债 | 必须关联到具体事件 |
| `transfer_item` | 物品转手 | 给出方必须持有该物品 |
| `add_history_note` | 追加历史备注 | 区分 PUBLIC/PRIVATE/GM_ONLY |

不在白名单中的操作一律丢弃。保护字段（六维/灵根层序/生存状态等）不可通过 STATE_DELTA 直接修改，只能通过对应的系统模块（cultivation/combat/death_protocol）的代码路径修改。

### 12.5 Prompt 分层装配

| 层 | 加载时机 | 内容 |
|---|---|---|
| 常驻 | 每次 AI 调用 | engine_rules.md（压缩版） |
| 区域 | 按玩家当前区域 | lore_dossier.md 对应段落 |
| 按名 | 消息提到具体势力/资源/实体 | faction_resource_entity.md 对应条目 |
| 战斗 | `/dh combat` 期间 | combat_rules.md |
| 经济 | 涉及交易/物价 | economy_rules.md |
| 死亡 | 生存状态非 stable | death_protocol.md |
| 初始化 | `/dh start` 时一次 | campaign_seed.md |

---

## 附录：术语表

| 术语 | 定义 |
|---|---|
| Tick | 世界自主演化的一个时间步。即使无玩家也执行。 |
| Cycle | 游戏内时间单位。一次正式事件结算或一场战斗结束推进一个 Cycle。 |
| Actor | 世界中能行动的实体。包括玩家角色、NPC、势力。 |
| STATE_DELTA | AI 输出中标记状态变化的代码块。引擎解析后写入 World State。 |
| 保护字段 | 不可通过 STATE_DELTA 自由修改的字段，只能通过对应系统模块的代码路径修改。 |
| 因果债 | 已绑定但尚未兑现的因果链接。累积到阈值会触发回响事件。 |
| CHAOS | 灵气/因果/遗迹/空间/天道压力多层叠加造成的非常态变化。 |
| 灵墟 | 世界现象。古战场、宗门遗址、洞府、秘境、禁地、皇陵、时空异常、梦境等。 |
| 编剧敕令 | GM 通过 decree 指定剧情结果。AI 安排合理来源，走正常 STATE_DELTA 路径。 |
