FROM python:3.13-slim

RUN pip install --no-cache-dir requests==2.32.3

EXPOSE 10000

CMD python -c "
import http.server, os
PORT = int(os.environ.get('PORT', 10000))
http.server.HTTPServer(('0.0.0.0', PORT), type('H', (http.server.BaseHTTPRequestHandler,), {'do_GET': lambda s: (s.send_response(200), s.end_headers(), s.wfile.write(b'OK'))})).serve_forever()
"