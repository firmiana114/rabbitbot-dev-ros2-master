from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
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
    :root{font-family:Arial,'Noto Sans SC',sans-serif;color:#172033;background:#eef2f6}body{margin:0}.wrap{max-width:1180px;margin:0 auto;padding:20px}.top{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:16px}.panel{background:white;border:1px solid #d7dde8;border-radius:8px;padding:16px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.card{background:#f7f9fc;border-radius:6px;padding:12px}.label{font-size:12px;color:#667085;text-transform:uppercase}.value{font-size:18px;font-weight:700;margin-top:4px}.actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:16px}.field{margin-top:16px}.text-input,.dialogue-editor,.hot-input{width:100%;box-sizing:border-box;padding:10px 11px;border:1px solid #cbd5e1;border-radius:6px;font-size:14px;color:#172033;background:#fff}.dialogue-editor{font-family:ui-monospace,Menlo,monospace;min-height:420px;line-height:1.45;resize:vertical}.hot-table{width:100%;border-collapse:collapse;margin-top:12px}.hot-table th,.hot-table td{border-top:1px solid #e2e8f0;padding:10px;text-align:left;vertical-align:top}.hot-table th{font-size:12px;color:#667085}.hot-name{min-height:44px}.hot-coordinate{font-family:ui-monospace,Menlo,monospace;min-height:84px;resize:vertical}.hot-script{min-height:84px;resize:vertical}.icon-btn{min-width:44px;padding:10px 12px}button{border:0;border-radius:6px;color:white;padding:11px 16px;font-size:15px;cursor:pointer}button:disabled{opacity:.45;cursor:not-allowed}.go{background:#137333}.task{background:#0f766e}.placeholder{background:#64748b}.back{background:#b3261e}.refresh{background:#334155}.restart{background:#7c2d12}.log{font-family:ui-monospace,Menlo,monospace;background:#111827;color:#d1d5db;border-radius:6px;padding:12px;line-height:1.5;font-size:12px;min-height:220px;overflow:auto}.error{color:#b3261e}.ok{color:#137333}.pose-line{white-space:pre-line}@media(max-width:820px){.grid,.cards{grid-template-columns:1fr}.top{align-items:flex-start;flex-direction:column}.hot-table,.hot-table thead,.hot-table tbody,.hot-table tr,.hot-table th,.hot-table td{display:block}.hot-table th{display:none}.hot-table td{padding:8px 0}}</style>
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
            <div class="card"><div class="label">开机自启动</div><div id="autostart" class="value">-</div></div>
          </div>
          <div class="label" style="margin-top:16px">开始任务</div>
          <div class="actions">
            <button id="guideBtn" class="go" onclick="startTask('guide')">导览</button>
          </div>
          <div class="actions">
            <button class="back" onclick="sendCommand('back')">返航</button>
            <button id="restartBtn" class="restart" onclick="restartProgram()">一键重启</button>
            <button id="stopBtn" class="back" onclick="stopProgram()">关闭程序</button>
            <button id="autostartBtn" class="refresh" onclick="toggleAutostart()">开机自启动</button>
          </div>
          <div class="field">
            <div class="label">重启地图</div>
            <input id="mapPathInput" class="text-input" type="text" value="/home/unitree/test9.pcd" oninput="mapPathTouched=true">
          </div>
          <p id="message"></p>
        </section>
        <section class="panel">
          <div class="label">定位状态</div>
          <div id="poseStatus" class="value">读取中</div>
          <div class="label" style="margin-top:12px">当前位姿</div>
          <div id="pose" class="value pose-line">暂无定位位姿数据</div>
        </section>
      </div>
      <section class="panel" style="margin-top:16px">
        <div class="top" style="margin-bottom:10px">
          <div>
            <div class="label">领导称呼</div>
            <div id="leaderCallingSummary" class="label">未加载</div>
          </div>
          <div class="actions" style="margin-top:0">
            <button id="leaderCallingLoadBtn" class="refresh" onclick="loadLeaderCalling()">加载领导称呼</button>
            <button id="leaderCallingSaveBtn" class="go" onclick="saveLeaderCalling()" disabled>保存领导称呼</button>
          </div>
        </div>
        <input id="leaderCallingInput" class="text-input" type="text" maxlength="80" placeholder="例如：各位领导" oninput="updateLeaderCallingState()" onkeydown="leaderCallingKeydown(event)">
        <p id="leaderCallingMessage"></p>
      </section>
      <section class="panel" style="margin-top:16px">
        <div class="top" style="margin-bottom:10px">
          <div class="label">点位台词热更新</div>
          <div class="actions" style="margin-top:0">
            <button id="hotRowsLoadBtn" class="refresh" onclick="loadHotRows()">加载点位台词</button>
            <button id="hotRowsAddBtn" class="refresh icon-btn" onclick="addHotRow()">+</button>
            <button id="hotRowsSaveBtn" class="go" onclick="saveHotRows()">保存点位台词</button>
          </div>
        </div>
        <div id="hotRowsSummary" class="label">未加载</div>
        <table id="hotRowsTable" class="hot-table">
          <thead><tr><th style="width:16%">点位名字</th><th style="width:30%">点位坐标</th><th>讲解台词</th><th style="width:80px">操作</th></tr></thead>
          <tbody id="hotRowsBody"></tbody>
        </table>
        <p id="hotRowsMessage"></p>
      </section>
      <section class="panel" style="margin-top:16px">
        <div class="top" style="margin-bottom:10px">
          <div class="label">导览讲解词</div>
          <div class="actions" style="margin-top:0">
            <button id="dialogueLoadBtn" class="refresh" onclick="loadDialogue()">加载讲解词</button>
            <button id="dialogueToggleBtn" class="refresh" onclick="toggleDialogueEditor()" disabled>折叠讲解词</button>
            <button id="dialogueSaveBtn" class="go" onclick="saveDialogue()" disabled>保存讲解词</button>
          </div>
        </div>
        <div id="dialogueSummary" class="label">未加载</div>
        <textarea id="dialogueEditor" class="dialogue-editor" hidden></textarea>
        <p id="dialogueMessage"></p>
      </section>
      <section class="panel" style="margin-top:16px">
        <div class="top" style="margin-bottom:10px">
          <div class="label">最近日志</div>
          <button id="logsToggleBtn" class="refresh" onclick="toggleLogs()">显示日志</button>
        </div>
        <pre id="logs" class="log" hidden></pre>
      </section>
    </div>
  </div>
<script>
var logsVisible=false;
var mapPathTouched=false;
var dialogueLoaded=false;
var dialogueCollapsed=false;
var hotRowSequence=0;
var leaderCallingLoaded=false;
var leaderCallingOriginal='';
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
    if(logsVisible){refreshLogs();}
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
        if(logsVisible){refreshLogs();}
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
function refreshLogs(){
  if(!logsVisible){return;}
  requestJson('GET','/api/logs?target=nav&lines=120',null,function(logError,body){
    if(logError){setText('logs',logError.message);return;}
    setText('logs',(body.lines&&body.lines.join(String.fromCharCode(10)))||'暂无日志');
  });
}
function toggleLogs(){
  logsVisible=!logsVisible;
  document.getElementById('logs').hidden=!logsVisible;
  setText('logsToggleBtn',logsVisible?'关闭日志':'显示日志');
  if(logsVisible){
    setText('logs','读取中...');
    refreshLogs();
  }else{
    setText('logs','');
  }
}
function dialogueSummaryText(summary){
  if(!summary){return '未加载';}
  return '文件：'+summary.path+' / 称呼：'+(summary.leader_calling||'-')+' / 地图：'+(summary.map_file||'-')+' / 步骤：'+summary.steps+' / 台词段：'+summary.segments+' / 点位：'+summary.points;
}
function updateDialogueFoldState(){
  document.getElementById('dialogueEditor').hidden=dialogueCollapsed;
  document.getElementById('dialogueSaveBtn').disabled=!dialogueLoaded||dialogueCollapsed;
  document.getElementById('dialogueToggleBtn').disabled=!dialogueLoaded;
  setText('dialogueToggleBtn',dialogueCollapsed?'展开讲解词':'折叠讲解词');
}
function renderDialogue(body){
  dialogueLoaded=true;
  dialogueCollapsed=false;
  document.getElementById('dialogueEditor').value=body.content||'';
  updateDialogueFoldState();
  setText('dialogueSummary',dialogueSummaryText(body.summary));
  setText('dialogueMessage',body.message||'');
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
    if(dialogueLoaded){loadDialogue();}
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
    if(dialogueLoaded){loadDialogue();}
  });
}
function toggleDialogueEditor(){
  if(!dialogueLoaded){return;}
  dialogueCollapsed=!dialogueCollapsed;
  updateDialogueFoldState();
}
function loadDialogue(){
  document.getElementById('dialogueLoadBtn').disabled=true;
  setText('dialogueMessage','正在加载讲解词...');
  requestJson('GET','/api/dialogue',null,function(error,body){
    document.getElementById('dialogueLoadBtn').disabled=false;
    if(error){setText('dialogueMessage',error.message);return;}
    renderDialogue(body);
  });
}
function saveDialogue(){
  if(!window.confirm('确定保存导览讲解词吗？保存后需要一键重启生效。')){return;}
  var button=document.getElementById('dialogueSaveBtn');
  button.disabled=true;
  setText('dialogueMessage','正在保存讲解词...');
  requestJson('POST','/api/dialogue',{content:document.getElementById('dialogueEditor').value},function(error,body){
    button.disabled=false;
    if(error){setText('dialogueMessage',error.message);return;}
    renderDialogue(body);
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
