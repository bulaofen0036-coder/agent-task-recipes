# 原始运行记录

每行一次运行，`python ../../tools/ab_report.py <文件> --baseline A` 可直接复算 RESULTS.md 里的表。

| 文件 | 内容 |
|---|---|
| `round2_data0.runs.jsonl` | 第二轮，第 0 套数据：flash A/R/I 各 5 次，pro A/R 各 5 次。`escaped=1` 的一行是越界运行，汇总时自动剔除 |
| `round2_data1.runs.jsonl` | 第二轮，第 1 套数据（换数据测复用）：flash A/R/I 各 3 次 |
| `round2_data1_config_void.runs.jsonl` | 作废：第 1 套数据第一版的改配置题把名字连同含义一起换了，隐藏测试判错了做对的 Agent；修题后重跑的结果在上一个文件里 |
| `round1.runs.jsonl` | 第一轮：Claude Code + Haiku 各 3 次（有效）；generic 行用的是旧的失败调用口径（返回码≠0 就算失败），只供参考 |
