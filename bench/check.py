# -*- coding: utf-8 -*-
"""客观核对：只看 Agent 留下的文件和隐藏测试，不看它说了什么。

    python check.py <任务> <工作目录> <truth.json>
打印一行 JSON：{"quality_ok": bool, "why": [...]}
"""
import csv
import json
import os
import subprocess
import sys
import textwrap


def check_log(work, truth):
    p = os.path.join(work, "answer.json")
    if not os.path.exists(p):
        return ["没有 answer.json"]
    try:
        a = json.load(open(p, encoding="utf-8-sig"))
    except ValueError as e:
        return [f"answer.json 不是合法 JSON：{e}"]
    why = []
    t = truth["log_triage"]
    if str(a.get("endpoint", "")).strip() != t["endpoint"]:
        why.append(f"endpoint={a.get('endpoint')!r}，应为 {t['endpoint']}")
    try:
        if int(a.get("count")) != t["count"]:
            why.append(f"count={a.get('count')}，应为 {t['count']}")
    except (TypeError, ValueError):
        why.append(f"count={a.get('count')!r} 不是整数")
    if t["top_reason"] not in str(a.get("top_reason", "")):
        why.append(f"top_reason={a.get('top_reason')!r}，应含 {t['top_reason']!r}")
    return why


def check_csv(work, truth):
    p = os.path.join(work, "monthly.csv")
    if not os.path.exists(p):
        return ["没有 monthly.csv"]
    got = {}
    with open(p, encoding="utf-8-sig", newline="") as f:
        rd = csv.DictReader(f)
        cols = [c.strip().lower() for c in (rd.fieldnames or [])]
        if cols[:3] != ["month", "region", "total"]:
            return [f"表头是 {rd.fieldnames}，应为 month,region,total"]
        for row in rd:
            row = {k.strip().lower(): (v or "").strip() for k, v in row.items()}
            try:
                got[f"{row['month']}|{row['region']}"] = round(float(row["total"]), 2)
            except ValueError:
                return [f"total 不是数字：{row}"]
    exp = truth["csv_monthly"]
    why = []
    missing = sorted(set(exp) - set(got))
    extra = sorted(set(got) - set(exp))
    wrong = [k for k in exp if k in got and abs(got[k] - exp[k]) > 0.011]
    if missing:
        why.append(f"缺 {len(missing)} 格，如 {missing[:3]}")
    if extra:
        why.append(f"多 {len(extra)} 格，如 {extra[:3]}")
    if wrong:
        k = wrong[0]
        why.append(f"{len(wrong)} 格金额不对，如 {k}: {got[k]} ≠ {exp[k]}")
    return why


HIDDEN = textwrap.dedent('''
    import importlib, os, pytest

    def fresh(mod):
        import svc.config
        importlib.reload(svc.config)
        m = importlib.import_module(mod)
        return importlib.reload(m)

    @pytest.mark.parametrize("env,want", [(None, @DEFAULT@), ("45", 45)])
    def test_everywhere(env, want, monkeypatch):
        if env is None:
            monkeypatch.delenv("@ENV@", raising=False)
        else:
            monkeypatch.setenv("@ENV@", env)
        assert fresh("svc.client").request_options()["@KEY@"] == want
        assert fresh("svc.worker").deadline_seconds() == want
        assert fresh("svc.cli").build_parser().parse_args([]).@KEY@ == want

    def test_worker_poll_uses_setting(monkeypatch):
        monkeypatch.setenv("@ENV@", "1")
        w = fresh("svc.worker")
        import time
        t0 = time.monotonic()
        assert w.poll(lambda: None) is None
        assert time.monotonic() - t0 < 5

    def test_invalid(monkeypatch):
        monkeypatch.setenv("@ENV@", "abc")
        with pytest.raises(Exception):
            fresh("svc.client").request_options()
''')


def check_repo(work, truth, meta):
    repo = os.path.join(work, "repo")
    why = []
    own = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=repo,
                         capture_output=True, text=True, timeout=300)
    if own.returncode != 0:
        why.append("仓库自带测试没过：" + own.stdout.strip().splitlines()[-1:][0] if own.stdout.strip() else "仓库自带测试没过")
    tests = [f for f in os.listdir(os.path.join(repo, "tests")) if f.startswith("test_") and f != "test_client.py"]
    if not tests:
        why.append("没有补新测试")
    hp = os.path.join(repo, "tests", "_hidden_check.py")
    hidden = HIDDEN.replace("@ENV@", meta["env"]).replace("@KEY@", meta["key"]).replace("@DEFAULT@", str(meta["default"]))
    open(hp, "w", encoding="utf-8").write(hidden)
    try:
        h = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", hp], cwd=repo,
                           capture_output=True, text=True, timeout=300)
    finally:
        os.remove(hp)
    if h.returncode != 0:
        failed = [l for l in h.stdout.splitlines() if l.startswith("FAILED")]
        why.append("隐藏测试没过：" + ("; ".join(failed[:3]) or h.stdout.strip()[-300:]))
    return why


def main():
    task, work, truth_p = sys.argv[1:4]
    truth = json.load(open(truth_p, encoding="utf-8"))
    mp = os.path.join(os.path.dirname(os.path.abspath(truth_p)), "meta.json")
    meta = json.load(open(mp, encoding="utf-8")) if os.path.exists(mp) else {"env": "APP_TIMEOUT", "key": "timeout", "default": 30}
    fn = {"log_triage": check_log, "csv_monthly": check_csv, "config_env": check_repo}[task]
    why = fn(work, truth, meta) if fn is check_repo else fn(work, truth)
    print(json.dumps({"quality_ok": not why, "why": why}, ensure_ascii=False))


if __name__ == "__main__":
    main()
