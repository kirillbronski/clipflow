import sys, pathlib, threading
sys.path[:0] = ['source', 'source/_internal']
import clipflow as app
from tempfile import TemporaryDirectory
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from instagram_media import download_photo
from yt_dlp import YoutubeDL
from PIL import Image
from io import BytesIO
image=BytesIO();Image.new('RGB',(32,32),'red').save(image,format='JPEG');payload=image.getvalue()
class Photo(BaseHTTPRequestHandler):
 def do_GET(self):
  self.send_response(200);self.send_header('Content-Type','image/jpeg');self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
 def log_message(self,*args):pass
server=ThreadingHTTPServer(('127.0.0.1',0),Photo)
threading.Thread(target=server.serve_forever,daemon=True).start()
try:
 with TemporaryDirectory() as temp:
  events=[]
  info={'id':'test','title':'Автор — Публикация','ext':'jpg','url':f'http://127.0.0.1:{server.server_port}/photo.jpg'}
  with YoutubeDL({'outtmpl':temp+'/%(title)s.%(ext)s','quiet':True}) as ydl:
   result=download_photo(ydl,info,temp,events.append)
   saved=pathlib.Path(result['filepath']);assert saved.read_bytes()==payload
   assert app.completed_media_paths(result,ydl,temp)==[str(saved)]
   assert events[-1]['downloaded_bytes']==len(payload)
   assert not list(pathlib.Path(temp).glob('*.part'))
   saved.unlink()
   def cancel(data):raise app.yt_dlp.utils.DownloadError('cancelled')
   try:download_photo(ydl,dict(info),temp,cancel)
   except app.yt_dlp.utils.DownloadError:pass
   else:raise AssertionError('Cancellation was ignored')
   assert not saved.exists()
   result=download_photo(ydl,dict(info),temp,events.append)
   assert pathlib.Path(result['filepath']).read_bytes()==payload
 print('PASS real JPG download, original bytes, progress, file actions, cancellation and retry without duplicates')
finally:server.shutdown();server.server_close()
