// Run: PLAYWRIGHT_MODULE=/path/to/playwright node tests/browser.cjs /path/to/index.html
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {pathToFileURL}=require('node:url');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
 const context=await browser.newContext({viewport:{width:1600,height:1100},acceptDownloads:true});
 const page=await context.newPage(),errors=[],requests=[];
 page.on('console',m=>{if(m.type()==='error')console.error('BROWSER:',m.text())});
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(/^https?:/.test(r.url()))requests.push(r.url())});
 await page.goto(pathToFileURL(path.resolve(process.argv[2])).href);
 await page.waitForSelector('.frame iframe');
 const state=()=>page.evaluate(()=>{const seed=JSON.parse(document.querySelector('#prototype-data').textContent);return JSON.parse(localStorage.getItem('prototype-singlefile:'+seed.id+':revision:'+seed.revision))||seed});
 assert.equal(await page.locator('.frame').count(),3);
 for(const frame of page.frames().slice(1))assert.equal(await frame.evaluate(()=>document.compatMode),'CSS1Compat');
 await page.locator('#fit').click();
 await page.locator('[data-mode=comment]').click();
 const box=await page.locator('.frame').first().boundingBox();
 await page.mouse.click(box.x+80,box.y+120);
 await page.locator('#editor-text').fill('Make this heading clearer <review>');await page.locator('#apply').click();
 assert.equal((await state()).comments.length,1);
 await page.locator('[data-mode=draw]').click();
 await page.mouse.move(box.x+90,box.y+160);await page.mouse.down();await page.mouse.move(box.x+180,box.y+180,{steps:5});await page.mouse.up();
 let before=await state();assert.equal(before.strokes.length,1);assert.equal(before.strokes[0].frameId,'overview');
 await page.locator('[data-mode=select]').click();
 const pinBefore=await page.locator('.pin').boundingBox(),title=await page.locator('[data-drag=overview]').boundingBox();
 await page.mouse.move(title.x+60,title.y+10);await page.mouse.down();await page.mouse.move(title.x+125,title.y+50,{steps:5});await page.mouse.up();
 let after=await state();assert.ok(Math.abs(after.frames[0].x-before.frames[0].x-65/before.viewport.z)<1);
 assert.deepEqual(after.comments,before.comments);assert.deepEqual(after.strokes,before.strokes);
 const pinAfter=await page.locator('.pin').boundingBox();assert.ok(Math.abs(pinAfter.x-pinBefore.x-65)<1);
 await page.locator('#undo').click();assert.equal((await state()).frames[0].x,before.frames[0].x);
 await page.locator('#redo').click();assert.equal((await state()).frames[0].x,after.frames[0].x);
 await page.getByRole('button',{name:'Resolve',exact:true}).click();assert.equal((await state()).comments[0].resolved,true);
 await page.reload();assert.equal((await state()).comments[0].resolved,true);assert.equal(await page.locator('.pin').count(),1);
 await page.locator('[data-mode=preview]').click();
 const iframeBox=await page.locator('iframe').first().boundingBox();
 const localButton=await page.frameLocator('iframe').first().locator('button').evaluate(e=>{const r=e.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}});
 const scale=(await state()).viewport.z;
 await page.mouse.click(iframeBox.x+localButton.x*scale,iframeBox.y+localButton.y*scale);
 await page.frameLocator('iframe').first().getByRole('button',{name:'You’re all caught up ✓'}).waitFor({timeout:3000});
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'prototype-canvas-test-'));
 let pending=page.waitForEvent('download');await page.locator('#save').click();const save=await pending;const saved=path.join(dir,'saved.html');await save.saveAs(saved);
 const clean=await browser.newContext();const p2=await clean.newPage();await p2.goto(pathToFileURL(saved).href);assert.equal(await p2.locator('.pin').count(),1);assert.equal(await p2.locator('#ink polyline').count(),1);
 assert.match(await p2.locator('#notes').innerText(),/Make this heading clearer/);
 pending=page.waitForEvent('download');await page.locator('#export').click();const exported=path.join(dir,'canvas.json');await(await pending).saveAs(exported);let data=JSON.parse(fs.readFileSync(exported));assert.equal(data.comments.length,1);assert.equal(data.strokes.length,1);
 await page.locator('#file').setInputFiles({name:'bad.json',mimeType:'application/json',buffer:Buffer.from('{"v":1}')});await page.getByRole('status').filter({hasText:'Invalid'}).waitFor();assert.equal((await state()).comments.length,1);
 await page.locator('#file').setInputFiles(exported);assert.equal((await state()).comments.length,1);
 await context.grantPermissions(['clipboard-read','clipboard-write']);await page.locator('#feedback').click();const feedback=JSON.parse(await page.evaluate(()=>navigator.clipboard.readText()));assert.equal(feedback.strokes.length,1);assert.ok(!('html' in feedback.frames[0]));
 // Same-origin old/new revision tabs retain separate edits.
 const rev=fs.readFileSync(saved,'utf8').replace(/(<script id="prototype-data" type="application\/json">)([\s\S]*?)(<\/script>)/,(_,a,b,c)=>{const s=JSON.parse(b);s.revision++;s.frames[0].html=s.frames[0].html.replace('A little room','A revised room');return a+JSON.stringify(s).replace(/</g,'\\u003c')+c});
 const revised=path.join(dir,'revised.html');fs.writeFileSync(revised,rev);const p3=await context.newPage();await p3.goto(pathToFileURL(revised).href);await p3.getByRole('button',{name:'Reopen',exact:true}).click();await page.locator('#plus').click();await p3.reload();assert.equal(await p3.getByRole('button',{name:'Resolve',exact:true}).count(),1);assert.match(await p3.frameLocator('iframe').first().locator('h1').first().innerText(),/revised/);
 await page.setViewportSize({width:390,height:844});await page.locator('#notes-toggle').click();assert.equal(await page.locator('aside').isVisible(),true);assert.ok((await page.locator('#stage').boundingBox()).height>100);
 await page.setViewportSize({width:1600,height:1100});await page.locator('[data-mode=select]').click();await page.locator('[data-drag=overview]').focus();await page.keyboard.press('Enter');const x=(await state()).frames[0].x;await page.keyboard.press('ArrowRight');assert.equal((await state()).frames[0].x,x+1);
 await page.locator('#fit').click();await page.screenshot({path:path.join(dir,'canvas.png')});
 assert.deepEqual(errors,[]);assert.deepEqual(requests,[]);
 console.log(JSON.stringify({result:'PASS',checks:['offline screens and standards mode','scaled frame drag and anchored marks','undo/redo','comments and reload','preview interaction','portable save in fresh context','JSON round trip and rejection','feedback export','revision isolation','mobile notes','keyboard movement','no page errors or network requests'],artifacts:dir},null,2));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
