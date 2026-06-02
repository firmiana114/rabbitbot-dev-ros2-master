# conf 目录说明

本目录用于放置 workflow 的现场配置文件。

导览台词文件按 `dialogue_<序号>.json` 命名，例如：

- `dialogue_0.json`：不显式指定时默认加载的 0 号台词
- `dialogue_1.json`：可通过 `RABBITBOT_DIALOGUE_INDEX=1` 选择
- `dialogue_2.json`：可通过 `RABBITBOT_DIALOGUE_INDEX=2` 选择

`dialogue*` 前缀的台词文件属于现场本地配置，已在 `.gitignore` 中忽略，不纳入版本管理。这样现场修改称呼和台词不会污染 Git 工作区。

本目录没有被整体忽略；除 `dialogue*` 前缀文件外，其它需要版本管理的配置文件仍可正常提交。
