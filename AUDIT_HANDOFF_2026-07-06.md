# ArstBot 项目审计与交接文档

最后更新：2026-07-06

本文档用于给后续接手的开发者或新的 AI 协作者快速建立上下文。
重点不是“漂亮总结”，而是把这次审计中已经看到、已经验证、已经怀疑的东西尽量落下来，
避免后续重复踩坑。

## 1. 本次审计范围

工作区根目录：

- `E:\AIproject\ArstBot`

主要审计对象：

- `astrbot_plugin_donghuang/`
- `astrbot_plugin_trpg/`
- 根目录规则与说明文档：
  - `README.md`
  - `PROJECT_PLAN.md`
  - `CLAUDE.md`

本次没有修改业务代码，只进行了阅读、静态检查、语法编译、数据校验和一致性核对。

## 2. 工作区结构概览

根目录当前主要内容：

- `astrbot_plugin_donghuang/`
- `astrbot_plugin_trpg/`
- `_template/`
- `README.md`
- `PROJECT_PLAN.md`
- `CLAUDE.md`
- `astrbot_plugin_donghuang.zip`
- `astrbot_plugin_trpg.zip`
- 若干世界观文档：
  - `东荒修仙TRPG世界运行总纲.txt`
  - `玄幻仙侠世界观构建标准.md`

补充说明：

- 外层 `E:\AIproject` 不是 git 仓库。
- `E:\AIproject\ArstBot` 当前也不是 git 仓库。
- 根文档使用 UTF-8 可正常读取。

## 3. 已确认的关键事实

### 3.1 `astrbot_plugin_donghuang` 体量和复杂度已经很高

- 主入口文件：`astrbot_plugin_donghuang/main.py`
- 语法可编译通过
- 文件长度约 5397 行
- AST 统计结果：
  - 1 个主类：`DonghuangPlugin`
  - 139 个函数
  - 37 个命令入口

最长的几个函数：

- `_generate_character_panels_batch`：221 行
- `__init__`：201 行
- `_resolve_turn_lock`：181 行
- `_build_system_prompt`：157 行
- `on_group_message`：153 行
- `_resolve_combat_round`：151 行
- `_apply_state_delta`：147 行
- `_reactive_narrate`：134 行

结论：

- 该插件已经不是“小插件”，而是一个混合了：
  - 指令层
  - 世界规则层
  - AI 提示词层
  - 状态机
  - 持久化
  - 大量静态资产加载
  - 战斗系统
  - 回滚系统
  的单文件系统。

### 3.2 `astrbot_plugin_trpg` 相对轻量

- 主入口文件：`astrbot_plugin_trpg/main.py`
- 语法可编译通过
- 文件单体规模明显小于 `donghuang`
- 更接近一个常规 AstrBot 插件

### 3.3 运行时 Python 在系统 PATH 中不可直接调用

系统里直接调用 `python` 会失败，但 Codex 工作区内置 Python 可用：

- `C:\Users\85399\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`

后续若让新的 AI 做自动化校验或脚本修复，应优先使用这一路径。

## 4. 本次已经做过的检查

### 4.1 语法编译

已确认以下文件可通过 `py_compile`：

- `astrbot_plugin_donghuang/main.py`
- `astrbot_plugin_trpg/main.py`

这说明至少没有明显语法错误，但不代表运行时逻辑正确。

### 4.2 数据文件数量统计

`astrbot_plugin_donghuang` 内部大致包含：

- `.jsonl`：1499 个
- `.json`：45 个
- `.py`：17 个
- `.md`：11 个

这意味着它的核心风险之一不是“代码”，而是“数据资产如何被正确读入”。

### 4.3 JSON / JSONL 有效性校验

做过两轮：

1. 按当前代码常用方式 `encoding="utf-8"` 读取：
   - 1499 个 JSONL 中有 1460 个报错
   - 主要错误为 UTF-8 BOM

2. 改用 `utf-8-sig` 读取：
   - 所有 JSONL 均可解析
   - 没发现结构性坏行

这是本次审计里最硬、最重要的发现之一。

## 5. 最高优先级问题

### 5.1 大量 JSONL 资产带 BOM，但代码大多按普通 UTF-8 读取

现象：

- 1499 个 JSONL 中有 1460 个文件以 UTF-8 BOM 开头
- 用 `utf-8-sig` 可以正常解析
- 用 `utf-8` 解析会在首行报 `Unexpected UTF-8 BOM`

影响范围非常大，包括但不限于：

- `data/techniques/`
- `data/items/`
- `data/items_s/`
- `data/bestiary_s/`
- `data/ecosystem_s/`
- `data/flora_s/`
- `data/timeline/`

代码中存在大量直接 `encoding="utf-8"` 的读取，例如：

- [main.py](E:/AIproject/ArstBot/astrbot_plugin_donghuang/main.py:236)
- [main.py](E:/AIproject/ArstBot/astrbot_plugin_donghuang/main.py:250)
- [main.py](E:/AIproject/ArstBot/astrbot_plugin_donghuang/main.py:263)
- [main.py](E:/AIproject/ArstBot/astrbot_plugin_donghuang/main.py:278)
- [main.py](E:/AIproject/ArstBot/astrbot_plugin_donghuang/main.py:357)
- [main.py](E:/AIproject/ArstBot/astrbot_plugin_donghuang/main.py:379)
- [main.py](E:/AIproject/ArstBot/astrbot_plugin_donghuang/main.py:1592)
- [main.py](E:/AIproject/ArstBot/astrbot_plugin_donghuang/main.py:1671)

风险：

- 高阶功法库、物品库、妖兽库、时间线等“看似存在，运行时却可能大量读不到”
- 这类失败还经常被 `except Exception: continue` 吞掉，容易表现为：
  - 掉落异常少
  - 样本池莫名为空
  - 高阶资源永远抽不出来
  - 时间线引用失效
  - 功法/物品按需加载长期退化

建议：

- 统一封装：
  - `read_text_sig(path)`
  - `load_json(path)`
  - `iter_jsonl(path)`
- 默认使用 `utf-8-sig`
- 不要在业务代码里散落 `fpath.open(encoding="utf-8")`
- 增加资产校验脚本，作为发布前必跑步骤

### 5.2 `astrbot_plugin_donghuang/.gitignore` 会把核心资产 `data/` 排除掉

当前文件：

- [`.gitignore`](E:/AIproject/ArstBot/astrbot_plugin_donghuang/.gitignore:1)

内容：

- `__pycache__/`
- `*.pyc`
- `.venv/`
- `data/`

问题：

- 这里的 `data/` 不是运行时生成目录
- 它是插件内置核心资产库
- 包含功法、物品、地点、NPC、时间线等内容

而 README 明确写了运行时数据实际在：

- [README.md](E:/AIproject/ArstBot/astrbot_plugin_donghuang/README.md:51)

也就是 `data/plugin_data/astrbot_plugin_donghuang/`

风险：

- 如果未来按项目规划将 `astrbot_plugin_donghuang/` 单独 `git init` 并发布
- 这个 `.gitignore` 很可能导致真正的插件仓库缺失 `data/`
- 最终会变成“代码在，世界没了”

建议：

- 立即移除 `.gitignore` 中的 `data/`
- 只忽略：
  - `__pycache__/`
  - `*.pyc`
  - `.venv/`
  - 本地导出产物
  - 临时日志

### 5.3 `main.py` 巨型化，架构边界已经失控

`astrbot_plugin_donghuang/main.py` 目前承担了过多职责：

- 插件初始化
- 世界规则加载
- 资产加载
- 提示词构造
- 指令实现
- 回合锁定
- 战斗系统
- 角色生成
- 状态增量解析
- 存档回滚
- 诊断逻辑

风险：

- 任何小需求都可能牵连全局
- 新 AI 接手时很难建立可靠心智模型
- 很容易出现“这里改了，那里 silently 坏掉”

建议拆分方向：

- `storage.py`
  - JSON 读写
  - 原子保存
  - group 级锁
- `assets.py`
  - 世界资产读取
  - JSONL 索引
  - 功法/物品/地点/妖兽抽取接口
- `prompts.py`
  - 各类 system prompt
  - 分类提示词
  - 事件提示词
- `rules.py` / `validators.py`
  - STATE_DELTA 校验
  - 保护字段
  - 货币/HP/突破等硬规则
- `commands/`
  - 只保留命令入口和参数解析
- `engine/turn.py`
  - 回合锁定
  - 正式事件结算
- `engine/combat.py`
  - 战斗逻辑

### 5.4 文档与代码发生漂移

README 中对世界规则文件的描述：

- [README.md](E:/AIproject/ArstBot/astrbot_plugin_donghuang/README.md:35)

里面写到：

- `economy_rules.md` 会在交易/经济事件加载
- `combat_rules.md` 会在战斗期间加载

但代码实际初始化时固定加载的是：

- `engine_rules.md`
- `death_protocol.md`
- `campaign_seed.md`
- `lore_dossier.md`
- `faction_resource_entity.md`

对应代码：

- [main.py](E:/AIproject/ArstBot/astrbot_plugin_donghuang/main.py:1537)
- [main.py](E:/AIproject/ArstBot/astrbot_plugin_donghuang/main.py:1541)

`economy_rules.md` 和 `combat_rules.md` 在代码中基本停留在注释级引用，没有看到明确进入提示词装配主链。

风险：

- 文档承诺的规则不一定真实生效
- 新人会以 README 为准误判系统行为

建议：

- 明确建立“规则装配层”
- 在代码里可追踪地声明：
  - 哪些文件常驻
  - 哪些文件按事件类型加载
  - 哪些文件目前尚未接入
- `/dh doctor` 最好能显示真实加载状态，而不是只看少数核心文件

### 5.5 `STATE_DELTA` 仍是自由文本路径写入，边界不够硬

核心代码：

- [main.py](E:/AIproject/ArstBot/astrbot_plugin_donghuang/main.py:5243)

当前策略是让 AI 输出类似：

- `world_state.xxx.yyy: 值`
- `player_profile.xxx.yyy: 值`

然后代码解析并直接写入对象树。

虽然已有保护字段机制，但仍存在风险：

- 字段拼错时可能静默长出新结构
- 类型不稳定，数值/列表/字符串可能漂移
- 世界状态路径几乎是开放式写入
- 一些错误会被日志吞掉，表面不炸，实际状态已偏

建议：

- 用受控 JSON schema 代替自由文本路径 DSL
- 例如定义白名单操作：
  - `append_event`
  - `add_history_note`
  - `adjust_currency`
  - `append_known_technique`
  - `set_relation_delta`
- 每个操作单独做类型、权限、范围校验

### 5.6 缺少 group 级并发锁，状态文件有覆盖写风险

当前存档是典型的：

- 读入内存 dict
- 在多个路径中修改
- 调用 `_save_*()` 直接写文件

相关代码：

- [main.py](E:/AIproject/ArstBot/astrbot_plugin_donghuang/main.py:1715)

潜在问题：

- AstrBot 群消息、管理员指令、LLM 回调可能并发执行
- 多个路径同时修改同一 group 状态时，后写入者可能覆盖前者修改

建议：

- 至少按 `group_id` 建 `asyncio.Lock`
- 所有会改以下状态的流程都进入同一把锁：
  - `campaign`
  - `world_state`
  - `event_log`
  - `player_profiles`
  - `output_log`

## 6. 中优先级问题

### 6.1 帮助文本、README、实际命令不同步

代码里实际有这些命令：

- `/dh ask`
- `/dh bestiary`
- `/dh weather`
- `/dh play`

其中：

- `README.md` 的命令汇总并没有完整反映全部命令
- `/dh play` 在帮助文本中也没有进入主帮助表

参考：

- [main.py](E:/AIproject/ArstBot/astrbot_plugin_donghuang/main.py:1390)
- [main.py](E:/AIproject/ArstBot/astrbot_plugin_donghuang/main.py:1459)
- [main.py](E:/AIproject/ArstBot/astrbot_plugin_donghuang/main.py:3693)
- [README.md](E:/AIproject/ArstBot/astrbot_plugin_donghuang/README.md:131)

建议：

- 从命令装饰器自动导出命令清单
- 自动校验：
  - README 命令表
  - `使用说明.md`
  - `_DH_COMMAND_GUIDE`
  - help text

### 6.2 zip 打包物结构存在兼容性风险

检查结果：

- `astrbot_plugin_donghuang.zip` 内部直接以文件为根，不带一层 `astrbot_plugin_donghuang/`
- `astrbot_plugin_trpg.zip` 同样如此

风险：

- 有些安装流程接受
- 有些安装流程会把文件直接散到目标目录

建议：

- 明确约定 zip 包是否必须带顶层插件目录
- 最好提供统一打包脚本，不靠手工压缩

### 6.3 发布流程没有自动校验

当前看到的情况：

- 没有 CI
- 没有 pytest
- 没有 ruff / mypy / pre-commit
- 没有打包校验脚本
- 没有资产完整性校验脚本

结论：

- 现在的质量主要靠人工和即时对话维护
- 功能越多，越不稳

## 7. 低优先级但应该记录的问题

### 7.1 仓库中存在编译产物和 zip 成品

当前看到了：

- `astrbot_plugin_donghuang/__pycache__/`
- `astrbot_plugin_trpg/__pycache__/`
- 多个 `.pyc`
- 根目录两个 `.zip`

说明：

- 这本身不一定是错误
- 但如果后续进入正式版本管理，建议明确区分：
  - 源码
  - 构建产物
  - 发布产物

### 7.2 `donghuang` 有明显的 MVP 痕迹，后续扩展方向需要先定边界

文档和代码里都多次出现：

- 战斗系统是单体妖兽 MVP
- 托管不覆盖逐回合战斗
- 某些世界事件只是埋钩，不完整闭环
- PRIVATE 信息目前只写档案，不做私聊投递

这不一定是缺陷，但它意味着：

- 后续 AI 在加功能前必须先判断“这是未实现，还是刻意不做”

## 8. 已验证但暂未判死的问题

以下问题目前“高度可疑”，但本次没有跑真实 AstrBot 环境联调，因此先记为待验证：

### 8.1 高阶功法 / 物品 / 时间线是否在真实运行中大量退化为样本池

原因：

- 大库按需加载路径基本都受 BOM 问题影响

现象猜测：

- 高阶掉落异常少
- 某些元素或类别永远抽不到

### 8.2 文档里写的按需加载规则文件是否真实生效

尤其是：

- `economy_rules.md`
- `combat_rules.md`

### 8.3 回滚与管理指令交错时的一致性

`README` 已经坦白说回滚是整体性的。

重点待测场景：

- `join` 后立刻发生叙事，再 rollback
- `kick` / `autopilot` / `force` 与 replay/rollback 交错
- 战斗中途与普通事件切换时的状态回退边界

## 9. 建议的接手顺序

如果后续是新的 AI 来接手，建议按下面顺序推进，不要一上来就大改剧情逻辑。

### 第一阶段：先修“会直接导致系统失真”的基础问题

1. 修正所有 JSONL / JSON 读取为统一的 `utf-8-sig` 数据访问层
2. 修复 `astrbot_plugin_donghuang/.gitignore`，不要忽略插件资产 `data/`
3. 加一个离线校验脚本：
   - 校验所有 JSON / JSONL 可解析
   - 输出坏文件数量
   - 检查关键目录是否为空
4. 明确 zip 打包格式，并写打包脚本

### 第二阶段：抽离基础设施

1. 抽出 `storage.py`
2. 抽出 `assets.py`
3. 抽出 `prompts.py`
4. 抽出 `validators.py`
5. 给 group 状态加锁

目标不是立刻重写功能，而是让 `main.py` 不再无限膨胀。

### 第三阶段：收紧状态机边界

1. 将 `STATE_DELTA` 从路径 DSL 升级为 schema 化操作
2. 给 world/profile/event/output 的写入建立统一入口
3. 增加回滚一致性测试

### 第四阶段：补测试和发布链

最低建议补这些测试：

- 资产可读测试
- 关键命令注册测试
- 帮助文本 / README / 实际命令同步测试
- `STATE_DELTA` 拦截测试
- 死亡协议测试
- 回滚测试
- 托管测试
- 战斗结算测试

## 10. 后续 AI 接手时的注意事项

1. 不要先凭 README 想当然，先看代码真实加载了哪些规则文件。
2. 不要一上来就改剧情逻辑，先修数据读取与发布链。
3. `donghuang` 的问题核心是“工程边界”，不是“设定不够多”。
4. 若修改 `main.py`，优先做“抽模块”而不是继续堆分支。
5. 改命令时必须同步检查：
   - help text
   - `_DH_COMMAND_GUIDE`
   - `README.md`
   - `使用说明.md`
6. 注意工作区规则：
   - 禁止跨插件 import
   - 每个插件必须自包含
   - 运行时数据不能写回源码目录

## 11. 这次审计使用过的关键检查结论

可直接复用的事实：

- `astrbot_plugin_donghuang/main.py` 语法可编译
- `astrbot_plugin_trpg/main.py` 语法可编译
- `astrbot_plugin_donghuang` 中共有 1499 个 JSONL，1460 个带 BOM
- 全部 JSONL 在 `utf-8-sig` 下可解析
- `astrbot_plugin_donghuang/.gitignore` 当前错误地忽略了 `data/`
- `astrbot_plugin_donghuang` 的 README 与实际命令存在漂移
- `donghuang` 主入口高度巨型化，已经达到必须拆模块的阶段

## 12. 推荐的第一批落地任务

如果要继续推进，建议优先开这几项具体任务：

1. 新建 `scripts/validate_donghuang_assets.py`
2. 新建统一 JSON / JSONL 读取工具，替换 `main.py` 中散落的 `encoding="utf-8"`
3. 修正 `astrbot_plugin_donghuang/.gitignore`
4. 增加 `AUDIT_HANDOFF_2026-07-06.md` 到根目录文档索引
5. 给 `donghuang` 加最小 smoke tests

---

这份文档是“交接底稿”，不是最终设计方案。
它的目标是让下一个接手的人或 AI 不需要从零重新摸项目，也不会因为只看表面文档而误判系统状态。
