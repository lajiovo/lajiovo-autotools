import json
import urllib.parse
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from config import _log

def start_http_servers(client_instance):
    # ===== 25567 端口：处理 /push 与 /stop =====
    class ControlRequestHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_GET(self):
            raw_path = self.path
            path_part, query_part = raw_path.split("?", 1) if "?" in raw_path else (raw_path, "")

            if path_part == "/stop":
                self._send_json({"status": "success", "message": "已接收下线指令，程序退出中..."})
                if client_instance.bot_loop:
                    import asyncio
                    asyncio.run_coroutine_threadsafe(
                        client_instance.shutdown_system("端口 /stop 触发"),
                        client_instance.bot_loop
                    )
                return

            if path_part == "/push":
                query_params = urllib.parse.parse_qs(query_part.replace("?", "&"))
                msg_list, group_list = query_params.get("msg", []), query_params.get("group", [])

                if not msg_list:
                    self._send_json({"status": "error", "message": "缺少 msg 参数"}, code=400)
                    return

                msg_content = msg_list[0]
                target_group_num = group_list[0] if group_list else None

                if client_instance.bot_loop:
                    import asyncio
                    asyncio.run_coroutine_threadsafe(
                        client_instance.push_message_to_group(msg_content, target_group_num),
                        client_instance.bot_loop
                    )

                self._send_json({"status": "success", "message": "推送任务已接收"})
            else:
                self.send_response(404)
                self.end_headers()

        def _send_json(self, data, code=200):
            self.send_response(code)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    # 只启动 25567 端口服务
    threading.Thread(
        target=lambda: HTTPServer(('', 25567), ControlRequestHandler).serve_forever(),
        daemon=True
    ).start()
    _log.info("🌐 控制与推送服务已启动 (端口 25567)")
