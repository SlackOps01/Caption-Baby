"""Isolated UI fixture: python tests/ui_fixture.py [--populated] [--port 8765].
Only serves synthetic content and stubbed APIs; never invokes transcription or Resolve.
"""
import argparse
import json
import shutil
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--populated', action='store_true')
parser.add_argument('--port', type=int, default=8765)
args = parser.parse_args()
lines = ['Every good story starts somewhere.', 'Take a moment to find your voice.', 'Make the details feel effortless.', 'Your words deserve to be seen.', 'A little clarity goes a long way.', 'Keep creating, one frame at a time.']
cues = [{'start': f'00:00:{i*3:02d},000', 'end': f'00:00:{i*3+2:02d},500', 'text': text} for i, text in enumerate(lines)]
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        route = self.path.split('?')[0].lstrip('/')
        if route == 'api/models':
            return self.reply(json.dumps({'models':[{'id':'fixture','name':'Fixture model','size':'0 MB','installed':True,'language':'English','note':'Test fixture'}], 'default':'fixture'}).encode(),'application/json')
        if route == 'api/status':
            return self.reply(json.dumps({'state':'done' if args.populated else 'idle', 'message':'Ready to edit', **({'cues':cues} if args.populated else {})}).encode(),'application/json')
        if route == 'fixture.mp4':
            return self.reply((ROOT / '.venv' / 'fixture-video.mp4').read_bytes(),'video/mp4')
        path = ROOT / 'web' / (route or 'index.html')
        if not path.is_file() or path.parent != ROOT / 'web':
            self.send_error(404); return
        data = path.read_bytes()
        if route in ('', 'index.html') and args.populated:
            inject = '''<script>window.addEventListener('load',()=>{ const v=document.getElementById('preview'); v.src='fixture.mp4'; v.load(); document.getElementById('source-name').textContent='Sample timeline'; });</script>'''
            data = data.replace(b'</body>', inject.encode() + b'</body>')
        self.reply(data, {'.html':'text/html; charset=utf-8','.css':'text/css','.js':'text/javascript'}.get(path.suffix,'application/octet-stream'))
    def do_POST(self):
        self.reply(json.dumps({'message':'Fixture action completed'}).encode(),'application/json')
    def reply(self, data, content_type):
        self.send_response(200); self.send_header('Content-Type',content_type); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
    def log_message(self, *args): pass
if __name__ == '__main__':
    video = ROOT / '.venv' / 'fixture-video.mp4'
    if args.populated and not video.exists():
        ffmpeg = shutil.which('ffmpeg')
        if not ffmpeg:
            raise SystemExit('Install ffmpeg to generate the synthetic fixture video.')
        video.parent.mkdir(exist_ok=True)
        subprocess.run([ffmpeg, '-v', 'error', '-f', 'lavfi', '-i', 'color=c=0x30363b:s=540x960:r=10:d=20', '-vf', 'drawbox=x=60:y=80:w=420:h=800:color=0x465159:t=fill,drawbox=x=90:y=110:w=360:h=740:color=0x69747a:t=fill', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-y', str(video)], check=True)
    ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
