"""
test_event_flow.py — 真实流程验收脚本

模拟完整的世界事件闭环流程：
  1. 新建 campaign
  2. seed 初始事件
  3. 玩家 action 推进事件
  4. 事件阶段变化
  5. 事件归档
  6. EVENT_LOG 写入
  7. rollback 恢复

纯开发验证工具，不是生产代码。

运行方式：
  python tools/test_event_flow.py
"""

import sys
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from world_event_pool import EventPool, EventStage, EventCategory, EventPriority, EventVisibility


class FakeCampaign:
    """模拟 campaign 数据结构。"""
    def __init__(self):
        self.data = {
            "state": "active",
            "cycle": 1,
            "next_event_id": 1,
            "event_pool": [],
        }


class FlowSimulator:
    """模拟 main.py 中的事件流程。"""

    def __init__(self):
        self.pool = EventPool()
        self.campaigns = {}
        self.event_logs = {}

    def _get_campaign(self, group_id):
        if group_id not in self.campaigns:
            self.campaigns[group_id] = FakeCampaign().data
        return self.campaigns[group_id]

    def step_create_campaign(self, group_id):
        """步骤1：新建 campaign"""
        campaign = self._get_campaign(group_id)
        self.event_logs[group_id] = []
        print(f"  📌 创建 campaign: {group_id}")
        return campaign

    def step_seed_events(self, group_id):
        """步骤2：手动 seed 初始事件（简化版，不用真实 asset_loader）"""
        events = []
        e1 = self.pool.add(
            group_id=group_id,
            title="灵气东移加速，东部灵脉出现偏转征象",
            category=EventCategory.LEYLINE_RESOURCE.value,
            stage=EventStage.SPROUT.value,
            region="东部",
            location="启阳",
            participants=["东部拓展宗门"],
            summary="灵气整体东移，东部新生支脉活跃",
            progress=0.15,
            priority=EventPriority.HIGH.value,
            visibility=EventVisibility.PUBLIC.value,
            player_related=False,
        )
        events.append(e1)

        e2 = self.pool.add(
            group_id=group_id,
            title="西部封印松动，西部局势持续恶化",
            category=EventCategory.FACTION_CONFLICT.value,
            stage=EventStage.ONGOING.value,
            region="西部",
            location="裂川",
            participants=["西部封禁势力"],
            summary="封禁结构稳定度高压，因果沉积接近临界",
            progress=0.45,
            priority=EventPriority.CRITICAL.value,
            visibility=EventVisibility.REGIONAL.value,
            player_related=False,
        )
        events.append(e2)

        print(f"  🌱 初始事件: {len(events)} 条")
        for e in events:
            print(f"     - {e.title}（{e.stage}，{e.region}，进度{int(e.progress*100)}%）")
        return events

    def step_player_action(self, group_id, action_type, region, location=""):
        """步骤3：玩家行动推动事件"""
        result = self.pool.apply_player_action(
            group_id=group_id,
            action_type=action_type,
            region=region,
            location=location,
            player_name="测试修士",
        )
        if result["affected_event"]:
            print(f"  ⚡ 玩家行动 {action_type}@{region}: 推动了「{result['title']}」"
                  f" {result['progress_before']:.1%}→{result['progress_after']:.1%}"
                  f"{'，阶段: '+result['old_stage']+'→'+result['new_stage'] if result['stage_changed'] else ''}")
        else:
            print(f"  ⚡ 玩家行动 {action_type}@{region}: 无影响")
        return result

    def step_archive_ended(self, group_id):
        """步骤4+5+6：归档已结束事件（两阶段提交）"""
        ended = [e for e in self.pool.list_all(group_id) if e.stage == EventStage.ENDED.value]
        if not ended:
            return []

        campaign = self._get_campaign(group_id)
        archived = []
        archive_ids = []

        for event in ended:
            record = self.pool.preview_archive(group_id, event.event_id)
            if record:
                record["cycle"] = f"Cycle-{campaign.get('cycle', 1):06d}"
                self.event_logs.setdefault(group_id, []).append(record)
                archive_ids.append(event.event_id)
                archived.append(record)

        # 模拟保存成功后 commit
        for event_id in archive_ids:
            self.pool.commit_archive(group_id, event_id)

        print(f"  📦 归档: {len(archived)} 条事件写入 EVENT_LOG")
        for r in archived:
            print(f"     - [{r['event_id']}] {r['title']}→EVENT_LOG")
        return archived

    def step_advance_world(self, group_id):
        """批量推进世界事件"""
        result = self.pool.advance_world_events(group_id)
        if result["advanced"]:
            print(f"  🔄 世界推进: {len(result['advanced'])} 条事件进度增加")
        if result["stage_changed"]:
            for item in result["stage_changed"]:
                print(f"     阶段变化: {item['title']}: {item['old_stage']}→{item['new_stage']}")
        if result["archived"]:
            # 写入 EVENT_LOG
            campaign = self._get_campaign(group_id)
            for record in result["archived"]:
                record["cycle"] = f"Cycle-{campaign.get('cycle', 1):06d}"
                self.event_logs.setdefault(group_id, []).append(record)
            for event_id in result["_archive_event_ids"]:
                self.pool.commit_archive(group_id, event_id)
            print(f"  📦 归档: {len(result['archived'])} 条")
        return result

    def step_snapshot(self, group_id):
        """拍快照"""
        snapshot = {
            "world_state": {"GLOBAL": {"phase": "灵气东移"}},
            "player_profiles": {},
            "event_log": json.loads(json.dumps(self.event_logs.get(group_id, []))),
            "campaign": json.loads(json.dumps(self._get_campaign(group_id))),
            "event_pool": json.loads(json.dumps(self.pool.dump(group_id))),
        }
        print(f"  📸 快照: {len(snapshot['event_pool'])} 条活跃事件")
        return snapshot

    def step_rollback(self, group_id, snapshot):
        """rollback"""
        self.pool.clear(group_id)
        saved_pool = snapshot.get("event_pool", [])
        if saved_pool:
            self.pool.load(group_id, saved_pool)
        self.event_logs[group_id] = json.loads(json.dumps(snapshot["event_log"]))
        print(f"  ⏪ 回滚: 恢复到 {len(saved_pool)} 条活跃事件")

    def show_status(self, group_id):
        """显示当前状态"""
        events = self.pool.list_all(group_id)
        log = self.event_logs.get(group_id, [])
        print(f"\n  📊 当前状态: {len(events)} 条活跃事件, {len(log)} 条历史记录")
        for e in events:
            print(f"     - {e.title}（{e.category}·{e.stage}，{e.region}，进度{int(e.progress*100)}%）")


def main():
    print("=" * 60)
    print("东荒世界事件闭环验收测试")
    print("=" * 60)

    sim = FlowSimulator()
    group_id = "验收测试群"

    # ── 步骤1: 新建 campaign ──
    print("\n【步骤1】新建 campaign")
    sim.step_create_campaign(group_id)

    # ── 步骤2: seed 初始事件 ──
    print("\n【步骤2】seed 初始事件")
    sim.step_seed_events(group_id)
    sim.show_status(group_id)

    # ── 步骤3: 玩家行动推动事件 ──
    print("\n【步骤3】玩家行动推动事件")
    sim.step_player_action(group_id, "explore", "东部", "启阳")
    sim.step_player_action(group_id, "battle", "西部", "裂川")
    sim.step_player_action(group_id, "cultivate", "东部")
    sim.show_status(group_id)

    # ── 步骤4: 拍快照 ──
    print("\n【步骤4】拍快照（回滚点）")
    snapshot = sim.step_snapshot(group_id)

    # ── 步骤5: 继续推进（/dh advance + 玩家行动） ──
    print("\n【步骤5】继续推进事件")
    sim.step_advance_world(group_id)
    sim.step_player_action(group_id, "investigate", "西部")
    sim.show_status(group_id)

    # ── 步骤6: 事件归档到 EVENT_LOG ──
    print("\n【步骤6】检查并归档已结束事件")
    sim.step_archive_ended(group_id)
    sim.show_status(group_id)

    # ── 步骤7: rollback 恢复 ──
    print("\n【步骤7】rollback 到步骤4的快照")
    sim.step_rollback(group_id, snapshot)
    sim.show_status(group_id)

    # ── 验收检查 ──
    print("\n" + "=" * 60)
    print("验收检查")
    print("=" * 60)

    events = sim.pool.list_all(group_id)
    log = sim.event_logs.get(group_id, [])

    # 检查1: rollback 后事件恢复
    assert len(events) == 2, f"❌ rollback 后应有 2 条活跃事件，实际 {len(events)}"
    print("  ✅ rollback 后活跃事件数量恢复")

    # 检查2: rollback 后 progress 恢复到快照值
    snapshot_pool = snapshot.get("event_pool", [])
    snapshot_progress = {e["event_id"]: e["progress"] for e in snapshot_pool}
    for e in events:
        if e.event_id in snapshot_progress:
            expected = snapshot_progress[e.event_id]
            assert abs(e.progress - expected) < 0.001, \
                f"❌ rollback 后 {e.title} progress 应为 {expected}，实际 {e.progress}"
            print(f"  ✅ {e.title[:10]}… progress 恢复到 {e.progress:.2f}（快照值 {expected:.2f}）")

    # 检查3: EVENT_LOG 也恢复了
    assert len(log) == 0, f"❌ rollback 后 EVENT_LOG 应为空（快照时还没有归档），实际 {len(log)} 条"
    print("  ✅ EVENT_LOG 恢复正确")

    # 检查4: 再次推进不报错
    print("\n  再次推进验证...")
    sim.step_advance_world(group_id)
    sim.show_status(group_id)

    # ── 旧快照兼容性测试 ──
    print("\n" + "=" * 60)
    print("旧快照兼容性测试")
    print("=" * 60)
    old_snapshot = {
        "world_state": {},
        "player_profiles": {},
        "event_log": [],
        "campaign": {},
        # 没有 event_pool 字段
    }
    sim.step_rollback(group_id, old_snapshot)
    assert len(sim.pool.list_all(group_id)) == 0, "❌ 旧快照恢复后池应为空"
    print("  ✅ 旧快照（无 event_pool）兼容恢复成功")

    print("\n🎉 全部验收测试通过！")


if __name__ == "__main__":
    main()
