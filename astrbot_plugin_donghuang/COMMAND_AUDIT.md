# COMMAND_AUDIT.md — 指令注册审计

审计日期：2026-07-08（C-0 任务第四节）
方法：对 `main.py` 做穷举式源码核对——`@dh.command("...")` 装饰器、
对应 `async def dh_...` 函数体、`_KNOWN_SUBCOMMANDS`、
`_DH_COMMAND_GUIDE`、顶部指令说明文档字符串、`README.md` 指令前缀清单、
以及每条命令体内是否真的调用 `self._is_gm(event)` 做管理员校验，逐条核对。

**结论先行：**
- 装饰器 ↔ 函数体：**50/50 完全一致**（本次审计过程中发现并修复了
  `/dh recap` 缺装饰器的 bug，见下方"本次修复"）。
- 管理员权限校验：**文档承诺"仅管理员"的命令，代码里确实都有
  `_is_gm()` 校验，没有发现"文档说要管理员、代码没检查"的情况。**
- 但发现一个相反方向的问题：**`/dh play` 完全没有权限校验**，任何群
  成员都能调用它去修改整个群的 `campaign["force_play"]` 全局状态（见
  第 4 节，本次判定为需要人工确认的风险，未擅自修复）。
- 三份"指令清单"（`_KNOWN_SUBCOMMANDS`、`_DH_COMMAND_GUIDE`、
  `README.md`）跟真实注册的 50 个命令都存在不同程度的缺项，缺项集合
  各不相同（见第 2、3 节），是文档/内部清单维护滞后于命令新增速度的
  持续性问题，不是某一次改动引入的新 bug。

---

## 1. 命令总表（50 个，按源码出现顺序）

| 命令 | 函数 | 装饰器已注册 | 管理员校验(`_is_gm`) | 出现在 `_KNOWN_SUBCOMMANDS` | 出现在 `_DH_COMMAND_GUIDE` | 出现在 README 指令前缀清单 |
|---|---|---|---|---|---|---|
| help | dh_help | ✅ | 否（公开） | ✅ | ✅ | ✅ |
| ask | dh_ask | ✅ | 否（公开） | ❌ | ❌ | ✅ |
| doctor | dh_doctor | ✅ | 否（公开自检） | ✅ | ✅ | ✅ |
| bestiary | dh_bestiary | ✅ | 否（公开） | ✅ | ✅ | ❌ |
| why | dh_why | ✅ | 否（公开） | ✅ | ✅ | ✅ |
| join | dh_join | ✅ | 否（公开） | ✅ | ✅ | ✅ |
| exit | dh_exit | ✅ | 否（公开） | ✅ | ✅ | ✅ |
| testfill | dh_testfill | ✅ | ✅ | ✅ | ✅ | ✅ |
| start | dh_start | ✅ | ✅ | ✅ | ✅ | ✅ |
| end | dh_end | ✅ | ✅ | ✅ | ✅ | ✅ |
| export | dh_export | ✅ | ✅ | ❌ | ✅ | ✅ |
| status | dh_status | ✅ | 部分（gm 看到更多信息） | ✅ | ✅ | ✅ |
| advance | dh_advance | ✅ | ✅ | ❌ | ❌ | ✅ |
| eventtest | dh_eventtest | ✅ | ✅ | ❌ | ❌ | ✅ |
| tick | dh_tick | ✅ | ✅ | ❌ | ❌ | ❌ |
| roster | dh_roster | ✅ | ✅ | ✅ | ✅ | ✅ |
| world | dh_world | ✅ | 否（公开） | ✅ | ✅ | ✅ |
| weather | dh_weather | ✅ | 否（公开） | ✅ | ✅ | ❌ |
| environment | dh_environment | ✅ | 部分（gm 看到更多信息） | ✅ | ❌ | ❌ |
| history | dh_history | ✅ | 否（公开） | ✅ | ✅ | ✅ |
| eventlog | dh_eventlog | ✅ | ✅ | ❌ | ❌ | ✅ |
| replay | dh_replay | ✅ | 否（公开） | ✅ | ✅ | ✅ |
| rollback | dh_rollback | ✅ | ✅ | ✅ | ✅ | ✅ |
| mycard | dh_mycard | ✅ | 否（公开） | ✅ | ✅ | ✅ |
| causal | dh_causal | ✅ | 否（公开） | ✅ | ✅ | ❌ |
| act | dh_act | ✅ | 否（公开） | ❌ | ❌ | ❌ |
| profile | dh_profile | ✅ | 否（公开） | ❌ | ❌ | ❌ |
| memories | dh_memories | ✅ | 否（公开） | ❌ | ❌ | ❌ |
| interact | dh_interact | ✅ | 否（公开） | ❌ | ❌ | ❌ |
| npc | dh_npc | ✅ | 否（公开） | ❌ | ❌ | ❌ |
| npc_events | dh_npc_events | ✅ | 否（公开） | ❌ | ❌ | ❌ |
| join_faction | dh_join_faction | ✅ | 否（公开） | ❌ | ❌ | ❌ |
| leave_faction | dh_leave_faction | ✅ | 否（公开） | ❌ | ❌ | ❌ |
| faction | dh_faction | ✅ | 否（公开） | ❌ | ❌ | ❌ |
| items | dh_items | ✅ | 否（公开） | ✅ | ✅ | ✅ |
| logout | dh_logout | ✅ | 否（公开） | ✅ | ✅ | ✅ |
| autopilot | dh_autopilot | ✅ | 部分（管理员可代他人开关） | ✅ | ✅ | ✅ |
| play | dh_play | ✅ | **无（见第4节风险）** | ❌ | ❌ | ❌ |
| kick | dh_kick | ✅ | ✅ | ✅ | ✅ | ✅ |
| blacklist | dh_blacklist | ✅ | ✅ | ✅ | ✅ | ✅ |
| unblacklist | dh_unblacklist | ✅ | ✅ | ✅ | ✅ | ✅ |
| combat | dh_combat | ✅ | ✅ | ✅ | ✅ | ✅ |
| decree | dh_decree | ✅ | ✅ | ✅ | ✅ | ✅ |
| force | dh_force | ✅ | ✅ | ✅ | ✅ | ✅ |
| stop | dh_stop | ✅ | ✅ | ✅ | ✅ | ✅ |
| save | dh_save | ✅ | 否（公开，玩家自救） | ✅ | ✅ | ✅ |
| stabilize | dh_stabilize | ✅ | 否（公开，队友互助） | ✅ | ✅ | ✅ |
| confirmdeath | dh_confirmdeath | ✅ | ✅ | ✅ | ✅ | ✅ |
| rejectdeath | dh_rejectdeath | ✅ | ✅ | ✅ | ✅ | ✅ |
| **recap** | dh_recap | ✅（**本次修复**，此前缺装饰器） | 否（公开） | ✅ | ✅ | ✅ |

---

## 2. `/dh recap`：本次修复记录

- **修复前状态**：`dh_recap` 函数体（[main.py:4794](main.py:4794)）完整存在，
  文档三处都承诺存在（顶部指令说明 [main.py:56](main.py:56)、菜单分组
  [main.py:1451](main.py:1451)、`_DH_COMMAND_GUIDE`/`_KNOWN_SUBCOMMANDS`），
  但函数上方缺少 `@dh.command("recap")` 装饰器，导致这个指令实际上
  **从未被注册**，玩家发 `/dh recap` 会被当成未知指令处理。
- **修复方式**：补上 `@dh.command("recap")` 装饰器（上一轮会话已完成，
  本次审计确认修复有效——已用 `py -m py_compile main.py` 和
  `test_full_regression.py` 25/25 验证无回归）。
- **为什么单独强调**：这是本次"逐条核对装饰器↔函数体"方法论能捕捉、
  但"读文档/读 help 文本"完全捕捉不到的一类 bug——文档和函数体都说
  这个功能存在，只有装饰器这一行的缺失是隐形的。**这提示我们：未来
  新增指令后，仅凭"写了函数、写了文档"不足以确认指令可用，必须要么
  跑一次端到端指令测试，要么像本次一样做装饰器级别的源码核对。**

---

## 3. 三份指令清单与真实注册命令的差异

### 3.1 `_KNOWN_SUBCOMMANDS`（用于"漏打斜杠"检测，[main.py:1362](main.py:1362)）
缺失（已注册但不在此清单里，会导致这些指令漏打斜杠时无法被自动识别/提示）：
`export`、`advance`、`eventtest`、`tick`、`eventlog`、`play`（6个）

### 3.2 `_DH_COMMAND_GUIDE`（用于 `/dh help` 展示 + `/dh ask` 智能推荐，[main.py:1501](main.py:1501)）
缺失（这些命令永远不会被 `/dh ask` 推荐给用户，`/dh help` 也看不到）：
`advance`、`eventtest`、`tick`、`eventlog`、`act`、`profile`、`memories`、
`interact`、`npc`、`npc_events`、`join_faction`、`leave_faction`、
`faction`、`play`（14个）

**这一条影响面比 3.1 更大**：`act`/`profile`/`interact`/`npc`/`faction`/
`join_faction`/`leave_faction`/`memories` 都是**面向普通玩家的核心
玩法指令**（行动/查看角色/NPC互动/势力加入），不是内部调试工具，但
新玩家如果只会用 `/dh help` 或 `/dh ask` 摸索，**发现不了这些指令的
存在**。这是文档漂移里优先级最高的一类。

### 3.3 `README.md` 第129-134行的指令前缀清单
缺失（相对全部 50 个已注册命令）：
`ask`、`bestiary`、`tick`、`weather`、`environment`、`causal`、`act`、
`profile`、`memories`、`interact`、`npc`、`npc_events`、`join_faction`、
`leave_faction`、`faction`、`play`（16个）

同样以玩法核心指令为主。`使用说明.md`（面向普通玩家）本次未做逐条
核对，建议下一轮审计把它也纳入同一张对照表，而不是只查 README。

---

## 4. 权限校验发现（需要人工确认，未擅自修复）

### 4.1 `/dh play` 无任何权限校验（中高风险）
- 位置：[main.py:5000](main.py:5000)
- 行为：`campaign["force_play"] = True/False`——写入的是**群级**
  `campaign` 状态，不是发起者自己的 `profile`。
- 问题：全文没有任何 `_is_gm` 或类似校验，**任何一个已加入的玩家
  都可以单方面把整个群切换成"强制游戏模式"或切回"自由聊天模式"**，
  会直接影响其他玩家和 AI 的对话判断行为。
- 对比：同样是"影响全团的开关类指令"，`autopilot`（个人托管开关）
  区分了"改自己"（任何人可以）和"改别人"（[main.py:4966](main.py:4966)
  处有 `_is_gm` 校验）；`play` 没有这种区分，因为它本来就没有"自己/
  别人"的概念，改的是群级唯一状态。
- **本次不擅自修复**：不确定这是有意设计成"任何玩家都能临时开关，
  图的是方便"，还是遗漏了管理员校验——如果是后者，风险等级会随着
  群规模增大而增大（人越多，越容易有人瞎按导致体验被意外改变）。
  **建议开发者明确这条指令的权限模型后再决定是否加校验。**

### 4.2 其余"仅管理员"命令：校验完整，未发现遗漏
逐条核对文档标注"【仅管理员】"的全部 15+ 个命令（`start`/`testfill`/
`end`/`export`/`advance`/`eventtest`/`tick`/`roster`/`eventlog`/
`rollback`/`kick`/`blacklist`/`unblacklist`/`combat`/`decree`/`force`/
`stop`/`confirmdeath`/`rejectdeath`），**全部在函数体内正确调用了
`self._is_gm(event)` 并在校验失败时提前 return**，没有发现"文档说仅
管理员、代码没检查"的反向漏洞。

---

## 5. 建议处理顺序（不属于本次审计范围，仅供参考）

1. **优先**：确认 `/dh play` 的权限模型意图（第4.1节），这是唯一
   一处"实际权限比文档/常理预期更宽松"的发现，其余都是文档滞后。
2. 把 3.2 节列出的 8 个玩家核心指令补进 `_DH_COMMAND_GUIDE`，成本低、
   收益直接（新玩家发现玩法的关键路径）。
3. 补齐 `_KNOWN_SUBCOMMANDS`（3.1节）和 `README.md`（3.3节），跟
   `使用说明.md` 一起在下一轮"文档同步"任务里统一处理，避免这次只改
   一半、下次又要重新核对。
