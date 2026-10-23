# -*- coding: utf-8 -*-
"""A/B 汇总 + 路线定级：把每次运行的记录汇成「每条路线 均值±标准差」，并给出每条路线的状态。

输入：runs.jsonl（每行一个 JSON）或 CSV。字段：
  task, route（或旧版的 group）, calls, failed, input_tokens, cost, seconds, quality_ok(1/0), toolchain(用 > 连接)
  可选：agent, model —— 有就按「agent/model」分开比较（同一配方在不同 Agent、模型上可能结论不同）
  route 取基线组名（默认 A）= 不给配方；其它值 = 配方的某条路线或某个版本

用法：python ab_report.py runs.jsonl [--baseline A] [--min-gain 0.15]

定级规则（每个 agent/model × 任务 单独判，与同条件的基线比；质量第一，成本第二）：
  淘汰  本路线质量判据没有全过（不用等够 3 次）
  合格  基线会做错、本路线全对（质量收益；费用变化照实写出）
  候选  次数 < 3，数据不够，继续跑
  淘汰  质量与基线持平时：失败调用均值高于基线且超出两组波动；或没有任何一项「明显」变好
  合格  质量与基线持平时：至少一项明显变好——调用/费用/耗时下降 ≥ min-gain 且差值大于两组标准差中较大者，或失败更少
  注意「失败调用」口径因 Agent 而异（命令非零退出也算），配方要求的探测/复核命令可能按设计返回非零，看轨迹再下结论
  合格的路线里费用均值最低的 = 默认，其余 = 备用
退出码：有路线被判淘汰时为 1（便于放进 CI）。
"""
import argparse
import csv
import json
import statistics as st
import sys
from collections import defaultdict

KEYS = ("calls", "failed", "input_tokens", "cost", "seconds")


def load(path):
    if path.endswith(".jsonl"):
        rows = [json.loads(l) for l in open(path, encoding="utf-8-sig") if l.strip()]
    else:
        rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    bad = [r for r in rows if str(r.get("escaped") or "0") not in ("0", "")]
    if bad:   # 跑出工作目录、看过答案/核对脚本/配方的运行不算有效样本
        print(f"（剔除 {len(bad)} 次越界运行：" + "，".join(f"{r.get('task')}/{r.get('route')}{r.get('run', '')}" for r in bad) + "）\n")
        rows = [r for r in rows if r not in bad]
    for r in rows:
        r["route"] = str(r.get("route") or r.get("group"))
        r["combo"] = "/".join(x for x in (str(r.get("agent") or ""), str(r.get("model") or "")) if x) or "-"
        for k in KEYS:
            r[k] = float(r[k])
        r["quality_ok"] = int(r["quality_ok"])
    return rows


def mean_sd(rs, k):
    v = [x[k] for x in rs]
    return st.mean(v), (st.stdev(v) if len(v) > 1 else 0.0)


def grade(rs, base, min_gain, is_base):
    n, q = len(rs), sum(x["quality_ok"] for x in rs)
    if is_base:
        return "基线", ""
    if not base:
        return "候选", "没有同条件的基线"
    why, gains = [], []
    if q < n:   # 质量是第一位的；有害证据不用等够 3 次
        return "淘汰", f"质量 {q}/{n}"
    qb = sum(x["quality_ok"] for x in base)
    if qb < len(base):   # 基线会做错、本路线全对：质量收益优先于成本，成本变化照实写出
        (cb, _), (cr, _) = mean_sd(base, "cost"), mean_sd(rs, "cost")
        cost_note = f"，费用 {'+' if cr >= cb else '-'}{abs(cr - cb) / cb:.0%}" if cb > 0 else ""
        return ("候选" if n < 3 else "合格"), f"质量 {qb}/{len(base)}→{q}/{n}{cost_note}" + (f"（只有 {n} 次）" if n < 3 else "")
    (fb, sfb), (fr, sfr) = mean_sd(base, "failed"), mean_sd(rs, "failed")
    note = ""
    if fr > fb and (fr - fb) > max(sfb, sfr):    # 和「明显变好」同一把尺子：超出波动才算
        why.append(f"失败 {fb:.1f}→{fr:.1f}")
    elif fr > fb:
        note = f"；失败略增 {fb:.1f}→{fr:.1f}（在波动内，看轨迹确认不是配方步骤引起的）"
    if why:
        return "淘汰", "；".join(why) + "（质量与基线持平时，多出的失败调用算成本损失）"
    if n < 3:
        return "候选", f"只有 {n} 次" + note
    for k, label in (("calls", "调用"), ("cost", "费用"), ("seconds", "耗时")):
        (mb, sb), (mr, sr) = mean_sd(base, k), mean_sd(rs, k)
        if mb > 0 and (mb - mr) / mb >= min_gain and (mb - mr) > max(sb, sr):
            gains.append(f"{label}-{(mb - mr) / mb:.0%}")
    if fr < fb:
        gains.append("失败更少")
    if not gains:
        return "淘汰", "没有明显变好（差距在波动内或不足 min-gain）" + note
    return "合格", "，".join(gains) + note


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs")
    ap.add_argument("--baseline", default="A")
    ap.add_argument("--min-gain", type=float, default=0.15)
    a = ap.parse_args()
    rows = load(a.runs)
    g = defaultdict(list)
    for r in rows:
        g[(r["combo"], r["task"], r["route"])].append(r)
    print("| Agent/模型 | 任务 | 路线 | 次数 | 调用 | 失败 | 输入token | 费用 | 耗时s | 质量 | 工具链一致 | 状态 | 依据 |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    status, bad = {}, 0
    for combo, task in sorted({(c, t) for c, t, _ in g}):
        base = g.get((combo, task, a.baseline))
        graded = []
        for (c, t, route), rs in sorted(g.items()):
            if (c, t) != (combo, task):
                continue
            s, why = grade(rs, base, a.min_gain, route == a.baseline)
            graded.append([route, rs, s, why])
        ok = [x for x in graded if x[2] == "合格"]
        best = min(ok, key=lambda x: mean_sd(x[1], "cost")[0])[0] if ok else None
        for x in graded:
            if x[2] == "合格":
                x[2] = "默认" if x[0] == best else "备用"
            status[(combo, task, x[0])] = x[2]
            bad += x[2] == "淘汰"
            route, rs, s, why = x
            f = {k: mean_sd(rs, k) for k in KEYS}
            q = sum(r["quality_ok"] for r in rs)
            same = len({r.get("toolchain", "") for r in rs}) == 1
            print(f"| {combo} | {task} | {route} | {len(rs)} | {f['calls'][0]:.1f}±{f['calls'][1]:.1f} | {f['failed'][0]:.1f} | "
                  f"{f['input_tokens'][0]:,.0f} | {f['cost'][0]:.4f}±{f['cost'][1]:.4f} | {f['seconds'][0]:.0f} | {q}/{len(rs)} | "
                  f"{'是' if same else '否'} | {s} | {why} |")
    combos = sorted({c for c, _, _ in status})
    if len(combos) > 1:
        print("\n跨 Agent/模型 对照（同一任务同一路线在不同组合上的状态）：")
        for task, route in sorted({(t, r) for _, t, r in status if r != a.baseline}):
            ss = {c: status.get((c, task, route), "—") for c in combos}
            tag = "一致" if len(set(v for v in ss.values() if v != "—")) == 1 else "不一致：按组合分开写选路规则"
            print(f"- {task} / {route}：" + "，".join(f"{c}={v}" for c, v in ss.items()) + f"（{tag}）")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
