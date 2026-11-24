import subprocess,time
from pathlib import Path
root=Path.cwd(); py=str(root/'.venv/Scripts/python.exe'); edge=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
for mode,port in [('empty',18765),('populated',18766)]:
 server=subprocess.Popen([py,str(root/'tests/ui_fixture.py'),'--port',str(port)]+(['--populated'] if mode=='populated' else []))
 try:
  time.sleep(1)
  for width,height in [(1440,900),(1920,1080),(1381,899),(1000,700)]:
   target=root/'.venv'/f'ui-{mode}-{width}.png'
   result=subprocess.run([edge,'--headless','--disable-gpu','--no-sandbox','--hide-scrollbars','--virtual-time-budget=3500',f'--window-size={width},{height}',f'--user-data-dir={root / ".venv" / ("fixture-"+mode+str(width))}',f'--screenshot={target}',f'http://127.0.0.1:{port}/'],capture_output=True,text=True,timeout=35)
   print(mode,width,'ok' if target.exists() else result.stderr[-300:],flush=True)
 finally:
  server.terminate(); server.wait()
