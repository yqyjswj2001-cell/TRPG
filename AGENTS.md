# AGENTS.md — 本工作区的强约束规则

这个仓库同时开发多个互相独立的 AstrBot 插件。完整规划见
[PROJECT_PLAN.md](PROJECT_PLAN.md)，这里只列**每次改代码都必须遵守**的硬规则。

## 边界（不能违反）

- 每个插件是一个顶层文件夹：`astrbot_plugin_<name>/`。文件夹名必须和
  `metadata.yaml` 的 `name`、`main.py` 里 `@register()` 的第一个参数、
  `PLUGIN_NAME` 常量完全一致。
- **禁止跨插件 import**：不要在任何一个 `astrbot_plugin_*/main.py` 里
  `import` 或引用另一个 `astrbot_plugin_*` 文件夹的代码/路径。
- **禁止建立跨插件共享目录**（`common/`、`shared/`、`utils/` 等放在仓库根
  目录、给多个插件公用）。两个插件需要同样的逻辑就各自复制一份，不要抽象。
- 每个插件文件夹必须自包含：单独复制出去也要能正常跑。
- 插件数据一律通过 `StarTools.get_data_dir(PLUGIN_NAME)` 获取路径（老版本
  AstrBot 退回 `data/plugin_data/<PLUGIN_NAME>/`），不要硬编码路径，也不要
  把运行时数据写进插件源码文件夹。
- 新增指令前先看根目录 `README.md` 的插件索引表，避免和已有插件的指令
  前缀冲突；加完新插件要回来更新这张表。
- 每个插件的 `requirements.txt` 独立维护，不建根目录统一依赖文件。
- 每个插件文件夹必须同时有 `README.md`（面向开发者：安装/依赖/发布信息）
  和 `使用说明.md`（面向普通使用者：指令示例、常见问题，口语化），两者
  内容不要照抄，读者不一样。

## 新增插件时

按 `_template/astrbot_plugin_template/` 脚手架复制改名，流程见
[PROJECT_PLAN.md](PROJECT_PLAN.md) 第 9 节。改完后跑一遍第 10 节的“导出前
自查清单”再交付。

## 现有插件

- `astrbot_plugin_trpg/` — QQ 群跑团助手，指令前缀：`/r` `/roll` `/pc` `/gm`
  `/npc` `/trpg`。
