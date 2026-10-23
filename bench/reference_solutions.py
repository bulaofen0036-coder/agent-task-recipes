# -*- coding: utf-8 -*-
"""参考解：给 check.py 做「正确答案必须判通过」的反向哨兵。

    python reference_solutions.py <工作目录> <数据目录>     # 工作目录 = make_fixtures 的一份副本
"""
import csv
import gzip
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime


def solve_log(w):
    cnt, why = Counter(), defaultdict(Counter)
    for f in sorted(os.listdir(os.path.join(w, "logs"))):
        p = os.path.join(w, "logs", f)
        op = gzip.open if f.endswith(".gz") else open
        with op(p, "rt", encoding="utf-8") as fh:
            for line in fh:
                m = re.match(r"(\S+)Z ERROR req=\S+ (\S+) -> (5\d\d): (.*)$", line.rstrip("\n"))
                if m and m.group(1).startswith(META["date"] + "T%02d:" % META["win"]):
                    cnt[m.group(2)] += 1
                    why[m.group(2)][m.group(4)] += 1
    ep, n = cnt.most_common(1)[0]
    json.dump({"endpoint": ep, "count": n, "top_reason": why[ep].most_common(1)[0][0]},
              open(os.path.join(w, "answer.json"), "w", encoding="utf-8"))


def parse_date(s):
    s = s.strip()
    if "-" in s:
        return datetime.strptime(s, "%Y-%m-%d")
    a, b, c = s.split("/")
    return datetime(int(a), int(b), int(c)) if len(a) == 4 else datetime(int(c), int(b), int(a))


def solve_csv(w):
    seen, tot = set(), defaultdict(float)
    with open(os.path.join(w, "sales", "sales_raw.csv"), encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            key = tuple(r.values())
            if key in seen:
                continue
            seen.add(key)
            if r["status"].strip().lower() != "paid":
                continue
            amt = float(re.sub(r"[^\d.]", "", r["amount"]))
            tot[(parse_date(r["date"]).strftime("%Y-%m"), r["region"].strip().capitalize())] += amt
    with open(os.path.join(w, "monthly.csv"), "w", encoding="utf-8", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["month", "region", "total"])
        for (m, rg), v in sorted(tot.items()):
            wr.writerow([m, rg, f"{v:.2f}"])


def solve_repo(w):
    r = os.path.join(w, "repo", "svc")
    c, env, dft, old = META["const"], META["env"], META["default"], META["old"]
    open(os.path.join(r, "config.py"), "w", encoding="utf-8").write(
        f'import os\n\n\ndef _read():\n    t = int(os.environ.get("{env}", "{dft}"))\n'
        f'    if t <= 0:\n        raise ValueError("{env} must be > 0")\n    return t\n\n\n'
        f"{c} = _read()\nRETRIES = 3\n")
    p = os.path.join(r, "worker.py")
    s = open(p, encoding="utf-8").read()
    s = s.replace("import time\n", "import time\n\nfrom svc import config\n", 1)
    s = s.replace(f"time.monotonic() + {old}", f"time.monotonic() + config.{c}").replace(f"return {old}", f"return config.{c}")
    open(p, "w", encoding="utf-8").write(s)
    open(os.path.join(w, "repo", "tests", "test_setting.py"), "w", encoding="utf-8").write(
        f"import importlib\n\n\ndef test_default(monkeypatch):\n    monkeypatch.delenv('{env}', raising=False)\n"
        f"    import svc.config\n    assert importlib.reload(svc.config).{c} == {dft}\n")


if __name__ == "__main__":
    w, fx = sys.argv[1], sys.argv[2]          # 工作目录、生成数据的目录（读 meta.json）
    META = json.load(open(os.path.join(fx, "meta.json"), encoding="utf-8"))
    solve_log(w)
    solve_csv(w)
    solve_repo(w)
    print("ok")
