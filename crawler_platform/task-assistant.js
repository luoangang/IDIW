let assistantSources=[],assistantHistory=[],assistantPlan=null,assistantApproval=null;
let assistantBusy=false,assistantConfigured=false,assistantSourceEditing=null,assistantCreating=false;
const assistantModes={keyword:'关键词检索',feed:'RSS 订阅匹配',identifier:'编号查询',site:'全站采集',unknown:'未登记'};
const assistantPost=(path,body)=>api(`/api/v1/assistant/${path}`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)});

function renderAssistantChat(pending=''){
  const container=$('assistantMessages');container.replaceChildren();
  for(const message of [...assistantHistory,...(pending?[{role:'user',content:pending}]:[])]){
    const row=document.createElement('div');row.className=`assistant-message ${message.role}`;
    const name=document.createElement('strong');name.textContent=message.role==='user'?'你':'DeepSeek';
    const content=document.createElement('p');content.textContent=message.content;row.append(name,content);container.appendChild(row);
  }
  if(!container.childElementCount){const empty=document.createElement('div');empty.className='empty';empty.textContent='新对话';container.appendChild(empty)}
  container.scrollTop=container.scrollHeight;
}

function assistantScheduleControls(){
  const mode=$('assistantSchedule').value,scheduled=mode==='daily'||mode==='weekly';
  $('assistantTimeLabel').hidden=!scheduled;$('assistantTime').required=scheduled;
  $('assistantWeekdayLabel').hidden=mode!=='weekly';$('assistantWeekday').required=mode==='weekly';
}

function renderAssistantSources(){
  const selected=new Map((Array.isArray(assistantPlan?.packages)?assistantPlan.packages:[]).filter(row=>row&&typeof row.package_key==='string').map(row=>[row.package_key,row]));
  const selectedWeight=source=>selected.has(source.package_key)&&selected.get(source.package_key).enabled!==false?1:0;
  const ordered=[...assistantSources].sort((a,b)=>selectedWeight(b)-selectedWeight(a));
  $('assistantSourceRows').innerHTML=ordered.map(source=>{
    const setting=selected.get(source.package_key),enabled=source.supported&&Boolean(setting&&setting.enabled!==false);
    return `<tr data-assistant-source="${escapeHtml(source.package_key)}"><td><input type="checkbox" class="assistant-source-enabled" aria-label="启用${escapeHtml(source.name)}" ${enabled?'checked':''} ${source.supported?'':'disabled'}></td><td><div class="source-name">${escapeHtml(source.name)}</div><div class="source-meta">${escapeHtml(assistantModes[source.profile.mode]||source.profile.mode)}</div></td><td><input type="number" class="assistant-source-limit" min="1" max="10000" step="1" value="${escapeHtml(Number.isInteger(setting?.item_limit)?setting.item_limit:100)}" aria-label="${escapeHtml(source.name)}单次上限" ${enabled?'':'disabled'}></td><td><button type="button" class="secondary" data-assistant-parameters="${escapeHtml(source.package_key)}" ${enabled?'':'disabled'}>参数</button></td></tr>`;
  }).join('')||'<tr><td colspan="4" class="empty">没有可用采集来源</td></tr>';
}

function readAssistantDraft(){
  if(!assistantPlan)return null;
  const selected=new Map((Array.isArray(assistantPlan.packages)?assistantPlan.packages:[]).filter(row=>row&&typeof row.package_key==='string').map(row=>[row.package_key,row]));
  const packages=[...$('assistantSourceRows').querySelectorAll('tr[data-assistant-source]')].filter(row=>row.querySelector('.assistant-source-enabled').checked).map(row=>({
    package_key:row.dataset.assistantSource,enabled:true,item_limit:Number(row.querySelector('.assistant-source-limit').value),
    config:selected.get(row.dataset.assistantSource)?.config||{},
  })).sort((a,b)=>a.package_key.localeCompare(b.package_key));
  const mode=$('assistantSchedule').value;
  return {name:$('assistantName').value,query:$('assistantQuery').value,aliases:$('assistantAliases').value.split('\n').map(value=>value.trim()).filter(Boolean),
    schedule_type:mode||null,schedule_time:mode==='manual'?null:$('assistantTime').value||null,
    weekday:mode==='weekly'?Number($('assistantWeekday').value)||null:null,timezone:'Asia/Shanghai',packages};
}

function applyAssistantDraft(draft){
  assistantPlan=structuredClone(draft);$('assistantDraftForm').hidden=false;$('assistantDraftEmpty').hidden=true;
  $('assistantName').value=typeof draft.name==='string'?draft.name:'';$('assistantQuery').value=typeof draft.query==='string'?draft.query:'';
  $('assistantAliases').value=Array.isArray(draft.aliases)?draft.aliases.filter(term=>typeof term==='string').join('\n'):'';
  $('assistantSchedule').value=['manual','daily','weekly'].includes(draft.schedule_type)?draft.schedule_type:'';
  $('assistantTime').value=typeof draft.schedule_time==='string'?draft.schedule_time:'';
  $('assistantWeekday').value=String(draft.weekday||'');assistantScheduleControls();renderAssistantSources();
}

function invalidateAssistantDraft(){
  assistantApproval=null;$('assistantCreate').disabled=true;$('assistantDraftState').textContent='待检查';
  $('assistantReview').textContent='配置待检查';
}

function showAssistantPreview(preview){
  assistantApproval=preview.ready?preview:null;
  $('assistantCreate').disabled=!preview.ready;$('assistantDraftState').textContent=preview.ready?'已检查':'待完善';
  const review=$('assistantReview');review.replaceChildren();
  for(const [kind,rows] of [['error',preview.errors||[]],['warning',preview.warnings||[]]]){
    const list=document.createElement('ul');list.className=kind==='error'?'error-message':'warning';
    for(const text of rows){const item=document.createElement('li');item.textContent=text;list.appendChild(item)}
    if(rows.length)review.appendChild(list);
  }
  if(preview.ready){const next=document.createElement('div');next.className='assistant-next';next.textContent=preview.next_run_at?`下一次执行：${formatTime(preview.next_run_at)}（北京时间）`:'手动执行，不会自动启动采集';review.appendChild(next)}
}

async function loadTaskAssistant(){
  const value=await api('/api/v1/assistant/catalog');
  if(assistantPlan)assistantPlan=readAssistantDraft();
  assistantSources=value.sources;assistantConfigured=value.configured;
  $('assistantModelStatus').textContent=value.configured?`DeepSeek · ${value.model}`:'DeepSeek 尚未配置 API Key';
  $('assistantSend').disabled=!assistantConfigured||assistantBusy;
  if(assistantPlan){renderAssistantSources();invalidateAssistantDraft()}
}

function setAssistantBusy(busy){
  assistantBusy=busy;$('assistantSend').disabled=busy||!assistantConfigured;$('assistantInput').disabled=busy;
  $('assistantReset').disabled=busy;$('assistantDraftForm').inert=busy;
}

function initTaskAssistant(){
  renderAssistantChat();
  $('assistantReset').addEventListener('click',()=>{
    if(assistantBusy||assistantCreating)return;
    if((assistantHistory.length||assistantPlan)&&!confirm('清空当前对话和未创建的草案？'))return;
    assistantHistory=[];assistantPlan=null;assistantApproval=null;$('assistantInput').value='';$('assistantChatStatus').textContent='';
    $('assistantDraftForm').hidden=true;$('assistantDraftEmpty').hidden=false;$('assistantDraftState').textContent='';renderAssistantChat();
  });
  $('assistantChatForm').addEventListener('submit',async event=>{
    event.preventDefault();if(assistantBusy)return;const text=$('assistantInput').value.trim();if(!text)return;
    if(assistantHistory.length>=20){$('assistantChatStatus').textContent='对话已达上限，请开始新对话';return}
    const draft=readAssistantDraft();if(assistantPlan)invalidateAssistantDraft();setAssistantBusy(true);
    $('assistantChatStatus').textContent='正在整理需求…';renderAssistantChat(text);
    try{
      const value=await assistantPost('chat',{messages:[...assistantHistory,{role:'user',content:text}],draft});
      assistantHistory.push({role:'user',content:text},{role:'assistant',content:value.reply});$('assistantInput').value='';
      if(value.draft!==null){applyAssistantDraft(value.preview?.draft||value.draft);if(value.preview)showAssistantPreview(value.preview)}
      $('assistantChatStatus').textContent='';renderAssistantChat();
    }catch(error){$('assistantChatStatus').textContent=error.message;renderAssistantChat()}
    finally{setAssistantBusy(false)}
  });
  $('assistantDraftForm').addEventListener('input',invalidateAssistantDraft);
  $('assistantDraftForm').addEventListener('change',event=>{
    invalidateAssistantDraft();if(event.target.id==='assistantSchedule')assistantScheduleControls();
    if(event.target.classList.contains('assistant-source-enabled')){
      const row=event.target.closest('tr');row.querySelector('.assistant-source-limit').disabled=!event.target.checked;
      row.querySelector('[data-assistant-parameters]').disabled=!event.target.checked;
    }
  });
  $('assistantDraftForm').addEventListener('submit',async event=>{
    event.preventDefault();if(assistantBusy)return;setAssistantBusy(true);$('assistantCheck').disabled=true;
    try{const preview=await assistantPost('preview',{draft:readAssistantDraft()});if(preview.ready)applyAssistantDraft(preview.draft);showAssistantPreview(preview)}
    catch(error){invalidateAssistantDraft();$('assistantReview').textContent=error.message}
    finally{$('assistantCheck').disabled=false;setAssistantBusy(false)}
  });
  $('assistantSourceRows').addEventListener('click',event=>{
    const button=event.target.closest('[data-assistant-parameters]');if(!button)return;
    assistantPlan=readAssistantDraft();const key=button.dataset.assistantParameters,source=assistantSources.find(row=>row.package_key===key);
    const setting=assistantPlan.packages.find(row=>row.package_key===key);if(!source||!setting)return;
    const properties=source.parameters_schema.properties||{},saved={...source.config,...setting.config};
    assistantSourceEditing={...source,config:Object.fromEntries(Object.entries(saved).filter(([key])=>Object.hasOwn(properties,key)))};
    $('assistantSourceTitle').textContent=`${source.name} · 任务参数`;$('assistantSourceNotice').textContent=source.profile.notes;
    const container=$('assistantSourceParameters');container.replaceChildren();
    Object.entries(properties).forEach(([key,schema])=>container.appendChild(parameterControl(assistantSourceEditing,key,schema)));
    if(!Object.keys(properties).length)container.textContent='无额外参数';$('assistantSourceDialog').showModal();
  });
  $('assistantSourceCancel').addEventListener('click',()=>$('assistantSourceDialog').close());
  $('assistantSourceForm').addEventListener('submit',event=>{
    event.preventDefault();if(!assistantSourceEditing)return;
    try{const config=collectParameters($('assistantSourceParameters'),assistantSourceEditing);assistantPlan.packages.find(row=>row.package_key===assistantSourceEditing.package_key).config=config;
      invalidateAssistantDraft();$('assistantSourceDialog').close()}
    catch(error){$('assistantSourceNotice').textContent=error.message}
  });
  $('assistantCreate').addEventListener('click',()=>{
    if(!assistantApproval||!$('assistantDraftForm').reportValidity())return;
    const draft=readAssistantDraft();const mode=draft.schedule_type==='manual'?'手动':`${draft.schedule_type==='weekly'?'每周'+['','一','二','三','四','五','六','日'][draft.weekday]:'每天'} ${draft.schedule_time}（北京时间）`;
    const sources=draft.packages.map(setting=>`${assistantSources.find(row=>row.package_key===setting.package_key)?.name||setting.package_key}：上限 ${setting.item_limit}`).join('\n');
    $('assistantConfirmSummary').textContent=`任务名称：${draft.name}\n关键词：${draft.query}\n别名：${draft.aliases.join('、')||'无'}\n执行计划：${mode}\n\n${sources}`;
    $('assistantConfirmNotice').textContent='';$('assistantConfirmDialog').showModal();
  });
  $('assistantConfirmCancel').addEventListener('click',()=>$('assistantConfirmDialog').close());
  $('assistantConfirmDialog').addEventListener('cancel',event=>{if(assistantCreating)event.preventDefault()});
  $('assistantConfirmSave').addEventListener('click',async()=>{
    if(!assistantApproval||assistantCreating)return;assistantCreating=true;$('assistantConfirmSave').disabled=true;$('assistantConfirmCancel').disabled=true;
    try{const value=await assistantPost('monitors',{draft:readAssistantDraft(),confirmation_token:assistantApproval.confirmation_token,confirmed:true});
      $('assistantConfirmDialog').close();invalidateAssistantDraft();$('assistantDraftState').textContent='已创建';
      const review=$('assistantReview');review.replaceChildren();const link=document.createElement('a');link.href=`/monitors/${value.id}/sources`;link.dataset.nav='';link.textContent=`任务 #${value.id} 已创建 · 查看来源设置`;review.appendChild(link);
      assistantHistory.push({role:'user',content:'确认创建当前草案'},{role:'assistant',content:`任务 #${value.id} 已创建，将按已确认计划执行。`});renderAssistantChat();
    }catch(error){$('assistantConfirmNotice').textContent=error.message}
    finally{assistantCreating=false;$('assistantConfirmSave').disabled=false;$('assistantConfirmCancel').disabled=false}
  });
}
