FROM python:3.13-slim
RUN set +e; pip install requests==2.32.3 > /tmp/pip_out.txt 2>&1; echo "PIP_EXIT=$?"; cat /tmp/pip_out.txt
EXPOSE 10000
CMD python -c "import http.server, os; http.server.HTTPServer(('0.0.0.0', int(os.environ.get('PORT', 10000))), type('H', (http.server.BaseHTTPRequestHandler,), {'do_GET': lambda s: (s.send_response(200), s.end_headers(), s.wfile.write(b'OK'))})).serve_forever()"