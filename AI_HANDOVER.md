# 东荒修仙跑团系统 AI 交接文档

## 当前阶段

当前开发阶段：
E-2 NPC生命周期一致性 已完成（30/30 回归通过）。
下一阶段候选：因果链收尾 / 势力AI / 战斗 / 修炼完善（见 DEVELOPMENT_STATUS.md）。

项目定位：

长期运行的修仙世界模拟系统。

核心原则：

代码管理事实。
AI负责叙事。


---

# 已完成系统


## 玩家系统

状态：
完成

包含：

- player_profile
- appearance
- player_action
- ACTION_LOG
- Outcome链


## NPC系统

状态：
主体完成，生命周期规则与EVENT_LOG同步已接线（E-2）

包含：

- NPCRegistry
- NPCMemory
- NPCRelationship
- NPCBehavior
- NPCInteraction
- NPCActionScheduler
- NPCLifeManager
- NPCLifeRules（新增，因果约束校验）


## 世界系统

状态：

完成基础循环


包含：

- WorldTick
- WorldEvolution
- WorldEnvironment
- WorldHistory
- EventPool


## 事件系统

状态：

完成


规则：

EventPool 是唯一正式事件入口。


## 状态修改

状态：

完成


规则：

OutcomeApplier 是唯一修改入口。


## 存档

状态：

完成


支持：

- campaign
- snapshot
- rollback
- 旧版本兼容