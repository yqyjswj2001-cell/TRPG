# ORPHAN_MODULE_AUDIT.md — 孤儿模块审计报告

审计日期：2026-07-08（C-0 任务）
审计范围：`cultivation_state.py`、`npc_perception.py`、`npc_attribute_roller.py`
方法：全仓库 `import` 关系检索（含 `.` 相对导入与裸导入两种写法）+ 读源码判断设计意图。

**结论先行（分类）：**

| 模块 | 分类 | 一句话结论 |
|---|---|---|
| `cultivation_state.py` | **B：未来预留** | 设计完整、自称"LONG-A 第1阶段"，是 main.py 现有简化版修炼系统的**升级替代设计**，尚未接线 |
| `npc_perception.py` | **B：未来预留** | 设计完整、自称"B-8"，被两个测试文件间接引用验证正确性，但运行时无人调用 |
| `npc_attribute_roller.py` | **A′：一次性构建工具（非孤儿）** | 性质等同 `bestiary_generator.py` 等离线生成脚本，已完成过一次性产出，不是"半成品业务逻辑" |

> **⚠️ 重要补充（模块依赖检查阶段发现，见 DEPENDENCY_MAP.md）**：
> 在后续的模块依赖检查中发现，仓库里在**同一天内新增了四个文件**——
> `cultivation_technique.py`（"LONG-A 第2阶段"）、
> `spiritual_root.py`（"LONG-A 第3阶段"）、
> `breakthrough_manager.py`（"LONG-A 第4阶段"）、
> `cultivation_ability.py`（"LONG-A 第5阶段"）——它们互相 import、
> 并且 `breakthrough_manager.py` 反过来 import 了本节的
> `cultivation_state.py`（"LONG-A 第1阶段"），构成一条完整的 5 阶段
> 修炼子系统开发链。**这五个文件全部没有被 main.py 或任何已接入
> 运行时的模块引用，也没有任何测试文件覆盖**——本次审计判断这不是
> "废弃代码"，而是**正在进行中、尚未接线的大型并行开发**（文件
> 修改时间集中在 2026-07-08 18:23–18:54，明显是同一批连续提交）。
> 详见 `DEPENDENCY_MAP.md` 第 3 节。**这意味着 `cultivation_state.py`
> 的分类需要修正为"进行中的多阶段开发，第1阶段"，而不是孤立的
> "未来预留"设计草稿**——它已经有下游依赖（`breakthrough_manager.py`）
> 在用它了，只是整条链还没有接到 `main.py`。本次同样不擅自处理
> （不修改、不接线、不删除），仅记录事实供开发者确认整体进度。

---

## 1. `cultivation_state.py`

### 1.1 是否被运行代码 import
**否。** 全仓库检索 `import cultivation_state` / `from .cultivation_state` /
`from cultivation_state`，除模块自身文件外**零匹配**。`main.py`、
`world_tick.py`、`outcome_applier.py`、`event_outcome_resolver.py` 均未引用。

### 1.2 是否存在对应功能替代模块
**是，main.py 内已有一套更简单的平行实现，两者字段不重叠：**

- `main.py` 现有：`_REALMS`（[main.py:633](main.py:633)）、
  `_adjust_cultivation_progress()`（[main.py:764](main.py:764)）、
  `breakthrough_status` 字段读写（[main.py:683](main.py:683)、[main.py:701](main.py:701)）。
- `main.py` **完全没有** `foundation`（根基）/`bottleneck`（瓶颈）/
  `consecutive_failures`（连续失败）/`cultivation_modifier`（修炼倍率）
  这套字段——全仓库检索这四个关键字，只在 `cultivation_state.py` 自己
  的文件里出现。

也就是说：`cultivation_state.py` 不是重复实现，而是**明确设计为 main.py
现有系统的下一阶段升级**——文件头注释直接写"替代 main.py 中
`_adjust_cultivation_progress`"，且刻意让 `REALMS`/`CULTIVATION_PROGRESS_MAX`
与 main.py 现有常量对齐，`make_method_state_delta()` 也明确说明是"供
`OutcomeApplier` 使用"的 delta 构造器，走的是现有落地通道，不是另起炉灶。

### 1.3 是否只有测试引用
**连测试引用都没有。** 全仓库检索（含 `tools/`）不存在任何
`test_cultivation_state.py` 或在别的测试文件里 import 它的情况。这是
三个模块里"孤立程度最高"的一个——不但没接入运行时，连正确性都没有
自动化验证过。

### 1.4 是否仍有设计价值
**有，而且价值明确。** 代码质量本身不差：
- 有完整的旧存档迁移函数 `migrate_profile_cultivation()`，本身就是
  按"缺字段自动补全"的原则写的，跟本次 C-0 任务第三节的存档兼容性
  要求是同一种工程纪律。
- 数值全部 clamp（`clamp_foundation`/`clamp_bottleneck`），没有 AI
  自由发挥空间，符合项目"数值由代码算、AI不编数字"的既有原则。
- 是否要启用取决于产品节奏（是否要上"根基/瓶颈"这套更硬核的修炼
  深度机制），这是内容/玩法决策，不是工程判断，本审计不代为决定。

**建议：先补一个 `tools/test_cultivation_state.py` 做纯函数级验证**
（不需要接入 main.py 也能测，因为全是无副作用的计算函数），把"代码是否
正确"和"要不要启用"这两件事解耦。这不违反"禁止修改NPC逻辑/禁止新增
玩法"——只是给已存在的纯函数补测试，没有改变任何行为。

---

## 2. `npc_perception.py`

### 2.1 是否被运行代码 import
**否。** `main.py` 全文检索 `perception`/`Perception`/`感知` 均无匹配，
`npc_context.py`、`npc_interaction_executor.py`、`npc_behavior.py` 等
运行时 NPC 相关模块也都没有引用它。

### 2.2 是否存在对应功能替代模块
**没有直接替代，但有相邻能力。** `npc_relationship.py` 负责数值化的
"关系值计算"，`npc_behavior.py` 负责"行为倾向"，两者都不做
"NPC 观察玩家外貌/气息、按境界差生成印象描述"这件事——
`npc_perception.py` 的 `perceive_player()` 是目前唯一实现这块的代码，
不存在功能重叫的问题。

### 2.3 是否只有测试引用
**是部分测试引用，但不是自己的独立测试文件：**
- `tools/test_npc_relationship.py` 引用了
  `from npc_perception import observe_player_with_memory, NPCPerceptionResult`
- `tools/test_player_appearance.py` 引用了
  `from npc_perception import perceive_player, _determine_perception_depth`

也就是说这个模块的正确性**有测试背书**，只是没有被生产代码路径调用——
跟 `cultivation_state.py`"连测试都没有"的情况不一样，风险等级更低。

### 2.4 是否仍有设计价值
**有。** 文件头注释标注"B-8"、内部又有"B-10"关系状态字段引用
（`relationship_state`），说明这是按某个分阶段路线图（B系列）预先写好、
等待后续阶段接入 `npc_context.py`/`_build_system_prompt` 的能力模块。
刻意遵守了"不读取隐藏字段（hidden_hook）"的项目级隐私约束，设计立场
和现有代码一致。

**建议：不需要新建测试**（已有间接测试覆盖），但应确认它是否该在
`npc_context.py` 的 `build_npc_context_for_ai()` 里被调用——这个决策
留给开发者，本审计只陈述事实。

---

## 3. `npc_attribute_roller.py`

### 3.1 是否被运行代码 import
**否，且不应该被 import。** 这个文件带 `if __name__ == "__main__":
main()` 入口，本质是命令行脚本：`python npc_attribute_roller.py` 一次性
生成 `data/major_npc_slots.json`（51条）和 `data/minor_npc_slots.json`
（300条）"属性签"。

### 3.2 是否存在对应功能替代模块
不适用——它跟 `bestiary_generator.py`/`item_generator.py`/
`technique_generator.py`/`place_generator.py` 等一系列离线资产生成脚本
是**同一类工具**，性质是"数据编译工具"，不是运行时业务逻辑模块。

### 3.3 是否只有测试引用
无测试引用，也不需要——它的产出是静态 JSON 文件，正确性靠"生成结果是否
符合数值范围"人工/离线验证，不是热路径代码。

### 3.4 是否仍有设计价值
**有，且已经实现了价值**：其产出 `data/major_npc_slots.json` /
`data/minor_npc_slots.json` 目前**确认存在于 `data/` 目录**，但本次
检索确认**没有任何运行时代码读取这两个文件**——真正被 `npc_registry.py`
（[npc_registry.py:87](npc_registry.py:87)、[npc_registry.py:102](npc_registry.py:102)）
和 `main.py`（[main.py:1645](main.py:1645)、[main.py:1654](main.py:1654)）
加载的是 `data/major_npcs.json` / `data/minor_npcs.json`（**不带
`_slots`**，字段更完整，显然是拿这批"属性签"当种子、经过后续离线加工
——大概率是人工/LLM 离线补全姓名性格背景——生成的最终成品）。

**这不是废弃候选，而是流水线中间产物生成器**：`_slots.json` 是半成品，
`npc_attribute_roller.py` 的职责在生成半成品的那一刻就已经结束。除非
未来要重新批量生成 NPC 属性签（比如扩大区域、新增势力），否则它不需要
被"接入"任何地方。

**分类不适用严格的 A/B/C**（这三类是为"业务逻辑模块该不该被程序调用"
设计的），更准确的类别是"离线工具，职责已完成，按需重新运行"——建议
和其他 `*_generator.py` 一起归入同一份工具清单，避免下次审计又把它
错判成孤儿代码。

---

## 4. 汇总与后续处理建议（不擅自处理，等待确认）

| 模块 | 风险等级 | 本审计的动作 | 需要开发者确认的问题 |
|---|---|---|---|
| `cultivation_state.py` | 中（零测试覆盖的完整子系统，容易在未来被误删或被重复实现） | 无代码改动，仅报告 | 是否计划启用"根基/瓶颈"深度修炼机制？如果近期不打算启用，是否要至少补一份纯函数测试防止腐化？ |
| `npc_perception.py` | 低（有间接测试背书，只是没接入 prompt 组装链） | 无代码改动，仅报告 | 是否应该在 `npc_context.py` 里接入 `perceive_player()`，让 NPC 感知实际影响叙事？ |
| `npc_attribute_roller.py` | 低（离线工具，产出已被消费一次） | 无代码改动，仅报告；建议归档为"生成器工具"分类，不再列入孤儿模块观察名单 | 无需确认，仅需在下次同类审计时用正确的分类标签 |

**本次审计严格遵守"禁止直接删除"约束：以上三个文件未做任何修改。**

---

## 后续更新（2026-07-08 晚，跨会话追加）

上面三个模块目前的真实状态，供下一次审计/开发直接用，不用重新查一遍：

- **`cultivation_state.py`**：本审计建议的"补一份纯函数测试"已经完成——
  现在被 `tools/test_cultivation_system.py` 覆盖（该文件顶部
  `from cultivation_state import (...)`），且整条 LONG-A 五阶段修炼链
  已经全部接入 `main.py`（`/dh cultivate`/`/dh technique`/
  `/dh breakthrough`/`/dh ability`/`/dh sect` 等指令），不再是"未接线"
  状态，详见 `DEVELOPMENT_STATUS.md`「修炼系统（LONG-A）六模块接线复核
  明细」。
- **`npc_perception.py`**：已接入。经用户明确授权后，`npc_context.py`
  的 `build_npc_context_for_ai()` 在"NPC 对该玩家没有任何记忆"（首次
  相遇）时会调用 `perceive_player()` 生成一段基于外貌/气息的初见印象，
  不再直接返回空字符串。原来"有记忆走记忆上下文"的行为完全不变（向后
  兼容，不传新增的可选参数时函数签名/行为跟之前一致）。测试见
  tools/test_npc_context_perception.py。
- **`npc_attribute_roller.py`**：分类修正为"离线生成工具"（跟
  `bestiary_generator.py` 等同类）后一直没有变化，不需要再被列入
  孤儿模块观察名单。
