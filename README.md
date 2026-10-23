# Agent 任务配方（Task Recipes）

把 Agent 反复做的高频任务写成**配方**：一类任务的最短正确做法，可以有多条路线。每条路线写清步骤、成功判据和失败时转向哪条。配方能被程序检查，并用 A/B 数据持续定级。

适用于任何调用工具的 Agent：Claude Code、Codex、Cursor、自建的函数调用 / LangGraph Agent、任何 MCP 客户端、团队内部的重复工作流。

> **状态：v0.2 实验版。** 方法和工具可用，结论来自 3 个通用任务、1 个专业软件任务、3 个 Agent/模型组合，每组 3–5 次。局限见 [`RESULTS.md`](RESULTS.md)。

## 实测：它能帮什么，不能帮什么

| 发现 | 数据 |
|---|---|
| **质量保险最稳** | 第二轮所有有效运行：不给配方全对 31/38，手写配方 **39/39**。DeepSeek pro 处理脏 CSV，不给配方 0/5（漏了去重），给了 5/5 |
| **便宜模型 + 固定套路的任务能省** | flash 日志排障调用 −34%；换一套数据后仍是调用 −31%、费用 −35% |
| **本来就做得好的 Agent 用不着** | Claude Code + Haiku 不给配方就 3/3 全对、5–8 次调用；加了配方没有一项明显变好 |
| **自动起草可用，要人改** | 从成功运行归纳的草稿，在新数据上和手写配方效果相当，但会抄下旧数据的文件名甚至答案 |
| **路线可迭代** | 专业软件案例：同一任务三条路线，一条淘汰（静态体检看不出、A/B 跑出来的），一条默认（调用 −34%），一条备用 |

**结论随 Agent 和模型变**，所以每个配方都按「Agent/模型」分别定级，不宣传成通用提速。完整数据、测试台和复现命令见 [`RESULTS.md`](RESULTS.md)。

## 配方 vs skill

skill 管「懂」：领域知识、规范、坑。配方管「做」：一类具体任务怎么一步步做、做完怎么核对、失败转哪条路。配方可以装在 skill 里分发（本包就是一个 skill），也可以注入规划器、MCP 服务器的 prompts，或附在任务消息后面。

两种落地方式，用同一份配方定义：
- **流程指导型**：把步骤交给 Agent，Agent 逐步调工具。先用这个。
- **组合执行型**：后端一个入口跑完全部步骤，必须逐步返回「完成 / 失败 / 没做」、失败位置和没完成的范围。跑稳了再升级。

## 怎么用

**给 Agent**：把 [`SKILL.md`](SKILL.md) 放进 Agent 的 skill 目录（Claude Code：`~/.claude/skills/task-recipes/`），或直接作为说明文档交给 Agent。它按 6 步做配方：找高频任务 → 测基线（先看值不值得做）→ 写配方（可先自动起草）→ 自动体检 → A/B 定级（含换数据复用测试）→ 运行中迭代。

**工具**（Python 3.8+，只用标准库）：

| 工具 | 作用 |
|---|---|
| `tools/check_recipe.py` | 配方体检：路线结构、默认路线、失败去向、验证日期；给了 MCP 工具清单时再查工具名、参数名、必填项。`--selftest` 跑必错哨兵 |
| `tools/ab_report.py` | A/B 汇总：按「Agent/模型 × 任务 × 路线」给出均值±标准差、定级（默认 / 备用 / 候选 / 淘汰）和跨组合对照 |
| `tools/draft_from_trace.py` | 从几次成功运行的轨迹归纳配方草稿：公共步骤当主干，标出「可能是试探」的步骤 |
| `tools/mine_claude_code.py` | 从 Claude Code 会话记录里找高频任务和反复出现的错误 |
| `bench/` | 通用测试台：3 个带坑的任务、确定性数据、隐藏测试、最小 Agent 和 Claude Code 运行器、越界扫描 |

```bash
python tools/check_recipe.py --selftest
python tools/check_recipe.py my_recipe.md                                   # 只查结构
python tools/check_recipe.py --mcp "your-mcp-server --args" my_recipe.md    # 再查工具名和参数
python tools/draft_from_trace.py run1.jsonl run2.jsonl run3.jsonl --name 我的任务
python tools/ab_report.py runs.jsonl --baseline A
```

## 目录

```
SKILL.md                      方法本身（给 Agent 读）
RESULTS.md                    实测数据、测试台、局限、和已有研究的关系
templates/recipe_template.md  配方模板（多路线、选路表、成功判据、失败去向、验收记录）
templates/composite_runner.py 组合执行型入口骨架：逐步报告、失败即停、--resume 断点续跑
tools/                        体检 / A/B 定级 / 自动起草 / 会话挖掘
bench/                        通用测试台与三个任务的配方（recipes/ 手写，induced/ 自动起草）
examples/tia-portal/          专业软件案例：多路线配方、坏配方及错在哪、原始数据
examples/case-study.md        专业软件案例的早期数据
```

## 四条规矩

1. **先测基线再决定做不做**：基线会做错的最值得做；基线全对又省的别做。质量判据必须是程序能核对的事实，并用「原样未做必判失败、参考答案必判通过」验过判据本身。
2. **上线前过两道关**：静态体检 + A/B（每组 ≥3 次，交替跑，Agent 不能翻到答案）。再换一套同类数据跑一遍。
3. **只覆盖用户问到的范围**。写错的配方比没有更糟：漏一个必填参数，每次多失败一次；塞了用户没问的步骤，调用翻倍还漏答。
4. **按组合定级、持续迭代**：新路线先当候选，跑够次数再升默认；淘汰的路线留在文件里，免得有人再写回来。

---

**English summary.** A method plus small stdlib-only tools for turning an agent's recurring tasks into *recipes*: multi-route procedures with real tool calls, success criteria and failure routing, checked statically and graded by A/B runs per agent/model combo. On a reproducible generic bench (log triage, dirty-CSV aggregation, config refactor with hidden tests): hand-written recipes passed 39/39 vs 31/38 without; DeepSeek v4 pro went from 0/5 to 5/5 on the dirty CSV task. A cheap model saved 31–34% tool calls on log triage, and the saving held on a fresh dataset. Claude Code + Haiku gained nothing because it was already correct and efficient. Recipes are quality insurance first; efficiency gains depend on the combo. Auto-drafted recipes (from successful traces) work, but they copy instance values, sometimes the answer itself, so validate them only on fresh data. Status: v0.2 experimental, see `RESULTS.md`.
