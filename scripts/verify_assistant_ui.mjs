// Run with PLAYWRIGHT_MODULE pointing to an installed Playwright package, or install it normally.
// All API responses are fixtures: this test never calls DeepSeek or creates a real monitor.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {readFile, mkdir} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const require=createRequire(import.meta.url);
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const output=path.join(root,'.test_tmp','assistant-ui');
await mkdir(output,{recursive:true});
const schema={type:'object',additionalProperties:false,properties:{pages:{type:'integer',minimum:1,maximum:10,default:2}}};
const sources=[
  {package_key:'google_news_rss',name:'Google 新闻 RSS',category:'news',supported:true,version:'1.0.3',profile:{mode:'keyword',languages:['zh','en'],notes:'新闻检索'},parameters_schema:schema,config:{pages:2}},
  {package_key:'rss_multi_feed',name:'通用 RSS',category:'news',supported:true,version:'1.0.0',profile:{mode:'feed',languages:['zh','en'],notes:'订阅匹配'},parameters_schema:schema,config:{pages:2}},
  {package_key:'qinyun_journals',name:'勤云中文期刊检索包',category:'academic',supported:true,version:'1.0.0',profile:{mode:'keyword',languages:['zh'],notes:'中文文献'},parameters_schema:{type:'object',properties:{journal_keys:{type:'array',minItems:1,maxItems:2,items:{type:'string',enum:['a','b','c']}}}},config:{journal_keys:['a']}},
  {package_key:'not_supported',name:'未登记来源',category:'news',supported:false,profile:{mode:'unknown',languages:[]},parameters_schema:{},config:{}},
];
const plan={name:'科学研究中的人工智能',query:'人工智能 科学研究',aliases:['AI for science','AI4S'],journal_scope:'selected',schedule_type:'daily',schedule_time:'09:00',weekday:null,timezone:'Asia/Shanghai',packages:sources.slice(0,3).map(source=>({package_key:source.package_key,enabled:true,item_limit:100,config:source.config}))};
const requests=[],errors=[];
let creates=0,chats=0,failChat=false;
const browser=await chromium.launch({channel:process.env.PLAYWRIGHT_CHANNEL||'msedge',headless:true});
try{
  const page=await browser.newPage({viewport:{width:1440,height:1050},deviceScaleFactor:1});
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('http://platform.test/**',async route=>{
    const url=new URL(route.request().url()),pathname=url.pathname;
    const json=value=>route.fulfill({contentType:'application/json',body:JSON.stringify(value)});
    if(pathname==='/api/v1/system/status')return json({checked_at:'2026-11-19T06:00:00Z',database:{state:'ready'},processes:[{role:'serve',state:'running',pid:123,started_at:'2026-11-19T05:00:00Z'},{role:'scheduler',state:'stopped'},{role:'worker-default',state:'stopped'}],collection:{queued:10,running:1,overdue_monitors:2,recent_issues:[{id:70,name:'RSS 验收任务',status:'partial',started_at:'2026-11-19T01:00:00Z',finished_at:'2026-11-19T01:05:00Z'}]}});
    if(pathname==='/api/v1/runs/70')return json({id:70,monitor_id:8,status:'partial',fetched:10,inserted:4,updated:1,unchanged:5,started_at:'2026-11-19T01:00:00Z',finished_at:'2026-11-19T01:05:00Z',request_snapshot:{query:'军事智能体'},packages:[{package_key:'rss_multi_feed',status:'partial',attempt_no:2,execution_id:'00000000-0000-0000-0000-000000000007',fetched:10,inserted:4,updated:1,unchanged:5,warning_count:1,warnings:[{code:'FEED_FAILED',message:'HTTP 503 <img src=x onerror=alert(1)>',feed_url:'https://example.org/feed'}]}]});
    if(pathname==='/api/v1/assistant/catalog')return json({configured:true,model:'fixture',sources});
    if(pathname==='/api/v1/assistant/chat'){
      chats++;
      if(failChat)return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({message:'模型暂时不可用'})});
      return json({reply:'已整理任务草案，请检查来源和时间。',draft:plan,preview:{ready:true,draft:plan,confirmation_token:'fixture',errors:[],warnings:[],next_run_at:'2026-11-20T01:00:00Z',coverage:[{name:'勤云中文期刊检索包',selected:1,total:3,max_select:2}]}});
    }
    if(pathname==='/api/v1/assistant/preview'){
      const draft=route.request().postDataJSON().draft;requests.push(draft);
      const ready=draft.journal_scope!=='all_chinese'&&draft.packages.some(row=>row.enabled);
      const count=draft.packages.find(row=>row.package_key==='qinyun_journals')?.config?.journal_keys?.length||0;
      return json({ready,draft,confirmation_token:ready?'fixture':undefined,next_run_at:'2026-11-20T01:00:00Z',errors:ready?[]:['期刊范围不完整，不能创建'],warnings:[],coverage:[{name:'勤云中文期刊检索包',selected:count,total:3,max_select:2}]});
    }
    if(pathname==='/api/v1/assistant/monitors'){creates++;await new Promise(resolve=>setTimeout(resolve,150));return json({id:42})}
    if(pathname.startsWith('/api/v1/packages/')&&pathname.endsWith('/journals'))return json([{journal_key:'a',name:'测试期刊甲',tags:['基础科学']},{journal_key:'b',name:'测试期刊乙',tags:['信息智能']},{journal_key:'c',name:'测试期刊丙',tags:['基础科学']}]);
    let filename=['/assistant','/system','/runs/70'].includes(pathname)?'dashboard.html':pathname==='/assets/task-assistant.js'?'task-assistant.js':pathname==='/assets/assistant.css'?'assistant.css':pathname.startsWith('/assets/vendor/lucide/')?`vendor/lucide/${pathname.slice('/assets/vendor/lucide/'.length)}`:null;
    if(filename){
      const resolved=path.resolve(root,'crawler_platform',filename);
      assert.ok(resolved.startsWith(path.join(root,'crawler_platform')+path.sep));
      return route.fulfill({body:await readFile(resolved),contentType:filename.endsWith('.html')?'text/html':filename.endsWith('.css')?'text/css':'application/javascript'});
    }
    return route.fulfill({status:404,body:'Not found'});
  });
  await page.goto('http://platform.test/assistant');
  await page.waitForFunction(()=>document.querySelector('#assistantSend').disabled===false);
  assert.equal(await page.locator('#assistantDraftEmpty').isVisible(),true);
  await page.locator('#assistantInput').fill('每天九点监控人工智能在科学研究中的新闻和论文');
  await page.locator('#assistantSend').click();
  await page.waitForFunction(()=>document.querySelectorAll('.assistant-message').length===2);
  await page.waitForFunction(()=>document.querySelectorAll('[data-assistant-icon] svg').length>10);
  assert.equal(await page.locator('.assistant-tag').count(),2);
  assert.equal(await page.locator('#assistantSourceRows tr[data-assistant-source]').count(),3);

  await page.locator('#assistantAliasInput').fill('科学智能');await page.locator('#assistantAliasInput').press('Enter');
  assert.equal(await page.locator('.assistant-tag').count(),3);assert.equal(chats,1);
  await page.locator('#assistantAliasInput').fill('ai4s');await page.locator('#assistantAliasInput').press('Enter');
  assert.equal(await page.locator('.assistant-tag').count(),3);
  await page.getByRole('button',{name:'移除 科学智能',exact:true}).click();
  assert.equal(await page.locator('.assistant-tag').count(),2);
  await page.locator('[data-assistant-remove="rss_multi_feed"]').click();
  assert.equal(await page.locator('#assistantSourceRows tr[data-assistant-source]').count(),2);
  await page.locator('#assistantAddSource').click();
  assert.equal(await page.locator('[data-assistant-add="not_supported"]').count(),0);
  await page.locator('[data-assistant-add="rss_multi_feed"]').click();await page.locator('#assistantAddClose').click();
  assert.equal(await page.locator('#assistantSourceRows tr[data-assistant-source]').count(),3);

  await page.locator('[data-assistant-parameters="google_news_rss"]').click();
  await page.locator('#assistantSourceParameters [data-parameter="pages"]').fill('7');
  await page.locator('#assistantSourceForm button[type="submit"]').click();
  await page.locator('[data-assistant-parameters="qinyun_journals"]').click();
  await page.locator('#assistantSourceParameters [data-journal-package]').click();
  await page.locator('#journalList input[value="b"]').check();await page.locator('#journalConfirm').click();
  await page.locator('#assistantSourceForm button[type="submit"]').click();
  await page.locator('#assistantAliasInput').fill('scientific discovery');
  await page.locator('#assistantCheck').click();
  await page.waitForFunction(()=>document.querySelector('#assistantCreate').disabled===false);
  assert.ok(requests.at(-1).aliases.includes('scientific discovery'));
  assert.equal(requests.at(-1).packages.find(row=>row.package_key==='google_news_rss').config.pages,7);
  assert.deepEqual(requests.at(-1).packages.find(row=>row.package_key==='qinyun_journals').config.journal_keys,['a','b']);
  assert.equal(await page.locator('#assistantCoverage').innerText().then(value=>value.includes('2 / 3')),true);

  await page.locator('#assistantJournalScope').selectOption('all_chinese');
  assert.equal(await page.locator('#assistantCreate').isDisabled(),true);
  await page.locator('#assistantCheck').click();
  await page.waitForFunction(()=>document.querySelector('#assistantReview').textContent.includes('不能创建'));
  assert.equal(await page.locator('#assistantCreate').isDisabled(),true);
  await page.locator('#assistantJournalScope').selectOption('selected');await page.locator('#assistantCheck').click();
  await page.waitForFunction(()=>document.querySelector('#assistantCreate').disabled===false);

  for(const width of [1280,1440,1920]){
    await page.setViewportSize({width,height:1050});
    await page.emulateMedia({reducedMotion:'reduce'});
    await page.screenshot({path:path.join(output,`assistant-${width}.png`),fullPage:true});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true,`overflow at ${width}`);
    const layout=await page.locator('.assistant-layout').boundingBox(),chat=await page.locator('.assistant-conversation').boundingBox(),draft=await page.locator('.assistant-draft').boundingBox();
    assert.ok(chat.x+chat.width<=draft.x+1);assert.ok(draft.x+draft.width<=layout.x+layout.width+1);
    const create=await page.locator('#assistantCreate').boundingBox();assert.ok(create.y+create.height<=1050);
  }
  await page.locator('#assistantCreate').click();await page.locator('#assistantConfirmSave').dblclick();
  await page.waitForFunction(()=>document.querySelector('#assistantReview').textContent.includes('#42'));
  assert.equal(creates,1);assert.equal(await page.locator('#assistantCreate').isDisabled(),true);
  failChat=true;await page.locator('#assistantInput').fill('保留已有配置，修改时间');await page.locator('#assistantSend').click();
  await page.waitForFunction(()=>document.querySelector('#assistantChatStatus').textContent.includes('暂时不可用'));
  assert.equal(await page.locator('#assistantInput').inputValue(),'保留已有配置，修改时间');
  assert.equal(await page.locator('#assistantName').inputValue(),plan.name);
  await page.goto('http://platform.test/system');
  await page.waitForFunction(()=>document.querySelector('#systemNotice').textContent.includes('未检测到'));
  assert.equal(await page.locator('#systemProcessRows tr').count(),4);
  assert.ok((await page.locator('#systemQueue').innerText()).includes('10'));
  await page.screenshot({path:path.join(output,'system-status.png'),fullPage:true});
  await page.goto('http://platform.test/runs/70');
  await page.waitForFunction(()=>document.querySelector('#runPackageRows').textContent.includes('批次 #2'));
  await page.locator('.run-warning-details summary').first().click();
  assert.ok((await page.locator('.run-warning-details').first().innerText()).includes('HTTP 503'));
  assert.equal(await page.locator('#runPackageRows img').count(),0);
  await page.screenshot({path:path.join(output,'run-diagnostics.png'),fullPage:true});
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({status:'passed',viewports:[1280,1440,1920],mockCreates:creates,screenshots:output,checks:['aliases','duplicate aliases','remove/add source','parameter drawer','nested journal picker','scope blocker','review invalidation','single create','model outage','system status','run warnings and log location','escaped warning content','no overflow','no JavaScript errors']},null,2));
}finally{await browser.close()}
