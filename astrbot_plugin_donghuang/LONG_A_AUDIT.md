# LONG_A_AUDIT.md — LONG-A 修炼系统审计

审计日期：2026-07-08（C-1 任务第二节）

**⚠️ 审计期间状态发生了实质性变化，必须先说明：** 任务下达时的前提是
"LONG-A 五个文件尚未接线"。但审计开始后不久，`main.py` 就被（并行的
另一个开发进程）实际修改，加入了对全部 LONG-A 模块的 import，并且
出现了**第六个文件 `sect_interface.py`（"LONG-A 第8阶段"）**。本审计
基于**审计完成时刻的真实代码状态**，不基于任务下达时的假设。本审计
过程中**没有做任何接线动作**——下面记录的接入行为都是本次会话开始
之前、由其他并行开发完成的，本次只负责如实核实和分类。

---

## 结论先行（分类）

| 模块 | 阶段 | 分类 | 一句话结论 |
|---|---|---|---|
| `cultivation_state.py` | 1 | **B：需要改造** | 已被 import，但零调用点；跟 main.py 现有修炼逻辑是平行实现，需要产品决策"何时切换"，不是简单接线问题 |
| `cultivation_technique.py` | 2 | **B：需要改造** | 已被 import，`TechniqueManager` 单例已能正常 `load()`；Outcome 白名单已就绪（`active_technique`/`known_techniques`）；但零调用点，且旧存档没有对应迁移调用 |
| `spiritual_root.py` | 3 | **A：可以接入（局部已接入）** | **唯一真正在跑的一条**：角色创建时调用 `generate_spiritual_root` 写入初始灵根；Outcome 白名单已就绪并有专门的嵌套合并逻辑（`_merge_spiritual_root_delta`）；rollback 无风险（数据在 profile 里，随快照走）|
| `breakthrough_manager.py` | 4 | **B：需要改造** | 已被 import（`BreakthroughManager`/`attempt_breakthrough`），零调用点；一旦启用会跟 main.py 现有的 `_apply_breakthrough` 直接产生功能重叠，必须先决定哪一套是权威实现 |
| `cultivation_ability.py` | 5 | **B：需要改造** | 已被 import，零调用点，且连 LONG-A 子系统内部都没有别的模块引用它（依赖链最末端）|
| `sect_interface.py` | 8（新发现） | **C：暂停** | 文件自己说明"只设计接口，不完整实现"；已被 import 但零调用点；Outcome 没有对应白名单字段（`CORE_STATE_WHITELIST`/`METHOD_STATE_WHITELIST` 都没有 `sect`）——即使想接，Outcome 这一层现在也接不住 |

---

## 逐项核对（任务要求的五个问题）

### 1. 是否有真实调用入口

用全文 grep 精确核对"类/函数被真正调用"而不是"被 import"：

| 符号 | 来源模块 | 是否被调用 | 调用点 |
|---|---|---|---|
| `generate_spiritual_root` | spiritual_root.py | **✅ 是** | `main.py._generate_initial_spiritual_root()`（[main.py:826](main.py:826)），角色创建时调用一次 |
| `extract_spiritual_root` / `calculate_cultivation_efficiency` / `calculate_technique_affinity` / `calculate_breakthrough_risk` / `describe_spiritual_root` | spiritual_root.py | ❌ 否 | 只在 import 列表出现 |
| `migrate_profile_spiritual_root` / `migrate_profile_cultivation` / `migrate_profile_technique` / `migrate_profile_abilities` / `migrate_profile_sect` | 各自模块 | ❌ 否 | 只在 import 列表出现——**意味着旧存档不会被迁移**，只有新建角色才会有 `spiritual_root` 字段 |
| `BreakthroughManager` / `attempt_breakthrough` | breakthrough_manager.py | ❌ 否 | 只在 import 列表出现 |
| `TechniqueManager` / `get_technique_manager` | cultivation_technique.py | ❌ 否 | 只在 import 列表出现（`TechniqueManager` 本身有 `load()` 方法，逻辑本身可独立运行/可测，只是没人调它） |
| `CultivationAbility` / `AbilityManager` | cultivation_ability.py | ❌ 否 | 只在 import 列表出现 |
| `SectInterface` / `SectInfo` | sect_interface.py | ❌ 否 | 只在 import 列表出现 |

**结论**：整条 LONG-A 链目前只有"新建角色时生成一份初始灵根数据"这一
个功能真正在跑，其余全部是"已导入、待调用"的状态。这跟
`DEVELOPMENT_STATUS.md` 里标注的 **PARTIAL** 一致。

### 2. 是否重复已有 profile 系统

**是，明确重复，且重复的是核心玩法逻辑：**

- `main.py` 现有 `_REALMS`（[main.py:633](main.py:633)）跟
  `cultivation_state.py` 的 `REALMS` 是同一份境界列表，字面量重复
  （两处硬编码，改一处很容易忘改另一处）。
- `main.py` 现有 `_apply_breakthrough()`（[main.py:668](main.py:668)）跟
  `breakthrough_manager.attempt_breakthrough()` 是同一个问题域的两套
  突破判定逻辑——前者没有"根基/瓶颈/灵根纯度/功法加成"这些概念，后者
  设计了完整的加成体系。两套并存但只有前者在跑。
- `main.py` 目前没有"功法系统"（学习/切换主修功法），
  `cultivation_technique.py` 是全新能力，不算重复；`cultivation_ability.py`
  （剑意/炼丹/炼器/阵法/符箓技能树）同理，是全新能力。
- `main.py` 现有的势力归属（`join_faction`/`leave_faction`）**不等于**
  `sect_interface.py` 设想的"宗门内部职位/贡献/师徒传承"——现有系统
  只有"属于哪个势力"，没有"在势力内部的位置"，`sect_interface.py`
  是对现有势力系统的深化，不是重复。

### 3. 是否与 Outcome 兼容

**分字段结论，不是非黑即白：**

- `spiritual_root`：✅ 完全兼容。`event_outcome.py` 的
  `CORE_STATE_WHITELIST`（[event_outcome.py:83](event_outcome.py:83)）已经
  把 `spiritual_root` 加入白名单，`outcome_applier.py` 也有专门的
  `_merge_spiritual_root_delta()`（[outcome_applier.py:465](outcome_applier.py:465)）
  处理数值增量+clamp、字符串绝对值、列表整体替换三种字段类型。这是
  目前唯一"接入质量"达到生产标准的一环。
- `foundation`/`bottleneck`/`consecutive_failures`/`cultivation_modifier`/
  `growth_stage`/`breakthrough_status`/`active_technique`/
  `known_techniques`/`abilities`：✅ 已在 `METHOD_STATE_WHITELIST`
  （[event_outcome.py:69](event_outcome.py:69)）注册，`outcome_applier.py`
  也有对应的数值 clamp 范围（`foundation: (0,200)`、`bottleneck: (0,5)`，
  [outcome_applier.py:54](outcome_applier.py:54)）。**但没有任何业务逻辑
  会真的生成写这些字段的 delta**——白名单已经就位，只是没人往里填数据，
  相当于"通道修好了，但没有车在跑"。
- `sect`：❌ 不兼容。`CORE_STATE_WHITELIST`/`METHOD_STATE_WHITELIST`
  都没有 `sect` 相关字段，如果现在就写一个 delta 尝试改 `FACTION_STATE.sect`
  或类似路径，会被 `OutcomeApplier` 当成"不在白名单"直接拒绝
  （这是正确的安全行为，不是 bug）。

### 4. 是否影响 rollback

**目前不影响，且预计未来也不会有结构性风险：**

- `/dh rollback` 靠的是 `_snapshot_group_state()` 对
  `world_state`/`player_profiles`/`event_log`/`campaign` 做深拷贝
  （[main.py:1843](main.py:1843)起）。LONG-A 写入的所有新字段（`spiritual_root`
  等）都是挂在 `profile["CORE_STATE"]`/`profile["METHOD_STATE"]` 这些
  已有 dict 树下的新 key，深拷贝对字段内容无感知、无差别处理，天然会
  被完整快照和回滚覆盖，不需要额外适配代码。
- `TechniqueManager`（`cultivation_technique.py` 里的模块级单例）是**只读静态目录数据**（从数据文件 `load()` 加载功法目录），跟
  `main.py` 现有的 `self.factions`/`self.items`/`self.talent_data` 这些
  静态资产是同一类角色——不属于"每个群的可变游戏状态"，天然不需要、
  也不应该被 rollback 覆盖。这是正确的设计，不是遗漏。
- **唯一需要留意的点**：一旦 `migrate_profile_*` 系列函数将来真的被
  接上（比如接入 `player_migration.py`，见 C-1 第五节），需要确认
  "迁移"发生的时机是在 rollback 快照*之前*还是*之后*一致——如果迁移
  逻辑在读档时无条件执行且是幂等的（多次跑结果一样），就不会有问题；
  本次审计确认这几个 `migrate_profile_*` 函数目前全部未被调用，所以
  这个风险目前是理论性的，等真正接线时需要重新检查一遍时机。

### 5. 是否值得进入主线

**分层回答，不是一个笼统的"值不值得"：**

- `spiritual_root.py` 的现状（只生成初始值）已经是安全的最小化接入，
  **可以维持现状**，不需要额外动作。
- 剩下五个文件要不要继续往前推、要不要真正开始调用，是**产品决策**
  （值不值得让"根基/瓶颈/功法/技能/宗门"这套更硬核的成长系统上线），
  不是工程判断——本审计不代为决定，只负责指出：如果决定推进，
  第一个要解决的不是接线本身，是"main.py 现有突破逻辑 vs
  breakthrough_manager 新逻辑，到底哪个是权威实现"这个功能重叠问题
  （第2节），否则会出现"两套突破判定同时存在、结果互相矛盾"的严重
  一致性风险。

---

## 建议处理顺序（仅供参考，不代为决定）

1. 明确"旧突破逻辑 vs breakthrough_manager"的切换计划（或者明确决定
   "LONG-A 用于未来版本，这一版先不切换"），避免两套逻辑同时被误用。
2. 如果决定继续推进，`migrate_profile_*` 系列应该接入统一的存档迁移
   入口（见 `player_migration.py`），而不是分散调用。
3. `sect_interface.py` 现在连 Outcome 白名单都没有，若要往前推进，
   第一步是先给 `event_outcome.py` 补 `sect` 相关白名单字段，这属于
   "修改 Outcome 结构"，按本阶段禁止事项，**不在本次处理范围**。
4. 建议给已经零测试覆盖的 `cultivation_technique.py`/
   `breakthrough_manager.py`/`cultivation_ability.py`/`sect_interface.py`
   补纯函数级测试——这些都是无副作用计算 + dataclass，测试成本低，
   而且能在它们真正接线之前提前暴露设计缺陷。

## 本次未做的事（明确边界）

- 未修改 `EventPool`/`Outcome` 结构。
- 未新增任何 LONG-A 与主线的调用连接。
- 未删除任何文件。
- 未对 `main.py` 现有修炼逻辑做任何改动。
