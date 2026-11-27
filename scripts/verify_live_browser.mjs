// Uses the actual local server, but never sends chat, creates tasks, or starts collection.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {mkdir} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const require=createRequire(import.meta.url);
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const output=path.join(root,'.test_tmp','live-ui');
await mkdir(output,{recursive:true});
const base=process.env.PLATFORM_TEST_URL||'http://127.0.0.1:8090';
const browser=await chromium.launch({channel:process.env.PLAYWRIGHT_CHANNEL||'msedge',headless:true});
try{
  const page=await browser.newPage({viewport:{width:1440,height:1050},reducedMotion:'reduce'});
  const errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  for(const route of ['/assistant','/system','/monitors','/sources']){
    const response=await page.goto(base+route);
    assert.equal(response.status(),200);
    await page.waitForLoadState('networkidle');
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,route);
    await page.screenshot({path:path.join(output,route.slice(1)+'.png'),fullPage:true});
  }
  const preview=await page.evaluate(async()=>{
    const response=await fetch('/api/v1/assistant/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    return {status:response.status,error:(await response.json()).error};
  });
  // Missing draft must reach application validation, rather than being rejected as cross-origin.
  assert.equal(preview.status,422);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({status:'passed',routes:4,same_origin_validation:preview.status,created_monitors:0,model_calls:0,screenshots:output}));
}finally{
  await browser.close();
}
