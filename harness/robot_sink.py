import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


# Stands in for the robot. OrderHub POSTs each dispatch here (-robot-url),
# and we keep every payload so tests can check what the robot received.
# Tests can also make it misbehave:
#   delay      seconds to wait before answering, like a slow robot (it still builds the order)
#   fail_next  how many of the next dispatches to reject with a 500 (those are not built)
class RobotSink:
    def __init__(self, port):
        self.port = port
        self.url = f"http://127.0.0.1:{port}/dispatch"
        self.received = []
        self.delay = 0
        self.fail_next = 0
        self.lock = threading.Lock()
        self.server = None

    def start(self):
        sink = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                with sink.lock:
                    rejected = sink.fail_next > 0
                    if rejected:
                        sink.fail_next -= 1
                    else:
                        sink.received.append(json.loads(body))
                time.sleep(sink.delay)
                self.send_response(500 if rejected else 200)
                self.end_headers()

            def log_message(self, *args):
                pass  # keep test output clean

        self.server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    # Back to a normal, fast robot. Called after every test.
    def behave(self):
        self.delay = 0
        self.fail_next = 0

    def dispatches_for(self, order_id):
        with self.lock:
            return [p for p in self.received if p["order_id"] == order_id]
