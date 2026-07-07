from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .commands import (
    CommandError,
    loop_service_autostart_enabled,
    read_map_path,
    restart_loop_service,
    send_workflow_command,
    set_loop_service_autostart,
    start_loop_service,
    start_task,
    stop_loop_service,
)
from .config import ConsoleConfig
from .dialogue import (
    DialogueError,
    read_dialogue_leader_calling,
    read_dialogue_editor,
    read_dialogue_hot_rows,
    resolve_dialogue_path,
    write_dialogue_config,
    write_dialogue_leader_calling,
    write_dialogue_hot_rows,
)
from .status import (
    detect_main_loop_running,
    get_latest_workflow_status,
    get_tail_lines,
    read_guide_state,
    is_port_open,
    latest_file,
    parse_latest_pose,
)


class CommandRequest(BaseModel):
    command: str


class TaskRequest(BaseModel):
    task: str


class RestartRequest(BaseModel):
    map_path: str | None = None


class DialogueRequest(BaseModel):
    content: str


class LeaderCallingRequest(BaseModel):
    leader_calling: str


class DialogueHotRowsRequest(BaseModel):
    rows: list[dict]


class AutostartRequest(BaseModel):
    enabled: bool


def _html() -> str:
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>RabbitBot 控制台</title>
  <style>
    :root{font-family:Arial,'Noto Sans SC',sans-serif;color:#182235;background:#f3f6fb}*{box-sizing:border-box}body{margin:0}.shell{min-height:100vh;display:grid;grid-template-columns:clamp(180px,13vw,220px) minmax(0,1fr)}.sidebar{background:#061a33;color:#eaf2ff;padding:22px 14px;display:flex;flex-direction:column;gap:18px;min-width:0}.brand{font-size:24px;font-weight:800;letter-spacing:.2px;padding:0 10px 14px}.nav{display:grid;gap:8px}.nav-item{border-radius:8px;padding:12px 14px;color:#c8d7ed;font-weight:700}.nav-item.active{background:#1261d8;color:#fff}.sidebar-spacer{flex:1}.main{min-width:0;overflow:hidden}.topbar{min-height:72px;background:#fff;border-bottom:1px solid #d9e1ee;display:flex;align-items:center;justify-content:space-between;gap:16px;padding:12px 22px}.title{font-size:22px;font-weight:800}.top-status{display:grid;grid-template-columns:repeat(4,minmax(110px,1fr));gap:10px;align-items:stretch;max-width:min(760px,58vw);width:100%}.status-pill{display:grid;gap:3px;min-width:0;padding:8px 12px;border-left:1px solid #dbe3ef}.status-pill strong{font-size:14px}.status-pill span{font-size:12px;color:#667085;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.content{padding:16px;min-width:0}.page[hidden]{display:none}.page-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px;align-items:stretch}.subpage{width:min(100%,1180px)}.stack{display:grid;gap:16px;min-width:0}.panel{background:white;border:1px solid #dbe3ef;border-radius:8px;padding:16px;box-shadow:0 6px 20px rgba(20,38,70,.05);min-width:0}.panel-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:12px}.panel-title{font-size:16px;font-weight:800}.panel-link{color:#1261d8;font-size:13px;font-weight:700}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}.card{background:#f8fafd;border:1px solid #e2e8f0;border-radius:8px;padding:14px;min-height:72px}.label{font-size:12px;color:#667085;font-weight:700}.value{font-size:19px;font-weight:800;margin-top:6px;color:#182235}.actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px}.primary-actions{display:grid;grid-template-columns:repeat(2,minmax(120px,1fr));gap:10px}.secondary-actions{display:grid;grid-template-columns:repeat(3,minmax(120px,1fr));gap:10px}.field{margin-top:14px}.text-input,.dialogue-editor,.hot-input{width:100%;padding:10px 11px;border:1px solid #cbd5e1;border-radius:7px;font-size:14px;color:#172033;background:#fff}.dialogue-editor{font-family:ui-monospace,Menlo,monospace;min-height:360px;line-height:1.45;resize:vertical}.hot-wrap{overflow-x:auto;max-width:100%}.hot-table{width:100%;border-collapse:collapse;margin-top:12px;min-width:min(780px,calc(100vw - 260px))}.hot-table th,.hot-table td{border-top:1px solid #e2e8f0;padding:10px;text-align:left;vertical-align:top}.hot-table th{font-size:12px;color:#667085}.hot-name{min-height:42px}.hot-coordinate{font-family:ui-monospace,Menlo,monospace;min-height:76px;resize:vertical}.hot-script{min-height:76px;resize:vertical}.icon-btn{min-width:46px;padding:10px 12px}button{border:0;border-radius:7px;color:white;padding:11px 15px;font-size:15px;font-weight:800;cursor:pointer;white-space:nowrap}button:disabled{opacity:.45;cursor:not-allowed}.sidebar .nav-item{border:0;border-radius:8px;background:transparent;color:#c8d7ed;padding:12px 14px;font-size:15px;font-weight:800;text-align:left;cursor:pointer;overflow:hidden;text-overflow:ellipsis}.sidebar .nav-item.active{background:#1261d8;color:#fff}.overview-card{width:100%;display:block;text-align:left;background:white;color:#182235;border:1px solid #dbe3ef;border-radius:8px;padding:18px;box-shadow:0 6px 20px rgba(20,38,70,.05);min-height:118px}.overview-card strong{display:block;font-size:17px;margin-bottom:8px}.overview-card span{display:block;color:#667085;font-size:13px;line-height:1.45;white-space:normal}.go{background:#137333}.task{background:#0f766e}.placeholder{background:#64748b}.back{background:#b3261e}.refresh{background:#334155}.restart{background:#7c2d12}.log{font-family:ui-monospace,Menlo,monospace;background:#111827;color:#d1d5db;border-radius:8px;padding:12px;line-height:1.5;font-size:12px;min-height:220px;overflow:auto}.error{color:#b3261e}.ok{color:#137333}.pose-line{white-space:pre-line}.wide{grid-column:span 2}.full{grid-column:1/-1}@media(max-width:1180px){.topbar{align-items:flex-start;flex-direction:column}.top-status{max-width:none}.wide{grid-column:1/-1}.secondary-actions{grid-template-columns:repeat(auto-fit,minmax(150px,1fr))}}@media(max-width:820px){.shell{grid-template-columns:1fr}.sidebar{position:static;display:block;padding:14px}.brand{padding-bottom:8px}.nav{grid-template-columns:repeat(auto-fit,minmax(120px,1fr))}.sidebar-spacer{display:none}.topbar{padding:16px}.top-status{grid-template-columns:repeat(2,minmax(0,1fr))}.content{padding:12px}.page-grid,.grid,.cards,.primary-actions,.secondary-actions{grid-template-columns:1fr}.panel-head{align-items:flex-start;flex-direction:column}.hot-table{min-width:640px}}@media(max-width:520px){.top-status{grid-template-columns:1fr}.hot-table,.hot-table thead,.hot-table tbody,.hot-table tr,.hot-table th,.hot-table td{display:block;min-width:0}.hot-table th{display:none}.hot-table td{padding:8px 0}}</style>
  <style>
    .control-page{width:100%;max-width:none}.control-deck{position:relative;overflow:hidden;min-height:calc(100vh - 104px);padding:22px;border:1px solid #1e5f95;border-radius:16px;color:#e9f7ff;background:#06121f}.control-deck:before{content:"";position:absolute;inset:0;background:linear-gradient(90deg,rgba(29,161,242,.07) 1px,transparent 1px),linear-gradient(rgba(29,161,242,.07) 1px,transparent 1px);background-size:46px 46px;pointer-events:none}.control-deck:after{content:"";position:absolute;inset:0;background:radial-gradient(circle at 50% 45%,rgba(0,154,255,.22),transparent 34%),linear-gradient(180deg,rgba(9,37,65,.3),rgba(2,8,16,.85));pointer-events:none}.control-deck>*{position:relative;z-index:1}.control-titlebar{display:grid;grid-template-columns:1fr 220px;align-items:center;gap:16px;margin-bottom:18px}.tech-status{border:1px solid #2d7cba;background:rgba(7,28,49,.78);color:#a9c9e8;border-radius:12px;padding:11px 14px;text-align:right}.control-title{text-align:center;font-size:30px;font-weight:900;letter-spacing:3px;text-shadow:0 0 18px rgba(42,183,255,.8)}.dev-badge{display:inline-flex;align-items:center;margin-left:8px;padding:3px 8px;border:1px solid rgba(255,205,86,.65);border-radius:999px;color:#ffd666;background:rgba(95,70,12,.4);font-size:12px;font-weight:900;letter-spacing:0}.control-layout{display:grid;grid-template-columns:minmax(240px,.72fr) minmax(320px,1.2fr) minmax(260px,.88fr);gap:16px;align-items:stretch}.tech-stack{display:grid;gap:14px}.tech-card{border:1px solid rgba(61,151,218,.75);border-radius:12px;background:rgba(4,22,39,.78);box-shadow:inset 0 1px 0 rgba(124,206,255,.22),0 12px 36px rgba(0,0,0,.28);overflow:hidden}.tech-card h3{margin:0;padding:13px 16px;background:linear-gradient(90deg,rgba(25,87,145,.68),rgba(3,18,34,.2));font-size:17px;color:#cfeeff}.tech-body{padding:16px}.metric-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.metric-number{font-size:31px;font-weight:900;color:#fff}.battery{height:36px;border:2px solid #b5f4ff;border-radius:6px;padding:3px;margin-top:8px}.battery span{display:block;height:100%;border-radius:3px;background:linear-gradient(90deg,#19d777,#57f5a6);box-shadow:0 0 18px rgba(39,242,146,.7)}.status-dot{display:inline-block;width:12px;height:12px;border-radius:50%;background:#24e07b;box-shadow:0 0 15px #24e07b;margin-right:8px}.joint-list{display:grid;gap:9px}.joint-list div{display:flex;justify-content:space-between;color:#a9c9e8}.joint-list strong{color:#4dff92}.robot-stage{min-height:520px;border:1px solid rgba(33,128,201,.5);border-radius:16px;background:radial-gradient(circle at center bottom,rgba(0,150,255,.3),transparent 30%),rgba(2,12,24,.45);display:grid;place-items:center;position:relative}.robot-stage:before{content:"";position:absolute;left:14%;right:14%;bottom:42px;height:22px;border:2px solid rgba(55,183,255,.55);border-radius:50%;box-shadow:0 0 32px rgba(55,183,255,.55)}.dev-overlay{position:absolute;top:18px;right:18px;padding:6px 12px;border:1px solid rgba(255,205,86,.65);border-radius:999px;color:#ffd666;background:rgba(16,20,28,.78);font-size:13px;font-weight:900;z-index:2}.robot-photo{position:relative;z-index:1;max-width:min(76%,430px);max-height:88%;object-fit:contain;filter:drop-shadow(0 0 28px rgba(40,183,255,.6));border-radius:12px}.task-info{display:grid;grid-template-columns:110px 1fr;gap:13px;color:#a9c9e8}.task-info strong{color:#e9f7ff}.progress-rail{height:10px;border-radius:99px;background:#0c2741;overflow:hidden}.progress-rail span{display:block;width:45%;height:100%;background:linear-gradient(90deg,#189dff,#1ee6ff);box-shadow:0 0 14px rgba(30,230,255,.9)}.map-grid{height:132px;border:1px solid rgba(67,157,220,.45);border-radius:10px;background:linear-gradient(90deg,rgba(44,151,235,.18) 1px,transparent 1px),linear-gradient(rgba(44,151,235,.18) 1px,transparent 1px);background-size:24px 24px;position:relative}.map-grid:before{content:"X-01";position:absolute;left:28%;top:52%;color:#e9f7ff}.map-grid:after{content:"";position:absolute;left:34%;right:18%;top:56%;border-top:3px dashed #1bbdff}.pin{position:absolute;right:14%;top:43%;width:18px;height:18px;border-radius:50%;background:#2ce07c;box-shadow:0 0 18px #2ce07c}.voice-wave{height:58px;background:repeating-linear-gradient(90deg,transparent 0 10px,#12caff 10px 12px,transparent 12px 18px);mask:linear-gradient(180deg,transparent 0,#000 30%,#000 70%,transparent 100%);opacity:.9}.motion-console{margin-top:16px;border:1px solid rgba(61,151,218,.75);border-radius:14px;background:rgba(5,20,37,.86);padding:18px}.motion-title{font-size:18px;font-weight:900;margin-bottom:12px}.motion-actions{display:grid;grid-template-columns:repeat(5,minmax(118px,1fr));gap:12px}.motion-actions button{min-height:64px;border:1px solid rgba(102,190,255,.55);background:rgba(17,55,89,.86);box-shadow:inset 0 0 18px rgba(24,143,255,.18)}.motion-actions .go{background:linear-gradient(180deg,#079456,#0b6842)}.motion-actions .back{background:linear-gradient(180deg,#7b1f1b,#4d1110)}.motion-actions .restart{background:linear-gradient(180deg,#0b5d98,#08385f)}.motion-actions .refresh{background:linear-gradient(180deg,#1b4a78,#102b49)}.motion-field{display:grid;grid-template-columns:minmax(240px,1fr) minmax(220px,.7fr);gap:14px;align-items:end;margin-top:14px}.motion-field .text-input{background:#061b30;border-color:#2a76ad;color:#e9f7ff}.control-message{min-height:42px;margin:0;padding:10px 12px;border:1px solid rgba(61,151,218,.4);border-radius:8px;color:#a9c9e8;background:rgba(2,10,18,.52)}@media(max-width:1180px){.control-titlebar,.control-layout,.motion-field{grid-template-columns:1fr}.tech-status{text-align:left}.motion-actions{grid-template-columns:repeat(auto-fit,minmax(140px,1fr))}.robot-stage{min-height:420px}}@media(max-width:620px){.control-deck{padding:14px}.control-title{font-size:22px}.metric-grid,.task-info{grid-template-columns:1fr}.robot-stage{min-height:360px}.robot-photo{max-width:86%}} 
  </style>
</head>
<body>
  <div id="app" class="shell">
    <aside class="sidebar">
      <div class="brand">RabbitBot</div>
      <nav class="nav">
        <button class="nav-item active" type="button" data-page="control" onclick="showPage('control')">任务控制</button>
        <button class="nav-item" type="button" data-page="status" onclick="showPage('status')">机器人状态</button>
        <button class="nav-item" type="button" data-page="dialogue" onclick="showPage('dialogue')">点位台词</button>
        <button class="nav-item" type="button" data-page="models" onclick="showPage('models')">模型服务</button>
      </nav>
      <div class="sidebar-spacer"></div>
    </aside>
    <main class="main">
      <header class="topbar">
        <div>
          <div class="title">RabbitBot 控制台</div>
          <div id="map" class="label">地图：-</div>
        </div>
        <div class="top-status">
          <div class="status-pill"><strong>控制台</strong><span id="overall">读取中</span></div>
          <div class="status-pill"><strong>主循环</strong><span id="mainLoop">-</span></div>
          <div class="status-pill"><strong>导航桥接</strong><span id="navBridge">-</span></div>
          <div class="status-pill"><strong>当前模式</strong><span id="workflow">-</span></div>
        </div>
      </header>
      <div class="content">
        <section id="page-control" class="page subpage control-page">
          <div class="control-deck">
            <div class="control-titlebar">
              <div class="control-title">双足机器人导览系统</div>
              <div class="tech-status">网络正常&nbsp;&nbsp;电量 92% <span class="dev-badge">开发中</span></div>
            </div>
            <div class="control-layout">
              <div class="tech-stack">
                <section class="tech-card">
                  <h3>机器人状态 <span class="dev-badge">开发中</span></h3>
                  <div class="tech-body">
                    <div class="metric-grid">
                      <div>
                        <div class="label">电量</div>
                        <div class="metric-number">92%</div>
                        <div class="battery"><span></span></div>
                      </div>
                      <div>
                        <div class="label">运行状态</div>
                        <div class="value"><span class="status-dot"></span>空闲</div>
                        <div class="label" style="margin-top:14px">当前模式</div>
                        <div class="value">自主导览</div>
                      </div>
                    </div>
                  </div>
                </section>
                <section class="tech-card">
                  <h3>运动状态 <span class="dev-badge">开发中</span></h3>
                  <div class="tech-body joint-list">
                    <div><span>头部</span><strong>正常</strong></div>
                    <div><span>躯干</span><strong>正常</strong></div>
                    <div><span>左臂</span><strong>正常</strong></div>
                    <div><span>右臂</span><strong>正常</strong></div>
                    <div><span>左腿</span><strong>正常</strong></div>
                    <div><span>右腿</span><strong>正常</strong></div>
                  </div>
                </section>
              </div>
              <section class="robot-stage">
                <span class="dev-overlay">开发中</span>
                <img class="robot-photo" src="/static/control_console/unitree-g1-dashboard.png" alt="宇树 G1 机器人展示图">
              </section>
              <div class="tech-stack">
                <section class="tech-card">
                  <h3>任务信息 <span class="dev-badge">开发中</span></h3>
                  <div class="tech-body task-info">
                    <span>当前任务</span><strong>展厅导览</strong>
                    <span>任务进度</span><div class="progress-rail"><span></span></div>
                    <span>当前站点</span><strong>等待开始</strong>
                    <span>下一站点</span><strong>按台词配置执行</strong>
                    <span>预计状态</span><strong>等待指令</strong>
                  </div>
                </section>
                <section class="tech-card">
                  <h3>导航地图 <span class="dev-badge">开发中</span></h3>
                  <div class="tech-body">
                    <div class="map-grid"><span class="pin"></span></div>
                  </div>
                </section>
                <section class="tech-card">
                  <h3>语音交互 <span class="dev-badge">开发中</span></h3>
                  <div class="tech-body">
                    <div class="value ok">正在聆听...</div>
                    <div class="voice-wave"></div>
                  </div>
                </section>
              </div>
            </div>
            <section class="motion-console">
              <div class="motion-title">开始任务 / 运动控制</div>
              <div class="motion-actions">
                <button id="guideBtn" class="go" onclick="startTask('guide')">导览</button>
                <button class="back" onclick="sendCommand('back')">返航</button>
                <button id="restartBtn" class="restart" onclick="restartProgram()">一键重启</button>
                <button id="stopBtn" class="back" onclick="stopProgram()">关闭程序</button>
                <button id="autostartBtn" class="refresh" onclick="toggleAutostart()">开机自启动</button>
              </div>
              <div class="motion-field">
                <div>
                  <div class="label">重启地图</div>
                  <input id="mapPathInput" class="text-input" type="text" value="/home/unitree/test9.pcd" oninput="mapPathTouched=true">
                </div>
                <p id="message" class="control-message"></p>
              </div>
            </section>
          </div>
        </section>
        <section id="page-status" class="page subpage" hidden>
          <div class="stack">
            <section class="panel">
            <div class="panel-head">
              <div class="panel-title">机器人状态</div>
              <div class="panel-link">自动刷新</div>
            </div>
            <div class="cards">
              <div class="card"><div class="label">开机自启动</div><div id="autostart" class="value">-</div></div>
              <div class="card"><div class="label">定位状态</div><div id="poseStatus" class="value">读取中</div></div>
            </div>
            <div class="field">
              <div class="label">当前位姿</div>
              <div id="pose" class="value pose-line">暂无定位位姿数据</div>
            </div>
          </section>
          </div>
        </section>
        <section id="page-dialogue" class="page subpage" hidden>
          <div class="stack">
            <section class="panel">
              <div class="panel-head">
                <div>
                  <div class="panel-title">领导称呼</div>
                  <div id="leaderCallingSummary" class="label">未加载</div>
                </div>
              </div>
              <input id="leaderCallingInput" class="text-input" type="text" maxlength="80" placeholder="例如：各位领导" oninput="updateLeaderCallingState()" onkeydown="leaderCallingKeydown(event)">
              <div class="actions">
                <button id="leaderCallingLoadBtn" class="refresh" onclick="loadLeaderCalling()">加载领导称呼</button>
                <button id="leaderCallingSaveBtn" class="go" onclick="saveLeaderCalling()" disabled>保存领导称呼</button>
              </div>
              <p id="leaderCallingMessage"></p>
            </section>
            <section class="panel">
            <div class="panel-head">
              <div>
                <div class="panel-title">点位台词热更新</div>
                <div id="hotRowsSummary" class="label">未加载</div>
              </div>
              <div class="actions" style="margin-top:0">
                <button id="hotRowsLoadBtn" class="refresh" onclick="loadHotRows()">加载点位台词</button>
                <button id="hotRowsAddBtn" class="refresh icon-btn" onclick="addHotRow()">+</button>
                <button id="hotRowsSaveBtn" class="go" onclick="saveHotRows()">保存点位台词</button>
              </div>
            </div>
            <div class="hot-wrap">
              <table id="hotRowsTable" class="hot-table">
                <thead><tr><th style="width:16%">点位名字</th><th style="width:30%">点位坐标</th><th>讲解台词</th><th style="width:80px">操作</th></tr></thead>
                <tbody id="hotRowsBody"></tbody>
              </table>
            </div>
            <p id="hotRowsMessage"></p>
          </section>
          </div>
        </section>
        <section id="page-models" class="page subpage" hidden>
          <div class="stack">
            <section class="panel">
            <div class="panel-head">
              <div class="panel-title">模型服务</div>
              <div class="panel-link">运行中</div>
            </div>
            <div class="grid">
              <div class="card"><div class="label">VLM</div><div class="value ok">健康</div></div>
              <div class="card"><div class="label">ASR</div><div class="value ok">健康</div></div>
              <div class="card"><div class="label">TTS</div><div class="value ok">健康</div></div>
              <div class="card"><div class="label">Planner</div><div class="value ok">健康</div></div>
            </div>
          </section>
          </div>
        </section>
      </div>
    </main>
  </div>
<script>
var mapPathTouched=false;
var hotRowSequence=0;
var leaderCallingLoaded=false;
var leaderCallingOriginal='';
function setText(id,text){document.getElementById(id).textContent=text;}
function showPage(page){
  var pages=document.querySelectorAll('.page');
  for(var i=0;i<pages.length;i++){pages[i].hidden=true;}
  var target=document.getElementById('page-'+page)||document.getElementById('page-control');
  target.hidden=false;
  var navItems=document.querySelectorAll('[data-page]');
  for(var j=0;j<navItems.length;j++){navItems[j].classList.toggle('active',navItems[j].getAttribute('data-page')===page);}
}
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
function guideStateValue(data){return data&&data.guide_state&&data.guide_state.state?data.guide_state.state:'unknown';}
function guideStateLabel(state){
  var labels={
    starting:'启动中',
    guide_preparing:'导览预启动中',
    qa_listening:'QA 待命，可开始导览',
    guide_running:'导览中',
    guide_finished_waiting_back:'导览完成，等待返航',
    returning:'返航中',
    guide_prepare_failed:'导览预启动失败',
    qa_disabled:'QA 模式关闭',
    unknown:'状态未知'
  };
  return labels[state]||state||'状态未知';
}
function canStartGuide(data){
  return data&&data.nav_bridge&&data.nav_bridge.ready&&guideStateValue(data)==='qa_listening';
}
function servicesReady(data){
  return data&&data.main_loop==='running'&&data.nav_bridge&&data.nav_bridge.ready&&data.guide_state&&data.guide_state.state==='qa_listening';
}
function autostartLabel(enabled){return enabled?'已启用':'未启用';}
function renderStatus(data){
  var guideState=guideStateValue(data);
  setText('map','地图：'+data.map_path);
  if(!mapPathTouched&&data.map_path){document.getElementById('mapPathInput').value=data.map_path;}
  setText('overall',servicesReady(data)?'全部就绪':(data.nav_bridge.ready?guideStateLabel(guideState):'导航未就绪'));
  setText('mainLoop',data.main_loop);
  setText('navBridge',data.nav_bridge.ready?'28180 就绪':'未就绪');
  setText('workflow',guideStateLabel(guideState));
  setText('autostart',autostartLabel(!!(data.autostart&&data.autostart.enabled)));
  setText('autostartBtn',!!(data.autostart&&data.autostart.enabled)?'关闭开机自启动':'启用开机自启动');
  document.getElementById('guideBtn').disabled=!canStartGuide(data);
  setText('poseStatus',(data.pose&&data.pose.status_message)||(data.pose&&data.pose.localized?'定位成功':'定位未成功：程序会持续重定位，需要遥控机器人的位姿，帮助机器人完成定位'));
  if(data.pose&&data.pose.available){
    var newline=String.fromCharCode(10);
    setText('pose','x '+data.pose.x+' / y '+data.pose.y+' / z '+data.pose.z+newline+'ox '+data.pose.ox+' / oy '+data.pose.oy+' / oz '+data.pose.oz+' / ow '+data.pose.ow);
  }else{
    setText('pose',(data.pose&&data.pose.message)||'暂无定位位姿数据');
  }
}
function refresh(){
  requestJson('GET','/api/status',null,function(error,data){
    if(error){showError(error.message);return;}
    renderStatus(data);
  });
}
function waitForServicesReady(button,startedAt){
  requestJson('GET','/api/status',null,function(error,data){
    if(error){
      setText('message','正在等待服务就绪：'+error.message);
    }else{
      renderStatus(data);
      if(servicesReady(data)){
        setText('message','所有服务已加载成功，可执行相关操作');
        button.disabled=false;
        return;
      }
      setText('message','正在等待所有服务加载完成...');
    }
    if(Date.now()-startedAt>90000){
      setText('message','服务仍未全部就绪，请查看状态或打开日志排查');
      button.disabled=false;
      return;
    }
    setTimeout(function(){waitForServicesReady(button,startedAt);},2000);
  });
}
function updateLeaderCallingState(){
  var input=document.getElementById('leaderCallingInput');
  var value=input.value.trim();
  document.getElementById('leaderCallingSaveBtn').disabled=!leaderCallingLoaded||!value||value===leaderCallingOriginal;
}
function leaderCallingKeydown(event){
  if(event.key==='Enter'&&!document.getElementById('leaderCallingSaveBtn').disabled){saveLeaderCalling();}
}
function renderLeaderCalling(body){
  leaderCallingLoaded=true;
  leaderCallingOriginal=(body.leader_calling||'').trim();
  document.getElementById('leaderCallingInput').value=leaderCallingOriginal;
  setText('leaderCallingSummary','文件：'+((body.summary&&body.summary.path)||body.path||'-')+' / 当前称呼会替换台词里的 {leader_calling}');
  setText('leaderCallingMessage',body.message||'');
  updateLeaderCallingState();
}
function loadLeaderCalling(){
  var button=document.getElementById('leaderCallingLoadBtn');
  button.disabled=true;
  setText('leaderCallingMessage','正在加载领导称呼...');
  requestJson('GET','/api/dialogue/leader-calling',null,function(error,body){
    button.disabled=false;
    if(error){setText('leaderCallingMessage',error.message);return;}
    renderLeaderCalling(body);
  });
}
function saveLeaderCalling(){
  var input=document.getElementById('leaderCallingInput');
  var value=input.value.trim();
  if(!value){setText('leaderCallingMessage','领导称呼不能为空');updateLeaderCallingState();return;}
  var button=document.getElementById('leaderCallingSaveBtn');
  button.disabled=true;
  setText('leaderCallingMessage','正在保存领导称呼...');
  requestJson('POST','/api/dialogue/leader-calling',{leader_calling:value},function(error,body){
    if(error){setText('leaderCallingMessage',error.message);updateLeaderCallingState();return;}
    renderLeaderCalling(body);
  });
}
function hotRowsSummaryText(summary,rowCount){
  if(!summary){return '未加载';}
  return '文件：'+summary.path+' / 表格行：'+rowCount+' / 总步骤：'+summary.steps+' / 总点位：'+summary.points;
}
function updateHotCoordinateState(tr){
  var nameInput=tr.querySelector('.hot-name');
  var coordinateInput=tr.querySelector('.hot-coordinate');
  var isOpening=(nameInput.value||'').trim().toLowerCase()==='opening'||tr.getAttribute('data-row-type')==='opening';
  coordinateInput.disabled=isOpening;
  if(isOpening){coordinateInput.value='';coordinateInput.placeholder='opening 无需点位坐标';}
  else{coordinateInput.placeholder='{"x":0,"y":0,"z":0,"ox":0,"oy":0,"oz":0,"ow":1,"mode":1}';}
}
function addHotRow(row){
  row=row||{};
  hotRowSequence+=1;
  var tbody=document.getElementById('hotRowsBody');
  var tr=document.createElement('tr');
  tr.setAttribute('data-row-id',row.id||'');
  tr.setAttribute('data-row-type',row.row_type||'step');
  tr.setAttribute('data-point-key',row.point_key||'');
  if(row.step_index!==undefined&&row.step_index!==null){tr.setAttribute('data-step-index',row.step_index);}
  var nameTd=document.createElement('td');
  var nameInput=document.createElement('input');
  nameInput.className='hot-input hot-name';
  nameInput.type='text';
  nameInput.value=row.point_name||'';
  nameInput.oninput=function(){updateHotCoordinateState(tr);};
  nameTd.appendChild(nameInput);
  var coordinateTd=document.createElement('td');
  var coordinateInput=document.createElement('textarea');
  coordinateInput.className='hot-input hot-coordinate';
  coordinateInput.placeholder='{"x":0,"y":0,"z":0,"ox":0,"oy":0,"oz":0,"ow":1,"mode":1}';
  coordinateInput.value=row.coordinate||'';
  coordinateTd.appendChild(coordinateInput);
  var scriptTd=document.createElement('td');
  var scriptInput=document.createElement('textarea');
  scriptInput.className='hot-input hot-script';
  scriptInput.value=row.script||'';
  scriptTd.appendChild(scriptInput);
  var actionTd=document.createElement('td');
  var removeBtn=document.createElement('button');
  removeBtn.className='back icon-btn';
  removeBtn.type='button';
  removeBtn.textContent='-';
  removeBtn.onclick=function(){tr.parentNode.removeChild(tr);};
  if((row.row_type||'')==='opening'){removeBtn.disabled=true;}
  actionTd.appendChild(removeBtn);
  tr.appendChild(nameTd);
  tr.appendChild(coordinateTd);
  tr.appendChild(scriptTd);
  tr.appendChild(actionTd);
  tbody.appendChild(tr);
  updateHotCoordinateState(tr);
}
function collectHotRows(){
  var rows=[];
  var trs=document.querySelectorAll('#hotRowsBody tr');
  for(var i=0;i<trs.length;i++){
    rows.push({
      id:trs[i].getAttribute('data-row-id')||'',
      row_type:trs[i].getAttribute('data-row-type')||'step',
      step_index:trs[i].getAttribute('data-step-index')||'',
      point_key:trs[i].getAttribute('data-point-key')||'',
      point_name:trs[i].querySelector('.hot-name').value,
      coordinate:trs[i].querySelector('.hot-coordinate').value,
      script:trs[i].querySelector('.hot-script').value
    });
  }
  return rows;
}
function renderHotRows(body){
  var tbody=document.getElementById('hotRowsBody');
  tbody.innerHTML='';
  var rows=body.rows||[];
  for(var i=0;i<rows.length;i++){addHotRow(rows[i]);}
  if(rows.length===0){addHotRow();}
  setText('hotRowsSummary',hotRowsSummaryText(body.summary,rows.length));
  setText('hotRowsMessage',body.message||'');
}
function loadHotRows(){
  document.getElementById('hotRowsLoadBtn').disabled=true;
  setText('hotRowsMessage','正在加载点位台词...');
  requestJson('GET','/api/dialogue/hot-rows',null,function(error,body){
    document.getElementById('hotRowsLoadBtn').disabled=false;
    if(error){setText('hotRowsMessage',error.message);return;}
    renderHotRows(body);
  });
}
function saveHotRows(){
  var button=document.getElementById('hotRowsSaveBtn');
  button.disabled=true;
  setText('hotRowsMessage','正在保存点位台词...');
  requestJson('POST','/api/dialogue/hot-rows',{rows:collectHotRows()},function(error,body){
    button.disabled=false;
    if(error){setText('hotRowsMessage',error.message);return;}
    renderHotRows(body);
  });
}
function sendCommand(command){
  requestJson('POST','/api/command',{command:command},function(error,body){
    setText('message',error?error.message:body.message);
    refresh();
  });
}
function startTask(task){
  requestJson('POST','/api/task',{task:task},function(error,body){
    setText('message',error?error.message:body.message);
    refresh();
  });
}
function startProgram(){
  var button=document.getElementById('startBtn');
  button.disabled=true;
  setText('overall','启动中');
  setText('message','正在启动导航主程序...');
  requestJson('POST','/api/start',{},function(error,body){
    if(error){setText('message',error.message);button.disabled=false;refresh();return;}
    setText('message',body.message+'，正在等待所有服务加载完成...');
    waitForServicesReady(button,Date.now());
  });
}

function stopProgram(){
  if(!window.confirm('确定关闭导航主程序吗？网页控制台会继续运行。')){return;}
  var button=document.getElementById('stopBtn');
  button.disabled=true;
  setText('overall','关闭中');
  setText('message','正在关闭导航主程序...');
  requestJson('POST','/api/stop',{},function(error,body){
    setText('message',error?error.message:body.message);
    setTimeout(function(){button.disabled=false;refresh();},1500);
  });
}
function toggleAutostart(){
  var button=document.getElementById('autostartBtn');
  var enable=button.textContent.indexOf('启用')===0;
  if(!window.confirm(enable?'确定启用导航主程序开机自启动吗？':'确定关闭导航主程序开机自启动吗？')){return;}
  button.disabled=true;
  setText('message',enable?'正在启用开机自启动...':'正在关闭开机自启动...');
  requestJson('POST','/api/autostart',{enabled:enable},function(error,body){
    button.disabled=false;
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
  var mapPath=document.getElementById('mapPathInput').value;
  requestJson('POST','/api/restart',{map_path:mapPath},function(error,body){
    if(error){setText('message',error.message);button.disabled=false;refresh();return;}
    setText('message',body.message+'，正在等待所有服务加载完成...');
    waitForServicesReady(button,Date.now());
  });
}
loadHotRows();
loadLeaderCalling();
refresh();
setInterval(refresh,2000);
</script>
</body>
</html>"""


def create_app(config: ConsoleConfig | None = None) -> FastAPI:
    config = config or ConsoleConfig.from_env()
    app = FastAPI(title="RabbitBot Control Console")
    static_dir = Path(__file__).with_name("static")
    app.mount("/static/control_console", StaticFiles(directory=static_dir), name="control_console_static")

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        return HTMLResponse(_html(), headers={"Cache-Control": "no-store"})

    @app.get("/api/status")
    def status() -> dict:
        main_loop = detect_main_loop_running()
        current_map_path = read_map_path(config.map_env_file, config.map_path)
        guide_state = read_guide_state(config.guide_state_file)
        autostart_enabled = loop_service_autostart_enabled(
            config.loop_service_name,
            systemctl_path=config.systemctl_path,
            sudo_path=config.sudo_path,
        )
        if main_loop != "running":
            pose = parse_latest_pose(Path("/missing-nav-log"))
            workflow = {"run_id": None, "status": "loop_not_running", "ready": False, "pid": None, "exit_code": None, "finished_at": None}
            return {
                "ok": True,
                "map_path": current_map_path,
                "main_loop": main_loop,
                "nav_bridge": {"ready": False, "port": config.nav_port},
                "workflow": workflow,
                "guide_state": guide_state.to_dict(),
                "autostart": {"enabled": autostart_enabled},
                "pose": pose.to_dict(),
            }

        nav_log = latest_file(config.nav_log_dir, "nav_bridge_*.log")
        pose = parse_latest_pose(nav_log) if nav_log else parse_latest_pose(Path("/missing-nav-log"))
        workflow = get_latest_workflow_status(config.workflow_control_dir)
        return {
            "ok": True,
            "map_path": current_map_path,
            "main_loop": main_loop,
            "nav_bridge": {"ready": is_port_open("127.0.0.1", config.nav_port), "port": config.nav_port},
            "workflow": workflow.to_dict(),
            "guide_state": guide_state.to_dict(),
            "autostart": {"enabled": autostart_enabled},
            "pose": pose.to_dict(),
        }


    @app.post("/api/task")
    def task(payload: TaskRequest) -> dict:
        try:
            return start_task(payload.task, config.command_script)
        except CommandError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/command")
    def command(payload: CommandRequest) -> dict:
        try:
            return send_workflow_command(payload.command, config.command_script)
        except CommandError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc



    @app.post("/api/start")
    def start() -> dict:
        try:
            return start_loop_service(
                config.loop_service_name,
                systemctl_path=config.systemctl_path,
                sudo_path=config.sudo_path,
            )
        except CommandError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/restart")
    def restart(payload: RestartRequest) -> dict:
        try:
            return restart_loop_service(
                config.loop_service_name,
                systemctl_path=config.systemctl_path,
                sudo_path=config.sudo_path,
                map_path=payload.map_path,
                map_env_file=config.map_env_file,
            )
        except CommandError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/stop")
    def stop() -> dict:
        try:
            return stop_loop_service(
                config.loop_service_name,
                systemctl_path=config.systemctl_path,
                sudo_path=config.sudo_path,
            )
        except CommandError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/autostart")
    def set_autostart(payload: AutostartRequest) -> dict:
        try:
            return set_loop_service_autostart(
                payload.enabled,
                config.loop_service_name,
                systemctl_path=config.systemctl_path,
                sudo_path=config.sudo_path,
            )
        except CommandError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/dialogue")
    def get_dialogue() -> dict:
        try:
            path = resolve_dialogue_path(config.dialogue_dir, config.dialogue_index, config.dialogue_file)
            return read_dialogue_editor(path)
        except DialogueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/dialogue")
    def save_dialogue(payload: DialogueRequest) -> dict:
        try:
            path = resolve_dialogue_path(config.dialogue_dir, config.dialogue_index, config.dialogue_file)
            return write_dialogue_config(path, payload.content)
        except DialogueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/dialogue/leader-calling")
    def get_dialogue_leader_calling() -> dict:
        try:
            path = resolve_dialogue_path(config.dialogue_dir, config.dialogue_index, config.dialogue_file)
            return read_dialogue_leader_calling(path)
        except DialogueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/dialogue/leader-calling")
    def save_dialogue_leader_calling(payload: LeaderCallingRequest) -> dict:
        try:
            path = resolve_dialogue_path(config.dialogue_dir, config.dialogue_index, config.dialogue_file)
            return write_dialogue_leader_calling(path, payload.leader_calling)
        except DialogueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/dialogue/hot-rows")
    def get_dialogue_hot_rows() -> dict:
        try:
            path = resolve_dialogue_path(config.dialogue_dir, config.dialogue_index, config.dialogue_file)
            return read_dialogue_hot_rows(path)
        except DialogueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/dialogue/hot-rows")
    def save_dialogue_hot_rows(payload: DialogueHotRowsRequest) -> dict:
        try:
            path = resolve_dialogue_path(config.dialogue_dir, config.dialogue_index, config.dialogue_file)
            return write_dialogue_hot_rows(path, payload.rows)
        except DialogueError as exc:
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
