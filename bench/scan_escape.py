# -*- coding: utf-8 -*-
"""查轨迹里有没有 Agent 跑出自己工作目录、看了答案/核对脚本/配方（看了就不算有效样本）。

    python scan_escape.py <out目录> [<out目录> ...]
打印每个越界的运行和证据；最后一行 JSON：{"tainted": [tag, ...]}，ab_report 前把这些行剔掉。
"""
import glob
import json
import os
import re
import sys

LEAK = re.compile(r"truth\.json|check\.py|reference_solutions|meta\.json|runs\.jsonl|[\\/]traces\b|\bfixtures\b|"
                  r"(?<![\w-])recipes/|(?<![\w-])induced/|\bscan_escape|\brun_bench|make_fixtures", re.I)
UP = re.compile(r"(?:^|[\s;&|(\"'])cd\s+\.\.[\\/]\.\.|\.\.[\\/]\.\.[\\/]")


def escapes(trace, tag):
    """一份轨迹里的越界证据（空列表 = 没越界）。"""
    own = re.compile(r"[\w:/.\-]*/work/" + re.escape(tag), re.I)   # 结果目录挪过位置也认得出
    ev = []
    for line in open(trace, encoding="utf-8"):
        e = json.loads(line)
        s = json.dumps(e.get("args", {}), ensure_ascii=False).replace("\\\\", "\\").replace("\\", "/")
        s = own.sub("<WORK>", s)          # 自己工作目录的绝对路径不算越界
        m = LEAK.search(s) or UP.search(s)
        if m:
            ev.append(s[max(0, m.start() - 50):m.end() + 50].replace("\n", " "))
    return ev


def scan(out):
    tainted = {}
    for p in sorted(glob.glob(os.path.join(out, "traces", "*.jsonl"))):
        tag = os.path.basename(p)[:-6]
        ev = escapes(p, tag)
        if ev:
            tainted[tag] = ev
    return tainted


def main():
    allt = []
    for out in sys.argv[1:]:
        t = scan(out)
        print(f"== {out}: {len(t)} 次运行越界")
        for tag, ev in t.items():
            print(f"   {tag}: {ev[0]}")
        allt += list(t)
    print(json.dumps({"tainted": allt}, ensure_ascii=False))


if __name__ == "__main__":
    main()
