---
recipe: log_triage
version: 0
verified: 未验证
models: []
server: <填>
---
# 配方草稿：log_triage

<!-- 由 3 份成功轨迹归纳。标「可能是试探」的步骤只在部分轨迹出现，先判断要不要留。参数里的 <占位> 要换成「来源说明」。补完「不要做 / 成功判据 / 失败时」后再体检、A/B。 -->

## 路线 A：<从轨迹归纳的做法>（候选）
**条件**：<填>
1. `list_dir(path="logs")`
2. 执行：`ls -la; echo "---"; ls -la logs | head -50`（可能是试探：只在部分轨迹出现）
3. 执行：`head -5 logs/app-20261022-13.log; echo "=== tail ==="; tail -3 logs/app-20261022-13.log; echo "=== gz ==="; zcat logs/app-20261022-14.log.gz | head -5; echo "---"; zcat logs/app-20261022-14.log.gz | wc -l`
4. 执行：`zcat logs/app-20261022-14.log.gz | awk '$4 ~ /^status=5/' | head -20; echo "=== count 5xx ==="; zcat logs/app-20261022-14.log.gz | awk '$4 ~ /^status=5/' | wc -l`
5. 执行：`zcat logs/app-20261022-14.log.gz | awk '{print $2}' | sort | uniq -c; echo "=== non-standard ==="; zcat logs/app-20261022-14.log.gz | grep -vE '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z (INFO|WARN|ERROR) /[^ ]* status=[0-9]{3}`（可能是试探：只在部分轨迹出现）
6. 执行：`cd logs; echo "=== 其他文件是否含 14: 时间戳(UTC) ==="; for f in app-20261022-{08,09,10,11,12,13,15,16,17}.log; do c=$(grep -c 'T14:' "$f"); echo "$f $c"; done
echo "=== 5xx by endpoint (14:00-14:59:59Z) ==="
zcat app-20261022-14.log.gz | awk '$2=="I`
7. `write_file(path="answer.json", content=<值>)`（可能是试探：只在部分轨迹出现）
8. 执行：`cd "<路径>" && cat answer.json && python -c "import json;d=json.load(open('answer.json'));print('JSON OK ->',d)"`

**成功判据**：<填：做完时能核对的事实>
**失败时**：<填>

## 不要做
- <从失败的调用里总结：本次轨迹里失败过的调用见下方>

<!-- 轨迹里失败过的调用（写「不要做」的素材）：
  - 执行：`cd logs && zcat app-20261022-14.log.gz > /tmp/h14.log && wc -l /tmp/h14.log && echo "--- 非标准行样例:" && grep -v -E '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z (INFO /[^ ]+ status=[0-9]+ [0-9]+ms req=[0-9a-f]+|ERROR req=[0-9a-f]+ /`
  - 执行：`cd logs
echo "=== /api/cart ERROR reason 分布 ==="
zcat app-20261022-14.log.gz | awk '$2=="ERROR" && $4=="/api/cart"{sub(/^[^ ]+ [^ ]+ [^ ]+ [^ ]+ -> [0-9]+: /,""); print}' | sort | uniq -c | sort -rn
echo "=== 交叉校验: ERROR 行数 vs 5xx 行数, 以及 /a`
-->
