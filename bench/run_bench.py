# -*- coding: utf-8 -*-
"""跑 A/B：每次复制一份新的测试数据，A = 只给任务原话，其它组 = 原话 + recipes/<任务>.md（或 --recipe 指定的文件）。

    python run_bench.py --agent generic --model deepseek-v4-flash --tasks log_triage,csv_monthly,config_env --conds A,R --reps 3
    python run_bench.py --agent claude --model haiku ...
结果逐行追加到 out/runs.jsonl（ab_report.py 直接读），轨迹在 out/traces/<tag>.jsonl；工作目录在系统临时目录 agent_bench/ 下。
generic 需要环境变量 BENCH_API_KEY / BENCH_BASE_URL（模型名用 --model）。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

from scan_escape import escapes

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

PROMPTS = {   # {xxx} 由数据目录里的 meta.json 填（不同 --variant 的日期、时间窗、配置名不同）
    "log_triage": ("logs", "当前目录下 logs/ 是某服务 {date} 的访问日志。找出 {date} {win:02d}:00:00 到 {win:02d}:59:59（UTC）之间"
                   "返回 5xx 次数最多的接口，统计它在这段时间的 5xx 次数和最常见的错误原因，把结果写进当前目录的 answer.json，"
                   "格式 {{\"endpoint\": \"...\", \"count\": 整数, \"top_reason\": \"...\"}}。"),
    "csv_monthly": ("sales", "sales/sales_raw.csv 是导出的订单。按月份和地区汇总已支付（paid）订单的金额，写成当前目录的 monthly.csv，"
                    "表头 month,region,total；month 写成 YYYY-MM，region 用首字母大写的英文名（East/West/North/South），"
                    "total 保留两位小数。斜杠日期里四位年份在前的是 年/月/日，否则是 日/月/年。"),
    "config_env": ("repo", "repo/ 是一个 Python 小项目。把{what}改成从环境变量 {env} 读取（整数秒，默认 {default}；值不合法时报错），"
                   "项目里所有用到{what}的地方都要跟着生效，补上测试，最后在 repo/ 里用 python -m pytest -q 跑通。"),
}
# 费用估算（元 / 百万 token）：命中缓存, 未命中, 输出。默认 deepseek-v4-flash 闲时价；别的模型用 --price 改。
DEFAULT_PRICE = "0.02,1,4"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", choices=["generic", "claude"], default="generic")
    ap.add_argument("--model", required=True)
    ap.add_argument("--tasks", default="log_triage,csv_monthly,config_env")
    ap.add_argument("--conds", default="A,R")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--start", type=int, default=1, help="起始编号（补跑时用）")
    ap.add_argument("--recipe", default="", help="组名=配方文件模板，逗号分隔，{task} 换成任务名；"
                                                  "默认 R=recipes/{task}.md,I=induced/{task}.md（I = draft_from_trace 自动起草、未经人改）")
    ap.add_argument("--price", default=DEFAULT_PRICE)
    ap.add_argument("--variant", type=int, default=0, help="测试数据版本：0 = 原始，1 = 同类任务换一套数据（测复用）")
    ap.add_argument("--out", default=os.path.join(HERE, "out"))
    a = ap.parse_args()
    fx = os.path.join(a.out, "fixtures")
    if not os.path.exists(os.path.join(fx, "meta.json")):
        subprocess.run([PY, os.path.join(HERE, "make_fixtures.py"), fx, "--variant", str(a.variant)], check=True)
    meta = json.load(open(os.path.join(fx, "meta.json"), encoding="utf-8"))
    if meta["variant"] != a.variant:
        sys.exit(f"{fx} 里是第 {meta['variant']} 套数据，和 --variant {a.variant} 不符；换个 --out")
    os.makedirs(os.path.join(a.out, "traces"), exist_ok=True)
    hit, miss, outp = (float(x) for x in a.price.split(","))
    for rep in range(a.start, a.start + a.reps):
        for task in a.tasks.split(","):
            for cond in a.conds.split(","):     # 同一轮里各组交替跑，避免时段差异只落在某一组
                tag = f"{a.agent}_{a.model}_{task}_{cond}{rep}".replace(":", "-").replace("/", "-")
                # 工作目录放到系统临时目录：放在 out/ 下时 Agent 往上翻两层就能看到 truth.json 和 check.py（真发生过）
                work = os.path.join(tempfile.gettempdir(), "agent_bench", os.path.basename(os.path.abspath(a.out)), "work", tag)
                if os.path.exists(work):
                    shutil.rmtree(work)
                sub, prompt = PROMPTS[task]
                prompt = prompt.format(**meta)
                shutil.copytree(os.path.join(fx, sub), os.path.join(work, sub))
                recipe_file = ""
                if cond != "A":
                    rmap = dict(x.split("=", 1) for x in (a.recipe or "R=recipes/{task}.md,I=induced/{task}.md").split(","))
                    recipe_file = os.path.join(HERE, rmap[cond].format(task=task))
                    prompt += "\n\n" + open(recipe_file, encoding="utf-8").read()
                msg = os.path.join(a.out, "traces", tag + ".msg.txt")
                open(msg, "w", encoding="utf-8").write(prompt)
                trace = os.path.join(a.out, "traces", tag + ".jsonl")
                if a.agent == "generic":
                    env = dict(os.environ, BENCH_MODEL=a.model)
                    r = subprocess.run([PY, os.path.join(HERE, "agent.py"), work, msg, trace], capture_output=True, text=True,
                                       encoding="utf-8", errors="replace", env=env, timeout=3600)
                else:
                    r = subprocess.run([PY, os.path.join(HERE, "claude_runner.py"), work, msg, trace, "--model", a.model],
                                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3600)
                try:
                    st = json.loads(r.stdout.strip().splitlines()[-1])
                except Exception:
                    print(f"{tag}: 运行失败 {r.stdout[-300:]} {r.stderr[-800:]}", flush=True)
                    continue
                q = subprocess.run([PY, os.path.join(HERE, "check.py"), task, work, os.path.join(fx, "truth.json")],
                                   capture_output=True, text=True, encoding="utf-8", errors="replace")
                qd = json.loads(q.stdout.strip().splitlines()[-1])
                chain = [json.loads(l)["tool"] for l in open(trace, encoding="utf-8")] if os.path.exists(trace) else []
                ev = escapes(trace, tag) if os.path.exists(trace) else []
                cost = st.get("cost_usd")
                if cost is None:
                    tin, h = st["input_tokens"], st.get("cache_hit_tokens", 0)
                    cost = ((tin - h) * miss + h * hit + st["output_tokens"] * outp) / 1e6
                row = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "agent": a.agent, "model": a.model, "variant": a.variant, "task": task,
                       "route": cond, "recipe_file": os.path.basename(recipe_file), "run": rep, "calls": st["calls"],
                       "failed": st["failed"], "input_tokens": st["input_tokens"], "output_tokens": st["output_tokens"],
                       "cost": round(cost, 5), "cost_unit": "USD" if st.get("cost_usd") is not None else "CNY",
                       "seconds": st["seconds"], "quality_ok": int(qd["quality_ok"]), "why": qd["why"],
                       "toolchain": ">".join(chain), "escaped": int(bool(ev))}
                with open(os.path.join(a.out, "runs.jsonl"), "a", encoding="utf-8") as f:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                print(f"{tag}: calls={row['calls']} failed={row['failed']} tin={row['input_tokens']} cost={row['cost']} "
                      f"{row['seconds']}s quality={'OK' if row['quality_ok'] else qd['why']}" + (f" 越界：{ev[0]}" if ev else ""), flush=True)


if __name__ == "__main__":
    main()
