#!/bin/sh
set -e

PORT=${PORT:-10000}

# Boot health server - keeps Render happy while we install deps
python -c "
import http.server, os, socket
port = int(os.environ.get('PORT', 10000))
s = http.server.HTTPServer(('0.0.0.0', port), type('H', (http.server.BaseHTTPRequestHandler,), {'do_GET': lambda s: (s.send_response(200), s.end_headers(), s.wfile.write(b'Booting...'))}))
s.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.serve_forever()
" &
BOOT_HS_PID=$!
echo "Boot health server started (PID=$BOOT_HS_PID, port=$PORT)"

pip install --no-cache-dir -r requirements.txt
echo "Dependencies installed"

# Stop boot server, let port settle
kill $BOOT_HS_PID 2>/dev/null
sleep 1

exec python start.py
