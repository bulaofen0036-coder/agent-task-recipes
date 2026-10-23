# -*- coding: utf-8 -*-
"""配方体检：配方里写到的工具必须存在；写到的参数名必须是该工具的参数；写了参数的调用，必填参数要写全。

工具调用的写法：行内代码 `ToolName(param=value, param2)`（见 templates/recipe_template.md）。

用法：
  python check_recipe.py --mcp "npx -y some-mcp-server" recipe1.md recipe2.md
  python check_recipe.py --tools tools.json recipes/*.md          # tools.json = MCP tools/list 的结果（列表或 {"tools": [...]}）
  python check_recipe.py --tools tools.json --proxy CallTool:name:argumentsJson recipe.md
        # 服务器用「代理工具」间接调用其它工具时（如 CallTool(name="X", argumentsJson="{...}")），也检查被代理的那个工具
  python check_recipe.py --selftest   # 必错哨兵：体检自己坏没坏
发现问题退出码 1。
"""
import argparse
import glob
import json
import re
import shlex
import subprocess
import sys

CALL = re.compile(r"`([A-Za-z_][\w.-]*)\(([^`]*)\)`")


def split_args(s):
    """按顶层逗号切参数（引号、花括号、方括号里的逗号不切）。"""
    out, depth, quote, cur = [], 0, None, ""
    for ch in s:
        if quote:
            cur += ch
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
        elif ch in "{[(":
            depth += 1
        elif ch in "}])":
            depth -= 1
        elif ch in ",，" and depth == 0:
            out.append(cur.strip())
            cur = ""
            continue
        cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def parse_call(inner):
    names, values = [], {}
    for part in split_args(inner):
        m = re.match(r"([A-Za-z_]\w*)\s*(?:=\s*(.*))?$", part, re.S)
        if m:
            names.append(m.group(1))
            values[m.group(1)] = (m.group(2) or "").strip()
    return names, values


def load_tools_mcp(cmd):
    argv = [t.strip('"') for t in shlex.split(cmd, posix=False)]   # Windows 路径带引号时去掉引号
    p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, text=True, encoding="utf-8")
    n = [0]

    def rpc(method, params=None, notify=False):
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        if not notify:
            n[0] += 1
            msg["id"] = n[0]
        p.stdin.write(json.dumps(msg) + "\n")
        p.stdin.flush()
        if notify:
            return None
        while True:
            line = p.stdout.readline()
            if not line:
                raise RuntimeError("MCP 服务器提前退出")
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("id") == n[0]:
                if "error" in r:
                    raise RuntimeError(r["error"])
                return r["result"]

    rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "check_recipe", "version": "1"}})
    rpc("notifications/initialized", notify=True)
    tools, cursor = [], None
    while True:
        r = rpc("tools/list", {"cursor": cursor} if cursor else {})
        tools += r.get("tools", [])
        cursor = r.get("nextCursor")
        if not cursor:
            break
    p.stdin.close()
    p.terminate()
    return tools


def load_tools_file(path):
    d = json.load(open(path, encoding="utf-8-sig"))
    return d["tools"] if isinstance(d, dict) else d


def check_text(text, schema, proxy=None):
    problems, n = [], 0
    for name, inner in CALL.findall(text):
        names, values = parse_call(inner)
        targets = [(name, names, bool(inner.strip()))]
        if proxy and name == proxy[0]:
            inner_name = values.get(proxy[1], "").strip("\"'")
            raw = values.get(proxy[2], "")
            keys = re.findall(r"\\?[\"'](\w+)\\?[\"']\s*:", raw)
            if inner_name:
                targets.append((inner_name, keys, True))
        for tname, keys, has_args in targets:
            n += 1
            if tname not in schema:
                problems.append(f"工具不存在：{tname}")
                continue
            props = set((schema[tname].get("properties") or {}).keys())
            req = set(schema[tname].get("required") or [])
            unknown = [k for k in keys if k not in props]
            missing = sorted(req - set(keys)) if has_args else []
            if unknown:
                problems.append(f"{tname} 没有参数 {unknown}（有：{sorted(props)}）")
            if missing:
                problems.append(f"{tname} 缺必填参数 {missing}")
    return n, problems


def selftest():
    schema = {"OpenProject": {"properties": {"path": {}}, "required": ["path"]},
              "GetStats": {"properties": {"target": {}, "brief": {}}, "required": ["target"]},
              "CallTool": {"properties": {"name": {}, "argumentsJson": {}}, "required": ["name", "argumentsJson"]}}
    good = '1. `OpenProject(path=<路径>)` 2. `GetStats(target=<名字>, brief=true)` 3. `CallTool(name="GetStats", argumentsJson="{\\"target\\":\\"X\\"}")`'
    bad = '1. `OpenProjekt(path=x)` 2. `OpenProject(projectPath=x)` 3. `GetStats(brief=true)` 4. `CallTool(name="GetStats", argumentsJson="{\\"tgt\\":\\"X\\"}")`'
    _, pg = check_text(good, schema, ("CallTool", "name", "argumentsJson"))
    _, pb = check_text(bad, schema, ("CallTool", "name", "argumentsJson"))
    expect = ["工具不存在：OpenProjekt", "OpenProject 没有参数", "OpenProject 缺必填参数", "GetStats 缺必填参数", "GetStats 没有参数 ['tgt']"]
    missed = [e for e in expect if not any(e in p for p in pb)]
    ok = not pg and not missed
    print("正确配方：", "无问题" if not pg else pg)
    print("错误配方报出：", pb)
    print("自测", "通过" if ok else f"失败（漏报 {missed}）")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mcp")
    ap.add_argument("--tools")
    ap.add_argument("--proxy", help="代理工具:工具名参数:参数JSON参数，如 CallTool:name:argumentsJson")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("files", nargs="*")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not (a.mcp or a.tools) or not a.files:
        ap.error("需要 --mcp 或 --tools，以及至少一个配方文件")
    tools = load_tools_mcp(a.mcp) if a.mcp else load_tools_file(a.tools)
    schema = {t["name"]: t.get("inputSchema") or {} for t in tools}
    proxy = tuple(a.proxy.split(":")) if a.proxy else None
    bad = 0
    files = [f for pat in a.files for f in (glob.glob(pat) or [pat])]
    for f in files:
        n, problems = check_text(open(f, encoding="utf-8-sig").read(), schema, proxy)
        print(("OK   " if not problems else "FAIL ") + f + f"（{n} 处调用，工具清单 {len(schema)} 个）")
        for p in problems:
            print("     - " + p)
        bad += bool(problems)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
