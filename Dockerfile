FROM python:3.13-slim

COPY . .

EXPOSE 10000

CMD python -c "import os, http.server; os.chdir('/app'); print('Files:', os.listdir('.')); http.server.HTTPServer(('0.0.0.0', int(os.environ.get('PORT', 10000))), type('H', (http.server.BaseHTTPRequestHandler,), {'do_GET': lambda s: (s.send_response(200), s.end_headers(), s.wfile.write(('OK dir=' + str(os.listdir('.')[:10])).encode()))})).serve_forever()"