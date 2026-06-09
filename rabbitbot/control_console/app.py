from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .commands import CommandError, restart_loop_service, send_workflow_command
from .config import ConsoleConfig
from .status import (
    detect_main_loop_running,
    get_latest_workflow_status,
    get_tail_lines,
    is_port_open,
    latest_file,
    parse_latest_pose,
)


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
    :root{font-family:Arial,'Noto Sans SC',sans-serif;color:#172033;background:#eef2f6}body{margin:0}.wrap{max-width:1180px;margin:0 auto;padding:20px}.top{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:16px}.panel{background:white;border:1px solid #d7dde8;border-radius:8px;padding:16px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.card{background:#f7f9fc;border-radius:6px;padding:12px}.label{font-size:12px;color:#667085;text-transform:uppercase}.value{font-size:18px;font-weight:700;margin-top:4px}.actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:16px}button{border:0;border-radius:6px;color:white;padding:11px 16px;font-size:15px;cursor:pointer}button:disabled{opacity:.45;cursor:not-allowed}.go{background:#137333}.back{background:#b3261e}.refresh{background:#334155}.restart{background:#7c2d12}.log{font-family:ui-monospace,Menlo,monospace;background:#111827;color:#d1d5db;border-radius:6px;padding:12px;line-height:1.5;font-size:12px;min-height:220px;overflow:auto}.error{color:#b3261e}.ok{color:#137333}.pose-line{white-space:pre-line}@media(max-width:820px){.grid,.cards{grid-template-columns:1fr}.top{align-items:flex-start;flex-direction:column}}</style>
</head>
<body>
  <div class="wrap">
    <div id="app">
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
            <button id="restartBtn" class="restart" onclick="restartProgram()">一键重启</button>
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
function setText(id,text){document.getElementById(id).textContent=text;}
function requestJson(method,url,payload,callback){
  var xhr=new XMLHttpRequest();
  xhr.open(method,url,true);
  xhr.setRequestHeader('Accept','application/json');
  if(payload){xhr.setRequestHeader('Content-Type','application/json');}
  xhr.onreadystatechange=function(){
    if(xhr.readyState!==4){return;}
    var body={};
    try{body=xhr.responseText?JSON.parse(xhr.responseText):{};}catch(error){callback(new Error('响应解析失败'));return;}
    if(xhr.status<200||xhr.status>=300){callback(new Error(body.detail||body.message||('请求失败：'+xhr.status)),body);return;}
    callback(null,body);
  };
  xhr.onerror=function(){callback(new Error('网络请求失败，请检查网页地址和局域网连接'));};
  xhr.send(payload?JSON.stringify(payload):null);
}
function showError(message){
  setText('overall','读取失败');
  setText('message',message);
}
function refresh(){
  requestJson('GET','/api/status',null,function(error,data){
    if(error){showError(error.message);return;}
    setText('map','地图：'+data.map_path);
    setText('overall',data.nav_bridge.ready?'在线':'导航未就绪');
    setText('mainLoop',data.main_loop);
    setText('navBridge',data.nav_bridge.ready?'28180 就绪':'未就绪');
    setText('workflow',data.workflow.status||'unknown');
    document.getElementById('goBtn').disabled=!data.nav_bridge.ready;
    if(data.pose&&data.pose.available){
      var newline=String.fromCharCode(10);
      setText('pose','x '+data.pose.x+' / y '+data.pose.y+' / z '+data.pose.z+newline+'ox '+data.pose.ox+' / oy '+data.pose.oy+' / oz '+data.pose.oz+' / ow '+data.pose.ow);
    }else{
      setText('pose',(data.pose&&data.pose.message)||'暂无定位位姿数据');
    }
    requestJson('GET','/api/logs?target=nav&lines=120',null,function(logError,body){
      if(logError){setText('logs',logError.message);return;}
      setText('logs',(body.lines&&body.lines.join(String.fromCharCode(10)))||'暂无日志');
    });
  });
}
function sendCommand(command){
  requestJson('POST','/api/command',{command:command},function(error,body){
    setText('message',error?error.message:body.message);
    refresh();
  });
}
function restartProgram(){
  if(!window.confirm('确定重新启动导航主程序吗？')){return;}
  var button=document.getElementById('restartBtn');
  button.disabled=true;
  setText('overall','重启中');
  setText('message','正在重新启动导航主程序...');
  requestJson('POST','/api/restart',{},function(error,body){
    setText('message',error?error.message:body.message);
    setTimeout(function(){button.disabled=false;refresh();},3000);
  });
}
refresh();
setInterval(refresh,2000);
</script>
</body>
</html>"""


def create_app(config: ConsoleConfig | None = None) -> FastAPI:
    config = config or ConsoleConfig.from_env()
    app = FastAPI(title="RabbitBot Control Console")

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        return HTMLResponse(_html(), headers={"Cache-Control": "no-store"})

    @app.get("/api/status")
    def status() -> dict:
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
    def command(payload: CommandRequest) -> dict:
        try:
            return send_workflow_command(payload.command, config.command_script)
        except CommandError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


    @app.post("/api/restart")
    def restart() -> dict:
        try:
            return restart_loop_service(
                config.loop_service_name,
                systemctl_path=config.systemctl_path,
                sudo_path=config.sudo_path,
            )
        except CommandError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/logs")
    def logs(target: str = "nav", lines: int = 120) -> dict:
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
