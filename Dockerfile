FROM python:3.13-slim
RUN set +e; pip install requests==2.32.3 > /tmp/pip_out.txt 2>&1; echo "PIP_EXIT=$?" >> /tmp/pip_out.txt
EXPOSE 10000
CMD python -c "
import http.server, os
pip_out = open('/tmp/pip_out.txt').read()
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(pip_out.encode())
http.server.HTTPServer(('0.0.0.0', int(os.environ.get('PORT', 10000))), H).serve_forever()
"