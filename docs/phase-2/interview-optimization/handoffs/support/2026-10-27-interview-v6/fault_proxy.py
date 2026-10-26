"""Candidate-only upstream fault: fail the first deepen request, forward others.

No credentials or request text is logged. Target remains the configured provider.
"""
import os,json,hashlib,threading,http.client,ssl
from urllib.parse import urlsplit
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from datetime import datetime,timezone

target=urlsplit(os.environ['UPSTREAM_BASE_URL'])
assert target.scheme=='https'
prompts={hashlib.sha256((Path('/prompts')/name).read_bytes()).hexdigest():stage for stage,name in
    [('judge','judge-prompt.txt'),('verify','verify-prompt.txt'),('speaker','speaker-prompt.txt'),('deepen','deepen-prompt.txt')]}
lock=threading.Lock();failed=False
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        reply=b'{"ready":true}'
        self.send_response(200);self.send_header('Content-Length',str(len(reply)));self.end_headers();self.wfile.write(reply)
    def do_POST(self):
        global failed
        data=self.rfile.read(int(self.headers['Content-Length']));body=json.loads(data)
        stage=prompts.get(hashlib.sha256(body['messages'][0]['content'].encode()).hexdigest(),'other')
        with lock:
            inject=stage=='deepen' and not failed
            if inject:failed=True
        response_id=None
        if inject:
            code=503;reply=b'{"error":{"message":"candidate fault injection: deepen unavailable"}}'
        else:
            conn=http.client.HTTPSConnection(target.hostname,target.port or 443,timeout=180,context=ssl.create_default_context())
            headers={k:v for k,v in self.headers.items() if k.lower() not in ('host','content-length','connection','transfer-encoding','accept-encoding')}
            headers['Accept-Encoding']='identity'
            conn.request('POST',self.path,body=data,headers=headers)
            response=conn.getresponse();code=response.status;reply=response.read();conn.close()
            try:response_id=json.loads(reply).get('id')
            except Exception:pass
        with lock:
            with Path('/records/proxy.jsonl').open('a') as stream:
                stream.write(json.dumps({'time':datetime.now(timezone.utc).isoformat(),'stage':stage,'injected':inject,
                    'status':code,'request_body_sha256':hashlib.sha256(data).hexdigest(),'response_id':response_id})+'\n')
        self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(reply)));self.end_headers();self.wfile.write(reply)
ThreadingHTTPServer(('0.0.0.0',18095),Handler).serve_forever()
