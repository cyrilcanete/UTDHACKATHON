const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async()=>{
  let browser, server;
  const errors = [];
  const port = process.env.MIRROR_TEST_PORT || '5091';
  try {
    server=spawn(process.env.PYTHON || 'python3',['app.py'],{cwd:path.resolve(__dirname,'..'),env:{...process.env,MIRROR_DEMO:'1',MIRROR_PORT:port}});
    await new Promise((resolve,reject)=>{const timeout=setTimeout(()=>reject(Error('Server startup timeout')),10000);server.stdout.once('data',()=>{clearTimeout(timeout);resolve()});server.once('exit',c=>reject(Error('Server exited: '+c)));server.stderr.on('data',x=>process.stderr.write(x));});
    browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE_PATH || undefined,args:['--no-sandbox','--disable-dev-shm-usage','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
    const page=await browser.newPage({viewport:{width:1920,height:1080}});
    page.on('pageerror',e=>errors.push(e.message));
    await page.goto(`http://127.0.0.1:${port}`);
    await page.waitForFunction(()=>window.state !== undefined || document.getElementById('welcome').innerText==='hello');
    await page.waitForTimeout(500);
    await page.evaluate(()=>document.fonts.ready);
    assert(await page.locator('#welcome').isVisible());
    assert(await page.evaluate(()=>document.fonts.check('142px Dancing')));
    await page.keyboard.press('ArrowRight'); await page.waitForTimeout(200);
    assert(await page.locator('#welcome').isVisible());
    const capture=async name=>{if(process.env.MIRROR_TEST_ARTIFACTS){fs.mkdirSync(process.env.MIRROR_TEST_ARTIFACTS,{recursive:true});await page.screenshot({path:path.join(process.env.MIRROR_TEST_ARTIFACTS,name+'.png')});}};
    await capture('welcome');
    await page.keyboard.press('i');
    await page.waitForFunction(()=>document.getElementById('stage').style.filter==='brightness(0.2)');
    await page.waitForTimeout(1100);
    assert.equal(await page.evaluate(()=>getComputedStyle(document.getElementById('stage')).filter),'brightness(0.2)');
    assert(await page.locator('#welcome').isVisible());
    await page.keyboard.press('b');
    await page.waitForFunction(()=>document.getElementById('stage').style.filter==='brightness(1)');
    assert(await page.locator('#welcome').isVisible());
    await page.keyboard.press('1'); await page.waitForFunction(()=>document.getElementById('greeting').textContent==='Hello, Cyril');
    async function layout() {
      const issues=await page.evaluate(()=>{
        const errors=[];
        if(document.body.scrollHeight>innerHeight||document.body.scrollWidth>innerWidth) errors.push('body overflow');
        for(const id of ['left-box','right-box','left-page','right-page','connection']){
          const e=document.getElementById(id),r=e.getBoundingClientRect();
          if(r.bottom>innerHeight||r.right>innerWidth||r.top<0||r.left<0)errors.push(id+' outside viewport');
          if(e.scrollHeight>e.clientHeight+1)errors.push(id+' clipped text');
        }
        if(getComputedStyle(document.getElementById('stage')).cursor!=='none')errors.push('cursor visible');
        if(document.getElementById('mirror-space').getBoundingClientRect().width/document.getElementById('stage').getBoundingClientRect().width<.45)errors.push('center too narrow');
        return errors;
      });assert.deepEqual(issues,[]);
    }
    await layout(); await capture('personal');
    await page.keyboard.press('ArrowRight'); await page.waitForFunction(()=>document.getElementById('mode').textContent==='work mode');
    await page.keyboard.press('h'); await page.waitForFunction(()=>document.getElementById('weather').textContent.includes('attention'));
    await layout(); await capture('work');
    const work=await (await page.request.get(`http://127.0.0.1:${port}/api/dashboard`)).json();
    assert(!('inbox' in work));assert(work.mirror.work.assistant.incident.id.startsWith('LOCAL-'));
    await page.keyboard.press('o');await page.waitForFunction(()=>document.getElementById('sensor-status').textContent.includes('stale'));await layout();
    await page.keyboard.press('n');await page.keyboard.press('ArrowLeft');await page.waitForFunction(()=>document.getElementById('mode').textContent==='personal mode');
    await page.keyboard.press('2');await page.waitForFunction(()=>document.getElementById('greeting').textContent==='Hello, Sarah');
    await page.keyboard.press('Escape');await page.waitForFunction(()=>!document.getElementById('welcome').hidden);
    assert.equal(await page.locator('#right-page').textContent(),'');
    const locked=await (await page.request.get(`http://127.0.0.1:${port}/api/dashboard`)).json();assert.equal(locked.mirror.active_profile,null);assert(!('inbox' in locked));
    await page.keyboard.press('d');assert(await page.locator('#demo').isVisible());
    await page.getByRole('button',{name:'Scan Sarah',exact:true}).click();await page.waitForFunction(()=>document.getElementById('greeting').textContent==='Hello, Sarah');
    // Every generated page fits, including very long names/URLs, and no words are dropped.
    const pagination=await page.evaluate(()=>{
      const el=document.getElementById('right-page');
      const original='Long message '.repeat(400)+'Z'.repeat(2200);
      const pages=pagesFor([card('Long content',original)],el);
      const clipped=pages.some(p=>{el.textContent=p.text;return el.scrollHeight>el.clientHeight});
      return {clipped,retained:pages.map(p=>p.text).join('').replace(/\s/g,'')===original.replace(/\s/g,'')};
    });assert.deepEqual(pagination,{clipped:false,retained:true});
    for(const viewport of [{width:1920,height:1000},{width:1366,height:768},{width:1920,height:1080}]) {await page.setViewportSize(viewport);await page.waitForTimeout(1200);await layout();}
    assert.deepEqual(errors,[]);
    console.log('PASS: welcome, Cyril/Sarah, knob directions/press, demo controls, hot/offline/recovery, privacy, font/cursor, pagination, 1920x1080 / 1920x1000 / 1366x768 layouts');
  } finally {if(browser)await browser.close();if(server)server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1});
