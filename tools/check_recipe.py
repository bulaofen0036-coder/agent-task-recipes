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


ROUTE_H = re.compile(r"^##\s*路线\s*([A-Za-z0-9_]+)[：:][^\n]*?(?:[（(](默认|备用|候选|淘汰)[)）])?\s*$", re.M)


def check_structure(text, max_age_days=90, today=None):
    """多路线结构 + 头部元数据。返回 (问题, 提示)。问题 = 必须修；提示 = 该重新验证了。"""
    import datetime as dt
    problems, warns = [], []
    if not re.search(r"^\s*\d+\.\s+\S", text, re.M):
        problems.append("没有任何编号步骤（空文件或格式不对）")
    fm = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    meta = dict(re.findall(r"^(\w+):\s*(.*?)\s*$", fm.group(1), re.M)) if fm else {}
    if not meta.get("version"):
        warns.append("头部没有 version")
    v = meta.get("verified", "")
    try:
        age = ((today or dt.date.today()) - dt.date.fromisoformat(v)).days
        if age > max_age_days:
            warns.append(f"已 {age} 天没重新验证（verified: {v}），工具或模型变过的话先重跑 A/B")
    except ValueError:
        warns.append(f"没有有效的验证日期（verified: {v or '空'}），A/B 通过前只能当候选用")
    heads = list(ROUTE_H.finditer(text))
    if not heads:
        if re.search(r"^##\s*路线", text, re.M):
            problems.append("有「## 路线」标题但格式不对，应为「## 路线 A：做法（默认）」")
        return problems, warns
    states = {h.group(1): h.group(2) for h in heads}
    for n, s in states.items():
        if not s:
            problems.append(f"路线 {n} 没标状态（默认/备用/候选/淘汰）")
    multi = len(heads) > 1   # 只有一条路线（如刚起草的候选）时，不要求默认路线和选路表
    if multi and list(states.values()).count("默认") != 1:
        problems.append(f"默认路线应恰好 1 条，现在 {list(states.values()).count('默认')} 条")
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        nxt = re.search(r"^##\s(?!\s*路线)", text[h.end():end], re.M)
        body = text[h.end(): h.end() + nxt.start()] if nxt else text[h.end():end]
        for must in ("成功判据", "失败时"):
            if must not in body:
                problems.append(f"路线 {h.group(1)} 缺「{must}」")
        for tgt in re.findall(r"转\s*路线\s*([A-Za-z0-9_]+)", body):
            if tgt not in states:
                problems.append(f"路线 {h.group(1)} 失败时转向不存在的路线 {tgt}")
            elif tgt == h.group(1):
                problems.append(f"路线 {h.group(1)} 失败时转向自己")
    sel = re.search(r"^##\s*选路\s*$(.*?)(?=^##\s)", text, re.S | re.M)
    if not sel and multi:
        problems.append("有多条路线但没有「## 选路」表")
    elif not sel:
        pass
    else:
        for tgt in re.findall(r"路线\s*([A-Za-z0-9_]+)", sel.group(1)):
            if tgt not in states:
                problems.append(f"选路表里的路线 {tgt} 不存在")
            elif states[tgt] == "淘汰":
                problems.append(f"选路表还在把请求派给已淘汰的路线 {tgt}")
    return problems, warns


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
    import datetime as dt
    good_r = ("---\nversion: 2\nverified: 2026-10-01\n---\n## 选路\n| 默认 | 路线 A |\n| 条件 | 路线 B |\n"
              "## 路线 A：甲（默认）\n1. x\n**成功判据**：y\n**失败时**：z → 转路线 B\n"
              "## 路线 B：乙（备用）\n**成功判据**：y\n**失败时**：停下\n## 不要做\n- 无\n")
    bad_r = ("---\nverified: 2026-01-01\n---\n## 选路\n| 默认 | 路线 C |\n| x | 路线 B |\n"
             "## 路线 A：甲（默认）\n**失败时**：转路线 D\n## 路线 B：乙（淘汰）\n**成功判据**：y\n**失败时**：转路线 B\n"
             "## 路线 E：丙\n**成功判据**：y\n**失败时**：停\n")
    today = dt.date(2026, 10, 23)
    sg, wg = check_structure(good_r, today=today)
    sb, wb = check_structure(bad_r, today=today)
    se, _ = check_structure("", today=today)
    if not any("没有任何编号步骤" in p for p in se):
        missed.append("空文件没报")
    expect_r = ["路线 E 没标状态", "路线 A 缺「成功判据」", "转向不存在的路线 D", "路线 B 失败时转向自己",
                "选路表里的路线 C 不存在", "已淘汰的路线 B"]
    expect_w = ["没有 version", "天没重新验证"]
    missed += [e for e in expect_r if not any(e in p for p in sb)] + [e for e in expect_w if not any(e in p for p in wb)]
    ok = not pg and not missed and not sg and not wg
    print("正确配方：", "无问题" if not (pg or sg or wg) else pg + sg + wg)
    print("错误配方报出：", pb + sb + wb)
    print("自测", "通过" if ok else f"失败（漏报 {missed}）")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mcp")
    ap.add_argument("--tools")
    ap.add_argument("--proxy", help="代理工具:工具名参数:参数JSON参数，如 CallTool:name:argumentsJson")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--max-age", type=int, default=90, help="超过多少天没重新验证就提示")
    ap.add_argument("files", nargs="*")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not a.files:
        ap.error("至少给一个配方文件；--mcp / --tools 给了才查工具名和参数，不给只查结构")
    tools = load_tools_mcp(a.mcp) if a.mcp else (load_tools_file(a.tools) if a.tools else [])
    schema = {t["name"]: t.get("inputSchema") or {} for t in tools}
    proxy = tuple(a.proxy.split(":")) if a.proxy else None
    bad = 0
    files = [f for pat in a.files for f in (glob.glob(pat) or [pat])]
    for f in files:
        text = open(f, encoding="utf-8-sig").read()
        n, problems = check_text(text, schema, proxy) if schema else (0, [])
        sp, warns = check_structure(text, a.max_age)
        problems += sp
        src = f"工具清单 {len(schema)} 个" if schema else "未给工具清单，只查结构"
        print(("OK   " if not problems else "FAIL ") + f + f"（{n} 处调用，{src}）")
        for p in problems:
            print("     - " + p)
        for w in warns:
            print("     · 提示：" + w)
        bad += bool(problems)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
