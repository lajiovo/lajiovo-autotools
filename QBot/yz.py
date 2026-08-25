import asyncio
import base64
import hashlib
import json
import logging
import os
import random
import time
import aiohttp


class YouzaiWSClient:
    """YouzaiBot (Yunzai / GSUIDCore) 按需 WebSocket 连接与内容处理器"""

    def __init__(self, bot_client):
        self.bot = bot_client
        self.ws_url = "ws://localhost:2536/OneBotv11"
        self.default_self_id = 985211

    # =========================================================================
    # 1. 假 ID 生成与持久化
    # =========================================================================
    def get_or_create_fake_user_id(self, user_openid: str) -> int:
        """为每个用户生成一个随机且持久化落盘的 8 位数字假 ID"""
        if not user_openid:
            return 10000000

        user_info = self.bot.data_mgr.get_user_info(user_openid) or {}
        user_data = self.bot.data_mgr.get_user_data(user_openid) or {}

        fake_id = user_info.get("fake_user_id") or user_data.get("fake_user_id")
        if fake_id and str(fake_id).isdigit():
            return int(fake_id)

        fake_id = random.randint(10000000, 99999999)

        user_info["fake_user_id"] = fake_id
        user_data["fake_user_id"] = fake_id

        self.bot.data_mgr.set_user_info(user_openid, user_info)
        self.bot.data_mgr.set_user_data(user_openid, user_data)

        logging.info(f"👤 [假 ID 映射生成] OpenID: {user_openid} -> FakeID: {fake_id}")
        return fake_id

    def get_or_create_fake_group_id(self, group_openid: str) -> int:
        """为每个群聊生成一个随机且持久化落盘的 8 位数字假 ID"""
        if not group_openid:
            return 90000000

        group_info = self.bot.data_mgr.get_group_info(group_openid) or {}
        fake_id = group_info.get("fake_group_id")

        if fake_id and str(fake_id).isdigit():
            return int(fake_id)

        fake_id = random.randint(10000000, 99999999)
        group_info["fake_group_id"] = fake_id
        self.bot.data_mgr.set_group_info(group_openid, group_info)

        logging.info(f"👥 [群假 ID 映射生成] GroupOpenID: {group_openid} -> FakeGroupID: {fake_id}")
        return fake_id

    def _get_self_id(self):
        """获取并规范化 self_id"""
        opsetting = self.bot.data_mgr.get_opsetting()
        val = opsetting.get("youzai_self_id", self.default_self_id)
        if isinstance(val, str) and val.isdigit():
            return int(val)
        return val

    # =========================================================================
    # 2. 按需连接与消息发送 (统一返回带 msg_type 的标准字典)
    # =========================================================================
    async def send_command(
        self,
        command_text: str,
        sender_openid: str,
        raw_message: object,
        group_id: str = "",
        is_c2c: bool = False,
    ) -> dict:
        """触发 #y 时建立连接，发送指令并等待响应，统一返回符合 main.py 发送规范的字典结构"""
        fake_user_id = self.get_or_create_fake_user_id(sender_openid)
        fake_group_id = self.get_or_create_fake_group_id(group_id) if not is_c2c else 0
        self_id = self._get_self_id()

        now = int(time.time())
        msg_id_num = int(hashlib.md5(f"{raw_message.id}".encode()).hexdigest()[:8], 16) % 1000000

        # 构建 OneBot v11 消息事件体
        if is_c2c:
            onebot_event = {
                "time": now,
                "self_id": self_id,
                "post_type": "message",
                "message_type": "private",
                "sub_type": "friend",
                "message_id": msg_id_num,
                "user_id": fake_user_id,
                "message": command_text,
                "raw_message": command_text,
                "font": 0,
                "sender": {
                    "user_id": fake_user_id,
                    "nickname": f"User_{str(fake_user_id)[-4:]}",
                },
            }
        else:
            onebot_event = {
                "time": now,
                "self_id": self_id,
                "post_type": "message",
                "message_type": "group",
                "sub_type": "normal",
                "message_id": msg_id_num,
                "user_id": fake_user_id,
                "message": command_text,
                "raw_message": command_text,
                "font": 0,
                "sender": {
                    "user_id": fake_user_id,
                    "nickname": f"User_{str(fake_user_id)[-4:]}",
                    "card": "",
                    "role": "member",
                },
                "group_id": fake_group_id,
            }

        logging.info(f"🔌 正在尝试连接 YouzaiBot WebSocket ({self.ws_url})...")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(self.ws_url, timeout=5.0) as ws:
                    logging.info("✅ 连接成功，发送握手与消息...")
                    # 1. 模拟发送 Go-CQHTTP 元事件
                    await self._send_meta_events(ws, self_id)

                    # 2. 发送 OneBot 消息
                    await ws.send_str(json.dumps(onebot_event))

                    # 3. 挂起等待响应（超时 15 秒）
                    response = await self._wait_for_response(ws, self_id, timeout=15.0)
                    return response

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logging.error(f"❌ YouzaiBot 连接失败或已断开: {e}")
            return {"msg_type": 0, "content": "⚠️ 无法连接至 YouzaiBot 服务或连接已断开。"}
        except Exception as e:
            logging.error(f"❌ YouzaiBot 通信异常: {e}")
            return {"msg_type": 0, "content": f"⚠️ 通信发生异常: {e}"}

    async def _send_meta_events(self, ws, self_id):
        """发送 Go-CQHTTP 上线元事件"""
        now = int(time.time())
        lifecycle_event = {
            "time": now,
            "self_id": self_id,
            "post_type": "meta_event",
            "meta_event_type": "lifecycle",
            "sub_type": "connect",
        }
        await ws.send_str(json.dumps(lifecycle_event))

        heartbeat_event = {
            "time": now,
            "self_id": self_id,
            "post_type": "meta_event",
            "meta_event_type": "heartbeat",
            "interval": 5000,
            "status": {"online": True, "good": True},
        }
        await ws.send_str(json.dumps(heartbeat_event))

    async def _wait_for_response(self, ws, self_id, timeout: float) -> dict:
        """等待 Yunzai 回包，连接中断则立即结束，统一封装为 dict 格式"""
        start_t = time.time()
        while time.time() - start_t < timeout:
            if ws.closed:
                logging.warning("⚠️ 收到消息前 WebSocket 已被对端关闭")
                break

            try:
                msg = await asyncio.wait_for(ws.receive(), timeout=1.0)
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    # 响应 Yunzai 探查请求
                    if "action" in data and "echo" in data:
                        await self._handle_action_request(ws, data, self_id)
                        action = data.get("action", "")
                        if action in [
                            "send_msg",
                            "send_group_msg",
                            "send_private_msg",
                            "send_group_forward_msg",
                            "send_forward_msg",
                        ]:
                            parsed_res = self._parse_onebot_message(data.get("params", {}))
                            if parsed_res:
                                return parsed_res
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    logging.warning("⚠️ WebSocket 收到关闭/错误信号，终止等待")
                    break
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logging.error(f"解析 YouzaiBot 响应异常: {e}")
                break

        return {"msg_type": 0, "content": "⚠️ 未能及时收到 YouzaiBot 的有效回复。"}

    async def _handle_action_request(self, ws, req: dict, self_id):
        """自动应答 Yunzai 探查 API"""
        action = req.get("action", "")
        echo = req.get("echo", "")

        res_data = {}
        if action in ["get_login_info", "get_self_info"]:
            res_data = {"user_id": self_id, "nickname": "QQBot"}
        elif action == "get_version_info":
            res_data = {
                "app_name": "go-cqhttp",
                "app_version": "v1.2.0",
                "protocol_version": "v11",
            }
        elif action == "get_friend_list":
            res_data = []
        elif action == "get_group_list":
            res_data = [{"group_id": 97361482, "group_name": "QBot群聊"}]
        elif action in ["get_group_member_list", "get_group_member_info"]:
            res_data = (
                [{"group_id": 97361482, "user_id": self_id, "nickname": "QQBot", "card": "", "role": "member"}]
                if action == "get_group_member_list"
                else {"group_id": 97361482, "user_id": self_id, "nickname": "QQBot", "card": "", "role": "member"}
            )
        elif "list" in action:
            res_data = []

        response_payload = {
            "status": "ok",
            "retcode": 0,
            "data": res_data,
            "echo": echo,
        }
        await ws.send_str(json.dumps(response_payload))

    # =========================================================================
    # 3. 响应解析与图片缓存 (规范化格式输出)
    # =========================================================================
    def _parse_onebot_message(self, params: dict):
        """解析 OneBot API 消息内容，统一返回带有 msg_type 的消息字典"""
        message_data = params.get("message") or params.get("messages") or params.get("nodes")
        if not message_data:
            return None

        if isinstance(message_data, str):
            return {"msg_type": 0, "content": message_data}

        if isinstance(message_data, list):
            text_pieces = []
            image_res = None

            for segment in message_data:
                if not isinstance(segment, dict):
                    continue

                seg_type = segment.get("type")
                seg_data = segment.get("data", {})

                if seg_type == "text":
                    text_pieces.append(seg_data.get("text", ""))

                elif seg_type == "image":
                    file_val = seg_data.get("file") or seg_data.get("url") or ""
                    if file_val:
                        saved_path = self._save_base64_to_cache(file_val)
                        if saved_path:
                            image_res = {
                                "msg_type": 7,
                                "file_path": saved_path,
                                "content": "".join(text_pieces),
                            }

                elif seg_type in ["node", "message"]:
                    sub_res = self._parse_onebot_message(seg_data)
                    if isinstance(sub_res, dict):
                        if sub_res.get("msg_type") == 7 and not image_res:
                            image_res = sub_res
                        elif sub_res.get("content"):
                            text_pieces.append(sub_res["content"])

            if image_res:
                return image_res
            if text_pieces:
                return {"msg_type": 0, "content": "\n".join(text_pieces)}

        return None

    def _save_base64_to_cache(self, base64_str: str) -> str:
        """保存图片至本地 temp_images/"""
        try:
            if base64_str.startswith("base64://"):
                base64_str = base64_str[9:]
            elif base64_str.startswith("data:image"):
                base64_str = base64_str.split(",")[-1]

            image_bytes = base64.b64decode(base64_str)
            md5_hash = hashlib.md5(image_bytes).hexdigest()

            os.makedirs("temp_images", exist_ok=True)
            file_path = os.path.join("temp_images", f"{md5_hash}.png")

            if not os.path.exists(file_path):
                with open(file_path, "wb") as f:
                    f.write(image_bytes)
                logging.info(
                    f"💾 [图片已成功缓存至本地] 路径: {file_path} | 大小: {len(image_bytes)/1024:.2f} KB"
                )

            return file_path
        except Exception as e:
            logging.error(f"❌ 解析并保存 Base64 图片失败: {e}")
            return ""