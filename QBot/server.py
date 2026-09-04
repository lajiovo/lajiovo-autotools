import json
import os
import time
import secrets
import urllib.parse
import threading
import mimetypes
import asyncio
from http.server import BaseHTTPRequestHandler, HTTPServer
import logging
from config import _log

# 读取同目录下 key.json 中的明文密码
KEY_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "key.json")
ASSETS_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets"))
SESSION_COOKIE = "qbot_session"
SESSION_TTL = 7 * 24 * 3600
_SESSIONS = {}
_SESSIONS_LOCK = threading.Lock()

PUBLIC_ASSET_FILES = {
    "login.html",
    "login.css",
    "login.js",
    "index.html",
}


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


def _create_session():
    token = secrets.token_urlsafe(32)
    with _SESSIONS_LOCK:
        _SESSIONS[token] = time.time() + SESSION_TTL
    return token


def _valid_session(token):
    if not token:
        return False
    now = time.time()
    with _SESSIONS_LOCK:
        expire_at = _SESSIONS.get(token)
        if expire_at is None:
            return False
        if now > expire_at:
            _SESSIONS.pop(token, None)
            return False
        _SESSIONS[token] = now + SESSION_TTL
        return True


def _revoke_session(token):
    if not token:
        return
    with _SESSIONS_LOCK:
        _SESSIONS.pop(token, None)


def start_http_servers(client_instance):
    """
    启动 25567 端口的 Web 控制台与 API 服务。
    参数 client_instance: 包含 data_mgr (BotDataManager 实例) 及 bot_loop 的客户端对象。
    """

    class ControlRequestHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            # 禁用默认的标准 HTTP 日志输出，避免控制台刷屏
            pass

        def _send_json(self, data, code=200, extra_headers=None):
            """统一构建 JSON 格式响应，并添加防缓存 Header"""
            self.send_response(code)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            if extra_headers:
                for k, v in extra_headers.items():
                    self.send_header(k, v)
            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

        def _redirect(self, location, extra_headers=None):
            self.send_response(302)
            self.send_header("Location", location)
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            if extra_headers:
                for k, v in extra_headers.items():
                    self.send_header(k, v)
            self.end_headers()

        def _parse_cookies(self):
            cookies = {}
            raw = self.headers.get("Cookie") or ""
            for part in raw.split(";"):
                if "=" not in part:
                    continue
                k, v = part.split("=", 1)
                cookies[k.strip()] = urllib.parse.unquote(v.strip())
            return cookies

        def _session_cookie_header(self, token, max_age=SESSION_TTL):
            return f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={int(max_age)}"

        def _clear_session_cookie_header(self):
            return f"{SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"

        def _get_session_token(self):
            return self._parse_cookies().get(SESSION_COOKIE)

        def _extract_provided_key(self, query_params=None, body_data=None):
            header_key = self.headers.get("X-Api-Key") or self.headers.get("Authorization")
            if header_key:
                header_key = str(header_key).replace("Bearer", "").strip()
            query_key = None
            if query_params:
                query_key = (query_params.get("key") or [None])[0]
            body_key = None
            if isinstance(body_data, dict):
                body_key = body_data.get("key")
            return header_key or query_key or body_key

        def _is_password_match(self, input_key):
            if not STORED_KEY or input_key is None:
                return False
            return str(input_key).strip() == STORED_KEY

        def _verify_auth(self, input_key=None):
            """校验：有效登录会话，或明文密码（Header / query / body）"""
            if _valid_session(self._get_session_token()):
                return True
            if not STORED_KEY:
                return False
            provided_key = self.headers.get("X-Api-Key") or input_key
            if not provided_key:
                return False
            return str(provided_key).strip() == STORED_KEY

        def _read_json_body(self):
            content_length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else ""
            if not raw:
                return {}
            try:
                data = json.loads(raw)
                return data if isinstance(data, dict) else {}
            except Exception:
                try:
                    parsed = urllib.parse.parse_qs(raw)
                    return {k: v[0] if isinstance(v, list) and v else v for k, v in parsed.items()}
                except Exception:
                    return {}

        def _collect_get_params(self):
            raw_path = self.path
            path_part, query_part = raw_path.split("?", 1) if "?" in raw_path else (raw_path, "")
            query_params = urllib.parse.parse_qs(query_part.replace("?", "&"))
            return path_part, query_params

        def _dispatch_push(self, payload, query_params=None):
            query_params = query_params or {}
            markdown = (
                (payload.get("markdown") if isinstance(payload, dict) else None)
                or (payload.get("msg") if isinstance(payload, dict) else None)
                or (payload.get("content") if isinstance(payload, dict) else None)
                or (query_params.get("markdown") or [None])[0]
                or (query_params.get("msg") or [None])[0]
                or (query_params.get("content") or [None])[0]
            )
            if not markdown:
                self._send_json({"status": "error", "message": "缺少 markdown / msg 参数"}, code=400)
                return

            group_val = None
            if isinstance(payload, dict):
                group_val = payload.get("group") or payload.get("target_group")
            if not group_val:
                group_list = query_params.get("group", [])
                group_val = group_list[0] if group_list else None

            if client_instance.bot_loop:
                asyncio.run_coroutine_threadsafe(
                    client_instance.push_message_to_group(str(markdown), group_val),
                    client_instance.bot_loop
                )
            self._send_json({"status": "success", "message": "Markdown 推送任务已接收"})

        def _asset_filename(self, relative_path):
            safe_path = os.path.normpath(relative_path).lstrip("/\\")
            if safe_path.startswith("bot" + os.sep) or safe_path.startswith("bot/"):
                safe_path = safe_path[4:].lstrip("/\\")
            if safe_path.startswith("assets" + os.sep) or safe_path.startswith("assets/"):
                safe_path = safe_path.split("assets", 1)[-1].lstrip("/\\")
            return safe_path.replace("\\", "/")

        def _serve_static_file(self, relative_path, require_auth=False):
            """读取并返回 assets 目录下的静态资源文件"""
            filename = self._asset_filename(relative_path)
            if not filename or ".." in filename.split("/"):
                self.send_response(403)
                self.end_headers()
                return

            file_path = os.path.abspath(os.path.join(ASSETS_DIR, filename))
            if not file_path.startswith(ASSETS_DIR) or not os.path.exists(file_path) or os.path.isdir(file_path):
                self.send_response(404)
                self.end_headers()
                return

            if require_auth and not self._verify_auth():
                if filename.endswith(".html"):
                    self._redirect("/bot/assets/login.html")
                    return
                self._send_json({"status": "error", "message": "身份校验失败：请先登录"}, code=401)
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
            path_part, query_params = self._collect_get_params()

            # ---------------- 1. 静态资源：登录页公开，聊天页需登录 ----------------
            if path_part in ("/", "/index.html", "/bot", "/bot/", "/bot/index.html", "/bot/login", "/bot/login.html"):
                return self._serve_static_file("login.html")

            if path_part in ("/bot/chat", "/bot/chat.html", "/bot/assets/chat.html"):
                return self._serve_static_file("chat.html", require_auth=True)

            if path_part.startswith("/bot/assets/") or path_part.startswith("/assets/"):
                filename = self._asset_filename(path_part)
                need_auth = filename not in PUBLIC_ASSET_FILES and filename.endswith(".html")
                return self._serve_static_file(filename, require_auth=need_auth)

            # ---------------- 2. /push 接口 (免密 Markdown 推送) ----------------
            if path_part == "/push":
                return self._dispatch_push({}, query_params)

            # ---------------- 登录 / 登出 ----------------
            if path_part == "/bot/api/login":
                provided = self._extract_provided_key(query_params=query_params)
                if self._is_password_match(provided):
                    token = _create_session()
                    self._send_json(
                        {"status": "success", "message": "登录成功"},
                        extra_headers={"Set-Cookie": self._session_cookie_header(token)},
                    )
                    return
                self._send_json({"status": "error", "message": "身份校验失败：密码不正确"}, code=401)
                return

            if path_part == "/bot/api/logout":
                _revoke_session(self._get_session_token())
                self._send_json(
                    {"status": "success", "message": "已退出登录"},
                    extra_headers={"Set-Cookie": self._clear_session_cookie_header()},
                )
                return

            # ---------------- 3. 需要鉴权的 GET 路由 ----------------
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

            # 获取已知用户列表
            if path_part == "/bot/api/users":
                users = client_instance.data_mgr.get_user_list()
                self._send_json({"status": "success", "data": users})
                return

            # 获取已知群聊列表
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

            # 获取指定对象（私聊或群聊）的显示昵称
            if path_part == "/bot/api/nickname":
                target_id = query_params.get("target_id", [""])[0]
                is_group = query_params.get("is_group", ["false"])[0].lower() == "true"
                nickname = client_instance.data_mgr.get_nickname(target_id, is_group=is_group)
                self._send_json({"status": "success", "nickname": nickname})
                return

            # 轮询检查是否有新消息
            if path_part == "/bot/api/check_new":
                reset = query_params.get("reset", ["true"])[0].lower() == "true"
                has_new = bool(client_instance.data_mgr.check_has_new_message(reset=reset))
                self._send_json({"status": "success", "data": {"has_new": has_new}})
                return

            # 读取系统完整 OP 配置
            if path_part == "/bot/api/opsetting":
                opsetting = client_instance.data_mgr.get_opsetting()
                self._send_json({"status": "success", "data": opsetting})
                return

            # 读取特定用户个人基础信息
            if path_part == "/bot/api/user_info":
                user_id = query_params.get("user_id", [""])[0]
                if not user_id:
                    self._send_json({"status": "error", "message": "缺少 user_id 参数"}, code=400)
                    return
                user_info = client_instance.data_mgr.get_user_info(user_id)
                self._send_json({"status": "success", "data": user_info})
                return

            # 读取特定群聊完整配置信息
            if path_part == "/bot/api/group_info":
                group_id = query_params.get("group_id", [""])[0]
                if not group_id:
                    self._send_json({"status": "error", "message": "缺少 group_id 参数"}, code=400)
                    return
                group_info = client_instance.data_mgr.get_group_info(group_id)
                self._send_json({"status": "success", "data": group_info})
                return

            # 读取自定义扩展数据
            if path_part == "/bot/api/extra":
                key = query_params.get("key_name", [""])[0]
                if not key:
                    self._send_json({"status": "error", "message": "缺少 key_name 参数"}, code=400)
                    return
                value = client_instance.data_mgr.get_extra_data(key)
                self._send_json({"status": "success", "data": value})
                return

            self.send_response(404)
            self.end_headers()

        def do_POST(self):
            raw_path = self.path
            path_part, query_part = raw_path.split("?", 1) if "?" in raw_path else (raw_path, "")
            query_params = urllib.parse.parse_qs(query_part.replace("?", "&"))
            data = self._read_json_body()

            # ---------------- 免密 Markdown 推送 ----------------
            if path_part == "/push":
                return self._dispatch_push(data, query_params)

            # ---------------- 登录：校验 key.json 明文密码并写入会话 Cookie ----------------
            if path_part == "/bot/api/login":
                provided = self._extract_provided_key(query_params=query_params, body_data=data)
                if self._is_password_match(provided):
                    token = _create_session()
                    self._send_json(
                        {"status": "success", "message": "登录成功"},
                        extra_headers={"Set-Cookie": self._session_cookie_header(token)},
                    )
                    return
                self._send_json({"status": "error", "message": "身份校验失败：密码不正确"}, code=401)
                return

            if path_part == "/bot/api/logout":
                _revoke_session(self._get_session_token())
                self._send_json(
                    {"status": "success", "message": "已退出登录"},
                    extra_headers={"Set-Cookie": self._clear_session_cookie_header()},
                )
                return

            # ---------------- 需要鉴权的 POST 路由 ----------------
            post_key = data.get("key") or self._extract_provided_key(query_params=query_params, body_data=data)
            if not self._verify_auth(post_key):
                self._send_json({"status": "error", "message": "身份校验失败：密码不正确或缺少 Auth Key"}, code=401)
                return

            # 发送私聊纯文本消息
            if path_part == "/bot/api/send_c2c":
                user_openid = data.get("user_openid") or data.get("user_id")
                content = data.get("content")
                if not user_openid or not content:
                    self._send_json({"status": "error", "message": "缺少 user_openid (或 user_id) 或 content 参数"}, code=400)
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
                group_openid = data.get("group_openid") or data.get("group_id")
                content = data.get("content")
                if not group_openid or not content:
                    self._send_json({"status": "error", "message": "缺少 group_openid (或 group_id) 或 content 参数"}, code=400)
                    return

                if client_instance.bot_loop:
                    asyncio.run_coroutine_threadsafe(
                        client_instance.api_send_group_text(group_openid, content),
                        client_instance.bot_loop
                    )
                self._send_json({"status": "success", "message": "群聊消息发送任务已提交"})
                return

            # 【新增 API】修改私聊用户昵称
            if path_part in ("/bot/api/set_user_nickname", "/bot/api/set_user_info"):
                user_id = data.get("user_id") or data.get("user_openid")
                nickname = data.get("nickname")
                info_dict = data.get("info_dict", {})

                if not user_id:
                    self._send_json({"status": "error", "message": "缺少 user_id 参数"}, code=400)
                    return

                # 构造要更新的用户信息对象
                update_payload = {}
                if nickname is not None:
                    update_payload["nickname"] = nickname
                if isinstance(info_dict, dict):
                    update_payload.update(info_dict)

                if not update_payload:
                    self._send_json({"status": "error", "message": "缺少要更新的用户信息字段 (如 nickname)"}, code=400)
                    return

                client_instance.data_mgr.set_user_info(str(user_id), update_payload)
                self._send_json({
                    "status": "success",
                    "message": "用户信息/昵称更新成功",
                    "user_id": str(user_id),
                    "updated": update_payload
                })
                return

            # 【新增 API】修改群聊备注/昵称
            if path_part == "/bot/api/set_group_nickname":
                group_id = data.get("group_id") or data.get("group_openid")
                nickname = data.get("nickname")

                if not group_id or nickname is None:
                    self._send_json({"status": "error", "message": "缺少 group_id 或 nickname 参数"}, code=400)
                    return

                client_instance.data_mgr.set_group_nickname(str(group_id), str(nickname))
                self._send_json({
                    "status": "success",
                    "message": "群聊别名/昵称更新成功",
                    "group_id": str(group_id),
                    "nickname": str(nickname)
                })
                return

            # 【新增 API】修改群聊标签/编号
            if path_part == "/bot/api/set_group_tag":
                group_id = data.get("group_id") or data.get("group_openid")
                grouptag = data.get("grouptag") or data.get("tag")

                if not group_id or grouptag is None:
                    self._send_json({"status": "error", "message": "缺少 group_id 或 grouptag 参数"}, code=400)
                    return

                client_instance.data_mgr.set_group_tag(str(group_id), str(grouptag))
                self._send_json({
                    "status": "success",
                    "message": "群聊标签/编号更新成功",
                    "group_id": str(group_id),
                    "grouptag": str(grouptag)
                })
                return

            # 保存/更新群聊完整配置
            if path_part == "/bot/api/set_group_info":
                group_id = data.get("group_id") or data.get("group_openid")
                info_dict = data.get("info_dict", {})

                if not group_id or not isinstance(info_dict, dict):
                    self._send_json({"status": "error", "message": "缺少 group_id 或有效的 info_dict 参数"}, code=400)
                    return

                client_instance.data_mgr.set_group_info(str(group_id), info_dict)
                self._send_json({
                    "status": "success",
                    "message": "群聊配置更新成功",
                    "group_id": str(group_id)
                })
                return

            # 设置并保存系统 OP 配置
            if path_part == "/bot/api/set_opsetting":
                setting_dict = data.get("opsetting")
                active = data.get("active")
                add_op_id = data.get("add_op")
                remove_op_id = data.get("remove_op")

                if setting_dict is not None and isinstance(setting_dict, dict):
                    client_instance.data_mgr.set_opsetting(setting_dict)
                if active is not None and isinstance(active, bool):
                    client_instance.data_mgr.set_system_active(active)
                if add_op_id:
                    client_instance.data_mgr.add_op(add_op_id)
                if remove_op_id:
                    client_instance.data_mgr.remove_op(remove_op_id)

                updated_opsetting = client_instance.data_mgr.get_opsetting()
                self._send_json({
                    "status": "success",
                    "message": "系统配置更新成功",
                    "data": updated_opsetting
                })
                return

            # 设置扩展自定义数据
            if path_part == "/bot/api/set_extra":
                key = data.get("key_name") or data.get("key")
                value = data.get("value")

                if not key:
                    self._send_json({"status": "error", "message": "缺少 key_name 或 key 参数"}, code=400)
                    return

                client_instance.data_mgr.set_extra_data(str(key), value)
                self._send_json({
                    "status": "success",
                    "message": f"扩展数据 [{key}] 保存成功"
                })
                return

            self.send_response(404)
            self.end_headers()

    # 启动 25567 端口服务线程
    threading.Thread(
        target=lambda: HTTPServer(('', 25567), ControlRequestHandler).serve_forever(),
        daemon=True
    ).start()
    logging.info("🌐 控制、API 与 Web 托管服务已启动 (端口 25567)")
