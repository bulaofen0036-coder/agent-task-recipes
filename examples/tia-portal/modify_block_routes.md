---
recipe: 修改已有 SCL 功能块（加接口变量 + 加语句）
version: 3
verified: 2026-10-23
models: [deepseek-v4-flash]
server: TIA Portal Openness MCP（V21）
---
# 配方：修改已有 SCL 功能块

适用：用户要给工程里**已经存在**的 SCL 功能块加变量、加几行逻辑，块号和背景 DB 不能变。
不适用：新建块（见 `new_scl_block_v2.md`）、梯形图块、要改块号。

## 选路

| 条件 | 走 |
|---|---|
| 默认 | 路线 S |
| 工程里不允许删外部源 / 改动只有一两行、想保留导出文档里的属性 | 路线 D |

## 路线 S：导出现状 → 重写整份源 → 删旧源 → 导入 → 生成（默认）
**条件**：无
1. `ConnectIsolated()` → `OpenProject(path=<工程路径>)` → `GetProjectTree()`（取 PLC 真名）
2. `CallTool(name="ExportAsDocuments", argumentsJson="{\"softwarePath\":\"<PLC真名>\",\"blockPath\":\"<块名>\",\"exportPath\":\"<新建的空目录>\"}")`，再读导出的 `<块名>.s7dcl`：这是现有接口和代码的唯一来源，不凭记忆重写
3. `WritePlcSclSourceFile(...)` 一次写完整源码：保留原有全部接口和逻辑，只加用户要的改动。第一行 `FUNCTION_BLOCK "<块名>"`，下一行 `{ S7_Optimized_Access := 'TRUE' }`，再下一行 `VERSION : 0.1`；`.s7dcl` 里的 `{ S7_MLC := ... }`、`NETWORK` / `END_NETWORK` 不抄。文件名 `<块名>.scl`
4. `DeletePlcExternalSource(softwarePath=<PLC真名>, externalSourceName=<块名>.scl)`：**直接调**，删除类工具经 `CallTool` 会被拒绝；同名旧源不删，导入会冲突
5. `CallTool(name="ImportPlcExternalSource", argumentsJson="{\"softwarePath\":\"<PLC真名>\",\"groupPath\":\"\",\"filePath\":\"<第3步返回的路径>\"}")`
6. `GenerateBlocksFromExternalSource(softwarePath=<PLC真名>, externalSourceName=<块名>.scl)`：返回必须是 updated 1；出现 created 说明块名写错了，停下报告
7. `CompileAndDiagnosePlc(softwarePath=<PLC真名>)`：0 错误才继续；有错只改报错的几行，重写整份源再走 4–7，最多 3 轮
8. `SaveProject()`

**成功判据**：生成结果是 updated（块号不变）、编译 0 错误、工程已保存；回复里贴出最终源码。
**失败时**：第 4 步被拒或不允许删源 → 转路线 D；编译 3 轮仍有错 → 停下，贴出错误原文。

## 路线 D：导出文档 → 局部修改 → 预检 → 覆盖导入（备用）
**条件**：不能删外部源，或只改一两行
1. `ConnectIsolated()` → `OpenProject(path=<工程路径>)` → `GetProjectTree()`
2. `CallTool(name="ExportAsDocuments", argumentsJson="{\"softwarePath\":\"<PLC真名>\",\"blockPath\":\"<块名>\",\"exportPath\":\"<新建的空目录>\"}")`
3. 读 `<块名>.s7dcl`，只改需要改的几处：新变量照现有格式写进对应 VAR 段，新语句写在 `NETWORK` 和 `END_NETWORK` 之间；属性行和 `.s7res` 不动
4. `CallTool(name="PreflightDocumentImport", argumentsJson="{\"importPath\":\"<第2步的目录>\",\"fileNameWithoutExtension\":\"<块名>\"}")`：有 error 按提示改了再查
5. `CallTool(name="ImportFromDocuments", argumentsJson="{\"softwarePath\":\"<PLC真名>\",\"groupPath\":\"\",\"importPath\":\"<第2步的目录>\",\"fileNameWithoutExtension\":\"<块名>\"}")`：返回必须有 replacedExisting=true；块在分组里时 groupPath 填分组
6. `CompileAndDiagnosePlc(softwarePath=<PLC真名>)`：0 错误才继续，最多 3 轮
7. `SaveProject()`

**成功判据**：导入是覆盖原块、编译 0 错误、工程已保存。
**失败时**：预检 3 轮仍报错 → 转路线 S。

## 路线 S1：同路线 S，但第 4 步经 CallTool 调删除（淘汰）
**条件**：无（保留在这里，防止以后有人把同一条错路写回来）
1. 与路线 S 相同，只是第 4 步写成 `CallTool(name="DeletePlcExternalSource", ...)`

**成功判据**：同路线 S
**失败时**：转路线 S
淘汰原因：引擎拒绝经 CallTool 调删除类工具，每次运行平均多失败 2 次。静态体检看不出来，A/B 跑出来的。

## 不要做
- 不要 `DeletePlcBlock`：块号会变，背景 DB 关联会断，而且没有任何报错。
- 不要用通用的写文件工具写 `.scl`：会丢 UTF-8 BOM，中文注释编译时乱码。
- 不要相信引擎说明里「生成不会覆盖已有块」的说法：V21 实测删源 → 导入 → 生成会原地更新已有块。

## 验收记录

| 日期 | 模型 | 路线 | 次数 | 调用 | 失败 | 费用 ¥ | 质量 | 结论 |
|---|---|---|---|---|---|---|---|---|
| 2026-10-23 | deepseek-v4-flash | 无配方 | 3 | 20.3 | 0 | 0.064 | 3/3 | 基线 |
| 2026-10-23 | deepseek-v4-flash | S1 | 3 | 17.7 | 2.0 | 0.055 | 3/3 | 淘汰：多出的失败调用 |
| 2026-10-23 | deepseek-v4-flash | S | 3 | 13.3 | 0.3 | 0.049 | 3/3 | 默认：调用 −34%，费用 −23% |
| 2026-10-23 | deepseek-v4-flash | D | 3 | 16.0 | 0.3 | 0.052 | 3/3 | 备用：调用 −21%，费用 −18% |

质量判据（独立于 Agent 的回答）：重新打开保存后的工程副本，导出该块，核对新接口变量、新赋值语句、块号仍为原号、编译 0 错误；原样未改的工程副本必须判失败。原始数据：`modify_block_runs.jsonl`。
