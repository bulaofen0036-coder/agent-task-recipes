# -*- coding: utf-8 -*-
"""生成三个通用任务的测试数据（固定随机种子，任何人生成的都一样），并算出标准答案。

    python make_fixtures.py <输出目录> [--variant 0|1]
输出目录下：logs/  sales/  repo/  三个任务各一份；truth.json（标准答案，给 check.py 用，不给 Agent 看）；
meta.json（本套数据的参数：日期、时间窗、配置名……，run_bench.py 用它拼任务原话，check.py 用它出隐藏测试）。
--variant 1 是「同类任务、不同数据」：日期、时间窗、出问题的接口、年份、配置项名字都换掉，用来测配方能不能复用。
每次运行前由 run_bench.py 复制一份新的给 Agent，Agent 改坏了也不影响下一次。
"""
import argparse
import gzip
import json
import os
import random
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timedelta

VARIANTS = {
    0: dict(seed=20261023, date=(2026, 10, 22), win=14, noise=13, hot1="/api/pay", hot2="/api/cart", noisy="/api/search",
            csv_start=(2026, 1, 1), const="TIMEOUT", old=10, env="APP_TIMEOUT", default=30, key="timeout", what="超时时间"),
    1: dict(seed=777, date=(2026, 11, 5), win=10, noise=11, hot1="/api/inventory", hot2="/api/users", noisy="/api/orders",
            csv_start=(2025, 3, 1), const="WAIT_LIMIT", old=60, env="APP_WAIT_LIMIT", default=300, key="wait", what="等待上限时间"),
}
# 换名时语义要和 repo 里用到它的地方对得上（worker 里是拉取任务的等待期限）：
# 曾用「缓存有效期」，Agent 合理地判定 worker 的 60 秒不是缓存期限而不改，隐藏测试反倒判它错。
V = VARIANTS[0]
R = random.Random(V["seed"])

# ---------------- 任务 1：日志排障 ----------------
ENDPOINTS = ["/api/orders", "/api/users", "/api/cart", "/api/pay", "/api/search", "/api/inventory", "/health"]
REASONS = ["upstream timeout: inventory-svc", "db pool exhausted", "upstream timeout: pay-gateway",
           "NullPointerException in CartService", "redis connection refused"]


def make_logs(root):
    d = os.path.join(root, "logs")
    os.makedirs(d)
    start = datetime(*V["date"], 8, 0, 0)
    win, noise = V["win"], V["noise"]
    in_window = Counter()
    reasons = defaultdict(Counter)
    for h in range(10):                         # 08:00–17:59，每小时一个文件
        hour = start + timedelta(hours=h)
        lines = []
        n = 6000 if hour.hour in (noise, win, win + 1) else 2500
        for _ in range(n):
            t = hour + timedelta(seconds=R.randrange(3600))
            ep = R.choices(ENDPOINTS, weights=[5, 3, 4, 2, 6, 3, 2])[0]
            code = 200
            if R.random() < 0.03:
                code = R.choice([500, 502, 503, 504])
            # 时间窗这一小时，两个接口出一批故障
            if hour.hour == win and ep == V["hot1"] and R.random() < 0.35:
                code = 504
            if hour.hour == win and ep == V["hot2"] and R.random() < 0.22:
                code = 500
            # 时间窗外的一小时，另一个接口有一大批 5xx（用来抓「没按时间过滤」）
            if hour.hour == noise and ep == V["noisy"] and R.random() < 0.4:
                code = 503
            ms = R.randrange(5, 900)
            rid = "%08x" % R.randrange(16 ** 8)
            lines.append((t, f"{t.strftime('%Y-%m-%dT%H:%M:%S')}Z INFO {ep} status={code} {ms}ms req={rid}"))
            if code >= 500:
                if ep == V["hot1"]:
                    why = R.choices(REASONS, weights=[1, 1, 6, 0, 1])[0]
                elif ep == V["hot2"]:
                    why = R.choices(REASONS, weights=[1, 1, 0, 5, 1])[0]
                else:
                    why = R.choice(REASONS)
                lines.append((t, f"{t.strftime('%Y-%m-%dT%H:%M:%S')}Z ERROR req={rid} {ep} -> {code}: {why}"))
                if hour.hour == win:
                    in_window[ep] += 1
                    reasons[ep][why] += 1
        lines.sort(key=lambda x: x[0])
        text = "\n".join(x[1] for x in lines) + "\n"
        name = f"app-{hour.strftime('%Y%m%d-%H')}.log"
        if hour.hour == win:                     # 时间窗那份已被轮转压缩（真实环境常见）
            with gzip.open(os.path.join(d, name + ".gz"), "wt", encoding="utf-8") as f:
                f.write(text)
        else:
            open(os.path.join(d, name), "w", encoding="utf-8").write(text)
    ep, cnt = in_window.most_common(1)[0]
    return {"endpoint": ep, "count": cnt, "top_reason": reasons[ep].most_common(1)[0][0]}


# ---------------- 任务 2：脏 CSV 按月汇总 ----------------
REGIONS = ["East", "West", "North", "South"]


def make_sales(root):
    d = os.path.join(root, "sales")
    os.makedirs(d)
    rows, truth = [], defaultdict(float)
    for i in range(1, 2201):
        day = datetime(*V["csv_start"]) + timedelta(days=R.randrange(240))
        amt = round(R.uniform(20, 3000), 2)
        region = R.choice(REGIONS)
        status = R.choices(["paid", "cancelled", "refunded"], weights=[85, 10, 5])[0]
        style = R.randrange(3)
        ds = day.strftime("%Y-%m-%d") if style == 0 else (day.strftime("%d/%m/%Y") if style == 1 else f"{day.year}/{day.month}/{day.day}")
        a_style = R.randrange(3)
        as_ = f"{amt:.2f}" if a_style == 0 else (f"¥{amt:,.2f}" if a_style == 1 else f"{amt:.2f} CNY")
        rs = R.choice([region, region.upper(), f" {region.lower()} "])
        st = R.choice([status, status.upper(), status.capitalize()])
        row = [f"SO{i:05d}", ds, as_, rs, st]
        rows.append(row)
        if R.random() < 0.06:                    # 重复导出的整行
            rows.append(list(row))
        if status == "paid":
            truth[(day.strftime("%Y-%m"), region)] += amt
    R.shuffle(rows)
    with open(os.path.join(d, "sales_raw.csv"), "w", encoding="utf-8", newline="") as f:
        f.write("order_id,date,amount,region,status\n")
        for r in rows:
            f.write(",".join(f'"{x}"' if "," in x else x for x in r) + "\n")
    return {f"{m}|{r}": round(v, 2) for (m, r), v in sorted(truth.items())}


# ---------------- 任务 3：代码库小改动 ----------------
def repo_files():
    c, old, k = V["const"], V["old"], V["key"]
    return {
        "svc/__init__.py": "",
        "svc/config.py": f'"""服务配置。"""\n{c} = {old}  # 秒\nRETRIES = 3\n',
        "svc/client.py": (
            f"from svc.config import {c}, RETRIES\n\n\n"
            "def request_options():\n"
            f"    return {{\"{k}\": {c}, \"retries\": RETRIES}}\n"),
        "svc/worker.py": (
            "import time\n\n\n"
            "def poll(fetch):\n"
            f"    \"\"\"拉取任务，超过 {old} 秒没结果就放弃。\"\"\"\n"
            f"    deadline = time.monotonic() + {old}\n"
            "    while time.monotonic() < deadline:\n"
            "        job = fetch()\n"
            "        if job:\n"
            "            return job\n"
            "    return None\n\n\n"
            "def deadline_seconds():\n"
            f"    return {old}\n"),
        "svc/cli.py": (
            "import argparse\n\nfrom svc import config\n\n\n"
            "def build_parser():\n"
            "    p = argparse.ArgumentParser()\n"
            f"    p.add_argument(\"--{k}\", type=int, default=config.{c})\n"
            "    return p\n"),
        "tests/test_client.py": (
            "from svc.client import request_options\n\n\n"
            "def test_retries():\n"
            "    assert request_options()[\"retries\"] == 3\n"),
        "README.md": "# svc\n\n小服务。运行测试：`python -m pytest -q`\n",
    }


def make_repo(root):
    d = os.path.join(root, "repo")
    for p, c in repo_files().items():
        fp = os.path.join(d, *p.split("/"))
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        open(fp, "w", encoding="utf-8").write(c)
    return {"note": "隐藏测试见 check.py"}


def main():
    global V, R
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--variant", type=int, default=0)
    a = ap.parse_args()
    V = VARIANTS[a.variant]
    R = random.Random(V["seed"])
    if os.path.exists(a.out):
        shutil.rmtree(a.out)
    os.makedirs(a.out)
    truth = {"log_triage": make_logs(a.out), "csv_monthly": make_sales(a.out), "config_env": make_repo(a.out)}
    json.dump(truth, open(os.path.join(a.out, "truth.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    meta = dict(V, variant=a.variant, date="%04d-%02d-%02d" % V["date"])
    json.dump(meta, open(os.path.join(a.out, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(truth["log_triage"], ensure_ascii=False), len(truth["csv_monthly"]), "monthly cells")


if __name__ == "__main__":
    main()
