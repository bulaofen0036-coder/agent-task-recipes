# 配方：新建 SCL 块 v2（TIA Portal Openness MCP）

**适用**：「写一个 SCL 功能块/函数，编译通过后保存」
**不适用**：改已有块（另一个配方：不能删块重建，会丢块号）、梯形图
**前提**：隔离实例或用户同意的工程副本

## 步骤
1. `ConnectIsolated()` → `OpenProject(path=<工程路径>)` → `GetProjectTree()`（取 PLC 真名）
2. `WritePlcSclSourceFile(sclContent=<完整源码>)` 一次写完整源码（FUNCTION_BLOCK "块名" … END_FUNCTION_BLOCK）。要点：版本行 `VERSION : 0.1`；变量名避开保留字（Time、Date、Counter、Timer 等）；IEC 定时器实例放在 VAR 里
3. `CallTool(name="ImportPlcExternalSource", argumentsJson="{\"softwarePath\":\"<PLC真名>\",\"groupPath\":\"\",\"filePath\":\"<第2步返回的路径>\"}")`（三个参数都必填，groupPath 传空串）
4. `GenerateBlocksFromExternalSource(softwarePath, externalSourceName=<第2步的文件名>)`
5. `CompileAndDiagnosePlc(softwarePath)`：0 错误才继续；有错只改报错的几行，用第 2 步的工具重写整份源码，再走 3–5 步，最多 3 轮
6. `SaveProject()`

## 完成判据
编译 0 错误、块已生成、工程已保存；回复里贴出最终源码。

## 验收记录
| 版本 | 无配方（3 次） | 本配方（3 次） | 质量 | 结论 |
|---|---|---|---|---|
| v1 | 调用 14.3 / 失败 0.3 / ¥0.058 | 11.0 / **1.0** / ¥0.050 | 全部一次编译通过 | 退回：漏写必填参数 groupPath，每次多失败一次 |
| v2 | 同上 | 9.3 / 0 / ¥0.048 | 全部一次编译通过、已保存、逻辑正确 | 上线 |

v1 的错误被 `tools/check_recipe.py` 静态抓到：`ImportPlcExternalSource 缺必填参数 ['groupPath']`。
