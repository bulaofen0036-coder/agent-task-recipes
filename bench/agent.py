# -*- coding: utf-8 -*-
"""最小通用 Agent：任何兼容 OpenAI Chat Completions 的模型 + 4 个通用工具（列目录 / 读文件 / 写文件 / 执行命令）。
只用标准库，方便别人复现。工具只能碰工作目录里的东西。

    BENCH_API_KEY=... BENCH_BASE_URL=https://api.deepseek.com/v1 BENCH_MODEL=deepseek-v4-flash \
    python agent.py <工作目录> <消息文件> <轨迹输出.jsonl>
最后一行打印 JSON：调用次数、失败次数、token、耗时、最终回答。
"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

MAX_STEPS = 40
OUT_LIMIT = 20000
BENCH_DIR = os.path.dirname(os.path.abspath(__file__))

TOOLS = [
    {"type": "function", "function": {"name": "list_dir", "description": "列出目录内容（名字、大小）",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "read_file", "description": "读文本文件，按行号分段读，单次最多 400 行",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "offset": {"type": "integer", "description": "起始行号，从 1 开始"},
                                                     "limit": {"type": "integer"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "write_file", "description": "写文本文件（整份覆盖，UTF-8）",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}},
    {"type": "function", "function": {"name": "run_command", "description": "在工作目录执行一条 shell 命令，返回退出码和输出（超长截断）",
     "parameters": {"type": "object", "properties": {"command": {"type": "string"}, "timeout": {"type": "integer", "description": "秒，默认 120"}},
                    "required": ["command"]}}},
]


def shell_argv(cmd):
    bash = shutil.which("bash")
    if os.name == "nt" and not bash:
        return cmd, True
    return [bash or "/bin/sh", "-c", cmd], False


class Tools:
    def __init__(self, work):
        self.work = os.path.abspath(work)
        self.last_exit = None

    def _p(self, path):
        p = os.path.abspath(os.path.join(self.work, path))
        if os.path.commonpath([p, self.work]) != self.work:
            raise ValueError("只能访问工作目录里的文件")
        return p

    def list_dir(self, path="."):
        p = self._p(path)
        return "\n".join(f"{n}{'/' if os.path.isdir(os.path.join(p, n)) else ''}\t{os.path.getsize(os.path.join(p, n))}"
                         for n in sorted(os.listdir(p))), True

    def read_file(self, path, offset=1, limit=400):
        limit = min(int(limit or 400), 400)
        offset = max(int(offset or 1), 1)
        with open(self._p(path), encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        part = lines[offset - 1: offset - 1 + limit]
        more = f"\n…（共 {len(lines)} 行，本次到第 {offset - 1 + len(part)} 行）" if offset - 1 + len(part) < len(lines) else ""
        return "".join(f"{offset + i}\t{l}" for i, l in enumerate(part)) + more, True

    def write_file(self, path, content):
        p = self._p(path)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w", encoding="utf-8", newline="").write(content)
        return f"已写入 {path}（{len(content)} 字符）", True

    def run_command(self, command, timeout=120):
        env = dict(os.environ)
        venv = os.path.join(BENCH_DIR, ".venv", "Scripts" if os.name == "nt" else "bin")
        if os.path.isdir(venv):
            env["PATH"] = venv + os.pathsep + env.get("PATH", "")
        env.update(PYTHONIOENCODING="utf-8", PIP_NO_INPUT="1")
        argv, use_shell = shell_argv(command)
        try:
            r = subprocess.run(argv, shell=use_shell, cwd=self.work, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=min(int(timeout or 120), 300), env=env)
        except subprocess.TimeoutExpired:
            return "超时", False
        out = (r.stdout or "") + (("\n[stderr]\n" + r.stderr) if r.stderr else "")
        if len(out) > OUT_LIMIT:
            out = out[:OUT_LIMIT] + f"\n…（输出共 {len(out)} 字符，已截断）"
        # shell 惯例：退出码 1 且没有 stderr = 「查无结果」（grep 没搜到、diff 有差异、test 为假），不算失败
        ok = r.returncode == 0 or (r.returncode == 1 and not (r.stderr or "").strip())
        self.last_exit = r.returncode
        return f"exit={r.returncode}\n{out}", ok


def chat(messages):
    body = json.dumps({"model": os.environ["BENCH_MODEL"], "messages": messages, "tools": TOOLS,
                       "temperature": float(os.environ.get("BENCH_TEMPERATURE", "0.7"))}).encode("utf-8")
    req = urllib.request.Request(os.environ["BENCH_BASE_URL"].rstrip("/") + "/chat/completions", data=body,
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + os.environ["BENCH_API_KEY"]})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            if attempt == 2:
                raise
            time.sleep(5)


def main():
    work, msg_file, trace_file = sys.argv[1:4]
    tools = Tools(work)
    system = (f"你是一个在命令行里干活的助手。工作目录：{tools.work}。操作系统：{os.name}；"
              f"run_command 用的是 {'bash' if shutil.which('bash') else '系统默认 shell'}。用工具把任务做完，做完后用一段话汇报结果。")
    messages = [{"role": "system", "content": system}, {"role": "user", "content": open(msg_file, encoding="utf-8").read()}]
    stats = {"calls": 0, "failed": 0, "input_tokens": 0, "output_tokens": 0, "cache_hit_tokens": 0, "llm_calls": 0}
    t0 = time.time()
    answer = ""
    with open(trace_file, "w", encoding="utf-8") as tr:
        for _ in range(MAX_STEPS):
            resp = chat(messages)
            u = resp.get("usage") or {}
            stats["llm_calls"] += 1
            stats["input_tokens"] += u.get("prompt_tokens", 0)
            stats["output_tokens"] += u.get("completion_tokens", 0)
            stats["cache_hit_tokens"] += u.get("prompt_cache_hit_tokens", 0)
            m = resp["choices"][0]["message"]
            keep = {k: v for k, v in m.items() if k in ("role", "content", "tool_calls", "reasoning_content")}
            keep["content"] = keep.get("content") or ""
            messages.append(keep)
            calls = m.get("tool_calls") or []
            if not calls:
                answer = m.get("content") or ""
                break
            for c in calls:
                name = c["function"]["name"]
                tools.last_exit = None
                try:
                    args = json.loads(c["function"]["arguments"] or "{}")
                    out, ok = getattr(tools, name)(**args)
                except Exception as e:  # 工具名错、参数错、路径越界都算失败调用，原文回给模型
                    args = args if isinstance(locals().get("args"), dict) else {}
                    out, ok = f"错误：{type(e).__name__}: {e}", False
                stats["calls"] += 1
                stats["failed"] += (not ok)
                tr.write(json.dumps({"tool": name, "args": args, "ok": ok, "exit": tools.last_exit, "out_len": len(out)},
                                    ensure_ascii=False) + "\n")
                messages.append({"role": "tool", "tool_call_id": c["id"], "content": out})
        else:
            answer = "（达到步数上限）"
    stats["seconds"] = round(time.time() - t0, 1)
    stats["answer"] = answer[:2000]
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
