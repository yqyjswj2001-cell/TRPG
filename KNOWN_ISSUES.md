## Windows编码问题

测试脚本emoji导致GBK失败。

解决：

PYTHONIOENCODING=utf-8


## /dh recap

函数存在但缺少command装饰。

已修复。


## LONG-A —— 已确认接入完毕

修炼系统六个文件（cultivation_state/spiritual_root/cultivation_technique/
breakthrough_manager/cultivation_ability/sect_interface）已全部接入
main.py，指令层也补齐（`/dh cultivate`/`technique`/`breakthrough`/
`ability`/`sect`），详见 DEVELOPMENT_STATUS.md「修炼系统（LONG-A）六模块
接线复核明细」。

## SYSTEM_ARCHITECTURE.md 第6节风险清单复核（本轮全部处理完）

- **6.1 JSONL BOM 问题**：复核后确认已解决，`asset_loader.py`/
  `cultivation_technique.py` 的运行时数据读取全部走 `utf-8-sig`，没有
  裸 `utf-8` 读风险数据。
- **6.2 STATE_DELTA 无白名单**：加了模块级白名单（不是字段级），详见
  SYSTEM_ARCHITECTURE.md 第6.2节。
- **6.4 无 group 级并发锁**：`_get_group_lock()` + 三个高风险入口
  （`on_group_message`/`dh_start`/`dh_decree`）已加锁，详见
  SYSTEM_ARCHITECTURE.md 第6.4节。
- **6.5 combat_rules.md/economy_rules.md 文档漂移**：两份文件开头的
  "只在 xx 时才加载"声明跟实际代码行为不符（这两个文件从未被
  `main.py` 实际加载进 AI prompt），已改成准确描述当前状态，不是
  假装问题已解决。

## /dh play 缺少权限校验 —— 已修复（经用户明确授权后处理）

`COMMAND_AUDIT.md` 第4.1节发现的问题：`/dh play`（开关"强制游戏模式"）
改的是**群级** `campaign["force_play"]` 状态，之前没有任何 `_is_gm()`
校验，任何已加入的普通玩家都能单方面切换。之前一直标记为"需要开发者
确认意图，不擅自修复"；用户明确授权后，采用了更安全的默认值：**开关
仅管理员可用，查看所有人可用**，跟 `/dh combat` 等群级开关指令的权限
模型保持一致。测试见 tools/test_play_permission.py（4项）。


## 孤儿模块

cultivation_state.py

npc_attribute_roller.py

需要确认。
（更新：cultivation_state.py 目前正被并行开发进程持续修改，已不是孤儿模块，
是多阶段修炼系统开发的一部分，见 DEVELOPMENT_STATUS.md「修炼」行。）


## test_world_evolution.py 偶发失败 —— 已修复

`test_multi_group_isolation` 原本断言"不同群的天气/灵气流向不应相同"，
但两次独立摇骰本来就有小概率撞出同一个结果，属于断言方式有问题（不是
生产代码的隔离真的失效）。已改为断言真正的隔离性质（两个群的 world_state
是独立对象、互不包含对方的区域数据），验证过连续 8 次运行稳定通过。

## breakthrough_manager.py 缺少双重导入兜底 —— 已修复

代码库里所有跨模块 import 统一约定 `try: from .x import y / except ImportError:
from x import y`（相对导入优先，绝对导入兜底，兼容"作为包导入"和"插件目录
被直接扔进 sys.path"两种加载方式）。唯独 `breakthrough_manager.py` 顶部
对 cultivation_state/cultivation_technique/spiritual_root 的三处 import
只写了裸的绝对导入，没有这层兜底——在真实 AstrBot 运行时侥幸能跑（插件
目录本来就在 sys.path 上），但只要 import 上下文换一种方式（比如把
main.py 当成 `astrbot_plugin_donghuang.main` 这样的包成员导入），
`_LONG_A_AVAILABLE` 就会被静默设成 False，整个 LONG-A 修炼系统失效且
没有任何报错提示。已按统一约定补上 try/except 双重导入。

## breakthrough_manager.py 导入错误 —— 已修复

`_apply_failure()` 引用 `affliction_data._AFFLICTION_IMMUNE_TALENTS`，
但该常量当时还没定义（并行开发中途状态），导致 test_cultivation_system.py
偶发 ImportError。已在 affliction_data.py 补上空的 `_AFFLICTION_IMMUNE_TALENTS
= frozenset()` 占位（不影响现有行为，具体免疫天赋名单留给天赋系统落地后
再填）。