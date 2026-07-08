# 东荒架构规则


## 禁止

不要创建：

第二套事件系统

第二套角色系统

第二套状态修改系统


---

## 数据流


玩家输入

↓

Action

↓

Outcome

↓

OutcomeApplier

↓

Profile/Faction/World


禁止跳过。


---

## 世界推进


唯一入口：

WorldTick


环境变化：

WorldEvolution


事件：

EventPool


历史：

WorldHistory


---

## NPC


NPCRegistry:

身份数据


NPCMemory:

玩家关系


NPCBehavior:

行为倾向


NPCLifeManager:

生命变化


不要混合。