# RabbitBot LAN Control Console Design

## Goal

Deliver a customer-facing web control page for the Orin so customers do not need terminal access to operate the deployed RabbitBot navigation workflow.

The first version is a lightweight LAN console at `http://<orin-ip>:8080`, protected by the simple password `123`. It exposes only safe, whitelisted controls for the existing navigation workflow.

## Current System Context

The project root is:

```text
/mnt/ssd/navgation/projects/rabbitbot-dev-ros2-master
```

The existing scripts are:

```text
scripts_1/start_nav_bridge_workflow_loop.sh
scripts_1/send_nav_workflow_command.sh
```

`start_nav_bridge_workflow_loop.sh` is the long-running navigation bridge and workflow control loop. It starts the navigation bridge, pre-starts the workflow, waits at a `go` gate, accepts `go` or `back`, monitors workflow completion, and handles return navigation.

`send_nav_workflow_command.sh` writes one command into the workflow command file. It supports:

```text
go
back
quit/exit
```

The customer page must expose only `go` and `back`. `quit/exit` is maintenance-only and must not be shown in the customer UI.

The long-running startup script will later be configured as a boot-time service. The web console does not replace that service.

## Recommended Architecture

Use a small Python FastAPI application running on the Orin:

```text
0.0.0.0:8080
```

Customers access it from the same LAN:

```text
http://<orin-ip>:8080
```

When the Orin moves to another LAN, only `<orin-ip>` changes. The port remains `8080` as long as the web service still listens on that port and the network/firewall allows it.

The app has two parts:

1. Backend API
   - Handles login/session validation.
   - Reads workflow, navigation, and log status.
   - Executes only whitelisted workflow commands.
   - Parses the latest localization pose from navigation bridge logs.

2. Frontend single-page console
   - Shows system readiness, selected map, workflow state, localization pose, recent logs.
   - Provides buttons for `开始任务` and `返航`.
   - Polls status every 1-2 seconds.

## Deployment Boundary

The web console must not directly run arbitrary terminal commands.

Allowed command actions:

```bash
bash /mnt/ssd/navgation/projects/rabbitbot-dev-ros2-master/scripts_1/send_nav_workflow_command.sh go
bash /mnt/ssd/navgation/projects/rabbitbot-dev-ros2-master/scripts_1/send_nav_workflow_command.sh back
```

The app must not expose `quit`, `exit`, shell input, file browser actions, or arbitrary script paths.

The web console may show whether the long-running loop appears healthy, but the first customer version does not need a restart/stop button. Restart and service management can be added later under a separate maintenance mode.

## Map Configuration

For the current test, the navigation map must be:

```text
/home/unitree/test9.pcd
```

The current startup script already supports map override through `NAV_PCD_PATH`:

```bash
NAV_PCD_PATH="${NAV_PCD_PATH:-/home/unitree/test1.pcd}"
```

Do not hard-code `test9.pcd` into the script for long-term use. Configure the boot service with:

```ini
Environment=NAV_PCD_PATH=/home/unitree/test9.pcd
```

The web console should show the active configured map path so the operator can confirm which map is being used.

## UI Design

The customer page has one main screen after login.

Top status band:

- Overall status: online/offline/degraded.
- Current map path, initially `/home/unitree/test9.pcd`.
- Last status refresh time.

Primary controls:

- `开始任务`: sends `go`.
- `返航`: sends `back`.
- `刷新状态`: manually refreshes status.

Status cards:

- Main loop state: running/not detected/unknown.
- Navigation bridge: port `28180` ready/not ready.
- Workflow: waiting for go/running/finished/error/unknown.
- Last command result.

Localization pose panel:

- `x`, `y`, `z`.
- `ox`, `oy`, `oz`, `ow`.
- Pose source: relocation success or periodic pose log.
- Pose age/update time.
- Localization state: locating/localized/no recent pose.

Recent logs panel:

- Tail of the latest navigation bridge log and workflow log.
- Include enough lines for diagnosis without overwhelming the customer.
- Keep ANSI color escape sequences stripped from the API response.

## Backend API

### `POST /api/login`

Request:

```json
{"password":"123"}
```

Response on success:

```json
{"ok":true}
```

Implementation can use a simple signed session cookie for the first version.

### `GET /api/status`

Returns summarized system state:

```json
{
  "ok": true,
  "map_path": "/home/unitree/test9.pcd",
  "main_loop": "running",
  "nav_bridge": {
    "ready": true,
    "port": 28180
  },
  "workflow": {
    "run_id": "20260605_163426",
    "status": "running",
    "exit_code": null,
    "finished_at": null
  },
  "pose": {
    "available": true,
    "x": -0.3913,
    "y": 16.9003,
    "z": -0.0693,
    "ox": 0.1253,
    "oy": 0.0844,
    "oz": 0.7378,
    "ow": 0.6579,
    "source": "pose_log",
    "updated_at": "2026-06-09T10:00:00+08:00"
  }
}
```

### `POST /api/command`

Request:

```json
{"command":"go"}
```

or:

```json
{"command":"back"}
```

Reject every other value.

Response:

```json
{"ok":true,"command":"go","message":"已发送命令：go"}
```

### `GET /api/logs?target=nav&lines=120`

Supported targets:

- `nav`: latest `logs/nav_workflow_control/nav_bridge_*.log`.
- `workflow`: latest `logs/nav_workflow_control/rabbitbot_workflow_*.log` or latest available workflow log under `logs/unified_runtime` if needed.

Response:

```json
{
  "ok": true,
  "target": "nav",
  "path": "/mnt/ssd/navgation/projects/rabbitbot-dev-ros2-master/logs/nav_workflow_control/nav_bridge_20260605_163322.log",
  "lines": ["..."]
}
```

## Status Detection

Main loop state can be detected by looking for the command loop process or by checking whether recent nav workflow control files/logs are being updated. Prefer process detection for immediate state and logs for detail.

Navigation bridge readiness:

- Check `127.0.0.1:28180` from the Orin.
- If open, report ready.
- If closed, report not ready.

Workflow status:

- Inspect latest files under:

```text
logs/nav_workflow_control/workflow_control/
```

- Choose the newest run ID with `.status`, `.pid`, `.ready`, `.exit_code`, or `.finished_at` files.
- Read `.status` where present. Expected values include `running` and `finished`.
- Presence of `.ready` while status is running indicates the workflow is pre-started and waiting at the go gate.

## Pose Parsing

Parse the newest navigation bridge log:

```text
logs/nav_workflow_control/nav_bridge_*.log
```

Recognize relocation success blocks:

```text
[Auto-Relocation] Success! Current pose:
x: -0.3913  y: 16.9003  z: -0.0693
ox: 0.1253  oy: 0.0844  oz: 0.7378  ow: 0.6579
```

Recognize periodic pose lines:

```text
[Pose] x: -0.3913  y: 16.9003  z: -0.0693  ox: 0.1253  oy: 0.0844  oz: 0.7378  ow: 0.6579
```

Use the latest valid pose. Strip ANSI escape sequences before parsing.

If no pose is found, return `available: false` with a clear status message such as `暂无定位位姿数据`.

## Error Handling

- If the user is not logged in, API returns HTTP 401.
- If `28180` is not ready, page shows navigation bridge offline and disables `开始任务` unless command sending is still intentionally allowed.
- If the command script returns non-zero, show the error message and keep the page usable.
- If logs are missing, show `暂无日志` instead of failing the whole status request.
- If pose parsing fails, return other status fields normally and mark pose unavailable.

## Service Management

The web console should have its own systemd service, separate from the navigation workflow loop service.

Example service intent:

```ini
[Service]
WorkingDirectory=/mnt/ssd/navgation/projects/rabbitbot-dev-ros2-master
Environment=RABBITBOT_CONSOLE_PASSWORD=123
Environment=NAV_PCD_PATH=/home/unitree/test9.pcd
ExecStart=/usr/bin/python3 -m rabbitbot_control_console
Restart=always
```

The exact module path can be finalized during implementation.

The navigation workflow loop should have its own boot service with:

```ini
Environment=NAV_PCD_PATH=/home/unitree/test9.pcd
ExecStart=/bin/bash /mnt/ssd/navgation/projects/rabbitbot-dev-ros2-master/scripts_1/start_nav_bridge_workflow_loop.sh
Restart=always
```

## Testing And Acceptance Criteria

Manual acceptance:

1. Start the navigation workflow loop with `NAV_PCD_PATH=/home/unitree/test9.pcd`.
2. Open `http://<orin-ip>:8080` from another LAN device.
3. Login with password `123`.
4. Confirm the page shows map path `/home/unitree/test9.pcd`.
5. Confirm the page shows navigation bridge readiness for port `28180`.
6. Confirm the localization pose panel updates from the latest `[Pose]` log output.
7. Click `开始任务`; verify `send_nav_workflow_command.sh go` is executed and the workflow starts.
8. Click `返航`; verify `send_nav_workflow_command.sh back` is executed and the return sequence starts or is queued appropriately.
9. Confirm `quit/exit` is not available in the UI or API.
10. Move the Orin to another LAN, use the new Orin IP with port `8080`, and verify the page still opens.

Automated checks where practical:

- Unit test command whitelist rejects anything except `go` and `back`.
- Unit test pose parser against relocation success blocks and periodic `[Pose]` lines.
- Unit test latest workflow status selection from sample `.status`, `.ready`, `.exit_code`, and `.finished_at` files.
- API test unauthenticated requests return 401.
- API test authenticated command calls invoke only the command wrapper with expected arguments.

## Out Of Scope For First Version

- Customer-facing restart/stop service buttons.
- Arbitrary terminal access.
- Multi-user roles.
- Internet/cloud access.
- Map upload or map switching UI.
- Full maintenance dashboard.
