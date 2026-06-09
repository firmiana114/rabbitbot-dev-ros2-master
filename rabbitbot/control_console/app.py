from __future__ import annotations

from pathlib import Path
import secrets

from fastapi import Cookie, Depends, FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .commands import CommandError, send_workflow_command
from .config import ConsoleConfig
from .status import (
    detect_main_loop_running,
    get_latest_workflow_status,
    get_tail_lines,
    is_port_open,
    latest_file,
    parse_latest_pose,
)


SESSION_COOKIE = "rabbitbot_console_session"


class LoginRequest(BaseModel):
    password: str


class CommandRequest(BaseModel):
    command: str


def _html() -> str:
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>RabbitBot 控制台</title>
  <style>
    :root{font-family:Arial,'Noto Sans SC',sans-serif;color:#172033;background:#eef2f6}body{margin:0}.wrap{max-width:1180px;margin:0 auto;padding:20px}.top{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:16px}.panel{background:white;border:1px solid #d7dde8;border-radius:8px;padding:16px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.card{background:#f7f9fc;border-radius:6px;padding:12px}.label{font-size:12px;color:#667085;text-transform:uppercase}.value{font-size:18px;font-weight:700;margin-top:4px}.actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:16px}button{border:0;border-radius:6px;color:white;padding:11px 16px;font-size:15px;cursor:pointer}button:disabled{opacity:.45;cursor:not-allowed}.go{background:#137333}.back{background:#b3261e}.refresh{background:#334155}.login{max-width:360px;margin:12vh auto}.input{width:100%;box-sizing:border-box;padding:11px;border:1px solid #cbd5e1;border-radius:6px;margin:10px 0 12px}.log{font-family:ui-monospace,Menlo,monospace;background:#111827;color:#d1d5db;border-radius:6px;padding:12px;line-height:1.5;font-size:12px;min-height:220px;overflow:auto}.error{color:#b3261e}.ok{color:#137333}.pose-line{white-space:pre-line}@media(max-width:820px){.grid,.cards{grid-template-columns:1fr}.top{align-items:flex-start;flex-direction:column}}</style>
</head>
<body>
  <div class="wrap">
    <form id="loginForm" class="panel login">
      <h2>RabbitBot 控制台</h2>
      <div class="label">请输入访问密码</div>
      <input id="password" class="input" type="password" autocomplete="current-password" placeholder="密码">
      <button class="refresh" type="submit">登录</button>
      <p id="loginError" class="error"></p>
    </form>
    <div id="app" style="display:none">
      <div class="top">
        <div><h2>RabbitBot 控制台</h2><div id="map" class="label">地图：-</div></div>
        <div id="overall" class="value">读取中</div>
      </div>
      <div class="grid">
        <section class="panel">
          <div class="cards">
            <div class="card"><div class="label">主循环</div><div id="mainLoop" class="value">-</div></div>
            <div class="card"><div class="label">导航桥接</div><div id="navBridge" class="value">-</div></div>
            <div class="card"><div class="label">Workflow</div><div id="workflow" class="value">-</div></div>
          </div>
          <div class="actions">
            <button id="goBtn" class="go" onclick="sendCommand('go')">开始任务</button>
            <button class="back" onclick="sendCommand('back')">返航</button>
            <button class="refresh" onclick="refresh()">刷新状态</button>
          </div>
          <p id="message"></p>
        </section>
        <section class="panel">
          <div class="label">定位位姿</div>
          <div id="pose" class="value pose-line">暂无定位位姿数据</div>
        </section>
      </div>
      <section class="panel" style="margin-top:16px">
        <div class="label">最近日志</div>
        <pre id="logs" class="log">读取中...</pre>
      </section>
    </div>
  </div>
<script>
async function submitLogin(event){
  if(event){event.preventDefault();}
  const password=document.getElementById('password').value;
  const res=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password})});
  if(!res.ok){document.getElementById('loginError').textContent='密码错误';return;}
  document.getElementById('loginForm').style.display='none';
  document.getElementById('app').style.display='block';
  refresh();
}
function setText(id,text){document.getElementById(id).textContent=text;}
async function refresh(){
  const res=await fetch('/api/status');
  if(res.status===401){document.getElementById('loginForm').style.display='block';document.getElementById('app').style.display='none';return;}
  const data=await res.json();
  setText('map','地图：'+data.map_path);
  setText('overall',data.nav_bridge.ready?'在线':'导航未就绪');
  setText('mainLoop',data.main_loop);
  setText('navBridge',data.nav_bridge.ready?'28180 就绪':'未就绪');
  setText('workflow',data.workflow.status || 'unknown');
  document.getElementById('goBtn').disabled=!data.nav_bridge.ready;
  if(data.pose && data.pose.available){setText('pose',`x ${data.pose.x} / y ${data.pose.y} / z ${data.pose.z}\nox ${data.pose.ox} / oy ${data.pose.oy} / oz ${data.pose.oz} / ow ${data.pose.ow}`);}else{setText('pose',(data.pose&&data.pose.message)||'暂无定位位姿数据');}
  const logs=await fetch('/api/logs?target=nav&lines=120');
  if(logs.ok){const body=await logs.json();setText('logs',body.lines.join('\n') || '暂无日志');}
}
async function sendCommand(command){
  const res=await fetch('/api/command',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({command})});
  const body=await res.json();
  setText('message',res.ok?body.message:body.detail);
  refresh();
}
setInterval(()=>{if(document.getElementById('app').style.display!=='none')refresh();},2000);
document.getElementById('loginForm').addEventListener('submit', submitLogin);
</script>
</body>
</html>"""


def create_app(config: ConsoleConfig | None = None) -> FastAPI:
    config = config or ConsoleConfig.from_env()
    app = FastAPI(title="RabbitBot Control Console")
    session_token = secrets.token_urlsafe(32)

    def require_auth(rabbitbot_console_session: str | None = Cookie(default=None)) -> None:
        if rabbitbot_console_session != session_token:
            raise HTTPException(status_code=401, detail="未登录")

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        return HTMLResponse(_html(), headers={"Cache-Control": "no-store"})

    @app.post("/api/login")
    def login(payload: LoginRequest, response: Response) -> dict:
        if payload.password != config.password:
            raise HTTPException(status_code=401, detail="密码错误")
        response.set_cookie(SESSION_COOKIE, session_token, httponly=True, samesite="lax")
        return {"ok": True}

    @app.get("/api/status")
    def status(_: None = Depends(require_auth)) -> dict:
        nav_log = latest_file(config.nav_log_dir, "nav_bridge_*.log")
        pose = parse_latest_pose(nav_log) if nav_log else parse_latest_pose(Path("/missing-nav-log"))
        workflow = get_latest_workflow_status(config.workflow_control_dir)
        return {
            "ok": True,
            "map_path": config.map_path,
            "main_loop": detect_main_loop_running(),
            "nav_bridge": {"ready": is_port_open("127.0.0.1", config.nav_port), "port": config.nav_port},
            "workflow": workflow.to_dict(),
            "pose": pose.to_dict(),
        }

    @app.post("/api/command")
    def command(payload: CommandRequest, _: None = Depends(require_auth)) -> dict:
        try:
            return send_workflow_command(payload.command, config.command_script)
        except CommandError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/logs")
    def logs(target: str = "nav", lines: int = 120, _: None = Depends(require_auth)) -> dict:
        bounded_lines = max(1, min(lines, 400))
        if target == "nav":
            path = latest_file(config.nav_log_dir, "nav_bridge_*.log")
        elif target == "workflow":
            path = latest_file(config.workflow_log_dir, "rabbitbot_workflow_*.log")
        else:
            raise HTTPException(status_code=400, detail="不支持的日志目标")
        return {
            "ok": True,
            "target": target,
            "path": str(path) if path else None,
            "lines": get_tail_lines(path, bounded_lines) if path else [],
        }

    return app


app = create_app()
