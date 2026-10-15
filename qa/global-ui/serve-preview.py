"""Serve a frozen QA build on localhost only. No API/backend and no production writes."""
import http.server,sys
from pathlib import Path
root=Path(sys.argv[1]).resolve()
class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(root),**kwargs)
    def do_GET(self):
        if not (root/self.path.split('?',1)[0].lstrip('/')).is_file():self.path='/index.html'
        return super().do_GET()
http.server.ThreadingHTTPServer(('127.0.0.1',5191),Handler).serve_forever()
