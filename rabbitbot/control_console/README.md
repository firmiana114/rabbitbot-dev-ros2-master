# RabbitBot 网页控制台说明

本目录实现 Orin 局域网网页控制台，用于交付现场人员在浏览器中启动导览、返航、重启导航主程序、切换地图、查看定位位姿、按需查看日志，以及编辑导览讲解词。

## 代码位置

- `app.py`：FastAPI 应用入口，包含页面 HTML/CSS/JS 的 `_html()` 函数，以及 `/api/status`、`/api/task`、`/api/command`、`/api/restart`、`/api/dialogue`、`/api/logs` 接口。
- `commands.py`：发送 workflow 命令、一键重启 `rabbitbot-loop.service`、写入运行时地图环境文件。
- `dialogue.py`：导览讲解词 JSON 的读取、结构校验、保存和自动备份。
- `config.py`：控制台配置来源，包括端口、地图默认值、台词文件路径、systemd 服务名。
- `status.py`：读取主循环状态、导航桥接端口、workflow 状态、定位位姿和日志尾部。
- `__main__.py`：`python3 -m rabbitbot.control_console` 启动入口。
- `scripts_1/start_control_console.sh`：systemd 实际调用的控制台启动脚本。
- `tests/control_console/`：控制台接口和页面关键内容测试。

页面代码目前没有单独的前端工程，所有前端页面都在 `app.py` 的 `_html()` 字符串内。修改按钮、布局、文案、JavaScript 交互时，优先查看这个函数。

## 访问方式

控制台服务运行在 Orin 上，默认监听：

```text
http://192.168.101.2:8080
```

如果 Orin 更换局域网 IP，只需要把浏览器地址中的 IP 换成新的 Orin IP；端口仍是 `8080`，除非修改了 `RABBITBOT_CONSOLE_PORT`。

控制台已经取消密码登录，打开页面即可使用。

## systemd 服务

控制台服务：

```bash
sudo systemctl status rabbitbot-control-console.service
sudo systemctl restart rabbitbot-control-console.service
```

导航主程序服务：

```bash
sudo systemctl status rabbitbot-loop.service
sudo systemctl restart rabbitbot-loop.service
```

网页上的“一键重启”调用后端 `/api/restart`，实际执行的是重启 `rabbitbot-loop.service`。网页上的“关闭程序”调用后端 `/api/stop`，实际执行的是停止 `rabbitbot-loop.service`，不会关闭网页控制台服务。

网页后端以 `pc` 用户运行，停止/重启 systemd 服务需要 sudoers 免密授权。交付部署时应安装仓库内的模板：

```bash
sudo install -m 0440 scripts_1/systemd/rabbitbot-control-console.sudoers /etc/sudoers.d/rabbitbot-control-console
sudo visudo -cf /etc/sudoers.d/rabbitbot-control-console
```

该模板只允许 `pc` 免密执行以下固定命令：

```text
/usr/bin/systemctl restart rabbitbot-loop.service
/usr/bin/systemctl stop rabbitbot-loop.service
```

## 地图切换和一键重启

页面左侧有“重启地图”输入框。

操作步骤：

1. 在“重启地图”中填写地图绝对路径，例如 `/home/unitree/test9.pcd`。
2. 点击“一键重启”。
3. 后端会先校验地图路径必须是绝对路径。
4. 校验通过后写入 `runtime/rabbitbot-loop.env`。
5. 后端重启 `rabbitbot-loop.service`，导航主程序启动时读取新地图。

运行时地图环境文件格式：

```text
NAV_PCD_PATH="/home/unitree/test9.pcd"
```

`scripts_1/systemd/rabbitbot-loop.service` 中有默认地图和环境文件覆盖配置：

```ini
Environment=NAV_PCD_PATH=/home/unitree/test9.pcd
EnvironmentFile=-/mnt/ssd/navgation/projects/rabbitbot-dev-ros2-master/runtime/rabbitbot-loop.env
```

## 导览任务

“开始任务”下有三个按钮：

- “导览”：当前已接入，等同发送 workflow 的 `go` 命令。
- “对话”：当前为占位按钮，只返回提示，不执行外部脚本。
- “视觉导航”：当前为占位按钮，只返回提示，不执行外部脚本。

“返航”按钮发送 workflow 的 `back` 命令。

“关闭程序”按钮用于停止导航主程序：

1. 点击“关闭程序”。
2. 浏览器会弹出确认框。
3. 确认后后端执行 `systemctl stop rabbitbot-loop.service`。
4. 网页控制台仍会继续运行，可继续查看状态，或后续点击“一键重启”重新启动导航主程序。

## 导览讲解词编辑

讲解词区域用于维护当前导览台词 JSON。默认编辑的文件是：

```text
conf/dialogue_0.json
```

如果后续通过环境变量设置了 `RABBITBOT_DIALOGUE_INDEX=1`，则会编辑 `conf/dialogue_1.json`。如果设置了 `RABBITBOT_DOCX_GUIDE_DIALOGUE_FILE`，则优先编辑该变量指定的完整路径。

操作步骤：
