# 反面教材：工程总览 v1（实测比不用配方更差）

> 保留这一版是为了说明「写错的配方比没有更糟」。和 v2 的差别只有三处，见文末。

## 步骤
1. `ConnectIsolated()` → `OpenProject(path=<工程路径>)`
2. `GetProjectTree()`
3. 每台 PLC 调一次 `CallTool(name="GetBlockStats", argumentsJson="{\"softwarePath\":\"<PLC真名>\"}")`
4. 调用关系：对每台 PLC 的每个 OB 调 `DescribeBlockLogic(softwarePath, blockPath)`
5. 第 2 步里有 HMI 才调 `GetHmiScreens(softwarePath=<HMI真名>)`

## 实测（大型工程：7 台 PLC、222 块；用户只问了「设备、块数和分组、HMI」）
| | 无配方 | v1 |
|---|---|---|
| 工具调用 | 18.3 | **43.0** |
| 失败调用 | 0.7 | **4.5** |
| 费用 | ¥0.076 | ¥0.112 |
| 质量 | 7 台块数全对 | 有 1 次漏了 3 台 |

## 错在哪
1. **第 4 步没按问题裁剪**：用户没问调用关系，配方却要求读每个 OB，7 台 PLC 读了二十多次，遇到不一致的块还失败。→ v2 改成「问到才做」。
2. **没说「不要调 GetDevices」**：Agent 照样先调它，结果太大被转存，又用文件工具翻找。→ v2 写进「不要做」。
3. **没说「不要用假路径试探」**：Agent 用 `__probe__` 之类的假名字去试 HMI 在不在，连失败 3 次。→ v2 明确「看第 2 步」。
