# 东荒 TRPG 设定资料库

汇集《东荒》修仙 TRPG 的世界观、主持规则、数值参数与内容资料，涵盖地域、势力、人物、功法、物品、生灵和历史，可用于世界构建、冒险设计及多人跑团。

## 内容

| 目录 | 内容 |
| --- | --- |
| [world/](world/) | 世界法则、区域档案、势力与资源、开局种子、战斗、经济、死亡与重生规则，共 7 份规则文档 |
| [data/](data/) | 地点、势力、人物、身世、关系、功法、物品、生灵、植物及历史条目，共 1,544 份 JSON / JSONL 内容资料 |
| [rules/](rules/) | 23 份结构化设定与数值表：姓名、八字、身世、天赋、伤病、天气、修炼、宗门、NPC、环境和数值参考 |
| [reference/](reference/) | 世界观构建标准、两份命名资料、8 份创作词表及整理记录 |

## 一起维护

先读[协作约定](reference/协作约定.md)，按“认领主题 → 独立分支 → PR → 另一人确认”修改。实际采用的规则记在[采用清单](reference/采用清单.md)，来源与授权见[资料来源与署名](reference/资料来源与署名.md)，变更摘要见[维护记录](reference/维护记录.md)。

GitHub 主分支保护需在仓库设置里实际启用，文档约定不能代替。仓库仍为公开资料库；提交前检查没有账号配置、秘密或个人资料。

## 阅读入口

- [核心规则](world/engine_rules.md)
- [世界档案](world/lore_dossier.md)
- [势力与资源](world/faction_resource_entity.md)
- [开局参考](world/campaign_seed.md)
- [战斗规则](world/combat_rules.md)
- [经济规则](world/economy_rules.md)
- [死亡与重生](world/death_protocol.md)
- [世界观构建标准](reference/玄幻仙侠世界观构建标准.md)

## 资料说明

`world/` 保存世界与玩法规则，`data/` 收录可检索的内容条目，`rules/` 提供静态参数表，`reference/` 汇集创作与维护资料。部分规则文档包含插件时期的术语、调用约定及伪代码，便于理解机制设计。

`rules/` 和 `reference/lexicons/` 为静态内容导出，保留原始数值、词表及来源信息；运行时缓存和派生计算不包含在静态表内。JSON 中数值索引以字符串键保存。

本仓库只管理设定与内容资料，不包含可运行的 AstrBot / NapCat 插件、安装配置或角色存档。资料整理过程见[整理记录](reference/整理记录.md)。

目录约定：世界规则放 `world/`，内容资料放 `data/`，纯设定表放 `rules/`，创作参考放 `reference/`；根目录保留本说明、`AGENTS.md` 与 `.gitignore`；`.github/` 放协作模板。临时文件、运行存档、日志、密码和 Token 不入库。
