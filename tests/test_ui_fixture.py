"""Exercise editor interactions against the local, isolated fixture."""
import json, subprocess, sys, time, urllib.request
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'.venv/browser-test-tools'))
import websocket
py=str(root/'.venv/Scripts/python.exe'); edge=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
server=subprocess.Popen([py,str(root/'tests/ui_fixture.py'),'--port','18767','--populated'])
browser=None
try:
 time.sleep(1)
 browser=subprocess.Popen([edge,'--headless','--no-sandbox','--disable-gpu','--remote-allow-origins=*','--remote-debugging-port=19223',f'--user-data-dir={root / ".venv" / "fixture-interaction"}','http://127.0.0.1:18767/'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 for i in range(50):
  try:
   pages=json.load(urllib.request.urlopen('http://127.0.0.1:19223/json')); page=next(p for p in pages if p['type']=='page' and '18767' in p.get('url','')); break
  except Exception: time.sleep(.2)
 ws=websocket.create_connection(page['webSocketDebuggerUrl'],timeout=10,origin='http://localhost')
 time.sleep(2)
 script='''(async () => {
 const check=(ok,name)=>{if(!ok)throw Error(name)};
 check(document.querySelectorAll('.cue-row').length===6,'captions loaded');
 check(!document.querySelector('.caption-panel').hidden,'inspector active');
 document.querySelector('#timeline-toggle').click(); check(!document.querySelector('#timeline-content').hidden,'timeline expands');
 document.querySelector('#timeline-toggle').click(); check(document.querySelector('#timeline-content').hidden,'timeline collapses');
 document.querySelector('.rail-settings').click(); check(!document.querySelector('.model-toolbar').hidden,'models open');
 document.querySelector('.rail-settings').click();
 document.querySelectorAll('[role=tab]')[1].click(); check(!document.querySelector('.video-panel').hidden,'video tab');
 document.querySelectorAll('[role=tab]')[0].click();
 document.querySelectorAll('.cue-row')[1].click(); check(document.querySelector('#cue-text').value.includes('moment'),'caption selection');
 document.querySelector('.word-chip').click(); await new Promise(r => setTimeout(r, 10)); document.querySelector('.swatch[data-color="#3d91f5"]').click();
 document.querySelector('.word-size-segments [data-value="125"]').click();
 check(document.querySelector('#word-color').value==='#3d91f5','word color'); check(document.querySelector('#word-size').value==='125','word size');
 check(document.querySelector('#overlay span').style.color!=='' && document.querySelector('#overlay span').style.fontSize==='125%','caption overlay styling');
 const search=document.querySelector('#search'); search.value='creating'; search.dispatchEvent(new Event('input',{bubbles:true})); check(document.querySelectorAll('.cue-row').length===1,'search filters');
 search.value=''; search.dispatchEvent(new Event('input',{bubbles:true}));
 const handle=document.querySelector('.resize-handle'); const before=document.querySelector('.viewer').getBoundingClientRect().width; handle.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true})); check(document.querySelector('.viewer').getBoundingClientRect().width>before,'keyboard resize');
 return 'PASS: fixture loading, timeline, models, tabs, selection, word styling, search, resize'; })()'''
 ws.send(json.dumps({'id':1,'method':'Runtime.evaluate','params':{'expression':script,'returnByValue':True,'awaitPromise':True}}))
 while True:
  res=json.loads(ws.recv())
  if res.get('id')==1: break
 if 'exceptionDetails' in res.get('result',{}): raise RuntimeError(str(res['result']['exceptionDetails']))
 print(res['result']['result'].get('value'))
finally:
 if browser: browser.terminate(); browser.wait()
 server.terminate(); server.wait()

