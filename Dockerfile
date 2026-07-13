FROM python:3.13-slim
RUN set +e; python3 -c "
import urllib.request
try:
    r = urllib.request.urlopen('https://pypi.org/simple/requests/', timeout=10)
    print('PYPI_OK:', r.status, len(r.read()))
except Exception as e:
    print('PYPI_FAIL:', e)
" > /tmp/network_test.txt 2>&1; cat /tmp/network_test.txt
EXPOSE 10000
CMD ["python", "-c", "import http.server, os; http.server.HTTPServer(('0.0.0.0', int(os.environ.get('PORT', 10000))), type('H', (http.server.BaseHTTPRequestHandler,), {'do_GET': lambda s: (s.send_response(200), s.end_headers(), s.wfile.write(b'OK'))})).serve_forever()"]