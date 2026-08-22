import json
import os
import urllib.parse
import threading
import mimetypes
import asyncio
from http.server import BaseHTTPRequestHandler, HTTPServer
import logging

# 读取同目录下 key.json 中的明文密码
KEY_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "key.json")

def _get_stored_key():
    """从 key.json 中直接读取明文 key 字符串"""
    if not os.path.exists(KEY_FILE_PATH):
        logging.warning(f"⚠️ 校验配置文件不存在: {KEY_FILE_PATH}，接口鉴权功能将不可用！")
        return None
    try:
        with open(KEY_FILE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            raw_key = str(data.get("key", "")).strip()
            if not raw_key:
                logging.warning("⚠️ key.json 中未配置 key 字段或内容为空！")
                return None
            return raw_key
    except Exception as e:
        logging.error(f"❌ 读取 key.json 失败: {e}")
        return None

STORED_KEY = _get_stored_key()


def start_http_servers(client_instance):
    # ===== 25567 端口：处理 API 请求与前端静态资源 =====
    class ControlRequestHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def _send_json(self, data, code=200):
            self.send_response(code)
            self.send_header("Content-type", "application/json; charset=utf-8")
            # 禁止 API 响应被浏览器缓存
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

        def _verify_auth(self, input_key=None):
            """校验密码：直接比对前端传入的明文与 key.json 中的明文密码"""
            if not STORED_KEY:
                return False

            provided_key = self.headers.get("X-Api-Key") or input_key
            if not provided_key:
                return False

            return str(provided_key).strip() == STORED_KEY

        def _serve_static_file(self, relative_path):
            """仅允许读取并返回 assets 目录下的静态资源文件 (HTML, CSS, JS 等)"""
            safe_path = os.path.normpath(relative_path).lstrip("/\\")
            
            # 如果访问路径是 bot/assets/xxx，剥离前面的 bot/ 得到 assets/xxx
            if safe_path.startswith("bot" + os.sep) or safe_path.startswith("bot/"):
                safe_path = safe_path[4:].lstrip("/\\")

            if not safe_path.startswith("assets"):
                self.send_response(403)
                self.end_headers()
                return

            base_dir = os.path.dirname(os.path.abspath(__file__))
            file_path = os.path.abspath(os.path.join(base_dir, safe_path))

            assets_dir = os.path.abspath(os.path.join(base_dir, "assets"))
            if not file_path.startswith(assets_dir) or not os.path.exists(file_path) or os.path.isdir(file_path):
                self.send_response(404)
                self.end_headers()
                return

            mime_type, _ = mimetypes.guess_type(file_path)
            if not mime_type:
                if file_path.endswith('.js'):
                    mime_type = 'application/javascript'
                elif file_path.endswith('.css'):
                    mime_type = 'text/css'
                else:
                    mime_type = 'application/octet-stream'

            try:
                with open(file_path, 'rb') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-type", f"{mime_type}; charset=utf-8")
                # 关键：强制网页静态资源完全不保存/不缓存，规避在外登录的数据残留风险
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
                self.end_headers()
                self.wfile.write(content)
            except Exception as e:
                logging.error(f"读取文件失败: {file_path}, 错误: {e}")
                self.send_response(500)
                self.end_headers()

        def do_GET(self):
            raw_path = self.path
            path_part, query_part = raw_path.split("?", 1) if "?" in raw_path else (raw_path, "")
            query_params = urllib.parse.parse_qs(query_part.replace("?", "&"))

            # ---------------- 1. 静态资源路由 (无校验，绝对禁止缓存) ----------------
            if path_part in ("/", "/index.html", "/bot", "/bot/", "/bot/index.html"):
                return self._serve_static_file("assets/index.html")
            
            if path_part.startswith("/bot/assets/"):
                return self._serve_static_file(path_part)

            # ---------------- 2. /push 接口 (免密) ----------------
            if path_part == "/push":
                msg_list, group_list = query_params.get("msg", []), query_params.get("group", [])
                if not msg_list:
                    self._send_json({"status": "error", "message": "缺少 msg 参数"}, code=400)
                    return

                msg_content = msg_list[0]
                target_group_num = group_list[0] if group_list else None

                if client_instance.bot_loop:
                    asyncio.run_coroutine_threadsafe(
                        client_instance.push_message_to_group(msg_content, target_group_num),
                        client_instance.bot_loop
                    )
                self._send_json({"status": "success", "message": "推送任务已接收"})
                return

            # ---------------- 3. 需要明文密码校验的 GET 路由 ----------------
            query_key = query_params.get("key", [None])[0]
            if not self._verify_auth(query_key):
                self._send_json({"status": "error", "message": "身份校验失败：密码不正确或缺少 Auth Key"}, code=401)
                return

            if path_part == "/bot/stop":
                self._send_json({"status": "success", "message": "已接收下线指令，程序退出中..."})
                if client_instance.bot_loop:
                    asyncio.run_coroutine_threadsafe(
                        client_instance.shutdown_system("端口 /bot/stop 触发"),
                        client_instance.bot_loop
                    )
                return

            # 获取用户列表
            if path_part == "/bot/api/users":
                users = client_instance.data_mgr.get_user_list()
                self._send_json({"status": "success", "data": users})
                return

            # 获取群聊列表
            if path_part == "/bot/api/groups":
                groups = client_instance.data_mgr.get_group_list()
                self._send_json({"status": "success", "data": groups})
                return

            # 获取聊天历史记录
            if path_part == "/bot/api/history":
                target_id = query_params.get("target_id", [""])[0]
                is_group = query_params.get("is_group", ["false"])[0].lower() == "true"
                if not target_id:
                    self._send_json({"status": "error", "message": "缺少 target_id 参数"}, code=400)
                    return
                
                history = client_instance.data_mgr.get_chat_history(target_id, is_group=is_group)
                self._send_json({"status": "success", "data": history})
                return

            # 获取昵称
            if path_part == "/bot/api/nickname":
                target_id = query_params.get("target_id", [""])[0]
                is_group = query_params.get("is_group", ["false"])[0].lower() == "true"
                nickname = client_instance.data_mgr.get_nickname(target_id, is_group=is_group)
                self._send_json({"status": "success", "nickname": nickname})
                return

            # 轮询获取是否有新消息
            if path_part == "/bot/api/check_new":
                reset = query_params.get("reset", ["true"])[0].lower() == "true"
                status_info = client_instance.data_mgr.check_has_new_message(reset=reset)
                self._send_json({"status": "success", "data": status_info})
                return

            self.send_response(404)
            self.end_headers()

        def do_POST(self):
            raw_path = self.path
            path_part = raw_path.split("?")[0]

            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else "{}"
            
            try:
                data = json.loads(body)
            except Exception:
                data = {}

            # ---------------- 需要明文密码校验的 POST 路由 ----------------
            post_key = data.get("key")
            if not self._verify_auth(post_key):
                self._send_json({"status": "error", "message": "身份校验失败：密码不正确或缺少 Auth Key"}, code=401)
                return

            # 发送私聊纯文本消息
            if path_part == "/bot/api/send_c2c":
                user_openid = data.get("user_openid")
                content = data.get("content")
                if not user_openid or not content:
                    self._send_json({"status": "error", "message": "缺少 user_openid 或 content 参数"}, code=400)
                    return

                if client_instance.bot_loop:
                    asyncio.run_coroutine_threadsafe(
                        client_instance.api_send_c2c_text(user_openid, content),
                        client_instance.bot_loop
                    )
                self._send_json({"status": "success", "message": "私聊消息发送任务已提交"})
                return

            # 发送群聊纯文本消息
            if path_part == "/bot/api/send_group":
                group_openid = data.get("group_openid")
                content = data.get("content")
                if not group_openid or not content:
                    self._send_json({"status": "error", "message": "缺少 group_openid 或 content 参数"}, code=400)
                    return

                if client_instance.bot_loop:
                    asyncio.run_coroutine_threadsafe(
                        client_instance.api_send_group_text(group_openid, content),
                        client_instance.bot_loop
                    )
                self._send_json({"status": "success", "message": "群聊消息发送任务已提交"})
                return

            self.send_response(404)
            self.end_headers()

    # 启动 25567 端口服务
    threading.Thread(
        target=lambda: HTTPServer(('', 25567), ControlRequestHandler).serve_forever(),
        daemon=True
    ).start()
    logging.info("🌐 控制、API 与 Web 托管服务已启动 (端口 25567)")