# Agent 任务配方（Task Recipes）

让 Agent 把**高频任务**按固定的最短正确做法执行：少调用、少 token、少失败，而且用数据证明。

适用于任何调用工具的 Agent：Claude Code、Codex、Cursor、自研 LangGraph/AutoGen Agent、任何 MCP 客户端。

## 它是什么

- **配方** = 一个高频任务的固定步骤 + 每步的真实工具名和参数 + 完成判据 + 已知失败的处理。
- **流程指导型**：把配方交给 Agent，Agent 照着逐步调用。改动小，先用这个。
- **组合执行型**：后端一个入口跑完全部步骤，必须逐步报告「完成 / 失败 / 没做」。配方跑稳之后再升级成这个。
- 和 skill 的区别：skill 管「懂」（领域知识、规则、坑），配方管「做」（一个具体任务怎么一步步做）。配方能被程序检查、能做 A/B 验收。

## 实测效果（工业编程 Agent，真实软件，每组 2–3 次）

| 任务 | 无配方 → 配方 | 失败 | 费用 |
|---|---|---|---|
| 中型工程总览 | 调用 17 → 6 | 0 → 0 | −40% |
| 大型工程总览（222 块） | 调用 18 → 13 | 0.7 → 0 | −34% |
| 新建功能块（编译通过并保存） | 调用 14 → 9 | 0.3 → 0 | −17% |

质量判据全部通过。**但写错的配方比没有更糟**：漏一个必填参数，每次多失败一次；塞了用户没问的步骤，调用翻倍还漏答。所以要按下面的方法做，而不是随手写一段提示词。详见 [`examples/case-study.md`](examples/case-study.md)。

## 怎么用

**给 Agent**：把 [`SKILL.md`](SKILL.md) 放进 Agent 的 skill 目录（Claude Code：`~/.claude/skills/task-recipes/`），或直接作为说明文档交给 Agent。它会按 6 步做配方：找高频任务 → 测基线 → 写配方 → 自动体检 → A/B 对比 → 上线与维护。

**工具**（Python 3.8+，无第三方依赖）：

| 工具 | 作用 |
|---|---|
| `tools/check_recipe.py` | 配方体检：对照 MCP 服务器的工具清单，检查工具名、参数名、必填项。`--selftest` 跑必错哨兵 |
| `tools/ab_report.py` | A/B 汇总：每组均值 + 是否达到上线标准 |
| `tools/mine_claude_code.py` | 从 Claude Code 会话记录里找高频任务和反复出现的错误 |

```bash
python tools/check_recipe.py --selftest
python tools/check_recipe.py --mcp "your-mcp-server --args" my_recipe.md
python tools/ab_report.py results.csv --baseline A
python tools/mine_claude_code.py --days 30
```

**模板**：[`templates/recipe_template.md`](templates/recipe_template.md)。工具调用写成行内代码 `` `ToolName(param=value)` ``，体检工具靠这个格式检查。

## 目录

```
SKILL.md                      方法本身（给 Agent 读）
templates/recipe_template.md  配方模板
templates/composite_runner.py 组合执行型入口骨架：逐步报告、失败即停、--resume 断点续跑
tools/                        体检 / A/B 汇总 / 会话挖掘
examples/case-study.md        实测案例与数据
examples/tia-portal/          真实配方：好的 v2、坏的 v1（附错在哪）、A/B 原始数据 ab_results.csv
```

## 三条最重要的规矩

1. **先测基线，再写配方**；质量判据必须是可核对的客观事实。判据写松了，A/B 结论就会失真（我们自己就踩过一次）。
2. **上线前过两道关**：静态体检（工具名、参数名、必填项）+ A/B（不比无配方差才上线）。
3. **只覆盖用户问到的范围**；工具或模型一变，重跑体检和 A/B。

---

**English summary.** A method (plus small tools) for turning an agent's high-frequency tasks into *recipes*: fixed steps with real tool names and parameters, a done-criterion, and known-failure handling. Start as *guided* recipes (injected into the agent), then promote stable ones to *composite* entry points that report per-step results, failure point, and unfinished scope. Measured on a real industrial-automation agent: 30–65% fewer tool calls, 17–40% lower cost, zero failed calls, same quality. A wrong recipe is worse than none, so every recipe must pass a static check against the server's tool schema and an A/B run against the no-recipe baseline. See `SKILL.md`.
