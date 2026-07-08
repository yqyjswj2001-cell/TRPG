# DATA_INTEGRITY_AUDIT.md — 存档数据完整性 / 恢复机制审计

审计日期：2026-07-08（C-0 任务第二、三节）
审计对象：`campaign.json`、`world_state.json`、`event_log.json`、
`action_log.json`（均在 `StarTools.get_data_dir(PLUGIN_NAME)` 下，
本地开发环境无真实存档文件，本次审计基于代码路径 + 合成损坏场景测试）。
配套测试：[tools/test_save_integrity.py](tools/test_save_integrity.py)（12 项，全部通过）。

**结论先行：加载路径的健壮性明显好于上一轮审计（`AUDIT_HANDOFF_2026-07-06.md`）
记录时的状态**——统一资产读取层 `asset_loader.py` 已经存在并被 main.py 实际
使用，BOM/损坏 JSON/空文件/缺失文件都有兜底。仍有两处结构性缺口，见第 4 节。

---

## 1. 加载路径：谁在读、怎么读

`main.py` 的 `_load_json(path, default)` 直接转调
`asset_loader.load_json_with_default(path, default)`（[main.py:1784](main.py:1784)、
[asset_loader.py:69](asset_loader.py:69)），四个存档文件全部走同一条路径：

```python
self.campaign        = self._load_json(self.campaign_file, {})
self.world_state      = self._load_json(self.world_state_file, {})
self.event_log        = self._load_json(self.event_log_file, {})
self.action_log       = self._load_json(self.action_log_file, [])
```

`asset_loader.load_json_with_default` 的实际行为（已用测试验证）：

| 场景 | 行为 | 是否会让插件启动失败 |
|---|---|---|
| 正常 JSON | 正确解析 | — |
| 带 UTF-8 BOM | 默认 `utf-8-sig` 编码，正确解析 | 否 |
| 空文件（0字节） | `json.JSONDecodeError` 被捕获，记录日志，返回调用方传入的 default | 否 |
| 文件不存在 | 直接返回 default，不抛异常 | 否 |
| 截断/语法损坏 JSON | `json.JSONDecodeError` 被捕获，记录日志，返回 default | 否 |
| 非 UTF-8 垃圾字节 | 通用 `Exception` 分支捕获，记录日志，返回 default | 否 |
| JSON 语法合法但顶层类型不对（如期待 dict 实际是 list） | **原样返回解析结果，不做类型校验** | 不会在加载这一步失败，但调用方后续按 dict 方式访问（如 `.get()`/`group_id in campaign`）大概率会在别处报错 |

**结论：加载层本身不会成为启动失败点。** 上一轮审计记录的"BOM 导致解析失败"
风险，在 `asset_loader.py` 这一层已经被系统性解决——但要注意这只覆盖了
"经过 `_al_load_json`/`_al_load_json_default` 读的文件"，第 5 节会说明
仍有个别路径没有走统一层。

---

## 2. 保存路径：原子性

`main.py._save_json`（[main.py:1787](main.py:1787)）：

```python
def _save_json(self, path: Path, data):
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
```

先写临时文件，再用 `os.replace`（Windows 下对应 `MoveFileEx` 加
`MOVEFILE_REPLACE_EXISTING`，跟 POSIX `rename()` 一样是原子操作）做替换。

**已验证的性质**（`test_atomic_save_interrupted_write_does_not_corrupt_original`）：
如果进程在写完 `.tmp` 但还没执行 `os.replace` 前被杀掉，原文件完全不受
影响——不存在"写一半，原文件被截断成半成品"的经典失败模式。

**唯一的剩余风险**：`.tmp` 文件本身在异常中断后会残留在数据目录里，
不会被自动清理（不影响正确性，只是磁盘上多一个孤儿临时文件）。这是低
优先级的卫生问题，不是数据安全问题，本次不处理。

---

## 3. 存档恢复机制审计（第三节要求）

### 3.1 是否缺字段自动补
**分层结论：campaign / world_state 级别有集中自愈，player_profile 级别只有零散自愈。**

- **campaign**：`_get_campaign()`（[main.py:2164](main.py:2164)）每次访问都会对
  9 个字段做 `setdefault` 自愈：`combat`、`npc_memory`、
  `npc_action_cooldown`、`npc_action_log`、`world_clock`、`tick_ledger`、
  `npc_world_queue`、`world_action_proposals`、`world_history`。这是一处
  写得很规范的"访问时自愈"模式，注释里明确标了各字段是哪个开发阶段
  （B-9/B-14 等）引入的，方便追溯。已用
  `test_get_campaign_self_heal_fields_present` 做静态回归锁定。
- **world_state**：启动时对所有已存在的 group 做一次性 `FACTION_STATE`
  补全（[main.py:1632](main.py:1632)，标注 B-5）。
- **player_profiles**：只在启动时对 `appearance` 字段做了一次性补全
  （[main.py:1575](main.py:1575)，标注 B-8）；除此之外，profile 的字段兼容是
  分散在各业务函数里的（比如 `_apply_breakthrough` 里对 `hp`/`six_dims`/
  `afflictions` 各自 `setdefault`），**没有一个统一的"读档时补全 profile
  全部字段"的入口**。这意味着：如果一份很旧的存档缺了某个从未被这些
  分散 setdefault 覆盖到的字段，只有在真正执行到那条访问路径时才会
  暴露问题（可能是 `KeyError`，也可能是 `.get()` 静默给默认值——取决于
  具体写法，没有统一保证）。

### 3.2 错误数据是否会导致启动失败
**不会，第 1 节已验证。** 四个存档文件的加载全部经过统一的容错层，
损坏数据最坏情况是"退回空 dict/list"，不会抛异常终止 `__init__`。

需要额外指出：**"不崩溃"不等于"不丢数据"**。如果 `campaign.json` 损坏，
加载层会安静地返回 `{}`，相当于该群所有开团状态清零——从"服务可用性"
角度这是对的（插件不会因为一个群的坏文件而整体起不来），但从"数据
是否丢失"角度，这是静默丢档，只在日志里留了一条 `logger.error`。
**建议（不在本次范围内动手）**：给"加载失败并回退默认值"这个分支加一条
更醒目的信号（比如往 `/dh doctor` 的诊断结果里带一条"检测到存档回退
到初始状态"的提示），而不只是写日志——GM 现在只能翻日志才能发现。

### 3.3 旧版本兼容
**部分验证。** 前述 setdefault 自愈机制本身就是旧版本兼容手段，且已经
经历过至少 5 轮标注（B-5/B-8/B-9/B-14，加上战斗系统上线前的兼容注释），
说明这是团队一直在维护的活跃机制，不是一次性补丁。**尚未验证的场景**：
更早期、字段命名方式发生过变化（不是新增字段，而是字段改名/改结构）的
"极老"存档——如果历史上有过这种破坏性变更，现有的 setdefault 模式无法
处理"旧字段名 → 新字段名"的迁移，只能处理"全新字段缺失"。这次审计没有
找到字段改名的历史证据，但也没有能力证伪，留作已知的验证盲区。

---

## 4. 结构性缺口（本次新确认的风险，未修复，等待确认后再处理）

1. **顶层类型不校验**（第1节）：如果 `campaign.json` 被外部工具/人手
   误存成了 list 或字符串，加载层不会拦截，问题会推迟到具体访问处才
   爆出来，报错信息可能跟"存档损坏"看起来毫无关系，排查成本高。
2. **player_profile 无集中迁移入口**（3.1节）：新增 profile 字段时，
   工程师必须记得同时在所有会读旧档的路径上补 `setdefault`，容易漏。
3. **静默丢档缺少可见信号**（3.2节）：加载失败退回默认值这件事目前
   只进日志，GM 侧没有直接感知手段。

以上三项均只是**报告**，本次未做任何代码改动（遵守"不改变数据结构"
约束）。是否要处理、何时处理，由开发者决定。

---

## 5. 一个已知但本次未深入验证的遗留项

上一轮审计（`AUDIT_HANDOFF_2026-07-06.md` 5.1 节）记录的"1499 个 JSONL
中 1460 个带 BOM"问题，本次确认 `asset_loader.py` 默认用 `utf-8-sig`
且已被 main.py 广泛复用（`_al_load_json`/`_al_load_jsonl` 出现在 main.py
至少 15 处静态资产加载点）——**从代码层面看这个问题已经被那一层封装
解决**。但本次没有重新扫描全部 1499 个 JSONL 文件逐一验证解析成功率
（那是一次性的资产健康检查，跟本次"存档结构完整性"审计范围不同）。
建议后续单独跑一次资产扫描确认，而不是假设"代码对了数据就一定没事"。
