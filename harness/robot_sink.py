import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


# Stands in for the robot. OrderHub POSTs each dispatch here (-robot-url),
# and we keep every payload so tests can check what the robot received.
class RobotSink:
    def __init__(self, port):
        self.port = port
        self.url = f"http://127.0.0.1:{port}/dispatch"
        self.received = []
        self.lock = threading.Lock()
        self.server = None

    def start(self):
        sink = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                with sink.lock:
                    sink.received.append(json.loads(body))
                self.send_response(200)
                self.end_headers()

            def log_message(self, *args):
                pass  # keep test output clean

        self.server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    def dispatches_for(self, order_id):
        with self.lock:
            return [p for p in self.received if p["order_id"] == order_id]
