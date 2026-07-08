# 开发状态


|系统|状态|
|-|-|
|玩家行动|完成|
|角色外观|完成|
|NPC记忆|完成|
|NPC关系|完成|
|NPC交互|完成|
|NPC主动行为|完成|
|NPC生命周期|完成（E-2，因果约束+EVENT_LOG同步+npc_join_faction/npc_leave_faction 均已接线）|
|环境系统|完成|
|因果链|完成（world_chain_manager.py 三段链路+深度限制+TTL，已有 test_world_chain_manager.py）|
|势力AI|完成（faction_ai_manager.py 候选生成 + world_tick._consume_world_action_proposals 消费闭环已打通，tools/test_faction_ai_manager.py）|
|战斗|完成（main.py 的 dh_combat/_resolve_combat_round/_combat_player_action 等已实现，tools/test_combat_system.py）|
|修炼|完成（六模块指令层全部接线，见下方明细；传承数值效果/师徒任务系统超出接线范围，见 NEXT_TASK.md「明确边界」）|

## 修炼系统（LONG-A）六模块接线复核明细

对方文件已稳定（`breakthrough_manager.py` 最后改动 2026/7/8 20:52，之后
无变化），逐一确认了 main.py 里的真实接线情况：

| 模块 | 接线状态 |
| --- | --- |
| `cultivation_state.py` | ✅ 已接线（角色状态核心，`dh_cultivate` 等多处使用） |
| `spiritual_root.py` | ✅ 已接线（角色创建 + `dh_cultivate` + 突破判定都在用） |
| `cultivation_technique.py` | ✅ 已接线：`dh_cultivate` 用它算功法加成，但**学新功法**此前完全没有指令——`known_techniques` 只在角色创建时由 AI 生成一次，之后没有任何途径新增。本轮新增 `/dh technique`（查看已学+按灵根/境界推荐）/`/dh technique <功法名>`（学习，境界不够会被 `can_learn_technique` 拒绝）。测试见 tools/test_technique_command.py（6 项，用假 TechniqueManager 隔离真实数据文件内容）。 |
| `breakthrough_manager.py` | ✅ 已接线（`CULTIVATION_BREAKTHROUGH` 事件结算时调用）。此前只能靠自然语言被 AI 分类命中，本轮加了 `/dh breakthrough` 直接入口——不是新判定逻辑，只是跳过分类步骤直接调用同一个 `_trigger_turn_lock("CULTIVATION_BREAKTHROUGH")`，"修为火候不够就拒绝"这条门槛原样保留。测试见 tools/test_breakthrough_command.py（7 项）。 |
| `cultivation_ability.py` | ✅ 已接线（本轮补上）：新增 `/dh ability` 指令，玩家可以查看技能面板、修炼"剑意/炼丹/炼器/阵法/符箓"五项技能，代码摇骰算经验/是否升级，AI 不参与判定。测试见 tools/test_ability_command.py（用 stub 手法绕过 astrbot 依赖，7 项用例覆盖群聊/报名校验、境界门槛、正常修炼、指点加成、升级）。 |
| `sect_interface.py` | ✅ 完整接线（含数值效果+师徒任务，用户明确授权后完成）：`/dh sect`（信息）/`contribute`（贡献+晋升）/`heritage`（查看）/`master`（师徒关系）/`worship <NPC>`（拜师）/`recruit <角色名>`（收徒）/`claim <传承类型>`（领取传承，**有具体数值效果**：秘术传承+3攻/器物传承+3防常驻挂在 `_combat_stats()`，血脉传承+10气血/道心传承+5灵力/功法传承+5修为进度领取时一次性生效）/`assign <徒弟> <任务内容>`+`complete`（师徒任务：师父布置、徒弟完成，双方各得贡献点）。测试见 tools/test_sect_command.py（26项）+ tools/test_combat_system.py。 |

## 真实 AstrBot 框架验证（本轮新增）

`pip install astrbot` 后确认可以装（PyPI 上有发布），已安装并新增
`tools/test_real_astrbot_registration.py`：用真实框架（不是手搓 stub）
确认 main.py 能正常导入、LONG-A 修炼系统真实可用、全部 51 个 `/dh` 子
指令都进了 AstrBot 自己的 `star_handlers_registry`。仍然做不到的是接
真实平台适配器跑完整消息收发链路（需要构造一整套 AstrBotConfig/
Database/ProviderManager 等重量级运行时对象），这已经超出"测试一个插件"
的合理范围，属于 AstrBot 本体集成测试的领域。

## 备注

- 本表此前"战斗未开始/因果链进行中"是过期信息：复核后发现两者代码层面
  已经基本完成，只是战斗系统此前没有测试覆盖。
- NPC生命周期 E-2 遗留的加入/离开势力已补上：action 名特意叫
  `npc_join_faction`/`npc_leave_faction`（不是 `join_faction`/
  `leave_faction`）——因为 main.py 里已经有玩家主动执行的
  `/dh join_faction`/`/dh leave_faction` 指令，是完全独立的另一套系统
  （改 profile.FACTION_STATE.affiliation），撞了名字容易和这次新加的
  NPC 被动生命周期动作搞混，所以加了 npc_ 前缀区分。复用 EventPool 的
  因果回响（CAUSAL_ECHO）/势力冲突事件的 `participants` 字段作为目标
  势力，不需要额外读取 NPCRegistry/factions 静态数据，也没有改 main.py。
  规则见 npc_life_rules.py 的 validate_npc_join_faction/
  validate_npc_leave_faction，测试见 tools/test_npc_life_manager.py。
- 势力AI/修炼这两块文件时间戳显示有并行开发进程正在实时修改，本轮没有
  深入复核，避免和正在进行的编辑冲突（参考此前 world_context.py 的教训：
  文件会在几秒内消失又重新出现）。等对方阶段性稳定后再复核+补测试。