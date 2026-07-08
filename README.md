# ArstBot 插件开发工作区

这个仓库用来同时开发、维护多个互相独立的 AstrBot 插件。每个插件都是仓库
根目录下的一个独立文件夹，彼此之间**没有代码依赖**，可以单独复制、单独
发布。

完整的开发规则见 [PROJECT_PLAN.md](PROJECT_PLAN.md)（人类阅读版）和
[CLAUDE.md](CLAUDE.md)（给 AI 编码助手的强约束摘要）。新建插件请从
[`_template/astrbot_plugin_template/`](_template/astrbot_plugin_template/)
复制脚手架开始。

如果某个插件需要自己的世界观内容（跟 `astrbot_plugin_donghuang` 一样），
构建世界观时可以参考
[`玄幻仙侠世界观构建标准.md`](玄幻仙侠世界观构建标准.md)——这是内容创作
层面的通用框架/checklist，不是代码，机器人不会在运行时加载它。

## 插件索引表

> 每新增一个插件，都要在这里加一行，并且检查“指令前缀”不能和已有插件重复。

| 插件文件夹 | 简介 | 已占用指令前缀 | 状态 |
| --- | --- | --- | --- |
| [`astrbot_plugin_trpg`](astrbot_plugin_trpg/) | QQ 群跑团（TRPG）助手：骰子、角色卡管理、AI 叙事、团务日志、团长权限、TRPG 模式（无前缀指令）、引导建团 | `/r` `/roll` `/pc` `/gm` `/npc` `/trpg`（含 `on`/`off`/`invite`/`start`/`end`）| 开发中 v1.2.0 |
| [`astrbot_plugin_donghuang`](astrbot_plugin_donghuang/) | 东荒修仙 TRPG 专属跑团机器人：世界观驱动的 AI 团长、多人锁定回合制、死亡与重生协议 | `/dh`（`join`/`start`/`end`/`status`/`force`/`save`/`stabilize`/`confirmdeath`/`rejectdeath`）| 开发中 v0.1.0（MVP） |

## 目录结构

```
ArstBot/
├── PROJECT_PLAN.md                     整体规划与规则（详细版）
├── CLAUDE.md                           给 AI 编码助手的规则摘要
├── README.md                           本文件：插件索引
├── _template/
│   └── astrbot_plugin_template/        新插件脚手架模板
├── astrbot_plugin_trpg/                插件 1：通用跑团助手
│   ├── README.md                       面向开发者：安装/依赖/发布信息
│   └── 使用说明.md                     面向普通使用者：指令示例、常见问题
├── astrbot_plugin_donghuang/            插件 2：东荒修仙 TRPG 专属机器人
│   └── world/                          拆分后的世界观规则文件（插件自包含）
└── astrbot_plugin_<下一个插件>/         ...
```
