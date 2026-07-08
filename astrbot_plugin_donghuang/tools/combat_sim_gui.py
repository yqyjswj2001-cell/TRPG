"""
combat_sim_gui.py - 战斗数值平衡模拟器（图形界面版）

双击插件目录下的「战斗平衡模拟器.bat」启动，或手动运行：
    py tools\\combat_sim_gui.py

功能：
  - 模拟设置：每格场数/种子/队伍人数/境界范围/妖兽品阶/策略/武器，
    点「开始模拟」后台跑批，进度条实时推进。
  - 胜率热力图：境界×品阶彩色格子（红=打不过，黄=势均力敌，绿=碾压，
    带"!"=有僵局），点击任意格子看该配置的完整统计。
  - 数值旋钮：妖兽各品阶数值区间/武器加成/逃跑DC/施法耗蓝/丹药回复/
    HP成长曲线都能改，改完直接重跑看效果。⚠ 旋钮只影响模拟进程，
    不会写回游戏代码——调出满意的数值后请手动同步到 main.py。
  - 每次矩阵模拟自动存档到 tools/balance_results/（含当时的数值常量
    快照），并自动对比上一次运行、列出胜率显著变化的格子。

实现说明：本文件只是 combat_simulator.py 的图形外壳，所有战斗数学
仍旧直接复用 main.py 的真实函数，见 combat_simulator.py 头部注释。
"""

import copy
import os
import queue
import random
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk

sys.path.insert(0, str(Path(__file__).resolve().parent))

import combat_simulator as cs  # noqa: E402  （它自己会装 astrbot stub 并引入 main.py）

m = cs.m

# 高分屏下让字体清晰（失败无所谓，只是模糊一点）
try:
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

# 游戏当前值的原始快照，供"恢复默认"和"是否已修改"判断用
_PRISTINE = {
    "MONSTER_TIER_STATS": copy.deepcopy(m._MONSTER_TIER_STATS),
    "TIER_COMBAT_BONUS": dict(m._TIER_COMBAT_BONUS),
    "FLEE_DC_BY_TIER": dict(m._FLEE_DC_BY_TIER),
    "TIER_HEAL_AMOUNT": dict(m._TIER_HEAL_AMOUNT),
    "CAST_MP_COST": m._CAST_MP_COST,
    "HP_CURVE": dict(cs.HP_CURVE),
}

_TIERS = list(cs._MONSTER_TIERS)
_STAT_FIELDS = [("hp", "气血"), ("mp", "灵力"), ("atk", "攻击"), ("def", "防御"), ("init", "先攻")]
_CJK_FONT = ("Microsoft YaHei UI", 10)
_MONO_FONT = ("NSimSun", 10)


def _lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _win_color(rate):
    """胜率→背景色：0%深红 → 50%琥珀 → 100%绿。"""
    red, amber, green = (198, 63, 55), (240, 190, 50), (46, 160, 90)
    rgb = _lerp(red, amber, rate / 0.5) if rate <= 0.5 else _lerp(amber, green, (rate - 0.5) / 0.5)
    return "#%02x%02x%02x" % rgb, rgb


def _fg_for(rgb):
    lum = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]
    return "#ffffff" if lum < 140 else "#1a1a1a"


def _cell_detail_text(c):
    return (
        f"{c['realm']} · {c['party']}人 vs {c['tier']}"
        f"（策略={c['strategy']}，{c['weapon_tier'] or '无武器'}，{c['battles']}场）\n"
        f"胜率 {c['win_rate']:.1%}　团灭 {c['wipe_rate']:.1%}　全员撤离 {c['fled_rate']:.1%}　僵局 {c['timeout_rate']:.1%}\n"
        f"平均 {c['avg_rounds']:.1f} 回合　有人倒地的场次 {c['downed_rate']:.1%}　场均倒地 {c['avg_downed']:.2f} 人\n"
        f"惨胜率 {c['pyrrhic_rate']:.1%}　胜时幸存者平均余血 {c['avg_win_hp_pct']:.0%}　"
        f"败时妖兽平均余血 {c['avg_loss_monster_hp_pct']:.0%}"
    )


def compute_matrix(params, progress_cb=None, cancel_event=None):
    """跑一遍矩阵并打包成跟 CLI 相同结构的 payload。独立于任何窗口部件，
    后台线程和 --selftest 共用这一个入口。"""
    random.seed(params["seed"])
    t0 = time.time()
    combos = [
        (party, tier, idx)
        for party in params["parties"]
        for tier in params["tiers"]
        for idx in params["realm_indices"]
    ]
    cells = []
    for n, (party, tier, idx) in enumerate(combos, 1):
        if cancel_event is not None and cancel_event.is_set():
            return None, None, 0.0
        cells.append(cs.run_cell(idx, tier, party, params["strategy"], params["weapon"], params["battles"]))
        if progress_cb:
            progress_cb(n, len(combos))

    flags = cs.analyze_flags(cells)
    rec = cs.recommend_ranges(cells)
    previous = cs._find_previous_result()
    diffs = cs.compare_with_previous(cells, previous)
    snap, digest = cs.constants_snapshot()
    payload = {
        "meta": {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "seed": params["seed"],
            "battles_per_cell": params["battles"],
            "elapsed_seconds": round(time.time() - t0, 1),
            "constants_hash": digest,
            "constants": snap,
            "source": "gui",
        },
        "matrix": cells,
        "strategy_experiment": [],
        "weapon_experiment": [],
        "flee_table": [],
        "flags": flags,
        "recommended_ranges": rec,
        "diff_vs_previous": diffs,
    }
    out_path = cs.save_results(payload) if params.get("save", True) else None
    return payload, out_path, time.time() - t0


class SimGUI:
    def __init__(self, root):
        self.root = root
        root.title("东荒 · 战斗数值平衡模拟器")
        root.geometry("1240x800")
        root.minsize(1000, 640)

        style = ttk.Style()
        for name in ("vista", "clam"):
            if name in style.theme_names():
                style.theme_use(name)
                break

        self._queue = queue.Queue()
        self._cancel = threading.Event()
        self._running = False
        self._last_payload = None

        notebook = ttk.Notebook(root)
        notebook.pack(side="top", fill="x", padx=8, pady=(8, 4))
        self._build_sim_tab(notebook)
        self._build_knob_tab(notebook)

        body = ttk.Frame(root)
        body.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        self._build_heatmap_panel(body)
        self._build_text_panel(body)

        self.status_var = tk.StringVar(value="就绪。设置好参数后点「开始模拟」。")
        ttk.Label(root, textvariable=self.status_var, anchor="w").pack(
            side="bottom", fill="x", padx=10, pady=(0, 6)
        )

        root.after(100, self._poll_queue)

    # ---------- 模拟设置页 ----------

    def _build_sim_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=8)
        notebook.add(tab, text=" 模拟设置 ")

        row1 = ttk.Frame(tab)
        row1.pack(fill="x")

        ttk.Label(row1, text="每格场数").pack(side="left")
        self.battles_var = tk.IntVar(value=300)
        ttk.Spinbox(row1, from_=20, to=2000, increment=50, width=6,
                    textvariable=self.battles_var).pack(side="left", padx=(4, 14))

        ttk.Label(row1, text="随机种子").pack(side="left")
        self.seed_var = tk.StringVar(value="")
        seed_entry = ttk.Entry(row1, width=10, textvariable=self.seed_var)
        seed_entry.pack(side="left", padx=(4, 2))
        ttk.Label(row1, text="(留空=随机)").pack(side="left", padx=(0, 14))

        ttk.Label(row1, text="队伍人数").pack(side="left")
        self.party_vars = {}
        for p in (1, 3, 5):
            var = tk.BooleanVar(value=(p != 5))
            self.party_vars[p] = var
            ttk.Checkbutton(row1, text=f"{p}人", variable=var).pack(side="left", padx=2)

        ttk.Label(row1, text="　妖兽品阶").pack(side="left")
        self.tier_vars = {}
        for t in _TIERS:
            var = tk.BooleanVar(value=True)
            self.tier_vars[t] = var
            ttk.Checkbutton(row1, text=t, variable=var).pack(side="left", padx=2)

        row2 = ttk.Frame(tab)
        row2.pack(fill="x", pady=(8, 0))

        ttk.Label(row2, text="境界范围").pack(side="left")
        self.realm_from = ttk.Combobox(row2, values=m._REALMS, width=10, state="readonly")
        self.realm_from.set(m._REALMS[0])
        self.realm_from.pack(side="left", padx=(4, 2))
        ttk.Label(row2, text="到").pack(side="left")
        self.realm_to = ttk.Combobox(row2, values=m._REALMS, width=10, state="readonly")
        self.realm_to.set(m._REALMS[-1])
        self.realm_to.pack(side="left", padx=(2, 14))

        ttk.Label(row2, text="策略").pack(side="left")
        self.strategy_box = ttk.Combobox(row2, values=list(cs.STRATEGIES), width=8, state="readonly")
        self.strategy_box.set("普攻")
        self.strategy_box.pack(side="left", padx=(4, 14))

        ttk.Label(row2, text="武器").pack(side="left")
        self.weapon_box = ttk.Combobox(row2, values=["无"] + _TIERS, width=8, state="readonly")
        self.weapon_box.set("无")
        self.weapon_box.pack(side="left", padx=(4, 14))

        self.run_btn = ttk.Button(row2, text="▶ 开始模拟", command=self._on_run)
        self.run_btn.pack(side="left", padx=(10, 4))
        self.cancel_btn = ttk.Button(row2, text="取消", command=self._cancel.set, state="disabled")
        self.cancel_btn.pack(side="left", padx=4)

        ttk.Button(row2, text="策略对比实验", command=lambda: self._on_experiment("strategy")).pack(side="left", padx=4)
        ttk.Button(row2, text="武器影响实验", command=lambda: self._on_experiment("weapon")).pack(side="left", padx=4)
        ttk.Button(row2, text="逃跑成功率表", command=lambda: self._on_experiment("flee")).pack(side="left", padx=4)
        ttk.Button(row2, text="打开结果文件夹", command=self._open_results_dir).pack(side="left", padx=(12, 0))

        self.progress = ttk.Progressbar(tab, mode="determinate")
        self.progress.pack(fill="x", pady=(10, 2))

    # ---------- 数值旋钮页 ----------

    def _build_knob_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=8)
        notebook.add(tab, text=" 数值旋钮 ")

        grid = ttk.Frame(tab)
        grid.pack(fill="x")

        ttk.Label(grid, text="品阶", width=6).grid(row=0, column=0)
        for j, (_, zh) in enumerate(_STAT_FIELDS):
            ttk.Label(grid, text=f"{zh}min~max").grid(row=0, column=1 + j * 2, columnspan=2, padx=2)

        self.monster_entries = {}
        for i, tier in enumerate(_TIERS, start=1):
            ttk.Label(grid, text=tier).grid(row=i, column=0, pady=1)
            for j, (key, _) in enumerate(_STAT_FIELDS):
                lo = tk.StringVar()
                hi = tk.StringVar()
                self.monster_entries[(tier, key)] = (lo, hi)
                ttk.Entry(grid, width=5, textvariable=lo).grid(row=i, column=1 + j * 2, padx=(6, 1))
                ttk.Entry(grid, width=5, textvariable=hi).grid(row=i, column=2 + j * 2, padx=(1, 6))

        misc = ttk.Frame(tab)
        misc.pack(fill="x", pady=(10, 0))

        def _tier_row(parent, row, label):
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w")
            out = {}
            for j, t in enumerate(_TIERS):
                ttk.Label(parent, text=t).grid(row=row, column=1 + j * 2, padx=(8, 1))
                var = tk.StringVar()
                out[t] = var
                ttk.Entry(parent, width=5, textvariable=var).grid(row=row, column=2 + j * 2)
            return out

        self.bonus_entries = _tier_row(misc, 0, "武器/法宝攻击加成")
        self.flee_entries = _tier_row(misc, 1, "逃跑难度DC")
        self.heal_entries = _tier_row(misc, 2, "丹药回血量")

        misc2 = ttk.Frame(tab)
        misc2.pack(fill="x", pady=(8, 0))
        ttk.Label(misc2, text="施法灵力消耗").pack(side="left")
        self.cast_var = tk.StringVar()
        ttk.Entry(misc2, width=5, textvariable=self.cast_var).pack(side="left", padx=(4, 16))
        ttk.Label(misc2, text="HP曲线：基础").pack(side="left")
        self.hp_base_var = tk.StringVar()
        ttk.Entry(misc2, width=5, textvariable=self.hp_base_var).pack(side="left", padx=2)
        ttk.Label(misc2, text="每突破+").pack(side="left")
        self.hp_step_var = tk.StringVar()
        ttk.Entry(misc2, width=5, textvariable=self.hp_step_var).pack(side="left", padx=2)
        ttk.Label(misc2, text="跨大境界+").pack(side="left")
        self.hp_boundary_var = tk.StringVar()
        ttk.Entry(misc2, width=5, textvariable=self.hp_boundary_var).pack(side="left", padx=2)

        btns = ttk.Frame(tab)
        btns.pack(fill="x", pady=(10, 0))
        ttk.Button(btns, text="✔ 应用旋钮到模拟", command=self._apply_knobs).pack(side="left")
        ttk.Button(btns, text="↺ 恢复游戏默认值", command=self._reset_knobs).pack(side="left", padx=8)
        self.knob_state_var = tk.StringVar()
        ttk.Label(btns, textvariable=self.knob_state_var).pack(side="left", padx=12)
        ttk.Label(
            tab,
            text="⚠ 旋钮只改本程序里的模拟数值，不会写回游戏代码；调出满意的组合后，请手动同步到 main.py 对应常量"
                 "（_MONSTER_TIER_STATS / _TIER_COMBAT_BONUS / _FLEE_DC_BY_TIER / _TIER_HEAL_AMOUNT / _CAST_MP_COST；"
                 "HP曲线在 _apply_breakthrough）。",
            foreground="#a05a00", wraplength=1150, justify="left",
        ).pack(fill="x", pady=(8, 0))

        self._load_knobs_from_live()

    def _load_knobs_from_live(self):
        for tier in _TIERS:
            for key, _ in _STAT_FIELDS:
                lo, hi = m._MONSTER_TIER_STATS[tier][key]
                self.monster_entries[(tier, key)][0].set(str(lo))
                self.monster_entries[(tier, key)][1].set(str(hi))
            self.bonus_entries[tier].set(str(m._TIER_COMBAT_BONUS[tier]))
            self.flee_entries[tier].set(str(m._FLEE_DC_BY_TIER[tier]))
            self.heal_entries[tier].set(str(m._TIER_HEAL_AMOUNT[tier]))
        self.cast_var.set(str(m._CAST_MP_COST))
        self.hp_base_var.set(str(cs.HP_CURVE["base"]))
        self.hp_step_var.set(str(cs.HP_CURVE["step"]))
        self.hp_boundary_var.set(str(cs.HP_CURVE["boundary_step"]))
        self._refresh_knob_state()

    def _apply_knobs(self):
        try:
            for tier in _TIERS:
                stats = {}
                for key, zh in _STAT_FIELDS:
                    lo = int(self.monster_entries[(tier, key)][0].get())
                    hi = int(self.monster_entries[(tier, key)][1].get())
                    if lo > hi:
                        raise ValueError(f"{tier}{zh}：min({lo}) 不能大于 max({hi})")
                    stats[key] = (lo, hi)
                m._MONSTER_TIER_STATS[tier].update(stats)
                m._TIER_COMBAT_BONUS[tier] = int(self.bonus_entries[tier].get())
                m._FLEE_DC_BY_TIER[tier] = int(self.flee_entries[tier].get())
                m._TIER_HEAL_AMOUNT[tier] = int(self.heal_entries[tier].get())
            m._CAST_MP_COST = int(self.cast_var.get())
            cs.HP_CURVE["base"] = int(self.hp_base_var.get())
            cs.HP_CURVE["step"] = int(self.hp_step_var.get())
            cs.HP_CURVE["boundary_step"] = int(self.hp_boundary_var.get())
        except ValueError as e:
            messagebox.showerror("数值不合法", str(e))
            return
        self._refresh_knob_state()
        self.status_var.set("旋钮已应用，下次模拟按新数值跑。")

    def _reset_knobs(self):
        for tier in _TIERS:
            m._MONSTER_TIER_STATS[tier].update(copy.deepcopy(_PRISTINE["MONSTER_TIER_STATS"][tier]))
        m._TIER_COMBAT_BONUS.update(_PRISTINE["TIER_COMBAT_BONUS"])
        m._FLEE_DC_BY_TIER.update(_PRISTINE["FLEE_DC_BY_TIER"])
        m._TIER_HEAL_AMOUNT.update(_PRISTINE["TIER_HEAL_AMOUNT"])
        m._CAST_MP_COST = _PRISTINE["CAST_MP_COST"]
        cs.HP_CURVE.update(_PRISTINE["HP_CURVE"])
        self._load_knobs_from_live()
        self.status_var.set("已恢复游戏当前默认数值。")

    def _knobs_modified(self):
        return not (
            m._MONSTER_TIER_STATS == _PRISTINE["MONSTER_TIER_STATS"]
            and m._TIER_COMBAT_BONUS == _PRISTINE["TIER_COMBAT_BONUS"]
            and m._FLEE_DC_BY_TIER == _PRISTINE["FLEE_DC_BY_TIER"]
            and m._TIER_HEAL_AMOUNT == _PRISTINE["TIER_HEAL_AMOUNT"]
            and m._CAST_MP_COST == _PRISTINE["CAST_MP_COST"]
            and cs.HP_CURVE == _PRISTINE["HP_CURVE"]
        )

    def _refresh_knob_state(self):
        if self._knobs_modified():
            self.knob_state_var.set("当前模拟数值：已修改 ⚠（结果文件的常量快照会如实记录）")
        else:
            self.knob_state_var.set("当前模拟数值：与游戏代码一致")

    # ---------- 热力图面板 ----------

    def _build_heatmap_panel(self, body):
        left = ttk.Frame(body)
        left.pack(side="left", fill="y", padx=(0, 6))

        bar = ttk.Frame(left)
        bar.pack(fill="x")
        ttk.Label(bar, text="胜率热力图 · 队伍").pack(side="left")
        self.party_box = ttk.Combobox(bar, values=[], width=5, state="readonly")
        self.party_box.pack(side="left", padx=4)
        self.party_box.bind("<<ComboboxSelected>>", lambda e: self._render_heatmap())
        ttk.Label(bar, text="（点格子看详情，! = 出现僵局）").pack(side="left", padx=4)

        self.heat_frame = ttk.Frame(left)
        self.heat_frame.pack(pady=(6, 4))

        self.detail_var = tk.StringVar(value="尚未运行模拟。")
        ttk.Label(left, textvariable=self.detail_var, font=_CJK_FONT,
                  wraplength=560, justify="left", relief="groove", padding=6).pack(fill="x", pady=(2, 0))

    def _build_text_panel(self, body):
        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True)
        ttk.Label(right, text="告警 / 推荐区间 / 与上次对比 / 实验输出").pack(anchor="w")
        self.text = scrolledtext.ScrolledText(right, font=_MONO_FONT, wrap="none", height=10)
        self.text.pack(fill="both", expand=True, pady=(4, 0))

    def _render_heatmap(self):
        for w in self.heat_frame.winfo_children():
            w.destroy()
        if not self._last_payload:
            return
        matrix = self._last_payload["matrix"]
        try:
            party = int(self.party_box.get())
        except (ValueError, TypeError):
            return
        rows = [c for c in matrix if c["party"] == party]
        if not rows:
            return
        tiers = [t for t in _TIERS if any(c["tier"] == t for c in rows)]
        realm_indices = sorted({c["realm_idx"] for c in rows})

        for j, t in enumerate(tiers):
            ttk.Label(self.heat_frame, text=t, font=_CJK_FONT).grid(row=0, column=1 + j, padx=1)
        for i, idx in enumerate(realm_indices, start=1):
            ttk.Label(self.heat_frame, text=m._REALMS[idx], font=_CJK_FONT).grid(
                row=i, column=0, sticky="e", padx=(0, 4))
            for j, t in enumerate(tiers):
                c = next((x for x in rows if x["realm_idx"] == idx and x["tier"] == t), None)
                if c is None:
                    continue
                hexcolor, rgb = _win_color(c["win_rate"])
                mark = "!" if c["timeout_rate"] > 0.02 else ""
                lbl = tk.Label(
                    self.heat_frame,
                    text=f"{c['win_rate']:.0%}/{c['avg_rounds']:.0f}回{mark}",
                    bg=hexcolor, fg=_fg_for(rgb), font=("Microsoft YaHei UI", 9),
                    width=11, relief="ridge", bd=1, cursor="hand2",
                )
                lbl.grid(row=i, column=1 + j, padx=1, pady=1)
                lbl.bind("<Button-1>", lambda e, cell=c: self.detail_var.set(_cell_detail_text(cell)))

    # ---------- 运行与线程 ----------

    def _collect_params(self):
        parties = [p for p, v in self.party_vars.items() if v.get()]
        tiers = [t for t, v in self.tier_vars.items() if v.get()]
        if not parties or not tiers:
            raise ValueError("至少要勾选一个队伍人数和一个妖兽品阶")
        i_from = m._REALMS.index(self.realm_from.get())
        i_to = m._REALMS.index(self.realm_to.get())
        if i_from > i_to:
            i_from, i_to = i_to, i_from
        seed_text = self.seed_var.get().strip()
        seed = int(seed_text) if seed_text else random.randrange(1 << 31)
        weapon = self.weapon_box.get()
        return {
            "battles": max(1, int(self.battles_var.get())),
            "seed": seed,
            "parties": sorted(parties),
            "tiers": tiers,
            "realm_indices": list(range(i_from, i_to + 1)),
            "strategy": self.strategy_box.get(),
            "weapon": None if weapon == "无" else weapon,
            "save": True,
        }

    def _set_running(self, running):
        self._running = running
        self.run_btn.config(state="disabled" if running else "normal")
        self.cancel_btn.config(state="normal" if running else "disabled")

    def _on_run(self):
        if self._running:
            return
        try:
            params = self._collect_params()
        except ValueError as e:
            messagebox.showerror("参数不合法", str(e))
            return
        total = len(params["parties"]) * len(params["tiers"]) * len(params["realm_indices"])
        self.progress.config(maximum=total, value=0)
        self._cancel.clear()
        self._set_running(True)
        knob_note = "（数值已修改⚠）" if self._knobs_modified() else ""
        self.status_var.set(
            f"模拟中：{total} 格 × {params['battles']} 场，种子={params['seed']}{knob_note}……")

        def worker():
            try:
                payload, path, elapsed = compute_matrix(
                    params,
                    progress_cb=lambda n, tot: self._queue.put(("progress", n)),
                    cancel_event=self._cancel,
                )
                if payload is None:
                    self._queue.put(("cancelled", None))
                else:
                    self._queue.put(("done", (payload, path, elapsed)))
            except Exception as e:  # 后台线程的异常必须送回主线程展示
                self._queue.put(("error", f"{type(e).__name__}: {e}"))

        threading.Thread(target=worker, daemon=True).start()

    def _on_experiment(self, kind):
        if self._running:
            return
        battles = max(1, int(self.battles_var.get()))
        self._set_running(True)
        self.status_var.set("实验运行中……")

        def worker():
            try:
                lines = []
                if kind == "strategy":
                    result = cs.run_strategy_experiment(battles=battles)
                    lines.append(f"【策略对比】（3人队伍，每格{battles}场）")
                    for idx, tier in [(4, "玄级"), (10, "地级"), (13, "天级")]:
                        lines.append(f"  {m._REALMS[idx]} vs {tier}：")
                        for c in result:
                            if c["realm_idx"] == idx and c["tier"] == tier:
                                extra = f"，逃走率{c['fled_rate']:.0%}" if c["strategy"] == "见势撤" else ""
                                lines.append(
                                    f"    {cs._pad(c['strategy'], 8)}胜率 {c['win_rate']:>4.0%}  "
                                    f"平均 {c['avg_rounds']:.1f} 回合  倒地率 {c['downed_rate']:.0%}{extra}")
                elif kind == "weapon":
                    result = cs.run_weapon_experiment(battles=battles)
                    lines.append(f"【武器影响】（练气五层3人 vs 玄级，普攻，每格{battles}场）")
                    for c in result:
                        label = c["weapon_tier"] or "无武器"
                        lines.append(f"    {cs._pad(label, 8)}胜率 {c['win_rate']:>4.0%}  平均 {c['avg_rounds']:.1f} 回合")
                else:
                    result = cs.run_flee_table()
                    lines.append("【逃跑成功率】（1d20+(根骨-10)//2 vs 品阶DC）")
                    lines.append("    " + cs._pad("根骨", 8) + "".join(cs._pad(t, 10) for t in _TIERS))
                    for bone in (8, 10, 12, 14):
                        row = cs._pad(str(bone), 8)
                        for t in _TIERS:
                            e = next(x for x in result if x["根骨"] == bone and x["tier"] == t)
                            row += cs._pad(f"{e['success_rate']:.0%}", 10)
                        lines.append("    " + row)
                self._queue.put(("experiment", "\n".join(lines)))
            except Exception as e:
                self._queue.put(("error", f"{type(e).__name__}: {e}"))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_queue(self):
        try:
            while True:
                kind, data = self._queue.get_nowait()
                if kind == "progress":
                    self.progress.config(value=data)
                elif kind == "done":
                    payload, path, elapsed = data
                    self._last_payload = payload
                    self._set_running(False)
                    self.progress.config(value=0)
                    parties = sorted({c["party"] for c in payload["matrix"]})
                    self.party_box.config(values=parties)
                    self.party_box.set(parties[0])
                    self._render_heatmap()
                    self._show_run_report(payload)
                    total = sum(c["battles"] for c in payload["matrix"])
                    self.status_var.set(
                        f"完成：{total} 场模拟耗时 {elapsed:.1f}s，"
                        f"种子={payload['meta']['seed']}，常量指纹={payload['meta']['constants_hash']}，"
                        f"已存 {path.name if path else '（未存档）'}")
                elif kind == "experiment":
                    self._set_running(False)
                    self.text.insert("1.0", data + "\n\n")
                    self.status_var.set("实验完成，结果已插入右侧文本区顶部。")
                elif kind == "cancelled":
                    self._set_running(False)
                    self.progress.config(value=0)
                    self.status_var.set("已取消，本次结果未保存。")
                elif kind == "error":
                    self._set_running(False)
                    self.progress.config(value=0)
                    self.status_var.set("出错了。")
                    messagebox.showerror("模拟出错", data)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _show_run_report(self, payload):
        lines = []
        meta = payload["meta"]
        lines.append(
            f"═══ 运行 {meta['timestamp']} · 种子{meta['seed']} · 每格{meta['battles_per_cell']}场 · "
            f"常量指纹{meta['constants_hash']} ═══")
        lines.append(f"\n【自动平衡告警】（{len(payload['flags'])} 条）")
        lines.extend(f"  {f}" for f in payload["flags"]) if payload["flags"] else lines.append("  （无告警）")
        lines.append("\n【推荐挑战区间】（胜率35%~90%）")
        for key, val in payload["recommended_ranges"].items():
            lines.append(f"  {cs._pad(key, 12)}{val}")
        if payload["diff_vs_previous"]:
            lines.append(f"\n【与上次运行的显著变化】（|Δ胜率|≥8pp，共 {len(payload['diff_vs_previous'])} 处）")
            lines.extend(f"  {d}" for d in payload["diff_vs_previous"])
        lines.append("")
        self.text.insert("1.0", "\n".join(lines) + "\n")

    def _open_results_dir(self):
        cs._RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(str(cs._RESULTS_DIR))


def _selftest():
    """无人值守自检：建窗但不进主循环，同步跑一个 2 格迷你矩阵并渲染
    热力图，验证计算与界面代码没有硬错误。"""
    root = tk.Tk()
    root.withdraw()
    app = SimGUI(root)
    params = {
        "battles": 5, "seed": 99, "parties": [1], "tiers": ["黄级"],
        "realm_indices": [0, 13], "strategy": "普攻", "weapon": None, "save": False,
    }
    payload, path, elapsed = compute_matrix(params)
    assert payload and len(payload["matrix"]) == 2
    app._last_payload = payload
    app.party_box.config(values=[1])
    app.party_box.set(1)
    app._render_heatmap()
    app._show_run_report(payload)
    app._apply_knobs()          # 用界面里的默认值走一遍应用逻辑
    assert not app._knobs_modified()
    app._reset_knobs()
    root.update_idletasks()
    root.destroy()
    print("selftest ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        _root = tk.Tk()
        SimGUI(_root)
        _root.mainloop()
