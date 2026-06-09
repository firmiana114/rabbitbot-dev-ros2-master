# conf 目录说明

本目录用于放置 workflow 的现场配置文件。

导览台词文件按 `dialogue_<序号>.json` 命名，例如：

- `dialogue_0.json`：不显式指定时默认加载的 0 号台词
- `dialogue_1.json`：可通过 `RABBITBOT_DIALOGUE_INDEX=1` 选择
- `dialogue_2.json`：可通过 `RABBITBOT_DIALOGUE_INDEX=2` 选择

`dialogue*` 前缀的台词文件属于现场本地配置，已在 `.gitignore` 中忽略，不纳入版本管理。这样现场修改称呼和台词不会污染 Git 工作区。

本目录没有被整体忽略；除 `dialogue*` 前缀文件外，其它需要版本管理的配置文件仍可正常提交。

## 台词 JSON 新字段

台词 JSON 支持在顶层配置地图文件名和点位列表：

- `map_file`：当前台词配置使用的地图文件名，例如 `test1.pcd`。该字段用于记录和日志排查，实际启动导航桥接时仍需确保 `NAV_PCD_PATH` 指向同一地图文件。
- `points`：DOCX 严格剧本点位列表，键名应优先与 `steps[].entity_key` 保持一致，例如 `point_2`、`point_3_to_5_transition`。
- `back_points`：可选返航点位列表，用于 `back` 命令；未配置或为空时，导航 loop 会按 `steps[].entity_key` 的 go 点位序列反向生成返航路线，并在存在 `point_1` 时补充为最终起点。

每个 `points` 条目建议包含：

- `name`：中文点位名，例如 `点位2`。
- `summary`：点位摘要。
- `description`：点位说明。
- `location`：导航坐标数组，每个坐标对象包含 `x`、`y`、`z`、`ox`、`oy`、`oz`、`ow`、`mode`。

workflow 会优先读取当前台词 JSON 的 `points`；如果台词文件没有配置对应点位，才回退到代码内的旧点位配置。修改点位或 `map_file` 后需要重启 workflow 进程，让新台词文件重新加载。

`back_points` 支持两种写法：

- 字符串数组：例如 `["point_5", "point_3_to_5_transition", "point_3", "point_2", "point_1_to_2_transition", "point_1"]`，每个字符串引用 `points` 中的键。
- 点位对象数组：每个对象可直接写 `name` 和 `location`，也可写 `point_key` 或 `entity_key` 引用 `points`。

导航 loop 发送给 28180 的返航坐标使用六元组 `(x, y, ox, oy, oz, ow)`，会从 `location` 中自动忽略 `z` 和 `mode`。返航开始时日志会打印点位来源、台词文件路径、分段数量和路线，便于确认到底使用了 `back_points` 还是 go 点位反序兜底。
