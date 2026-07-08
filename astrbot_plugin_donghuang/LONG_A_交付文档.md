# LONG-A 交付文档：玩家修仙成长生态系统

## 1. 修改文件

| 文件 | 修改内容 |
|------|---------|
| `event_outcome.py` | 新增 `METHOD_STATE_WHITELIST`、`CORE_STATE_WHITELIST` 白名单 |
| `outcome_applier.py` | 新增 `_apply_method_state_delta`、`_apply_core_state_delta`、`_merge_spiritual_root_delta`、`_clamp_cultivation_field` 方法；扩展 `_FIELD_RANGES` |
| `main.py` | 导入新模块；扩展 `_PROFILE_PROTECTED_NESTED_FIELDS`；新增 `_generate_initial_spiritual_root` 辅助函数；角色生成时初始化新字段；`/dh mycard` 展示新信息；突破流程替换为 BreakthroughManager（保存结果避免重复掷骰）；NPC 记忆使用已保存结果；EventPool 生成修炼事件；新增 `/dh cultivate` 指令；旧存档迁移 |
| `world_context.py` | `_extract_player_status` 扩展：显示境界/进度/根基/瓶颈/灵根 |
| `npc_perception.py` | `perceive_player` 扩展：敏锐深度感知修炼状态，洞察深度感知灵根异变 |
| `README.md` | 新增 LONG-A 模块说明和指令 |
| `使用说明.md` | 新增修炼系统升级说明和 `/dh cultivate` 指令 |

## 2. 新增文件

| 文件 | 行数 | 功能 |
|------|------|------|
| `cultivation_state.py` | ~535 | 修炼状态模型：CultivationState 数据类、增益计算、根基/瓶颈变化、突破DC、旧存档迁移 |
| `spiritual_root.py` | ~470 | 灵根系统：SpiritualRoot 数据类、五行+异变灵根、纯度/效率计算、功法亲和度、突破风险、生成函数 |
| `cultivation_technique.py` | ~390 | 功法系统：CultivationTechnique 数据类、TechniqueManager 加载器、速度/突破加成计算 |
| `breakthrough_manager.py` | ~560 | 突破体系：BreakthroughManager、BreakthroughResult、generate_cultivation_events（EventPool集成） |
| `cultivation_ability.py` | ~340 | 技能能力系统：CultivationAbility、AbilityManager、五类技能升级/经验/效果 |
| `sect_interface.py` | ~290 | 宗门成长接口：SectInterface、SectInfo、贡献/职位/传承/师徒（接口预留） |
| `tools/test_cultivation_system.py` | ~730 | 测试：166 项全绿 |

## 3. 数据结构

### METHOD_STATE 扩展字段

```
METHOD_STATE: {
    primary_path: str,           # 已有
    growth_stage: str,           # 已有
    breakthrough_status: str,    # 已有
    known_techniques: list,      # 已有
    progress: int,               # 已有 (0~100)
    # ── LONG-A 新增 ──
    foundation: int,             # 根基值 0~200，默认 100
    bottleneck: int,             # 瓶颈等级 0~5，默认 0
    consecutive_failures: int,   # 连续突破失败次数，默认 0
    cultivation_modifier: float, # 修炼倍率 0.1~3.0，默认 1.0
    active_technique: str,       # 当前主修功法名称，默认 ""
    abilities: {                 # 技能能力表
        "剑意": {"level": 0, "exp": 0, "max_level": 5},
        "炼丹": {"level": 0, "exp": 0, "max_level": 5},
        "炼器": {"level": 0, "exp": 0, "max_level": 5},
        "阵法": {"level": 0, "exp": 0, "max_level": 5},
        "符箓": {"level": 0, "exp": 0, "max_level": 5},
    },
}
```

### CORE_STATE 扩展字段

```
CORE_STATE: {
    spirit_root_tier: int,       # 已有
    spirit_root_element: str,    # 已有
    stability: str,              # 已有
    chaos_influence: str,        # 已有
    # ── LONG-A 新增 ──
    spiritual_root: {
        primary: str,            # 主灵根属性（金/木/水/火/土）
        secondary: list,         # 副灵根属性列表
        purity: float,           # 灵根纯度 0.1~1.0
        mutation: str,           # 异变类型（none/雷/冰/风/空间）
        efficiency: float,       # 修炼效率倍率 0.3~3.0
    },
}
```

### FACTION_STATE 扩展字段

```
FACTION_STATE: {
    affiliation: str,            # 已有
    relations: dict,             # 已有
    # ── LONG-A 新增 ──
    sect: {
        name: str,               # 宗门名称
        position: str,           # 职位
        contribution: int,       # 贡献点
        contribution_rank: int,  # 贡献等级
        heritage: list,          # 传承列表
        master: str,             # 师父名称
        disciples: list,         # 徒弟列表
        joined_cycle: int,       # 加入周期
        status: str,             # 状态（active/suspended/expelled）
    },
}
```

## 4. 流程图

### 4.1 修炼增益流程

```
玩家行动（打坐/战斗/服用丹药）
    │
    ▼
暗定运气检定 → luck_tier（极大成功/大成功/成功/失败/大失败）
    │
    ▼
基础增益 = _CULTIVATION_GAIN_BY_LUCK[luck_tier]
    │
    ▼
calculate_cultivation_gain()
    ├── 灵根效率 × spiritual_root.efficiency
    ├── 功法速度 × technique_speed_bonus
    ├── 修炼倍率 × cultivation_modifier
    ├── 瓶颈衰减 × (1 - bottleneck × 0.15)
    └── 环境加成 + environment_bonus
    │
    ▼
adjust_cultivation_progress() → clamp(0, 100)
    │
    ▼
写入 profile.METHOD_STATE.progress
    │
    ▼
修炼成功时：根基 +1
```

### 4.2 突破流程

```
修为进度 >= 100 → 触发突破事件
    │
    ▼
BreakthroughManager.roll_breakthrough(profile)
    ├── 计算 DC = 20 + 境界修正 + 瓶颈修正 - 根基修正 - 功法加成
    ├── 掷骤 1d20 + 悟性修正
    ├── 判断 success = roll >= DC
    └── 返回 BreakthroughResult（只掷一次骰！）
    │
    ▼
BreakthroughManager.apply_breakthrough(result, profile)
    ├── 成功：境界提升 + HP增加 + 六维精进(30%) + 根基恢复
    └── 失败：进度打对折 + 根基损耗 + 气血损伤 + 可能病症(40%)
    │
    ▼
generate_cultivation_events(result, profile, event_pool, group_id)
    ├── 成功+大境界 → EventPool.add("突破异象")
    ├── 成功+异变+大境界 → EventPool.add("天劫降临")（概率触发）
    ├── 成功+20%概率 → EventPool.add("功法顿悟")
    └── 失败 → EventPool.add("闭关走火")
    │
    ▼
NPC 感知记忆（使用已保存的 result，不重新掷骰）
    └── 突破成功 → npc_memory_manager.add_memory("此人气息已不同往日")
```

### 4.3 OutcomeApplier 修炼 Delta 流程

```
EventOutcome.profile_delta
    │
    ▼
_apply_profile_delta()
    ├── field == "METHOD_STATE" → _apply_method_state_delta()
    │   ├── 白名单校验（METHOD_STATE_WHITELIST）
    │   ├── abilities → _merge_dict_no_clamp
    │   ├── known_techniques → 整体替换
    │   └── 数值字段 → 增量 + _clamp_cultivation_field
    │
    ├── field == "CORE_STATE" → _apply_core_state_delta()
    │   ├── 白名单校验（CORE_STATE_WHITELIST）
    │   └── spiritual_root → _merge_spiritual_root_delta()
    │       ├── purity/efficiency → 增量 + clamp
    │       ├── secondary → 整体替换
    │       └── 其他 → 绝对值赋值
    │
    └── field == "cultivation_realm" → 代码通道直接写入
```

## 5. 测试结果

```
============================================================
LONG-A 修仙成长生态系统测试
============================================================
=== cultivation_state 测试 ===
=== spiritual_root 测试 ===
=== cultivation_ability 测试 ===
=== sect_interface 测试 ===
=== event_outcome 白名单测试 ===
=== outcome_applier 测试 ===
=== 旧存档兼容测试 ===
=== 多玩家隔离测试 ===
=== 突破管理器 + 修炼事件测试 ===
============================================================
结果：166 通过，0 失败
============================================================
```

测试覆盖：
- cultivation_state: 境界列表、索引、下一境界、大境界判断、提取、增益计算、瓶颈衰减、根基变化、瓶颈变化、突破DC、进度调整、倍率计算、delta构造
- spiritual_root: 五行灵根、特殊灵根、生成、效率计算、功法亲和度、突破风险、纯度变化、clamp、提取、旧存档兼容、描述、能力亲和度、delta构造
- cultivation_ability: 技能数据类、管理器提取、经验获取、技能升级、检定、效果、描述、delta、旧存档迁移
- sect_interface: 宗门信息、加入/退出检查、贡献计算、职位晋升、传承、描述、delta、旧存档迁移
- event_outcome: 白名单完整性
- outcome_applier: METHOD_STATE delta、CORE_STATE delta、cultivation_realm 通道
- 旧存档兼容: cultivation/spiritual_root/abilities/sect 迁移
- 多玩家隔离: 玩家间状态隔离
- 突破+事件: 突破检定、结果不可变性（Phase 7 bug fix）、事件模板、事件生成、不同结果类型

## 6. 兼容性

### 旧存档自动迁移

所有新字段都通过 `migrate_profile_*` 函数自动补全，不破坏已有数据：

| 迁移函数 | 补充字段 | 推导来源 |
|---------|---------|---------|
| `migrate_profile_cultivation` | foundation, bottleneck, consecutive_failures, cultivation_modifier, abilities, active_technique, technique_details | 默认值 |
| `migrate_profile_spiritual_root` | CORE_STATE.spiritual_root | spirit_root_tier + spirit_root_element |
| `migrate_profile_technique` | active_technique, technique_details, technique_exp | 默认值 |
| `migrate_profile_abilities` | METHOD_STATE.abilities | 默认空能力表 |
| `migrate_profile_sect` | FACTION_STATE.sect | 默认空宗门 |

### 回退兼容

- 如果新模块导入失败（`_LONG_A_AVAILABLE = False`），所有功能回退到旧路径
- 旧的 `_roll_breakthrough` / `_apply_breakthrough` 函数保留，新路径不可用时自动使用
- `/dh mycard` 在新系统不可用时回退到旧格式

## 7. 未完成部分

### 7.1 宗门系统（Phase 8）仅接口预留

- `SectInterface` 只定义了接口，未实现：
  - 实际的宗门加入/退出流程
  - 贡献点获取的完整规则（任务/战斗/资源/日常）
  - 职位晋升的事件触发
  - 传承的具体效果（功法传承/秘术传承/血脉传承/器物传承/道心传承）
  - 师徒关系的双向绑定和任务系统
  - 宗门对修为/突破的加成效果

### 7.2 功法系统未完全集成

- `TechniqueManager` 可加载 JSONL 功法数据，但：
  - 未与 `/dh mycard` 的"已知功法"展示深度集成（只显示名称不显示详情）
  - 功法熟练度（technique_exp）未与修炼流程联动
  - 功法学习判定（`can_learn_technique`）未接入任何指令
  - 功法效果（`apply_technique_effect`）未在战斗/修炼中实际调用

### 7.3 技能能力未与行动联动

- 五类技能（剑意/炼丹/炼器/阵法/符箓）的升级/检定逻辑已实现，但：
  - 未与日常修炼行动联动（如"练剑"应增加剑意经验）
  - 未与战斗联动（剑意等级应影响攻击加成）
  - 未与物品制作联动（炼丹/炼器等级应影响成功率/品质）
  - 未新增 `/dh ability` 指令查看技能详情

### 7.4 修炼事件的生命周期管理

- `generate_cultivation_events` 通过 EventPool 创建事件，但：
  - 未实现事件的自动推进（萌芽→扩散→进行中→收束→结束）
  - 天劫事件未实现渡劫检定逻辑
  - 闭关走火事件未实现自动消退机制
  - 功法顿悟事件未与实际功法学习联动

### 7.5 NPC 感知的精细化

- 当前 NPC 感知只覆盖旁观者类型（百姓/散修/外门弟子/内门弟子），未：
  - 区分 NPC 与玩家的实际距离/区域
  - 根据NPC修为差异产生不同深度的感知
  - 与 NPCBehavior 的 help_probability/price_bias 联动

## 8. 风险说明

### 8.1 性能风险

- **功法加载**：`TechniqueManager.load()` 在首次调用时加载所有 JSONL 文件，数据量较大（数百个文件、数千条功法），可能增加启动时间。缓解：使用全局单例，只加载一次。
- **旧存档迁移**：每次加载 profiles 时对所有角色执行 5 个迁移函数，角色数量多时可能增加加载时间。缓解：迁移函数都是轻量级 `.get()` 检查，开销极小。

### 8.2 数据一致性风险

- **突破结果复用**：Phase 7 修复后，突破结果通过 `_bt_results` 字典在同一个 `_resolve_turn_lock` 调用内传递。如果未来有其他代码路径触发突破（如 `/dh decree`），需要同样保存结果，否则 NPC 记忆会重新掷骰。
- **EventPool 事件与 profile 状态**：修炼事件通过 EventPool 创建，但 EventPool 事件的生命周期（萌芽→结束→归档）与 profile 的突破结果状态是独立的。如果事件被归档但 profile 未更新，或反之，可能出现叙事不一致。

### 8.3 白名单安全风险

- 新增的 `METHOD_STATE_WHITELIST` 和 `CORE_STATE_WHITELIST` 允许通过 OutcomeApplier 写入修炼相关字段。虽然 `_PROFILE_PROTECTED_NESTED_FIELDS` 阻止了 AI STATE_DELTA 通道的直接写入，但代码通道（如突破管理器）可以绕过保护。这是设计意图，但需要确保所有代码路径都经过审查。
- `cultivation_realm` 的特殊通道允许通过 `profile_delta` 直接写入，绕过白名单检查。这是突破流程的必要设计，但需要确保只有受信任的代码路径使用此通道。

### 8.4 数值平衡风险

- **灵根效率**：天灵根（纯度90%+）修炼效率 2.0，废灵根（纯度<30%）效率 0.4，差距 5 倍。如果灵根生成概率分布不合理，可能导致部分角色成长过快或过慢。
- **瓶颈累积**：连续突破失败每 2 次增加 1 级瓶颈，每级瓶颈减少 15% 修炼效率。5 级瓶颈时效率仅剩 25%，可能导致角色陷入"越失败越难成功"的恶性循环。缓解：突破成功时瓶颈 -1，且瓶颈不自动增加（只在连续失败时增加）。
- **异变灵根天劫**：异变灵根在大境界突破时天劫概率可达 15%~25%。如果天劫检定未实现（当前只创建事件不执行检定），可能导致叙事中出现天劫但无实际后果。

### 8.5 向后兼容风险

- 新增的 `spiritual_root` 子结构可能与未来 AstrBot 版本的 profile 结构冲突。缓解：使用独立的子字典，不修改已有字段。
- 旧存档迁移在每次加载时执行，如果迁移逻辑有 bug，可能反复修改 profile。缓解：迁移函数使用 `if "field" not in dict` 检查，只补全缺失字段，不会覆盖已有值。
