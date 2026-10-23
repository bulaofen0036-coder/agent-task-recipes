# -*- coding: utf-8 -*-
"""从成功运行的轨迹归纳配方草稿（候选路线）。

轨迹格式：每行一个 JSON {"tool": "名字", "args": {...}, "ok": true/false}
（bench/agent.py、bench/claude_runner.py 直接产出这种格式；别的 Agent 自己转一下）

    python draft_from_trace.py run1.jsonl run2.jsonl run3.jsonl [--drop FindTools,GetAuthoringGuide] [--name 任务名]

做法：去掉失败的调用和 --drop 列出的「找工具/读说明」类调用；连续重复的同一种调用合并成「对每个对象做一次」；
多份轨迹时取它们的公共子序列当主干，只在部分轨迹出现的步骤标「可能是试探」。
长参数值换成 <占位>，短的字面量（布尔、数字、空串、短字符串）原样保留——漏掉这些正是手写配方最常见的错。
输出是候选路线草稿：要人删掉试探步骤、补「不要做 / 成功判据 / 失败时」，再走体检和 A/B。
"""
import argparse
import json
import re

SHELL_TOOLS = {"run_command", "Bash", "bash", "shell", "execute_command"}
# 不同 Agent 的同类工具归成一个名字，跨 Agent 的轨迹也能求公共步骤
ALIAS = {"Read": "read", "read_file": "read", "Write": "write", "write_file": "write", "Edit": "edit", "patch": "edit",
         "Glob": "list", "LS": "list", "list_dir": "list", "Grep": "search", "search_files": "search"}


def load(path):
    out = []
    for line in open(path, encoding="utf-8-sig"):
        if line.strip():
            e = json.loads(line)
            if e.get("ok", True):
                out.append(e)
    return out


SKIP_PROGS = {"cd", "echo", "printf", "head", "tail", "sort", "uniq", "wc", "cat", "true", "set"}


def shell_head(cmd):
    """命令的主程序名（跳过 cd/echo/head 这类辅助命令），如 `cd x && zcat f | awk …` → zcat。
    只取主程序是为了让不同运行里写法不同的同一步能对上；整条管道形状几乎每次都不一样。"""
    parts = re.split(r"\s*(?:\|\||&&|\||;|\n)\s*", cmd.strip())
    for p in parts:
        toks = [t for t in p.split() if not re.match(r"^\w+=", t)]
        if toks and toks[0].split("/")[-1] not in SKIP_PROGS:
            return toks[0].split("/")[-1]
    return "?"


def key(e):
    a = e.get("args") or {}
    if e["tool"] in SHELL_TOOLS:
        return ("shell", shell_head(str(a.get("command", ""))))
    if e["tool"] == "CallTool" and "name" in a:
        return ("CallTool", a["name"])
    if e["tool"] in ALIAS:
        return (ALIAS[e["tool"]], "")
    return (e["tool"], ",".join(sorted(a)))


def show_val(v):
    if isinstance(v, bool) or v is None or isinstance(v, (int, float)):
        return json.dumps(v)
    s = str(v)
    if s == "":
        return '""'
    if len(s) <= 20 and not re.search(r"[\\/:]", s):
        return json.dumps(s, ensure_ascii=False)
    return "<" + ("路径" if len(s) < 260 and "\n" not in s and re.search(r"[\\/]", s) else "值") + ">"


def render(e):
    a = e.get("args") or {}
    if e["tool"] in SHELL_TOOLS:
        cmd = re.sub(r"[A-Za-z]:\\[^\s\"']+|/(?:[\w.-]+/){2,}[\w.-]*", "<路径>", str(a.get("command", "")))
        return f"执行：`{cmd[:240]}`"
    if e["tool"] == "CallTool" and "argumentsJson" in a:
        try:
            inner = json.loads(a["argumentsJson"])
            inner_s = ", ".join(f'\\"{k}\\":{json.dumps(show_val(v), ensure_ascii=False)[1:-1]}' for k, v in inner.items())
            return f'`CallTool(name="{a.get("name")}", argumentsJson="{{{inner_s}}}")`'
        except ValueError:
            pass
    return f"`{e['tool']}(" + ", ".join(f"{k}={show_val(v)}" for k, v in a.items()) + ")`"


def collapse(events):
    out = []
    for e in events:
        if out and key(out[-1][0]) == key(e) and e["tool"] not in SHELL_TOOLS:
            out[-1][1] += 1
        else:
            out.append([e, 1])
    return out


def lcs(a, b):
    n, m = len(a), len(b)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            dp[i][j] = dp[i + 1][j + 1] + 1 if a[i] == b[j] else max(dp[i + 1][j], dp[i][j + 1])
    i = j = 0
    out = []
    while i < n and j < m:
        if a[i] == b[j]:
            out.append(a[i])
            i += 1
            j += 1
        elif dp[i + 1][j] >= dp[i][j + 1]:
            i += 1
        else:
            j += 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("traces", nargs="+")
    ap.add_argument("--drop", default="FindTools,GetAuthoringGuide,GetMinimalExample,Bootstrap,GetState,TodoWrite")
    ap.add_argument("--name", default="<任务名>")
    a = ap.parse_args()
    drop = set(x for x in a.drop.split(",") if x)
    runs = [collapse([e for e in load(p) if e["tool"] not in drop]) for p in a.traces]
    runs.sort(key=len)            # 最短的成功轨迹当主干：同样做成了，走得最少的那条最值得照抄
    common = [key(x[0]) for x in runs[0]]
    for r in runs[1:]:
        common = lcs(common, [key(x[0]) for x in r])
    base = runs[0]
    print(f"---\nrecipe: {a.name}\nversion: 0\nverified: 未验证\nmodels: []\nserver: <填>\n---")
    print(f"# 配方草稿：{a.name}\n")
    print(f"<!-- 由 {len(runs)} 份成功轨迹归纳。标「可能是试探」的步骤只在部分轨迹出现，先判断要不要留。"
          "参数里的 <占位> 要换成「来源说明」；命令里抄下来的具体值（文件名、日期、对象名，甚至答案）要改成「怎么找到它」。"
          "补完「不要做 / 成功判据 / 失败时」后再体检、A/B——A/B 用换过的数据，别用归纳时那份。 -->\n")
    print("## 路线 A：<从轨迹归纳的做法>（候选）")
    print("**条件**：<填>")
    ci, k = 0, 1
    for e, cnt in base:
        in_common = ci < len(common) and key(e) == common[ci]
        if in_common:
            ci += 1
        rep = f"（对每个对象各一次，本轨迹 {cnt} 次）" if cnt > 1 else ""
        mark = "" if in_common or len(runs) == 1 else "（可能是试探：只在部分轨迹出现）"
        print(f"{k}. {render(e)}{rep}{mark}")
        k += 1
    print("\n**成功判据**：<填：做完时能核对的事实>\n**失败时**：<填>\n")
    print("## 不要做\n- <从失败的调用里总结：本次轨迹里失败过的调用见下方>\n")
    fails = []
    for p in a.traces:
        for line in open(p, encoding="utf-8-sig"):
            if line.strip():
                e = json.loads(line)
                if not e.get("ok", True):
                    fails.append(render(e))
    if fails:
        print("<!-- 轨迹里失败过的调用（写「不要做」的素材）：")
        for f in fails[:15]:
            print("  - " + f)
        print("-->")


if __name__ == "__main__":
    main()
