# astrbot_plugin_donghuang — 东荒修仙 TRPG 专属跑团机器人

一个专门服务于"东荒修仙"这套硬核世界观的 AstrBot 插件，包含 AI 驱动的
剧情叙事、多人锁定回合制结算、死亡与重生协议。跟通用的 `astrbot_plugin_trpg`
是完全独立的两个插件（互不 import，各自可以单独复制部署）。

> 想知道具体怎么玩（指令示例、常见问题），请看
> [使用说明.md](使用说明.md)。本文件只讲安装、依赖、数据结构和世界观文件
> 拆分的技术信息。

## 安装方法

1. 把整个 `astrbot_plugin_donghuang` 文件夹复制到 AstrBot 的插件目录：
   ```
   AstrBot/data/plugins/astrbot_plugin_donghuang/
   ```
2. 重启 AstrBot，或在管理面板「插件管理」页面点击刷新/重载。
3. 在群里发送 `/dh help`，机器人回复指令列表说明安装成功。

## 依赖

无第三方依赖，只用 Python 标准库。所有剧情生成/事件判定/游戏内外判断都
需要 AstrBot 当前启用一个 LLM 提供商（本地 Ollama/LM Studio 或云端均可）。

> ⚠️ 本地模型如果不支持提示词缓存复用，每条消息的响应速度取决于喂给模型
> 的提示词体量（见下方"世界观文件拆分"），建议先用小规模测试确认延迟
> 可以接受。

## 世界观文件拆分（`world/` 子文件夹）

原始的《东荒修仙TRPG世界运行总纲.txt》被拆成若干文件，全部放在插件自己
的 `world/` 子文件夹里（不依赖仓库根目录的任何文件，保证插件文件夹单独
复制出去也能正常跑）：

| 文件 | 内容 | 什么时候加载 |
| --- | --- | --- |
| `engine_rules.md` | 世界物理法则、GM稳定协议、对话输出协议、RUN_LOOP、玩家档案定义（含数值例外修订汇总）、最终硬校验 | **每次 AI 调用都加载**，目标体量 1万~1.5万字 |
| `lore_dossier.md` | 五个区域的档案、历史时间线、隐藏影响者、未来事件类型 | 按玩家当前区域查对应段落 |
| `faction_resource_entity.md` | 势力/资源/实体的运行规则和索引 | 只在消息提到具体名字时查阅 |
| `campaign_seed.md` | 固定初始化种子 `EAST-WORLD-SEED-01`，世界骨架的原始参考 | 只在 `/dh start` 初始化时加载一次 |
| `death_protocol.md` | 死亡/重生协议 | 只在某玩家"生存状态"非 stable 时加载 |
| `economy_rules.md` | 灵石/贡献点货币体系、品级换算参考、地域物价倾向、动态经济事件、物品转手规则 | 只在明显涉及交易/物价/经济类事件时加载 |
| `combat_rules.md` | 回合制战斗系统规范：核心参数、状态效果池、回合流程伪代码、AI接口规范、完整战斗示例 | 只在 `/dh combat` 发起战斗、直到战斗结束期间加载 |

修改这套世界观规则，直接编辑 `world/` 下对应的文件即可，不需要改代码
（除非要新增槽位数量、修改初始 WORLD_STATE 等结构性内容，这些写在
`main.py` 顶部的常量里）。

## 数据保存在哪里？

全部在 AstrBot 的 `data/plugin_data/astrbot_plugin_donghuang/` 目录下：

- `campaign.json` — 每个群的开团状态、名额报名、回合锁定进度、活跃事件池
- `world_state.json` — 每个群当前的世界状态（GLOBAL/REGION/FACTION/...），
  额外有一个 `GM_ONLY.final_event` 字段存"最终世界事件"伏笔，代码永远不会
  把这个字段输出给玩家，只会喂给 AI 做叙事参考
- `event_log.json` — 每个群的事件历史，只增不改，代码里没有任何"编辑/
  删除已有事件"的接口
- `player_profiles.json` — 每个群每个角色的档案（姓名/年龄/性别/身高/
  灵根/六维属性/出身/处境等），每份档案里还有一个 `hidden_hook` 字段存该
  角色的隐藏主线，同样只喂给 AI、绝不通过任何指令输出给玩家
- `logs/群号/日期.log` — 团务日志，纯文本
- `output_log.json` — 每个群最近若干条"AI叙事记录点"（反应式叙事/正式
  事件结算），每条都带一份该输出生效**之前**的整体状态快照（world_state/
  player_profiles/event_log/campaign/event_pool 的深拷贝），供 `/dh replay` 列出、
  `/dh rollback` 回退用；超过 `OUTPUT_LOG_MAX`（默认50）条自动丢弃最老的
  记录及其快照

## 角色生成方式

角色不是玩家自己建的，而是团长 `/dh start` 时批量生成：数值型/客观事实
（区域、性别、年龄、身高、灵根层序/属性、六维属性）由 Python 代码用
`random` 真随机抽取，保证公平且不受 AI 摆布；姓名、出身、处境、隐藏主线
这些叙事性内容交给 AI 生成。开局区域完全独立随机，不保证玩家分散或聚集。

## MVP 范围说明

快照/回滚机制现在有了一个轻量版实现（`/dh replay` + `/dh rollback`，见
下方"指令前缀"），但跟总纲里设想的版本不完全一样，有几个明确的简化：
- 快照是**整体性**的：一条记录点只对应"这条 AI 输出发生前"的完整状态，
  不区分是 AI 叙事造成的变化还是同期的管理指令（join/kick/给道具）造成
  的变化，回退时会一起退回去，做不到只挑 AI 那部分单独撤销。
- 只覆盖 `_reactive_narrate`（反应式叙事）和 `_resolve_turn_lock`（正式
  事件结算）两条路径；回合制战斗（`/dh combat`）期间的逐回合叙事**不**
  产生独立的记录点，没法回退到战斗中间的某一回合。
- 只保留最近 `OUTPUT_LOG_MAX`（默认50）条记录，更早的输出没法回退。
- 依然遵守"EVENT_LOG 只增不改"：正常游戏过程中不会自动回滚，只有管理员
  主动执行 `/dh rollback` 才会整体退回；如果 AI 返回的状态增量格式有
  问题，代码会直接丢弃这次增量（只保留叙事文字），不会写坏任何 JSON
  文件，也不会自己触发回滚。

PRIVATE 信息目前只会写进对应玩家的档案里，不会在群里以任何形式展示（本
仓库目前没有私聊发送的先例，等确认 AstrBot 适配器支持私信后再考虑升级）。

## 托管（autopilot）

`campaign["slots"][slot]["auto_pilot"]` 记录每个槽位是否处于托管状态，
用来解决"玩家长期不回复导致其他人卡住"的问题，跟 `/dh kick`（直接请出
游戏）是不同的处理方式——托管让角色"留在场上但走最保守路线"：
- 正式事件触发回合锁定时（`_trigger_turn_lock`），托管中的槽位会被立刻
  自动提交一句由代码按角色`心性`属性生成的保守行动，不用等；
- 每次 `campaign["cycle"]` 前进一格（一次正式事件结算或一场战斗结束），
  `_tick_autopilot_cultivation` 给所有托管中、生存状态 `stable` 的角色一次
  固定的小额修为增益（模拟"打坐"），不会原地不动也不会走risky路线；
- 托管状态**不会**被普通发言自动解除（自动解除有误触发风险，比如只是
  随口一句无关的话）。`on_group_message` 里托管中的槽位发消息会被直接
  拦下、提示需要先 `/dh autopilot off`，不会被当成行动处理。

已知限制：回合制战斗（`/dh combat`）的逐回合行动目前不受托管覆盖——
托管中的角色如果卷入战斗，仍然需要真人或团长 `/dh force` 跳过等待。

## 编剧敕令（decree）

`/dh decree <想要的结果>`（`dh_decree`）是团长/管理员直接指定剧情结果的
通道——正常剧情靠"AI 分类玩家发言 → 反应式叙事/回合锁定"这条路径推进，
`decree` 是唯一一个允许 GM 跳过这条路径、直接告诉 AI "这件事必须发生"
的入口。实现上完全复用现有基础设施，没有另起一套逻辑：
- 调用 AI 时明确要求"把这个结果合理化"（安排具体来源：天劫/隐藏阵法/
  路过高人/势力暗中出手等），不是让 AI 生硬地凭空执行；
- 解析出的 STATE_DELTA 走跟平时完全一样的 `_apply_state_delta`，也就是
  说 `_PROFILE_PROTECTED_TOP_FIELDS`/`_PROFILE_PROTECTED_NESTED_FIELDS`
  这套保护字段机制同样生效——`decree` **不能**绕过死亡协议直接把某个
  玩家的 `生存状态` 改成 `dead`，也不能直接篡改六维/修为进度这类硬数值；
  真要"杀死"一个玩家角色，仍然只能通过把 HP 打到 0、走"濒死 → 死亡豁免
  → 团长 `/dh confirmdeath` 确认"这一整套既有流程；
- 调用前会先经过 `_record_ai_output` 拍快照，产生一个 `/dh replay` 记录
  点——效果不满意可以 `/dh rollback` 撤销，不是不可逆操作。

## 指令前缀

`/dh`（`join`/`exit`/`logout`/`autopilot`/`decree`/`start`/`stop`/`end`/`status`/
`roster`/`kick`/`blacklist`/`unblacklist`/`export`/`mycard`/`recap`/`items`/
`world`/`history`/`eventlog`/`advance`/`eventtest`/`replay`/`rollback`/`combat`/`force`/`testfill`/`save`/
`stabilize`/`confirmdeath`/`rejectdeath`/`doctor`/`why`/`help`/`ask`/`bestiary`/
`weather`/`environment`/`causal`/`act`/`profile`/`memories`/`interact`/`npc`/
`npc_events`/`join_faction`/`leave_faction`/`faction`/`tick`/`play`/`cultivate`/`technique`/`breakthrough`/`ability`/`sect`），跟
`astrbot_plugin_trpg`
占用的 `/r /roll /pc /gm /npc /trpg` 不冲突。物品转手（把随身携带的东西给
另一位角色/NPC）不设专门指令，走口头描述 + AI 判断的叙事流程，见
`world/economy_rules.md`。回合制战斗（先攻/命中/伤害/状态效果全部由代码
摇骰，AI 只负责叙事）见 `world/combat_rules.md`。`/dh recap` 只汇总
PUBLIC 团史和状态摘要，不会输出 `history_note` 里的 PRIVATE 备注——
PRIVATE 信息始终只写进档案文件，不通过任何指令回显到群里。

## LONG-A: 玩家修仙成长生态系统

本插件实现了完整的修仙成长体系（LONG-A），包含以下模块：

### 新增模块

| 文件 | 功能 |
|------|------|
| `cultivation_state.py` | 修炼状态模型：境界、修为进度、根基值、瓶颈等级、连续失败次数、修炼倍率 |
| `spiritual_root.py` | 灵根系统：五行+异变灵根、纯度计算、功法亲和度、突破风险 |
| `cultivation_technique.py` | 功法系统：品阶分类、修炼速度计算、突破加成、功法加载器，玩家用 `/dh technique` 查看/学习新功法 |
| `breakthrough_manager.py` | 突破体系：检定流程、成功/失败判定、状态更新、NPC感知触发 |
| `cultivation_ability.py` | 技能能力系统：剑意/炼丹/炼器/阵法/符箓五类技能，等级与经验，玩家用 `/dh ability` 查看/修炼 |
| `sect_interface.py` | 宗门成长接口：贡献点、职位晋升、传承（有具体数值效果）、师徒（含任务系统），全部接了玩法指令：`/dh sect`/`contribute`/`heritage`/`master`/`worship <NPC>`/`recruit <角色名>`/`claim <传承类型>`/`assign <徒弟> <任务>`/`complete` |

### 核心机制

**修炼增益计算**：修炼增益 = 基础增益 × 灵根效率 × 功法速度 × 修炼倍率 × (1 - 瓶颈衰减)

**突破检定**：1d20 + 悟性修正 vs DC(20 + 境界修正 + 瓶颈修正 - 根基修正 - 功法加成)

**旧存档兼容**：所有新字段都支持从旧版 `spirit_root_tier`/`spirit_root_element` 自动迁移，不会破坏已有数据。

### 测试覆盖

运行 `tools/test_cultivation_system.py` 验证全部 166 项测试用例通过。
`/dh ability` 指令测试见 `tools/test_ability_command.py`（7 项），
`/dh sect` 指令测试见 `tools/test_sect_command.py`（26 项），
`/dh technique` 指令测试见 `tools/test_technique_command.py`（6 项），
`/dh breakthrough` 指令测试见 `tools/test_breakthrough_command.py`（7 项）。

## 战斗数值平衡模拟器（开发工具）

双击插件目录下的 **`战斗平衡模拟器.bat`** 打开图形界面（也可命令行跑
`py tools\combat_simulator.py`）。一次模拟几万场战斗（约10秒），输出
境界×妖兽品阶×队伍人数的胜率热力图、策略/武器对比、自动平衡告警和
推荐挑战区间；"数值旋钮"页可以临时改妖兽数值/逃跑DC/HP曲线等常量
重跑对比（只影响模拟，调好后需手动同步回 `main.py`）。每次运行的完整
数据和当时的数值常量快照都会存进 `tools/balance_results/`，改完数值
重跑会自动列出与上一次相比胜率显著变化的格子。所有战斗数学直接复用
`main.py` 的真实结算函数，防漂移冒烟测试见 `tools/test_combat_simulator.py`。
