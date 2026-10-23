# -*- coding: utf-8 -*-
"""A/B 汇总：把每次运行的结果（CSV）汇成「每组均值 + 是否达到上线标准」。

CSV 列：task,group,run,calls,failed,input_tokens,cost,seconds,quality_ok,toolchain
  group：基线组名（默认 A）与配方组名（任意，如 B、C、v2）
  quality_ok：1/0，按事先定好的客观判据（块数对不对、编译过没过……）
  toolchain：本次的工具调用序列，用 > 连接（用来判断几次之间是否一致）

用法：python ab_report.py results.csv [--baseline A] [--min-gain 0.15]
上线标准（对每个配方组，与同任务基线组比）：
  质量判据全部通过；失败均值不高于基线；并且「调用、费用、耗时」至少一项下降不少于 min-gain，或失败均值更低。
"""
import argparse
import csv
import statistics as st
import sys
from collections import defaultdict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--baseline", default="A")
    ap.add_argument("--min-gain", type=float, default=0.15)
    a = ap.parse_args()
    rows = list(csv.DictReader(open(a.csv, encoding="utf-8-sig")))
    g = defaultdict(list)
    for r in rows:
        g[(r["task"], r["group"])].append(r)
    num = lambda rs, k: st.mean(float(x[k]) for x in rs)
    print("| 任务 | 组 | 次数 | 调用 | 失败 | 输入token | 费用 | 耗时s | 质量通过 | 工具链一致 | 结论 |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    bad = 0
    for task in sorted({t for t, _ in g}):
        base = g.get((task, a.baseline))
        for (t, grp), rs in sorted(g.items()):
            if t != task:
                continue
            m = {k: num(rs, k) for k in ("calls", "failed", "input_tokens", "cost", "seconds")}
            q = sum(int(x["quality_ok"]) for x in rs)
            same = len({x["toolchain"] for x in rs}) == 1
            verdict = "基线"
            if grp != a.baseline:
                if not base:
                    verdict = "无基线，不能判"
                else:
                    b = {k: num(base, k) for k in ("calls", "failed", "cost", "seconds")}
                    why = []
                    if q < len(rs):
                        why.append(f"质量 {q}/{len(rs)}")
                    if m["failed"] > b["failed"]:
                        why.append(f"失败 {b['failed']:.1f}→{m['failed']:.1f}")
                    gain = any(b[k] > 0 and (b[k] - m[k]) / b[k] >= a.min_gain for k in ("calls", "cost", "seconds")) \
                        or m["failed"] < b["failed"]
                    if not gain:
                        why.append("调用/费用/耗时都没有明显下降")
                    verdict = "达标" if not why else "不达标：" + "；".join(why)
                    bad += bool(why)
            print(f"| {task} | {grp} | {len(rs)} | {m['calls']:.1f} | {m['failed']:.1f} | {m['input_tokens']:,.0f} | "
                  f"{m['cost']:.3f} | {m['seconds']:.0f} | {q}/{len(rs)} | {'是' if same else '否'} | {verdict} |")
    if any(len(v) < 3 for v in g.values()):
        print("\n注意：每组少于 3 次，结论只作参考。")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
