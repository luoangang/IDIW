let assistantSources=[],assistantHistory=[],assistantPlan=null,assistantApproval=null;
let assistantBusy=false,assistantConfigured=false,assistantSourceEditing=null,assistantCreating=false;
let assistantAliases=[],assistantIcons=null;
const assistantModes={keyword:'关键词检索',feed:'RSS 订阅匹配',identifier:'编号查询',site:'全站采集',unknown:'未登记'};
const assistantHelpBadge=source=>{const help=source&&(source.help||source.description);return help?`<span class="package-help" title="${escapeHtml(help)}">说明</span>`:''};
const assistantDataBadges=source=>{const parts=[];if(source&&source.meta_tag)parts.push(`<span class="package-data meta" title="${escapeHtml(source.meta_help||'')}">${escapeHtml(source.meta_tag)}</span>`);if(source&&source.pdf_tag){const cls=String(source.pdf_tag).includes('链接')?'pdf':'no-pdf';parts.push(`<span class="package-data ${cls}" title="${escapeHtml(source.pdf_help||'')}">${escapeHtml(source.pdf_tag)}</span>`)}return parts.join('')};
async function assistantPost(path,body){
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),75000);
  try{return await api(`/api/v1/assistant/${path}`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body),signal:controller.signal})}
  catch(error){if(error.name==='AbortError')throw new Error(path==='monitors'?'创建请求超时，请先检查监控任务列表，避免重复创建':'请求超时，当前对话和草案已保留，请稍后重试');throw error}
  finally{clearTimeout(timer)}
}

function renderAssistantIcons(root=document){
  if(!assistantIcons)return;
  root.querySelectorAll('[data-assistant-icon]').forEach(node=>{
    const icon=assistantIcons[node.dataset.assistantIcon];
    if(icon)node.replaceChildren(assistantIcons.createElement(icon,{'aria-hidden':'true',focusable:'false'}));
  });
}

function assistantState(text,state='pending'){
  $('assistantDraftState').textContent=text;$('assistantDraftState').dataset.state=state;
}

function renderAssistantAliases(){
  const items=$('assistantAliasItems');items.replaceChildren();
  assistantAliases.forEach((term,index)=>{
    const tag=document.createElement('span');tag.className='assistant-tag';
    const text=document.createElement('span');text.textContent=term;
    const remove=document.createElement('button');remove.type='button';remove.title=`移除 ${term}`;remove.setAttribute('aria-label',remove.title);
    remove.innerHTML='<span class="assistant-icon" data-assistant-icon="x" aria-hidden="true"></span>';
    remove.addEventListener('click',()=>{assistantAliases.splice(index,1);renderAssistantAliases();invalidateAssistantDraft()});
    tag.append(text,remove);items.appendChild(tag);
  });
  renderAssistantIcons(items);
}

function commitAssistantAlias(){
  const input=$('assistantAliasInput'),term=input.value.trim();
  if(!term)return true;
  const duplicate=assistantAliases.some(value=>value.normalize('NFKC').toLocaleLowerCase()===term.normalize('NFKC').toLocaleLowerCase());
  const error=term.length>100?'每项别名最多 100 字':!duplicate&&assistantAliases.length>=30?'检索别名最多 30 项':'';
  input.setCustomValidity(error);$('assistantAliasNotice').textContent=error;
  if(error)return false;
  if(!duplicate)assistantAliases.push(term);
  input.value='';renderAssistantAliases();invalidateAssistantDraft();return true;
}

function renderAssistantChat(pending=''){
  const container=$('assistantMessages');container.replaceChildren();
  for(const message of [...assistantHistory,...(pending?[{role:'user',content:pending}]:[])]){
    const row=document.createElement('div');row.className=`assistant-message ${message.role}`;
    const avatar=document.createElement('span');avatar.className='assistant-avatar';avatar.innerHTML=`<span class="assistant-icon" data-assistant-icon="${message.role==='user'?'user':'bot'}" aria-hidden="true"></span>`;
    const body=document.createElement('div');body.className='assistant-message-body';
    const name=document.createElement('strong');name.textContent=message.role==='user'?'你':'DeepSeek';
    const content=document.createElement('p');content.textContent=message.content;body.append(name,content);row.append(avatar,body);container.appendChild(row);
  }
  if(!container.childElementCount){const empty=document.createElement('div');empty.className='assistant-chat-empty';empty.innerHTML='<span class="assistant-icon" data-assistant-icon="conversation" aria-hidden="true"></span><h3>新对话</h3>';container.appendChild(empty)}
  renderAssistantIcons(container);
  container.scrollTop=container.scrollHeight;
}

function assistantScheduleControls(){
  const mode=$('assistantSchedule').value,scheduled=mode==='daily'||mode==='weekly';
  $('assistantTimeLabel').hidden=!scheduled;$('assistantTime').required=scheduled;
  $('assistantWeekdayLabel').hidden=mode!=='weekly';$('assistantWeekday').required=mode==='weekly';
}

function renderAssistantSources(){
  const selected=new Map((Array.isArray(assistantPlan?.packages)?assistantPlan.packages:[]).filter(row=>row&&typeof row.package_key==='string').map(row=>[row.package_key,row]));
  const ordered=assistantSources.filter(source=>selected.has(source.package_key));
  $('assistantSourceRows').innerHTML=ordered.map(source=>{
    const setting=selected.get(source.package_key),enabled=source.supported&&Boolean(setting&&setting.enabled!==false);
    const chosen=setting?.config?.journal_keys||source.config?.journal_keys,journalCount=Array.isArray(chosen)?` · 已选 ${chosen.length} 本期刊`:'';
    return `<tr data-assistant-source="${escapeHtml(source.package_key)}"><td><input type="checkbox" class="assistant-source-enabled" aria-label="启用${escapeHtml(source.name)}" ${enabled?'checked':''} ${source.supported?'':'disabled'}></td><td><div class="source-name">${escapeHtml(source.name)}${assistantHelpBadge(source)}${assistantDataBadges(source)}</div><div class="source-meta">${escapeHtml(assistantModes[source.profile.mode]||source.profile.mode)}${escapeHtml(journalCount)}</div></td><td><input type="number" class="assistant-source-limit" min="1" max="10000" step="1" value="${escapeHtml(Number.isInteger(setting?.item_limit)?setting.item_limit:100)}" aria-label="${escapeHtml(source.name)}单次上限" ${enabled?'':'disabled'}></td><td><div class="assistant-source-actions"><button type="button" class="assistant-text-button" data-assistant-parameters="${escapeHtml(source.package_key)}" aria-label="${escapeHtml(source.name)}参数" title="调整来源参数" ${enabled?'':'disabled'}><span class="assistant-icon" data-assistant-icon="settings" aria-hidden="true"></span></button><button type="button" class="assistant-text-button danger" data-assistant-remove="${escapeHtml(source.package_key)}" aria-label="移除${escapeHtml(source.name)}" title="移除来源"><span class="assistant-icon" data-assistant-icon="trash" aria-hidden="true"></span></button></div></td></tr>`;
  }).join('')||'<tr><td colspan="4" class="empty">尚未选择来源</td></tr>';
  $('assistantSourceCount').textContent=`已选 ${ordered.length} 个`;
  renderAssistantIcons($('assistantSourceRows'));
}

function renderAssistantSourcePicker(){
  const selected=new Set((assistantPlan?.packages||[]).map(row=>row.package_key));
  const query=$('assistantSourceSearch').value.trim().toLocaleLowerCase();
  const rows=assistantSources.filter(source=>source.supported&&!selected.has(source.package_key)&&[source.name,source.package_key,source.category].join(' ').toLocaleLowerCase().includes(query));
  $('assistantSourcePicker').innerHTML=rows.map(source=>`<div class="assistant-picker-item"><div><div class="source-name">${escapeHtml(source.name)}${assistantHelpBadge(source)}${assistantDataBadges(source)}</div><div class="source-meta">${escapeHtml(assistantModes[source.profile.mode])} · ${escapeHtml(source.profile.languages.join(' / '))}</div></div><button type="button" data-assistant-add="${escapeHtml(source.package_key)}">添加</button></div>`).join('')||'<div class="assistant-picker-empty">没有匹配的可添加来源</div>';
}

function readAssistantDraft(){
  if(!assistantPlan)return null;
  const selected=new Map((Array.isArray(assistantPlan.packages)?assistantPlan.packages:[]).filter(row=>row&&typeof row.package_key==='string').map(row=>[row.package_key,row]));
  const packages=[...$('assistantSourceRows').querySelectorAll('tr[data-assistant-source]')].map(row=>({
    package_key:row.dataset.assistantSource,enabled:row.querySelector('.assistant-source-enabled').checked,item_limit:Number(row.querySelector('.assistant-source-limit').value),
    config:selected.get(row.dataset.assistantSource)?.config||{},
  })).sort((a,b)=>a.package_key.localeCompare(b.package_key));
  const mode=$('assistantSchedule').value;
  return {name:$('assistantName').value,query:$('assistantQuery').value,aliases:[...assistantAliases],journal_scope:$('assistantJournalScope').value,
    schedule_type:mode||null,schedule_time:mode==='manual'?null:$('assistantTime').value||null,
    weekday:mode==='weekly'?Number($('assistantWeekday').value)||null:null,timezone:'Asia/Shanghai',packages};
}

function applyAssistantDraft(draft,highlight=false){
  const previous=assistantPlan?readAssistantDraft():null;
  assistantPlan=structuredClone(draft);$('assistantDraftForm').hidden=false;$('assistantDraftEmpty').hidden=true;
  $('assistantName').value=typeof draft.name==='string'?draft.name:'';$('assistantQuery').value=typeof draft.query==='string'?draft.query:'';
  assistantAliases=Array.isArray(draft.aliases)?draft.aliases.filter(term=>typeof term==='string'):[];renderAssistantAliases();
  $('assistantAliasInput').value='';$('assistantAliasInput').setCustomValidity('');$('assistantAliasNotice').textContent='';
  $('assistantJournalScope').value=draft.journal_scope==='all_chinese'?'all_chinese':'selected';
  $('assistantSchedule').value=['manual','daily','weekly'].includes(draft.schedule_type)?draft.schedule_type:'';
  $('assistantTime').value=typeof draft.schedule_time==='string'?draft.schedule_time:'';
  $('assistantWeekday').value=String(draft.weekday||'');assistantScheduleControls();renderAssistantSources();
  if(highlight){
    for(const [key,id] of Object.entries({name:'assistantName',query:'assistantQuery',aliases:'assistantAliasTags',schedule_type:'assistantSchedule',schedule_time:'assistantTime',weekday:'assistantWeekday',packages:'assistantSourceRows'})){
      if(JSON.stringify(previous?.[key])===JSON.stringify(draft[key]))continue;
      const node=$(id);node.classList.remove('assistant-updated');void node.offsetWidth;node.classList.add('assistant-updated');
    }
  }
}

function invalidateAssistantDraft(){
  assistantApproval=null;$('assistantCreate').disabled=true;assistantState('待检查');
  $('assistantReview').textContent='配置待检查';
  $('assistantCoverage').replaceChildren();
}

function showAssistantPreview(preview){
  assistantApproval=preview.ready?preview:null;
  $('assistantCreate').disabled=!preview.ready;assistantState(preview.ready?'已检查':'待完善',preview.ready?'ready':'pending');
  const coverage=$('assistantCoverage');coverage.replaceChildren();
  if(preview.coverage?.length){
    const list=document.createElement('div');list.className='assistant-coverage';
    const title=document.createElement('strong');title.textContent='期刊覆盖范围';list.appendChild(title);
    for(const source of preview.coverage){const row=document.createElement('div');row.className='assistant-coverage-row';const name=document.createElement('span');name.textContent=source.name;const count=document.createElement('span');count.textContent=`${source.selected} / ${source.total} 本 · 上限 ${source.max_select}`;row.append(name,count);list.appendChild(row)}
    coverage.appendChild(list);
  }
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
  $('assistantSendText').textContent=busy?'处理中':'发送';$('assistantMessages').setAttribute('aria-busy',String(busy));
}

function initTaskAssistant(){
  import('/assets/vendor/lucide/icons.js').then(icons=>{assistantIcons=icons;renderAssistantIcons()}).catch(()=>{});
  renderAssistantChat();
  $('assistantAliasInput').addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.isComposing){event.preventDefault();commitAssistantAlias()}});
  $('assistantAliasInput').addEventListener('input',()=>{$('assistantAliasInput').setCustomValidity('');$('assistantAliasNotice').textContent=''});
  $('assistantAliasInput').addEventListener('blur',commitAssistantAlias);
  $('assistantAddSource').addEventListener('click',()=>{assistantPlan=readAssistantDraft();$('assistantSourceSearch').value='';renderAssistantSourcePicker();$('assistantAddDialog').showModal();$('assistantSourceSearch').focus()});
  $('assistantAddClose').addEventListener('click',()=>$('assistantAddDialog').close());
  $('assistantSourceSearch').addEventListener('input',renderAssistantSourcePicker);
  $('assistantSourcePicker').addEventListener('click',event=>{
    const button=event.target.closest('[data-assistant-add]');if(!button)return;
    const source=assistantSources.find(row=>row.package_key===button.dataset.assistantAdd);
    if(!source?.supported||assistantPlan.packages.some(row=>row.package_key===source.package_key))return;
    assistantPlan.packages.push({package_key:source.package_key,enabled:true,item_limit:100,config:structuredClone(source.config)});
    renderAssistantSources();renderAssistantSourcePicker();invalidateAssistantDraft();
  });
  $('assistantReset').addEventListener('click',()=>{
    if(assistantBusy||assistantCreating)return;
    if((assistantHistory.length||assistantPlan)&&!confirm('清空当前对话和未创建的草案？'))return;
    assistantHistory=[];assistantPlan=null;assistantApproval=null;assistantAliases=[];$('assistantInput').value='';$('assistantChatStatus').textContent='';
    $('assistantDraftForm').hidden=true;$('assistantDraftEmpty').hidden=false;assistantState('尚无草案','empty');renderAssistantChat();
  });
  $('assistantChatForm').addEventListener('submit',async event=>{
    event.preventDefault();if(assistantBusy)return;const text=$('assistantInput').value.trim();if(!text)return;
    if(assistantHistory.length>=20){$('assistantChatStatus').textContent='对话已达上限，请开始新对话';return}
    if(!commitAssistantAlias()){$('assistantAliasInput').reportValidity();return}
    const draft=readAssistantDraft();if(assistantPlan)invalidateAssistantDraft();setAssistantBusy(true);
    $('assistantChatStatus').textContent='正在整理需求…';renderAssistantChat(text);
    try{
      const value=await assistantPost('chat',{messages:[...assistantHistory,{role:'user',content:text}],draft});
      assistantHistory.push({role:'user',content:text},{role:'assistant',content:value.reply});$('assistantInput').value='';
      if(value.draft!==null){applyAssistantDraft(value.preview?.draft||value.draft,true);if(value.preview)showAssistantPreview(value.preview)}
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
    event.preventDefault();if(assistantBusy||!commitAssistantAlias())return;setAssistantBusy(true);$('assistantCheck').disabled=true;
    try{const preview=await assistantPost('preview',{draft:readAssistantDraft()});if(preview.ready)applyAssistantDraft(preview.draft);showAssistantPreview(preview)}
    catch(error){invalidateAssistantDraft();$('assistantReview').textContent=error.message}
    finally{$('assistantCheck').disabled=false;setAssistantBusy(false)}
  });
  $('assistantSourceRows').addEventListener('click',event=>{
    const remove=event.target.closest('[data-assistant-remove]');
    if(remove){assistantPlan=readAssistantDraft();assistantPlan.packages=assistantPlan.packages.filter(row=>row.package_key!==remove.dataset.assistantRemove);renderAssistantSources();invalidateAssistantDraft();return}
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
      renderAssistantSources();invalidateAssistantDraft();$('assistantSourceDialog').close()}
    catch(error){$('assistantSourceNotice').textContent=error.message}
  });
  $('assistantCreate').addEventListener('click',()=>{
    if(!commitAssistantAlias()||!assistantApproval||!$('assistantDraftForm').reportValidity())return;
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
      $('assistantConfirmDialog').close();invalidateAssistantDraft();assistantState('已创建','ready');
      const review=$('assistantReview');review.replaceChildren();const link=document.createElement('a');link.href=`/monitors/${value.id}/sources`;link.dataset.nav='';link.textContent=`任务 #${value.id} 已创建 · 查看来源设置`;review.appendChild(link);
      assistantHistory.push({role:'user',content:'确认创建当前草案'},{role:'assistant',content:`任务 #${value.id} 已创建，将按已确认计划执行。`});renderAssistantChat();
    }catch(error){$('assistantConfirmNotice').textContent=error.message}
    finally{assistantCreating=false;$('assistantConfirmSave').disabled=false;$('assistantConfirmCancel').disabled=false}
  });
}
