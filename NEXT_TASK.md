# 当前任务

E-2 NPC生命周期一致性 —— 已完成（30/30 回归通过，见 npc_life_rules.py /
tools/test_npc_life_consistency.py，报告见对话记录 / AI_HANDOVER.md）。

# 已收尾（本轮全部完成，用户明确授权后处理，不是我单方面拍板发明的内容）

## 修炼系统（LONG-A）

六模块全部接线完毕，每一个都有真实玩家可用的指令入口：
`/dh cultivate`/`/dh technique`/`/dh breakthrough`/`/dh ability`/
`/dh sect`(+`heritage`/`master`/`worship`/`recruit`/`claim`/`assign`/
`complete`)。详见 DEVELOPMENT_STATUS.md「修炼系统六模块接线复核明细」。

## 宗门传承数值效果 + 师徒双向任务系统

之前判断"发明未指定的游戏数值/机制超出接线范围"，用户明确授权后按
以下原则设计（不是凭空拍脑袋）：

- **传承数值**（`sect_interface.py` 的 `HERITAGE_EFFECTS`）：规模参照
  已有的装备品阶加成（黄级武器+2攻）和天赋效果量级，比黄级装备略高、
  比天赋略低，避免一步到位碾压现有成长线。攻防类加成（秘术/器物传承）
  动态挂在 `_combat_stats()`，跟武器品阶加成同一个位置；气血/灵力/
  修为类加成（血脉/道心/功法传承）在 `/dh sect claim` 领取时一次性生效。
- **师徒任务**（`/dh sect assign`/`/dh sect complete`）：assign 由师父
  单方面布置（不做"徒弟确认"这一步，跟 `/dh kick` 一样的权限哲学——
  社交层面的同意交给团桌讨论，不在代码层面拦），完成后师徒双方各获得
  贡献点奖励（徒弟+5，师父+3，量级参照 `POSITION_DAILY_CONTRIBUTION`）。

**Outcome 白名单结论也更新了**：原来以为 `sect` 字段没进白名单、改不了
Outcome 结构，实测后发现是误判——`FACTION_STATE` 本来就在
`PROFILE_FIELD_WHITELIST` 里，而 `outcome_applier._merge_dict_no_clamp()`
对嵌套字段本来就不做二次白名单校验，所以 AI 生成的 STATE_DELTA 写
`FACTION_STATE.sect.contribution` 这类路径其实一直都能通过（已用脚本
实测验证）。`LONG_A_AUDIT.md` 那条"Outcome 接不住 sect"的结论已经过期，
**没有修改 Outcome/EventPool 结构**，这条约束依然完整保留。

测试：tools/test_sect_command.py（26项）、
tools/test_combat_system.py（新增传承攻防加成用例）。

## 其它发现性修复（用户设"继续未完成的工作"目标后处理）

- `_KNOWN_SUBCOMMANDS`/`_DH_COMMAND_GUIDE`/`使用说明.md` 补齐本轮新增的
  五个修炼系统指令（之前漏登记）。
- `ORPHAN_MODULE_AUDIT.md`：`npc_perception.py` 已接入
  `npc_context.py`（首次相遇时用外貌生成初见印象，向后兼容不破坏原有
  记忆上下文逻辑）；`cultivation_state.py` 建议的纯函数测试确认已被
  `test_cultivation_system.py` 满足。
- `/dh play` 补上权限校验（开关仅管理员，查看所有人可用，跟 `/dh combat`
  等群级开关指令权限模型一致）。
- `/dh doctor` 新增存档完整性诊断：加载失败静默回退默认值时会提示，
  之前只写日志。
- `_load_json` 新增顶层类型校验（期待 dict 却读到 list 时按解析失败
  处理，回退默认值）。
- `player_profile` 缺字段自愈统一到 `_ensure_profile_defaults()`
  单一入口（读档时+角色创建时都调用），不再分散在各业务函数里。
- npc_join_faction/npc_leave_faction 独立 action 类型：复用 EventPool
  事件的 participants 字段做目标势力，特意加 npc_ 前缀跟玩家指令
  `/dh join_faction` 区分开。
- test_world_evolution.py 天气随机性 flaky 测试：改成断言真正的隔离
  性质而非随机结果不等。

# 结构性限制（已用最大努力验证，仍然做不到，附具体证据）

`pip install astrbot` 后确认这个包在 PyPI 上可以装（之前"环境没装
astrbot"是过期判断）。已安装并新增 tools/test_real_astrbot_registration.py，
用**真实**框架（不是手搓 stub）验证了：main.py 能正常 import、LONG-A
修炼系统真实可用、全部 `/dh` 子指令都真的进了 AstrBot 自己的
`star_handlers_registry`。

**仍然做不到的**：真正接一个 QQ/微信等平台适配器、跑通完整的
`事件队列 → 消息收发 → 指令实际执行并回复群聊` 全链路。已经实际去查过
构造成本，不是拍脑袋判断：

- `Context.__init__` 要求 9 个必填参数：event_queue、AstrBotConfig、
  BaseDatabase、ProviderManager、PlatformManagerProtocol、
  ConversationManager、PlatformMessageHistoryManager、PersonaManager、
  AstrBotConfigManager、KnowledgeBaseManager、CronJobManager。
- 其中 `BaseDatabase` 是一个抽象基类，`__abstractmethods__` 数出来有
  约 90 个方法待实现（会话管理/人格管理/定时任务/API Key/统计等一整套
  持久层）。

逐一伪造这些对象等于重新实现一个精简版 AstrBot 宿主程序，这已经超出
"测试一个插件"该做的范围，属于 AstrBot 本体自己的集成测试领域——真要
跑端到端，正确路径是在一台装好 AstrBot、配好真实平台凭证的机器上手动
测，不是在这个无头开发环境里硬造。这不是"不想做"，是查证过后确认
在当前环境下没有合理成本的实现路径。

**追加验证（用户设"将这三类全做完"目标后又重新尝试了一次，没有轻易
放弃）**：发现 `BaseDatabase` 其实有真实的 `astrbot.core.db.sqlite.
SQLiteDatabase(db_path)` 具体实现（不需要自己伪造那 90 个抽象方法），
一度以为能大幅降低搭建成本。但继续尝试单独 import
`ProviderManager`/`PlatformManager`/`ConversationManager` 等其余几个
必需对象时，直接触发 `ImportError: cannot import name 'ProviderManager'
from partially initialized module...(most likely due to a circular
import)`——这些内部模块之间有循环依赖，只有通过 AstrBot 自己完整的
启动引导流程（`initial_loader` 之类，涉及读取配置文件、初始化日志等
一整套顺序）才能正确构造，不是"每个类单独 new 一下"就能绕开的问题。
这比"参数多"更进一步证实了：搭建过程本身依赖 AstrBot 完整应用生命
周期，不是插件测试该承担的成本。结论不变，但现在有了更具体的失败
证据（循环导入错误信息），而不只是参数数量的推断。
