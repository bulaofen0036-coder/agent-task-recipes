# 反面教材：新建 SCL 块 v1（漏写一个必填参数）

只列出与 v2 不同的那一步。用 `tools/check_recipe.py` 跑这个文件，应当报「缺必填参数 groupPath」。

3. `CallTool(name="ImportPlcExternalSource", argumentsJson="{\"softwarePath\":\"<PLC真名>\",\"filePath\":\"<第2步返回的路径>\"}")`

实测：3 次执行每次都在这一步先失败一次，Agent 读报错补上参数后才继续（失败 0.3 → 1.0）。
