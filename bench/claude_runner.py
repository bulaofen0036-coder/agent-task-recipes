# -*- coding: utf-8 -*-
"""用 Claude Code 无头模式（claude -p）跑同一个任务，输出格式与 agent.py 一致。

    python claude_runner.py <工作目录> <消息文件> <轨迹输出.jsonl> [--model haiku]
用 --setting-sources project 跳过用户级设置（钩子等），工作目录里没有项目设置，所以基本是原厂 Claude Code。
注意：用的是 bypassPermissions（无头模式下没人点批准），只在测试副本目录里跑。
"""
import argparse
import json
import shutil
import subprocess
import time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work")
    ap.add_argument("msg")
    ap.add_argument("trace")
    ap.add_argument("--model", default="haiku")
    a = ap.parse_args()
    exe = shutil.which("claude")
    argv = [exe, "-p", open(a.msg, encoding="utf-8").read(), "--model", a.model, "--output-format", "stream-json",
            "--verbose", "--permission-mode", "bypassPermissions", "--no-session-persistence",
            "--setting-sources", "project", "--max-budget-usd", "2"]
    t0 = time.time()
    p = subprocess.run(argv, cwd=a.work, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
    stats = {"calls": 0, "failed": 0, "input_tokens": 0, "output_tokens": 0, "cache_hit_tokens": 0, "llm_calls": 0,
             "cost_usd": None, "answer": ""}
    pending = {}
    with open(a.trace, "w", encoding="utf-8") as tr:
        for line in p.stdout.splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("type") == "assistant":
                for c in ev["message"].get("content", []):
                    if c.get("type") == "tool_use":
                        pending[c["id"]] = (c["name"], c.get("input") or {})
            elif ev.get("type") == "user":
                content = ev.get("message", {}).get("content", [])
                for c in content if isinstance(content, list) else []:
                    if c.get("type") == "tool_result" and c.get("tool_use_id") in pending:
                        name, args = pending.pop(c["tool_use_id"])
                        ok = not c.get("is_error")
                        stats["calls"] += 1
                        stats["failed"] += (not ok)
                        tr.write(json.dumps({"tool": name, "args": args, "ok": ok}, ensure_ascii=False) + "\n")
            elif ev.get("type") == "result":
                u = ev.get("usage") or {}
                stats["input_tokens"] = u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
                stats["cache_hit_tokens"] = u.get("cache_read_input_tokens", 0)
                stats["output_tokens"] = u.get("output_tokens", 0)
                stats["cost_usd"] = ev.get("total_cost_usd")
                stats["llm_calls"] = ev.get("num_turns", 0)
                stats["answer"] = (ev.get("result") or "")[:2000]
                stats["is_error"] = ev.get("is_error")
    stats["seconds"] = round(time.time() - t0, 1)
    if p.returncode != 0 and not stats["answer"]:
        stats["answer"] = "（claude 退出码 %d）%s" % (p.returncode, p.stderr[-500:])
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
