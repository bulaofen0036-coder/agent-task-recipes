# -*- coding: utf-8 -*-
"""从 Claude Code 会话记录里找「值得做成配方」的高频任务。只读，不上传任何东西。

    python mine_claude_code.py [--days 30] [--root ~/.claude/projects]

输出：工具用量、Shell 命令种类、被反复调用的脚本、出错类型（含钩子拦截）、每会话调用量。
怎么读：反复调用的脚本 / 反复出现的命令组合 = 已经在手工串的多步流程（组合执行型的候选）；
同一类出错反复出现 = 缺一个固定写法或检查（流程指导型或工具层修复的候选）。
"""
import argparse
import collections
import glob
import json
import os
import re
import time


def kind_of(cmd):
    c = re.sub(r"^(cd\s+[^&;]+(&&|;)\s*)+", "", cmd.strip())
    m = re.match(r"(git(?:\s+-C\s+\S+)?\s+[a-z-]+|gh\s+[a-z]+(?:\s+[a-z]+)?|npm\s+\w+|docker\s+\w+|kubectl\s+\w+)", c)
    if m:
        return re.sub(r"-C\s+\S+\s+", "", m.group(1))
    for pat, k in [(r"\bpython\d?|uv run", "运行 python"), (r"\.ps1\b|powershell", "运行 PowerShell 脚本"),
                   (r"msbuild|dotnet build|cargo build|go build|make\b", "编译"), (r"pytest|dotnet test|npm test|go test", "测试"),
                   (r"curl|wget|Invoke-WebRequest", "网络请求"), (r"Get-Process|tasklist|ps aux|Get-CimInstance", "查进程")]:
        if re.search(pat, c, re.I):
            return k
    return (c.split() or ["?"])[0][:30]


def err_kind(t, tool):
    m = re.search(r"PreToolUse:\w+ hook error", t)
    if m:
        k = re.search(r"【([^】]{1,30})】", t)
        return "钩子拦截·" + (k.group(1) if k else "其它")
    for pat, k in [(r"No such tool available", "工具未加载"), (r"modified since read|has not been read", "Edit 前提不满足"),
                   (r"Traceback \(most recent call last\)", "脚本异常"), (r"ParserError|is not recognized|not found: command", "命令语法/不存在"),
                   (r"UnicodeEncodeError|UnicodeDecodeError", "编码"), (r"timed out|timeout", "超时"), (r"^Exit code", "非零退出")]:
        if re.search(pat, t, re.M):
            return k
    return f"其它（{tool}）"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--root", default=os.path.expanduser("~/.claude/projects"))
    a = ap.parse_args()
    cut = time.time() - a.days * 86400
    files = [f for f in glob.glob(os.path.join(a.root, "**", "*.jsonl"), recursive=True)
             if "subagents" not in f and os.path.getmtime(f) > cut]
    tools, kinds, scripts, errs = (collections.Counter() for _ in range(4))
    ex = {}
    per = []
    for f in files:
        pend, n = {}, 0
        for line in open(f, encoding="utf-8", errors="replace"):
            try:
                o = json.loads(line)
            except ValueError:
                continue
            c = (o.get("message") or {}).get("content")
            if not isinstance(c, list):
                continue
            for b in c:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "tool_use":
                    name, inp = b.get("name", ""), b.get("input") or {}
                    tools[name] += 1
                    n += 1
                    pend[b.get("id")] = name
                    if name in ("Bash", "PowerShell"):
                        cmd = inp.get("command", "")
                        kinds[kind_of(cmd)] += 1
                        for s in re.findall(r"([\w.-]+\.(?:py|ps1|sh|js|ts|bat))\b", cmd):
                            scripts[s] += 1
                elif b.get("type") == "tool_result" and b.get("is_error"):
                    t = b.get("content")
                    t = t if isinstance(t, str) else " ".join(x.get("text", "") for x in (t or []) if isinstance(x, dict))
                    k = err_kind(t.strip(), pend.get(b.get("tool_use_id"), "?"))
                    errs[k] += 1
                    ex.setdefault(k, t.strip()[:100].replace("\n", " "))
        per.append(n)
    per.sort()
    print(f"# 近 {a.days} 天：{len(files)} 个会话，{sum(tools.values()):,} 次工具调用"
          + (f"，每会话中位 {per[len(per) // 2]} 次" if per else ""))
    for title, cnt, k in [("工具用量", tools, 15), ("Shell 命令种类", kinds, 25), ("被反复调用的脚本（多步流程候选）", scripts, 25)]:
        print(f"\n## {title}")
        for name, v in cnt.most_common(k):
            print(f"{v:7}  {name}")
    print(f"\n## 出错 {sum(errs.values())} 次（反复出现的 = 缺固定写法或检查）")
    for name, v in errs.most_common(15):
        print(f"{v:7}  {name}    例：{ex[name]}")


if __name__ == "__main__":
    main()
