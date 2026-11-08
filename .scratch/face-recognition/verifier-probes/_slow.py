import base64, http.server, time
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==")
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        time.sleep(6)
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(PNG)))
        self.end_headers()
        self.wfile.write(PNG)
    def log_message(self, *args):
        pass
http.server.HTTPServer(("127.0.0.1", 8111), H).serve_forever()