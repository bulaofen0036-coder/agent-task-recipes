---
recipe: config_env
version: 0
verified: 未验证
models: []
server: <填>
---
# 配方草稿：config_env

<!-- 由 3 份成功轨迹归纳。标「可能是试探」的步骤只在部分轨迹出现，先判断要不要留。参数里的 <占位> 要换成「来源说明」。补完「不要做 / 成功判据 / 失败时」后再体检、A/B。 -->

## 路线 A：<从轨迹归纳的做法>（候选）
**条件**：<填>
1. `list_dir(path="repo")`
2. 执行：`find repo -type f -name "*.py" | head -50; echo "---"; ls -la repo`
3. `read_file(path=<路径>)`（对每个对象各一次，本轨迹 7 次）（可能是试探：只在部分轨迹出现）
4. 执行：`cd repo && grep -rn "TIMEOUT\|timeout\|10" --include="*.py" --include="*.md" --include="*.toml" --include="*.cfg" --include="*.ini" . ; echo "---files---"; find . -type f | sort; echo "---py---"; python -V; python -m pytest -q 2>&1 | tail -`（可能是试探：只在部分轨迹出现）
5. `write_file(path=<路径>, content=<值>)`（对每个对象各一次，本轨迹 11 次）
6. 执行：`cd repo && python -m pytest -q 2>&1 | tail -20`
7. 执行：`cd repo && grep -rn "10" --include="*.py" svc/ ; echo "== default =="; python -c "from svc.client import request_options; from svc.worker import deadline_seconds; from svc.cli import build_parser; print(request_options(), deadline_seconds()`
8. 执行：`cd repo && python -m pytest -q; echo "exit=$?"; ls tests`

**成功判据**：<填：做完时能核对的事实>
**失败时**：<填>

## 不要做
- <从失败的调用里总结：本次轨迹里失败过的调用见下方>

