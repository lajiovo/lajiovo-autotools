import asyncio
import base64
import hashlib
import json
import logging
import os
import time
import aiohttp

import botpy
from botpy.message import C2CMessage, GroupMessage
from botpy.types.message import MarkdownPayload, MessageMarkdownParams

from config import (
    APP_ID,
    APP_SECRET,
    zConfig,
    BotDataManager,
    apply_sdk_patch,
)
from game import GameSystem
from opcmd import handle_op_command
from server import start_http_servers

# ------------------- 文件配置区 -------------------
TARGET_BOT_PREFIX = zConfig.get_config("bot.target_bot_prefix")

# 官方文件上传错误码映射表
UPLOAD_ERROR_MAP = {
    850018: "群被禁言或者机器人被禁言",
    850019: "不支持的文件格式",
    850026: "下载原始文件失败（请检查 URL 是否可访问或重试）",
    850027: "发送数据超时",
    850031: "上传文件超过大小限制",
    10000: "不支持的操作",
    40093001: "文件上传失败，请重试（BDH 通道异常）",
    40093002: "超过今天发送文件容量上限",
}
# --------------------------------------------------

apply_sdk_patch()


class YouzaiWSClient:
    """Yunzai / YouzaiBot 长连接 WebSocket 管理器，维持常驻在线与心跳机制"""

    def __init__(self, bot_client):
        self.bot_client = bot_client
        self.session = None
        self.ws = None
        self.is_connected = False
        self.self_id = 985211
        self._loop_task = None
        self._heartbeat_task = None
        self.active_listeners = []  # 正在等待响应的请求队列列表

    def _get_self_id(self):
        opsetting = self.bot_client.data_mgr.get_opsetting()
        configured_self_id = opsetting.get("youzai_self_id") or zConfig.get_config("bot.youzai_self_id", None)
        if configured_self_id and str(configured_self_id).isdigit():
            return int(configured_self_id)
        elif configured_self_id:
            return configured_self_id
        return 985211

    async def start(self):
        """启动长连接后台任务"""
        if not self._loop_task or self._loop_task.done():
            self._loop_task = asyncio.create_task(self._ws_maintain_loop())

    async def _ws_maintain_loop(self):
        """后台持续维护 WebSocket 保持长期在线"""
        ws_urls = [
            "ws://localhost:2536/OneBotv11",
            "ws://localhost:2536/GSUIDCore",
            "ws://localhost:2536/OPQBot",
            "ws://localhost:2536/ComWeChat",
            "ws://localhost:2536/",
        ]

        while True:
            try:
                if not self.session or self.session.closed:
                    self.session = aiohttp.ClientSession()

                ws = None
                for url in ws_urls:
                    try:
                        ws = await self.session.ws_connect(url, timeout=3.0)
                        if ws:
                            logging.info(f"🟢 [YouzaiBot] 成功建立持久 WebSocket 通信连接 ({url})")
                            break
                    except Exception:
                        continue

                if not ws:
                    await asyncio.sleep(5)
                    continue

                self.ws = ws
                self.is_connected = True
                self.self_id = self._get_self_id()

                # 发送 go-cqhttp 上线宣告与初始心跳
                await self._send_connect_meta()

                # 启动后台定期心跳协程
                if self._heartbeat_task and not self._heartbeat_task.done():
                    self._heartbeat_task.cancel()
                self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

                # 持续监听收包
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        try:
                            data = json.loads(msg.data)
                            await self._handle_incoming_packet(data)
                        except Exception as e:
                            logging.error(f"[YouzaiBot WS] 数据包处理异常: {e}")
                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        break

            except Exception as e:
                logging.warning(f"⚠️ [YouzaiBot WS] 连接中断: {e}")
            finally:
                self.is_connected = False
                self.ws = None
                if self._heartbeat_task and not self._heartbeat_task.done():
                    self._heartbeat_task.cancel()
                await asyncio.sleep(3)  # 3秒后尝试重连

    async def _send_connect_meta(self):
        if not self.ws or self.ws.closed:
            return
        now_ts = int(time.time())
        lifecycle_event = {
            "time": now_ts,
            "self_id": self.self_id,
            "post_type": "meta_event",
            "meta_event_type": "lifecycle",
            "sub_type": "connect",
        }
        heartbeat_event = {
            "time": now_ts,
            "self_id": self.self_id,
            "post_type": "meta_event",
            "meta_event_type": "heartbeat",
            "status": {
                "app_initialized": True,
                "app_enabled": True,
                "app_good": True,
                "online": True,
                "good": True,
            },
            "interval": 5000,
        }
        await self.ws.send_str(json.dumps(lifecycle_event))
        await self.ws.send_str(json.dumps(heartbeat_event))

    async def _heartbeat_loop(self):
        """每 5 秒自动推送心跳包，保持长连接处于 active 激活状态"""
        while self.is_connected and self.ws and not self.ws.closed:
            try:
                await asyncio.sleep(5)
                now_ts = int(time.time())
                heartbeat_event = {
                    "time": now_ts,
                    "self_id": self.self_id,
                    "post_type": "meta_event",
                    "meta_event_type": "heartbeat",
                    "status": {
                        "app_initialized": True,
                        "app_enabled": True,
                        "app_good": True,
                        "online": True,
                        "good": True,
                    },
                    "interval": 5000,
                }
                await self.ws.send_str(json.dumps(heartbeat_event))
            except Exception:
                break

    async def _handle_incoming_packet(self, data: dict):
        if not isinstance(data, dict):
            return

        # 1. 响应 Yunzai 对 Client 的 API 请求 (必须带 echo 才能解决 Yunzai 超时报错)
        if "action" in data and "echo" in data:
            action = data.get("action")
            echo = data.get("echo")

            parsed_reply = self.bot_client._parse_onebot_message(data)
            if parsed_reply:
                self._dispatch_to_listeners(parsed_reply)

            res_data = {}
            if action in ["get_login_info", "get_version_info"]:
                res_data = {
                    "user_id": self.self_id,
                    "nickname": "QQBot",
                    "app_name": "go-cqhttp",
                    "app_version": "v1.2.0",
                }
            elif action == "get_friend_list":
                res_data = []
            elif action == "get_group_list":
                res_data = [{"group_id": 97361482, "group_name": "Group_97361482"}]
            elif action == "get_group_member_list":
                res_data = [{"group_id": 97361482, "user_id": 53729962, "nickname": "53729962", "card": "", "role": "member"}]
            elif action == "get_group_info":
                res_data = {"group_id": 97361482, "group_name": "Group_97361482"}
            elif action == "get_group_member_info":
                res_data = {"group_id": 97361482, "user_id": 53729962, "nickname": "53729962", "card": "", "role": "member"}
            elif action in ["send_group_msg", "send_private_msg", "send_msg"]:
                res_data = {"message_id": int(time.time() * 1000) % 1000000}
            elif "list" in action or "map" in action.lower():
                res_data = []

            res_pkg = {
                "status": "ok",
                "retcode": 0,
                "data": res_data,
                "echo": echo,
            }
            if self.ws and not self.ws.closed:
                await self.ws.send_str(json.dumps(res_pkg))
            return

        # 2. 普通推包/回复解析
        parsed_reply = self.bot_client._parse_onebot_message(data)
        if parsed_reply:
            self._dispatch_to_listeners(parsed_reply)

    def _dispatch_to_listeners(self, reply):
        for listener_queue in self.active_listeners:
            listener_queue.put_nowait(reply)

    async def send_command(self, youzai_cmd: str, sender_openid: str, group_id: str = "", is_c2c: bool = False):
        if not self.is_connected or not self.ws or self.ws.closed:
            # 尝试快速等待 1 秒
            await asyncio.sleep(1)
            if not self.is_connected or not self.ws or self.ws.closed:
                return "❌ 无法连接到 YouzaiBot 服务 (ws://localhost:2536/)"

        user_id_num = self.bot_client._get_or_create_fake_user_id(sender_openid)
        group_id_num = (abs(hash(group_id)) % (10 ** 8) + 10000) if group_id else 0
        now_ts = int(time.time())

        # 构造并发送 OneBot v11 消息事件
        onebot_event = {
            "time": now_ts,
            "self_id": self.self_id,
            "post_type": "message",
            "message_type": "private" if is_c2c else "group",
            "sub_type": "friend" if is_c2c else "normal",
            "message_id": int(time.time() * 1000) % 1000000,
            "user_id": user_id_num,
            "message": youzai_cmd,
            "raw_message": youzai_cmd,
            "font": 0,
            "sender": {
                "user_id": user_id_num,
                "nickname": str(user_id_num),
                "card": "",
                "role": "member",
            },
        }
        if not is_c2c:
            onebot_event["group_id"] = group_id_num

        # 挂载局部监听队列收集响应
        listener_queue = asyncio.Queue()
        self.active_listeners.append(listener_queue)

        try:
            await self.ws.send_str(json.dumps(onebot_event))

            responses = []
            start_wait = time.time()

            # 循环收集响应消息 (最多等待 10 秒)
            while time.time() - start_wait < 10.0:
                try:
                    resp = await asyncio.wait_for(listener_queue.get(), timeout=2.5)
                    responses.append(resp)
                except asyncio.TimeoutError:
                    if responses:
                        break

            if not responses:
                return "⚠️ YouzaiBot 未返回任何响应消息"

            if len(responses) == 1:
                return responses[0]

            combined_texts = []
            for resp in responses:
                if isinstance(resp, dict):
                    return resp
                elif isinstance(resp, str):
                    combined_texts.append(resp)

            return "\n".join(combined_texts) if combined_texts else "⚠️ YouzaiBot 未返回有效文本"

        finally:
            if listener_queue in self.active_listeners:
                self.active_listeners.remove(listener_queue)


class MyClient(botpy.Client):

    # =========================================================================
    # 1. 初始化与生命周期
    # =========================================================================
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_time = time.time()  # 记录程序初始化开机时间戳
        self.bot_loop = None
        self.data_mgr = BotDataManager()
        self.game_sys = GameSystem(self.data_mgr)
        self.youzai_mgr = YouzaiWSClient(self)  # 初始化 YouzaiBot 长连接管理器
        self.processed_msg_ids = {}  # 消息 ID 去重字典 {msg_id: timestamp}
        self.msg_seq_map = {}        # msg_id 对应的 seq 递增字典 {msg_id: {"seq": int, "time": float}}

    async def on_ready(self):
        logging.info(f"robot 「{self.robot.name}」 已成功上线！")
        self.bot_loop = asyncio.get_running_loop()
        start_http_servers(self)
        await self.youzai_mgr.start()  # 启动 YouzaiBot 持久 WebSocket 通信任务
        await self.notify_group_3("🟢 机器人已上线并准备就绪！")

    # =========================================================================
    # 2. 核心 HTTP 底层请求封装与辅助函数
    # =========================================================================
    def _is_duplicate_msg(self, msg_id: str) -> bool:
        """检查消息 ID 是否在短时间内重复触发，若是则过滤处理"""
        if not msg_id:
            return False
        now = time.time()
        # 清理超过 60 秒的 msg_id 记录
        self.processed_msg_ids = {
            k: v for k, v in self.processed_msg_ids.items() if now - v < 60
        }
        if msg_id in self.processed_msg_ids:
            return True
        self.processed_msg_ids[msg_id] = now
        return False

    def _get_next_msg_seq(self, msg_id: str) -> int:
        """根据 msg_id 获取并自动递增下一个 msg_seq 序号，防止腾讯 40054005 消息去重拦截"""
        if not msg_id:
            return 1
        now = time.time()
        # 清理超过 300 秒的 msg_seq 记录
        self.msg_seq_map = {
            k: v for k, v in self.msg_seq_map.items() if now - v.get("time", 0) < 300
        }

        if msg_id not in self.msg_seq_map:
            self.msg_seq_map[msg_id] = {"seq": 1, "time": now}
            return 1
        else:
            self.msg_seq_map[msg_id]["seq"] += 1
            self.msg_seq_map[msg_id]["time"] = now
            return self.msg_seq_map[msg_id]["seq"]

    async def _raw_post(self, route_path: str, payload: dict, **path_params):
        """通用底层 HTTP POST 请求，绕过 SDK 强类型校验"""
        route = botpy.http.Route("POST", route_path, **path_params)
        http_client = getattr(self.api, "_http", None) or getattr(
            self, "_http", None
        )
        if not http_client:
            raise AttributeError("未能获取到 SDK 底层 _http 请求对象")
        return await http_client.request(route, json=payload)

    async def _raw_put(self, route_path: str, payload: dict, **path_params):
        """通用底层 HTTP PUT 请求，绕过 SDK 强类型校验"""
        route = botpy.http.Route("PUT", route_path, **path_params)
        http_client = getattr(self.api, "_http", None) or getattr(
            self, "_http", None
        )
        if not http_client:
            raise AttributeError("未能获取到 SDK 底层 _http 请求对象")
        return await http_client.request(route, json=payload)

    # =========================================================================
    # 3. 各种类型消息发送接口 (Text, Markdown, Image, Card, Panel/Menu)
    # =========================================================================
    def _save_base64_to_cache(self, base64_str: str) -> str:
        """解析 Base64 字符串并缓存至本地 ./temp_images 目录，返回本地文件路径"""
        try:
            os.makedirs("temp_images", exist_ok=True)

            clean_b64 = base64_str
            if "base64," in clean_b64:
                clean_b64 = clean_b64.split("base64,")[1]
            elif clean_b64.startswith("base64://"):
                clean_b64 = clean_b64[9:]
            clean_b64 = clean_b64.strip()

            img_bytes = base64.b64decode(clean_b64)
            img_hash = hashlib.md5(img_bytes).hexdigest()
            file_path = os.path.join("temp_images", f"{img_hash}.png")

            if not os.path.exists(file_path):
                with open(file_path, "wb") as f:
                    f.write(img_bytes)
                logging.info(f"💾 [图片已成功缓存至本地] 路径: {file_path} | 大小: {len(img_bytes) / 1024:.2f} KB")
            else:
                logging.info(f"⚡ [命中本地图片缓存] 路径: {file_path}")

            return file_path
        except Exception as e:
            logging.error(f"❌ [图片缓存至本地失败]: {e}")
            return ""

    # --- 文本/引用消息 ---
    async def send_group_text(
        self,
        group_openid: str,
        content: str,
        msg_id: str = "",
        ref_msg_id: str = None,
    ):
        """发送纯文本消息 (msg_type=0)，支持引用回复"""
        kwargs = {
            "group_openid": group_openid,
            "msg_type": 0,
            "content": content,
            "msg_id": msg_id,
        }
        if ref_msg_id:
            kwargs["message_reference"] = {"message_id": ref_msg_id}

        await self.api.post_group_message(**kwargs)
        logging.info(f"💬 [文本/引用消息发送成功] OpenID: {group_openid}")

    async def send_c2c_text(
        self,
        user_openid: str,
        content: str,
        msg_id: str = "",
        ref_msg_id: str = None,
    ):
        """发送单聊纯文本消息 (msg_type=0)，支持引用回复"""
        payload = {
            "msg_type": 0,
            "content": content,
        }
        if msg_id:
            payload["msg_id"] = msg_id
        if ref_msg_id:
            payload["message_reference"] = {"message_id": ref_msg_id}

        await self._raw_post(
            "/v2/users/{user_openid}/messages",
            payload,
            user_openid=user_openid,
        )
        logging.info(f"💬 [单聊文本消息发送成功] UserOpenID: {user_openid}")

    # --- Markdown & 内嵌键盘 ---
    async def send_group_markdown_by_content(
        self,
        group_openid: str,
        content: str,
        msg_id: str = "",
        keyboard: dict = None,
    ):
        """通过原生的 Markdown 文本内容发送群消息 (msg_type=2)，支持拼接内嵌键盘"""
        markdown = MarkdownPayload(content=content)
        kwargs = {
            "group_openid": group_openid,
            "msg_type": 2,
            "markdown": markdown,
            "msg_id": msg_id,
        }
        if keyboard:
            kwargs["keyboard"] = keyboard

        await self.api.post_group_message(**kwargs)
        logging.info(f"📢 [Markdown 发送成功] OpenID: {group_openid}")

    async def send_c2c_markdown_by_content(
        self,
        user_openid: str,
        content: str,
        msg_id: str = "",
        keyboard: dict = None,
    ):
        """通过原生的 Markdown 文本内容发送单聊消息 (msg_type=2)，支持拼接内嵌键盘"""
        payload = {
            "msg_type": 2,
            "markdown": {"content": content},
        }
        if msg_id:
            payload["msg_id"] = msg_id
        if keyboard:
            payload["keyboard"] = keyboard

        await self._raw_post(
            "/v2/users/{user_openid}/messages",
            payload,
            user_openid=user_openid,
        )
        logging.info(f"📢 [单聊 Markdown 发送成功] UserOpenID: {user_openid}")

    async def send_group_markdown_by_template(
        self,
        group_openid: str,
        template_id: str,
        params_dict: dict,
        msg_id: str = "",
        keyboard: dict = None,
    ):
        """通过自定义模板 ID 和参数列表发送 Markdown 消息"""
        params = [
            MessageMarkdownParams(key=k, values=v if isinstance(v, list) else [v])
            for k, v in params_dict.items()
        ]
        markdown = MarkdownPayload(
            custom_template_id=template_id, params=params
        )
        kwargs = {
            "group_openid": group_openid,
            "msg_type": 2,
            "markdown": markdown,
            "msg_id": msg_id,
        }
        if keyboard:
            kwargs["keyboard"] = keyboard

        await self.api.post_group_message(**kwargs)
        logging.info(f"📢 [Markdown 模板发送成功] OpenID: {group_openid}")

    # --- 富媒体图片发送 ---
    async def send_group_image(
        self,
        group_openid: str,
        file_path_or_url: str,
        content: str = "",
        msg_id: str = "",
        ref_msg_id: str = None,
    ):
        """支持本地路径、Base64 或网络 URL 发送群图片 (msg_type=7)"""
        # 如果传入的是 Base64 字符串，先缓存落盘为本地文件
        if (
            file_path_or_url.startswith("base64://")
            or "base64," in file_path_or_url
            or (
                not file_path_or_url.startswith("http")
                and not os.path.exists(file_path_or_url)
                and len(file_path_or_url) > 100
            )
        ):
            cached_path = self._save_base64_to_cache(file_path_or_url)
            if cached_path:
                file_path_or_url = cached_path

        logging.info(f"🖼️ 正在处理群图片发送 | OpenID: {group_openid} | 资源: {file_path_or_url}")

        try:
            upload_payload = {"file_type": 1, "srv_send_msg": False}

            if file_path_or_url.startswith("http://") or file_path_or_url.startswith(
                "https://"
            ):
                upload_payload["url"] = file_path_or_url
            else:
                if not os.path.exists(file_path_or_url):
                    err_msg = f"本地图片文件不存在: {file_path_or_url}"
                    logging.error(f"❌ [群图片发送失败] {err_msg}")
                    raise FileNotFoundError(err_msg)

                # 检查是否有外部 HTTP 静态服务配置
                opsetting = self.data_mgr.get_opsetting()
                public_server_url = opsetting.get("public_server_url") or zConfig.get_config("bot.public_server_url", None)

                if public_server_url and file_path_or_url.startswith("temp_images"):
                    filename = os.path.basename(file_path_or_url)
                    file_http_url = f"{public_server_url.rstrip('/')}/temp_images/{filename}"
                    upload_payload["url"] = file_http_url
                    logging.info(f"🌐 [使用公网 HTTP URL 方案上传图片]: {file_http_url}")
                else:
                    with open(file_path_or_url, "rb") as f:
                        file_base64 = base64.b64encode(f.read()).decode("utf-8")
                    upload_payload["file_data"] = file_base64

            upload_res = await self._raw_post(
                "/v2/groups/{group_openid}/files",
                upload_payload,
                group_openid=group_openid,
            )

            # 解析上传响应结果并打印详细信息
            logging.debug(f"🔍 [群文件上传响应原始数据]: {upload_res}")

            file_info = None
            if isinstance(upload_res, dict):
                err_code = upload_res.get("code")
                if err_code and err_code != 0:
                    err_desc = UPLOAD_ERROR_MAP.get(
                        err_code, upload_res.get("message", "未知上传错误")
                    )
                    logging.error(
                        f"❌ [群图片上传被拒绝] 错误码: {err_code} ({err_desc}) | 提示信息: {upload_res.get('message', '')}"
                    )
                    raise RuntimeError(f"群文件上传失败 [{err_code}]: {err_desc}")

                file_info = upload_res.get("file_info")
                file_uuid = upload_res.get("file_uuid", "N/A")
                ttl = upload_res.get("ttl", "N/A")
                logging.info(
                    f"✅ [群文件上传成功] UUID: {file_uuid} | TTL: {ttl}s"
                )
            else:
                file_info = getattr(upload_res, "file_info", upload_res)

            if not file_info:
                logging.error(f"❌ [群图片上传异常] 响应中未包含有效的 file_info 字段: {upload_res}")
                raise ValueError("上传接口未返回有效的 file_info")

            # 组装发送消息请求
            seq = self._get_next_msg_seq(msg_id)
            kwargs = {
                "group_openid": group_openid,
                "msg_type": 7,
                "msg_id": msg_id,
                "msg_seq": seq,
                "media": {"file_info": file_info},
            }
            if ref_msg_id:
                kwargs["message_reference"] = {"message_id": ref_msg_id}

            send_res = await self.api.post_group_message(**kwargs)
            logging.info(f"🖼️ [富媒体图片发送成功] OpenID: {group_openid}")
            return send_res

        except Exception as e:
            logging.error(
                f"❌ [群富媒体图片发送失败] OpenID: {group_openid} | 异常详情: {e}",
                exc_info=True,
            )
            # 降级兜底方案：如果图片发送失败，且有附带的文字，则尝试发送纯文字
            if content:
                logging.info("⚠️ 图片发送失败，触发文本降级保底机制...")
                await self.send_group_text(group_openid, f"[图片发送失败] {content}", msg_id)
            raise

    async def send_c2c_image(
        self,
        user_openid: str,
        file_path_or_url: str,
        content: str = "",
        msg_id: str = "",
        ref_msg_id: str = None,
    ):
        """支持本地路径、Base64 或网络 URL 发送单聊图片 (msg_type=7)"""
        if (
            file_path_or_url.startswith("base64://")
            or "base64," in file_path_or_url
            or (
                not file_path_or_url.startswith("http")
                and not os.path.exists(file_path_or_url)
                and len(file_path_or_url) > 100
            )
        ):
            cached_path = self._save_base64_to_cache(file_path_or_url)
            if cached_path:
                file_path_or_url = cached_path

        logging.info(f"🖼️ 正在处理单聊图片发送: {file_path_or_url}")

        if file_path_or_url.startswith("http://") or file_path_or_url.startswith(
            "https://"
        ):
            upload_res = await self._raw_post(
                "/v2/users/{user_openid}/files",
                {"file_type": 1, "url": file_path_or_url},
                user_openid=user_openid,
            )
        else:
            if not os.path.exists(file_path_or_url):
                raise FileNotFoundError(f"本地图片不存在: {file_path_or_url}")

            with open(file_path_or_url, "rb") as f:
                file_base64 = base64.b64encode(f.read()).decode("utf-8")

            upload_payload = {"file_type": 1, "file_data": file_base64}
            upload_res = await self._raw_post(
                "/v2/users/{user_openid}/files",
                upload_payload,
                user_openid=user_openid,
            )

        file_info = (
            upload_res.get("file_info")
            if isinstance(upload_res, dict)
            else getattr(upload_res, "file_info", upload_res)
        )

        seq = self._get_next_msg_seq(msg_id)
        payload = {
            "msg_type": 7,
            "msg_seq": seq,
            "media": {"file_info": file_info},
        }
        if msg_id:
            payload["msg_id"] = msg_id
        if ref_msg_id:
            payload["message_reference"] = {"message_id": ref_msg_id}

        await self._raw_post(
            "/v2/users/{user_openid}/messages",
            payload,
            user_openid=user_openid,
        )
        logging.info(f"🖼️ [单聊富媒体图片发送成功] UserOpenID: {user_openid}")

    # --- 图文卡片 ---
    async def send_group_card(
        self,
        group_openid: str,
        title: str,
        desc: str,
        pic_url: str,
        jump_url: str,
        msg_id: str = "",
    ):
        """发送图文卡片消息 (msg_type=8)"""
        payload = {
            "msg_type": 8,
            "card": {
                "type": "tuwen",
                "content": {
                    "title": title,
                    "description": desc,
                    "pic_url": pic_url,
                    "url": jump_url,
                },
            },
        }
        if msg_id:
            payload["msg_id"] = msg_id

        await self._raw_post(
            "/v2/groups/{group_openid}/messages",
            payload,
            group_openid=group_openid,
        )
        logging.info(f"🃏 [图文卡片发送成功] OpenID: {group_openid}")

    # --- 指令面板 & 自定义菜单 ---
    async def create_panel(
        self,
        scope: str,
        panel: dict,
        target_type: str = "all",
        user_openids: list = None,
        group_openids: list = None,
    ):
        """创建指令面板，仅支持 c2c 和 group 场景"""
        if scope not in ["c2c", "group"]:
            raise ValueError("仅支持 c2c 或 group 场景创建面板")

        payload = {
            "scope": scope,
            "target_type": target_type,
            "panel": panel,
        }
        if scope == "c2c" and target_type == "specific" and user_openids:
            payload["user_openids"] = user_openids
        elif scope == "group" and target_type == "specific" and group_openids:
            payload["group_openids"] = group_openids

        res = await self._raw_post("/v2/panels", payload)
        logging.info(f"📋 [创建指令面板成功] Scope: {scope}, Response: {res}")
        return res

    async def set_c2c_menu(self, menu: dict):
        """修改 C2C 全局自定义菜单"""
        payload = {"menu": menu}
        res = await self._raw_put("/v2/menu", payload)
        logging.info(f"📌 [修改C2C自定义菜单成功] Response: {res}")
        return res

    # =========================================================================
    # 4. SERVER / 外部调用与系统辅助
    # =========================================================================
    def _get_or_create_fake_user_id(self, user_openid: str) -> int:
        """获取或随机生成用户的符合条件的假用户 ID (8 位数字)，并通过 data_mgr 接口持久化落盘"""
        if not user_openid:
            return 100001

        user_info = self.data_mgr.get_user_info(user_openid) or {}
        fake_id = user_info.get("fake_user_id")

        if not fake_id:
            import random
            fake_id = random.randint(10000000, 99999999)

            user_info["fake_user_id"] = fake_id
            self.data_mgr.set_user_info(user_openid, user_info)

            user_data = self.data_mgr.get_user_data(user_openid) or {}
            user_data["fake_user_id"] = fake_id
            self.data_mgr.set_user_data(user_openid, user_data)

        return int(fake_id)

    async def call_youzaibot(
        self,
        youzai_cmd: str,
        sender_openid: str,
        group_id: str = "",
        is_c2c: bool = False,
    ):
        """通过常驻长连接 WebSocket 发送指令给 YouzaiBot"""
        return await self.youzai_mgr.send_command(
            youzai_cmd=youzai_cmd,
            sender_openid=sender_openid,
            group_id=group_id,
            is_c2c=is_c2c,
        )

    def _parse_onebot_message(self, data: dict):
        """解析 OneBot v11 响应数据包，提取文本或富媒体内容"""
        import re

        raw_msg = None
        if isinstance(data, dict):
            if data.get("action") in [
                "send_group_msg",
                "send_private_msg",
                "send_msg",
            ]:
                raw_msg = data.get("params", {}).get("message")
            elif "reply" in data:
                raw_msg = data.get("reply")
            elif "message" in data:
                raw_msg = data.get("message")

        if not raw_msg:
            return None

        text_parts = []
        image_url = None

        if isinstance(raw_msg, str):
            img_match = re.search(
                r"\[CQ:image,[^\]]*?(?:file|url)=([^,\]]+)[^\]]*\]", raw_msg
            )
            if img_match:
                image_url = img_match.group(1)

            clean_text = re.sub(r"\[CQ:[^\]]+\]", "", raw_msg).strip()
            if clean_text:
                text_parts.append(clean_text)

        elif isinstance(raw_msg, list):
            for seg in raw_msg:
                if not isinstance(seg, dict):
                    continue
                seg_type = seg.get("type")
                seg_data = seg.get("data", {})
                if seg_type == "text":
                    text_parts.append(seg_data.get("text", ""))
                elif seg_type == "image":
                    image_url = seg_data.get("url") or seg_data.get("file")

        full_text = "\n".join(text_parts).strip()

        if image_url:
            return {"msg_type": 7, "url": image_url, "content": full_text}
        elif full_text:
            return full_text
        return None

    def _get_group_openid_by_num(self, target_group_num, opsetting: dict = None):
        """获取指定编号对应的群 OpenID
        查找优先级：优先从 opsetting["group_tags"] 读取，其次从 groupinfo (get_group_list/get_group_tag) 读取
        """
        if target_group_num is None:
            return None

        eff_str = str(target_group_num)
        if opsetting is None:
            opsetting = self.data_mgr.get_opsetting()

        group_tags = opsetting.get("group_tags", {})
        if isinstance(group_tags, dict):
            if eff_str in group_tags and isinstance(group_tags[eff_str], str):
                return group_tags[eff_str]
            for gid, tag in group_tags.items():
                if str(tag) == eff_str:
                    return gid

        group_list = self.data_mgr.get_group_list()
        for g_info in group_list:
            gid = g_info.get("group_id")
            tag_num = g_info.get("tag_num")
            grouptag = g_info.get("grouptag")
            direct_tag = self.data_mgr.get_group_tag(gid) if gid else ""

            if (
                (tag_num is not None and str(tag_num) == eff_str)
                or (grouptag is not None and str(grouptag) == eff_str)
                or (direct_tag and str(direct_tag) == eff_str)
            ):
                return gid

        return None

    async def notify_group_3(self, message: str):
        """上下线通知群（从 opsetting 读取提醒群编号，默认群 3；优先 opsetting 读取 group_tags，其次 groupinfo）"""
        opsetting = self.data_mgr.get_opsetting()
        target_group_num = opsetting.get("notify_group_num", 3)

        target_openid = self._get_group_openid_by_num(target_group_num, opsetting)

        if target_openid:
            try:
                await self.api.post_group_message(
                    group_openid=target_openid, msg_type=0, content=message
                )
                logging.info(
                    f"📢 [群{target_group_num}通知成功] 内容: {message}"
                )
            except Exception as e:
                logging.error(
                    f"❌ 发送群 {target_group_num} 通知失败: {e}"
                )
        else:
            logging.info(
                f"ℹ️ 未绑定【群 {target_group_num}】，跳过通知。"
            )

    async def shutdown_system(self, reason: str = "系统下线"):
        logging.info(f"🛑 正在执行系统退出程序... 原因: {reason}")
        await self.notify_group_3(
            f"🔴 机器人收到下线指令 ({reason})，正在退出..."
        )
        await asyncio.sleep(1)
        os._exit(0)

    async def push_message_to_group(
        self, msg_content: str, target_group_num: str = None
    ):
        """推送消息到指定群，接入新版 data_mgr 协议"""
        push_active = self.data_mgr.get_extra_data("push_active", True)
        if not push_active:
            logging.info("ℹ️ Push 功能已关闭，跳过推送。")
            return

        opsetting = self.data_mgr.get_opsetting()
        default_push_group = opsetting.get("push_target_group", None)

        target_openid, warning_msg = None, ""
        effective_group_num = target_group_num or default_push_group

        if effective_group_num:
            target_openid = self._get_group_openid_by_num(effective_group_num, opsetting)

        if not target_openid:
            target_openid = self._get_group_openid_by_num(1, opsetting)

            if effective_group_num and target_openid:
                warning_msg = f"\n\n⚠️ [系统提示] 未找到绑定的群 {effective_group_num}，已默认推送至群 1"

        if not target_openid:
            logging.error(
                f"❌ 推送失败：未找到群 {effective_group_num}，且数据库中未绑定【群 1】。"
            )
            return

        full_content = f"{msg_content}{warning_msg}"

        self.data_mgr.append_push_history({
            "target_group": effective_group_num,
            "target_openid": target_openid,
            "content": full_content,
            "role": "push",
        })

        try:
            await self.api.post_group_message(
                group_openid=target_openid,
                msg_type=0,
                content=full_content,
            )
            logging.info(f"📢 [推送成功] OpenID: {target_openid}")

        except Exception as e:
            logging.error(f"❌ 推送消息被拒收/失败: {e}")

    # =========================================================================
    # 5. 指令处理与统一回复分发逻辑
    # =========================================================================
    def handle_op_command(
        self,
        args: list,
        sender_openid: str,
        raw_message: object,
        group_id: str,
    ):
        return handle_op_command(self, args, sender_openid, raw_message, group_id)

    async def send_reply(
        self, res: dict, target_id: str, msg_id: str, is_c2c: bool = False
    ):
        """统一合并的回复发送函数，根据 res 数据字典中的 msg_type 参数分发逻辑"""
        msg_type = res.get("msg_type", 0)
        reply_content = res.get("content", "")

        if msg_type == 2:
            if is_c2c:
                await self.send_c2c_markdown_by_content(
                    user_openid=target_id,
                    content=reply_content,
                    msg_id=msg_id,
                    keyboard=res.get("keyboard"),
                )
            else:
                await self.send_group_markdown_by_content(
                    group_openid=target_id,
                    content=reply_content,
                    msg_id=msg_id,
                    keyboard=res.get("keyboard"),
                )
        elif msg_type == 7:
            if is_c2c:
                await self.send_c2c_image(
                    user_openid=target_id,
                    file_path_or_url=res.get("url") or res.get("file_path"),
                    content=reply_content,
                    msg_id=msg_id,
                )
            else:
                await self.send_group_image(
                    group_openid=target_id,
                    file_path_or_url=res.get("url") or res.get("file_path"),
                    content=reply_content,
                    msg_id=msg_id,
                )
        elif msg_type == 8:
            card = res.get("card", {})
            card_content = card.get("content", {})
            reply_content = card_content.get("title", "")
            if is_c2c:
                await self.send_c2c_text(
                    user_openid=target_id,
                    content=reply_content,
                    msg_id=msg_id,
                )
            else:
                await self.send_group_card(
                    group_openid=target_id,
                    title=card_content.get("title", ""),
                    desc=card_content.get("description", ""),
                    pic_url=card_content.get("pic_url", ""),
                    jump_url=card_content.get("url", ""),
                    msg_id=msg_id,
                )
        else:
            if is_c2c:
                await self.send_c2c_text(
                    user_openid=target_id, content=reply_content, msg_id=msg_id
                )
            else:
                await self.send_group_text(
                    group_openid=target_id,
                    content=reply_content,
                    msg_id=msg_id,
                )

        if reply_content:
            if is_c2c:
                self.data_mgr.append_c2c_message(
                    user_id=target_id, content=reply_content, role="assistant"
                )
            else:
                self.data_mgr.append_group_message(
                    group_id=target_id, user_id="BOT", content=reply_content, role="assistant"
                )

    async def process_command(
        self,
        content: str,
        sender_openid: str,
        raw_message: object,
        group_id: str,
        is_c2c: bool = False,
    ):
        target_id = sender_openid if is_c2c else group_id

        # 针对 #y 开头的指令处理：自动截取 #y 之后的内容 (xxx) 转发给 YouzaiBot
        if content.lower().startswith("#y"):
            youzai_cmd = content[2:].strip()
            youzai_res = await self.call_youzaibot(
                youzai_cmd, sender_openid, group_id=group_id, is_c2c=is_c2c
            )
            if isinstance(youzai_res, dict):
                await self.send_reply(
                    youzai_res, target_id, raw_message.id, is_c2c=is_c2c
                )
                return None
            return youzai_res

        parts = content[1:].strip().split()
        cmd = parts[0].lower() if parts else ""

        if cmd == "op":
            op_res = self.handle_op_command(
                parts[1:], sender_openid, raw_message, group_id
            )
            if asyncio.iscoroutine(op_res):
                op_res = await op_res

            if isinstance(op_res, dict):
                await self.send_reply(
                    op_res, target_id, raw_message.id, is_c2c=is_c2c
                )
                return None
            return op_res

        if cmd == "ping":
            elapsed_seconds = int(time.time() - self.start_time)
            days, remainder = divmod(elapsed_seconds, 86400)
            hours, remainder = divmod(remainder, 3600)
            minutes, seconds = divmod(remainder, 60)

            uptime_str = ""
            if days > 0:
                uptime_str += f"{days}天"
            if hours > 0 or days > 0:
                uptime_str += f"{hours}小时"
            if minutes > 0 or hours > 0 or days > 0:
                uptime_str += f"{minutes}分"
            uptime_str += f"{seconds}秒"

            system_active = self.data_mgr.is_system_active()
            status_text = "正常开启" if system_active else "暂停维护中"
            return (
                f"Pong! 机器人正常运行中 ⚡\n当前服务状态：{status_text}\n已连续运行：{uptime_str}"
            )

        if not self.data_mgr.is_system_active():
            return None

        game_res = self.game_sys.handle_command(cmd, parts, sender_openid)

        if isinstance(game_res, dict):
            await self.send_reply(game_res, target_id, raw_message.id, is_c2c=is_c2c)
            return None

        return game_res

    # =========================================================================
    # 6. 事件接收与回调处理 (群消息 & 私聊消息)
    # =========================================================================
    def _extract_message_extra(self, message: object) -> dict:
        """从单聊/群聊消息事件对象中提取丰富的结构化元数据"""
        def _to_dict(obj):
            if isinstance(obj, dict):
                return obj
            if hasattr(obj, "__dict__"):
                return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
            return {}

        raw = _to_dict(message)
        
        msg_type = getattr(message, "message_type", raw.get("message_type", 0)) or 0
        timestamp = getattr(message, "timestamp", raw.get("timestamp", ""))
        
        scene_obj = getattr(message, "message_scene", raw.get("message_scene"))
        scene_dict = _to_dict(scene_obj) if scene_obj else {}
        ext_list = getattr(scene_obj, "ext", scene_dict.get("ext", [])) or []
        scene_ext = {}
        for item in ext_list:
            if isinstance(item, str) and "=" in item:
                k, v = item.split("=", 1)
                scene_ext[k.strip()] = v.strip()

        author_obj = getattr(message, "author", raw.get("author"))
        author_dict = _to_dict(author_obj) if author_obj else {}
        username = getattr(author_obj, "username", author_dict.get("username", ""))
        member_role = getattr(author_obj, "member_role", author_dict.get("member_role", "member"))
        is_bot = getattr(author_obj, "bot", author_dict.get("bot", False))

        mentions_raw = getattr(message, "mentions", raw.get("mentions", [])) or []
        mentions = []
        for m in mentions_raw:
            m_dict = _to_dict(m)
            mentions.append({
                "id": getattr(m, "id", m_dict.get("id", "")),
                "username": getattr(m, "username", m_dict.get("username", "")),
                "bot": getattr(m, "bot", m_dict.get("bot", False)),
            })

        attachments_raw = getattr(message, "attachments", raw.get("attachments", [])) or []
        attachments = []
        for att in attachments_raw:
            att_dict = _to_dict(att)
            attachments.append({
                "url": getattr(att, "url", att_dict.get("url", "")),
                "filename": getattr(att, "filename", att_dict.get("filename", "")),
                "content_type": getattr(att, "content_type", att_dict.get("content_type", "")),
                "size": getattr(att, "size", att_dict.get("size", 0)),
                "width": getattr(att, "width", att_dict.get("width", 0)),
                "height": getattr(att, "height", att_dict.get("height", 0)),
                "voice_wav_url": getattr(att, "voice_wav_url", att_dict.get("voice_wav_url", "")),
                "asr_refer_text": getattr(att, "asr_refer_text", att_dict.get("asr_refer_text", "")),
            })

        ark_obj = getattr(message, "ark_data", raw.get("ark_data"))
        ark_data = {}
        if ark_obj:
            ark_dict = _to_dict(ark_obj)
            ark_data = {
                "prompt": getattr(ark_obj, "prompt", ark_dict.get("prompt", "")),
                "ark_type": getattr(ark_obj, "ark_type", ark_dict.get("ark_type", "")),
                "ark_name": getattr(ark_obj, "ark_name", ark_dict.get("ark_name", "")),
                "fields": getattr(ark_obj, "fields", ark_dict.get("fields", {})),
            }

        elements_raw = getattr(message, "msg_elements", raw.get("msg_elements", [])) or []
        msg_elements = []
        for elem in elements_raw:
            elem_dict = _to_dict(elem)
            msg_elements.append({
                "msg_idx": getattr(elem, "msg_idx", elem_dict.get("msg_idx", "")),
                "message_type": getattr(elem, "message_type", elem_dict.get("message_type", 0)),
                "content": getattr(elem, "content", elem_dict.get("content", "")),
            })

        return {
            "message_type": msg_type,
            "timestamp": timestamp,
            "username": username,
            "member_role": member_role,
            "is_bot": is_bot,
            "mentions": mentions,
            "scene_ext": scene_ext,
            "msg_idx": scene_ext.get("msg_idx", ""),
            "ref_msg_idx": scene_ext.get("ref_msg_idx", ""),
            "auth_token": scene_ext.get("auth_token", ""),
            "attachments": attachments,
            "ark_data": ark_data,
            "msg_elements": msg_elements,
        }

    async def _handle_group_msg(self, message: GroupMessage, event_name: str):
        content = getattr(message, "content", "").strip()
        group_id = getattr(message, "group_openid", "")
        msg_id = getattr(message, "id", "")

        # 消息接收去重，防止 SDK 重复触发
        if self._is_duplicate_msg(msg_id):
            logging.info(f"⚡ [跳过重复群消息事件] msg_id: {msg_id}")
            return

        author = getattr(message, "author", None)
        sender_openid = (
            getattr(author, "member_openid", "未知用户") if author else "未知用户"
        )
        sender_openid = sender_openid.upper()

        extra = self._extract_message_extra(message)
        
        full_content = content
        if extra["ark_data"]:
            ark = extra["ark_data"]
            title = ark.get("fields", {}).get("title") or ark.get("prompt") or ""
            full_content = f"[卡片:{ark.get('ark_name','未知卡片')}] {title} {content}".strip()
        elif extra["msg_elements"]:
            ref_texts = [e["content"] for e in extra["msg_elements"] if e.get("content")]
            if ref_texts:
                full_content = f"[引用/合并消息: \"{' | '.join(ref_texts)}\"] {content}".strip()
        elif extra["attachments"]:
            att_descs = []
            for att in extra["attachments"]:
                if att.get("asr_refer_text"):
                    att_descs.append(f"[语音: {att['asr_refer_text']}]")
                elif "image" in att.get("content_type", ""):
                    att_descs.append(f"[图片: {att.get('url','')}]")
                else:
                    att_descs.append(f"[文件: {att.get('filename','')}]")
            full_content = f"{' '.join(att_descs)} {content}".strip()

        logging.info(
            f"[{event_name}] 群消息 | 群ID: {group_id} | 发送者: {sender_openid} "
            f"({extra.get('username') or '无昵称'} | 角色: {extra['member_role']}) | 类型: {extra['message_type']} | "
            f"msg_idx: {extra['msg_idx']} | 内容: {full_content}"
        )

        if full_content:
            self.data_mgr.append_group_message(
                group_id=group_id, user_id=sender_openid, content=full_content, role="user"
            )

        if content.startswith(TARGET_BOT_PREFIX):
            content = content[len(TARGET_BOT_PREFIX) :].strip()

        if content.startswith("/#"):
            content = "#" + content[2:].lstrip("#").strip()
        elif content.startswith(("#", "/")):
            content = "#" + content[1:].lstrip("#").strip()

        if content.startswith("#"):
            reply_text = await self.process_command(
                content, sender_openid, message, group_id, is_c2c=False
            )
            if reply_text:
                try:
                    await self.api.post_group_message(
                        group_openid=group_id, msg_type=0, msg_id=msg_id, content=reply_text
                    )
                    self.data_mgr.append_group_message(
                        group_id=group_id, user_id="BOT", content=reply_text, role="assistant"
                    )
                except Exception as e:
                    logging.error(f"指令回复失败: {e}")

    async def _handle_c2c_msg(self, message: C2CMessage, event_name: str):
        content = getattr(message, "content", "").strip()
        msg_id = getattr(message, "id", "")

        # 消息接收去重，防止 SDK 重复触发
        if self._is_duplicate_msg(msg_id):
            logging.info(f"⚡ [跳过重复单聊消息事件] msg_id: {msg_id}")
            return

        author = getattr(message, "author", None)
        sender_openid = (
            getattr(author, "user_openid", "未知用户") if author else "未知用户"
        )
        sender_openid = sender_openid.upper()

        extra = self._extract_message_extra(message)
        
        full_content = content
        if extra["ark_data"]:
            ark = extra["ark_data"]
            title = ark.get("fields", {}).get("title") or ark.get("prompt") or ""
            full_content = f"[卡片:{ark.get('ark_name','未知卡片')}] {title} {content}".strip()
        elif extra["msg_elements"]:
            ref_texts = [e["content"] for e in extra["msg_elements"] if e.get("content")]
            if ref_texts:
                full_content = f"[引用/合并消息: \"{' | '.join(ref_texts)}\"] {content}".strip()
        elif extra["attachments"]:
            att_descs = []
            for att in extra["attachments"]:
                if att.get("asr_refer_text"):
                    att_descs.append(f"[语音: {att['asr_refer_text']}]")
                elif "image" in att.get("content_type", ""):
                    att_descs.append(f"[图片: {att.get('url','')}]")
                else:
                    att_descs.append(f"[文件: {att.get('filename','')}]")
            full_content = f"{' '.join(att_descs)} {content}".strip()

        logging.info(
            f"[{event_name}] 单聊消息 | 发送者: {sender_openid} "
            f"({extra.get('username') or '无昵称'}) | 类型: {extra['message_type']} | "
            f"msg_idx: {extra['msg_idx']} | ref_msg_idx: {extra['ref_msg_idx']} | "
            f"内容: {full_content}"
        )

        if full_content:
            self.data_mgr.append_c2c_message(
                user_id=sender_openid, content=full_content, role="user"
            )

        if content.startswith("/#"):
            content = "#" + content[2:].lstrip("#").strip()
        elif content.startswith(("#", "/")):
            content = "#" + content[1:].lstrip("#").strip()

        if content.startswith("#"):
            reply_text = await self.process_command(
                content, sender_openid, message, "", is_c2c=True
            )
            if reply_text:
                try:
                    await self.send_c2c_text(
                        user_openid=sender_openid, content=reply_text, msg_id=msg_id
                    )
                    self.data_mgr.append_c2c_message(
                        user_id=sender_openid, content=reply_text, role="assistant"
                    )
                except Exception as e:
                    logging.error(f"单聊指令回复失败: {e}")

    async def on_c2c_message_create(self, message: C2CMessage):
        await self._handle_c2c_msg(message, "on_c2c_message_create")

    async def on_group_at_message_create(self, message: GroupMessage):
        await self._handle_group_msg(message, "on_group_at_message_create")

    async def on_group_message_create(self, message: GroupMessage):
        await self._handle_group_msg(message, "on_group_message_create")


# =========================================================================
# 程序入口
# =========================================================================
if __name__ == "__main__":
    intents = botpy.Intents(public_messages=True, direct_message=True)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    client = MyClient(intents=intents)
    client.run(appid=APP_ID, secret=APP_SECRET)