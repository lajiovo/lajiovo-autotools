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
    """
    启动 25567 端口的 Web 控制台与 API 服务。
    参数 client_instance: 包含 data_mgr (BotDataManager 实例) 及 bot_loop 的客户端对象。
    """

    class ControlRequestHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            # 禁用默认的标准 HTTP 日志输出，避免控制台刷屏
            pass

        def _send_json(self, data, code=200):
            """统一构建 JSON 格式响应，并添加防缓存 Header"""
            self.send_response(code)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

        def _verify_auth(self, input_key=None):
            """校验 API 访问凭证：比对传入明文与 key.json 中的明文密钥"""
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

            # ---------------- 2. /push 接口 (免密推送) ----------------
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
                status_info = client_instance.data_mgr.check_has_new_message(reset=reset)
                self._send_json({"status": "success", "data": status_info})
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

            # 读取全量推送历史
            if path_part == "/bot/api/push_history":
                push_history = client_instance.data_mgr.get_pushhistory()
                self._send_json({"status": "success", "data": push_history})
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