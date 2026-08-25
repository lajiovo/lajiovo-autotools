import asyncio
import base64
import hashlib
import json
import logging
import os
import random
import time
import aiohttp


class YunzaiWSClient:
    """YunzaiBot (Yunzai / GSUIDCore) 常驻 WebSocket 连接与内容处理器

    实现 WebSocket 常驻后台监听，自动进行双向假 ID 与真实 OpenID 的映射与反查。
    支持 Yunzai 自由推文并通过 client.send_reply 实时发回消息。
    """

    def __init__(self, bot_client):
        """初始化 WebSocket 客户端实例

        :param bot_client: 主程序 Bot 实例，用于数据持久化及配置管理
        """
        self.bot = bot_client
        self.ws_url = "ws://localhost:2536/OneBotv11"
        self.default_self_id = 985211

        # WebSocket 常驻连接控制器与后台监听任务
        self.session = None
        self.ws = None
        self.listen_task = None
        self.lock = asyncio.Lock()

         # 双向 ID 映射与最新消息 ID 记录表
        self.fake_to_user_openid = {}
        self.fake_to_group_openid = {}
        self.recent_msg_ids = {}
        self.msg_seq_counters = {}
        self._global_seq_counter = 0
        self._target_locks = {}
        self._last_send_times = {}

    def get_or_create_fake_user_id(self, user_openid: str) -> int:
        """为每个用户生成一个随机且持久化落盘的 8 位数字假 ID 并记录映射

        :param user_openid: 用户的真实 OpenID
        :return: 对应的 8 位数字 Fake User ID
        """
        if not user_openid:
            return 10000000

        user_info = self.bot.data_mgr.get_user_info(user_openid) or {}
        user_data = self.bot.data_mgr.get_user_data(user_openid) or {}

        fake_id = user_info.get("fake_user_id") or user_data.get("fake_user_id")
        if not (fake_id and str(fake_id).isdigit()):
            fake_id = random.randint(10000000, 99999999)
            user_info["fake_user_id"] = fake_id
            user_data["fake_user_id"] = fake_id
            self.bot.data_mgr.set_user_info(user_openid, user_info)
            self.bot.data_mgr.set_user_data(user_openid, user_data)
            logging.info(f"👤 [假 ID 映射生成] OpenID: {user_openid} -> FakeID: {fake_id}")

        fake_id_int = int(fake_id)
        # 更新双向内存字典
        self.fake_to_user_openid[str(fake_id_int)] = user_openid
        self.fake_to_user_openid[fake_id_int] = user_openid
        return fake_id_int

    def get_or_create_fake_group_id(self, group_openid: str) -> int:
        """为每个群聊生成一个随机且持久化落盘的 8 位数字假 ID 并记录映射

        :param group_openid: 群聊的真实 OpenID
        :return: 对应的 8 位数字 Fake Group ID
        """
        if not group_openid:
            return 90000000

        group_info = self.bot.data_mgr.get_group_info(group_openid) or {}
        fake_id = group_info.get("fake_group_id")

        if not (fake_id and str(fake_id).isdigit()):
            fake_id = random.randint(10000000, 99999999)
            group_info["fake_group_id"] = fake_id
            self.bot.data_mgr.set_group_info(group_openid, group_info)
            logging.info(f"👥 [群假 ID 映射生成] GroupOpenID: {group_openid} -> FakeGroupID: {fake_id}")

        fake_id_int = int(fake_id)
        # 更新双向内存字典
        self.fake_to_group_openid[str(fake_id_int)] = group_openid
        self.fake_to_group_openid[fake_id_int] = group_openid
        return fake_id_int

    def get_openid_by_fake_user_id(self, fake_user_id: int | str) -> str:
        """根据 8 位 Fake User ID 反查对应的真实 User OpenID"""
        if not fake_user_id:
            return ""
        fake_id_str = str(fake_user_id)
        if fake_id_str in self.fake_to_user_openid:
            return self.fake_to_user_openid[fake_id_str]

        # 内存中未命中时，扫描 data_mgr 缓存反查
        try:
            users_data = getattr(self.bot.data_mgr, "users_data", {}) or getattr(self.bot.data_mgr, "users", {})
            for openid, uinfo in users_data.items():
                if isinstance(uinfo, dict) and str(uinfo.get("fake_user_id")) == fake_id_str:
                    self.fake_to_user_openid[fake_id_str] = openid
                    return openid
        except Exception as e:
            logging.error(f"❌ 反查 Fake User ID 失败: {e}")
        return ""

    def get_openid_by_fake_group_id(self, fake_group_id: int | str) -> str:
        """根据 8 位 Fake Group ID 反查对应的真实 Group OpenID"""
        if not fake_group_id:
            return ""
        fake_id_str = str(fake_group_id)
        if fake_id_str in self.fake_to_group_openid:
            return self.fake_to_group_openid[fake_id_str]

        # 内存中未命中时，扫描 data_mgr 缓存反查
        try:
            groups_data = getattr(self.bot.data_mgr, "groups_data", {}) or getattr(self.bot.data_mgr, "groups", {})
            for openid, ginfo in groups_data.items():
                if isinstance(ginfo, dict) and str(ginfo.get("fake_group_id")) == fake_id_str:
                    self.fake_to_group_openid[fake_id_str] = openid
                    return openid
        except Exception as e:
            logging.error(f"❌ 反查 Fake Group ID 失败: {e}")
        return ""

    def _get_self_id(self) -> int:
        """获取并规范化机器人本身的 self_id"""
        opsetting = self.bot.data_mgr.get_opsetting()
        val = opsetting.get("youzai_self_id", self.default_self_id)
        if isinstance(val, str) and val.isdigit():
            return int(val)
        return val

    async def _ensure_connection(self) -> bool:
        """确保常驻 WebSocket 连接处于连接状态，并启动后台接收监听循环

        :return: bool 连接建立成功与否
        """
        if self.ws and not self.ws.closed:
            return True

        logging.info(f"🔌 [建立常驻连接] 正在连接 YunzaiBot WebSocket ({self.ws_url})...")
        try:
            if not self.session or self.session.closed:
                self.session = aiohttp.ClientSession()

            self.ws = await self.session.ws_connect(self.ws_url, timeout=5.0)
            logging.info("✅ YunzaiBot 常驻 WebSocket 连接建立成功！")

            self_id = self._get_self_id()
            await self._send_meta_events(self.ws, self_id)

            # 启动/重新启动后台常驻监听任务
            if not self.listen_task or self.listen_task.done():
                self.listen_task = asyncio.create_task(self._listen_loop())

            return True
        except Exception as e:
            logging.error(f"❌ YunzaiBot 常驻连接建立失败: {e}")
            self.ws = None
            return False

    async def _listen_loop(self):
        """常驻后台监听循环：持续接收 Yunzai 的推文与 API 请求并自动分发"""
        logging.info("🎧 YunzaiBot 常驻后台监听循环已开启...")
        while True:
            try:
                if not self.ws or self.ws.closed:
                    await asyncio.sleep(3)
                    await self._ensure_connection()
                    continue

                msg = await self.ws.receive()
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    action = data.get("action", "")

                    # 捕获 Yunzai 主动发出的发消息请求
                    if action in [
                        "send_msg",
                        "send_group_msg",
                        "send_private_msg",
                        "send_group_forward_msg",
                        "send_forward_msg",
                    ]:
                        # 1. 响应 Yunzai API 成功
                        echo = data.get("echo", "")
                        response_payload = {
                            "status": "ok",
                            "retcode": 0,
                            "data": {"message_id": int(time.time() * 1000) % 1000000},
                            "echo": echo,
                        }
                        await self.ws.send_str(json.dumps(response_payload))

                        # 2. 解析 Fake ID 并自动匹配真实 OpenID 发送消息
                        await self._dispatch_yunzai_message(data)

                    elif "action" in data:
                        # 响应 Yunzai 的探查 API (如 get_login_info 等)
                        self_id = self._get_self_id()
                        await self._handle_action_request(self.ws, data, self_id)

                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    logging.warning("⚠️ WebSocket 收到关闭或错误信号，尝试自动重连...")
                    await asyncio.sleep(3)
                    await self._ensure_connection()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"❌ YunzaiBot 常驻监听循环异常: {e}")
                await asyncio.sleep(2)

    async def _dispatch_yunzai_message(self, data: dict):
        """解析 Yunzai 消息体，自动查找到真实 OpenID 并通过 client.send_reply 发送"""
        params = data.get("params", {}) if isinstance(data.get("params"), dict) else {}
        parsed_res = self._parse_onebot_message(params)
        if not parsed_res:
            return

        detail_type = params.get("message_type") or params.get("detail_type") or ""
        group_id = params.get("group_id")
        user_id = params.get("user_id")

        is_c2c = False
        target_openid = ""
        fake_key = ""

        # 判断消息类型并选择对应 Fake ID 反查真实 OpenID
        if detail_type == "private" or (not group_id and user_id):
            is_c2c = True
            target_openid = self.get_openid_by_fake_user_id(user_id)
            fake_key = f"user_{user_id}"
        else:
            is_c2c = False
            target_openid = self.get_openid_by_fake_group_id(group_id)
            fake_key = f"group_{group_id}"

        if not target_openid:
            logging.error(f"⚠️ 无法找到对应的真实 OpenID (GroupFakeID: {group_id}, UserFakeID: {user_id})，跳过推送。")
            return

        # 尝试匹配该目标最近的消息 ID 进行回复关联
        raw_msg_id = self.recent_msg_ids.get(fake_key, "")
        seq_key = f"{fake_key}_{raw_msg_id}" if raw_msg_id else fake_key

        # 为每个 TargetOpenID 建立独立的串行锁，防止文本与图片并发请求碰撞
        if target_openid not in self._target_locks:
            self._target_locks[target_openid] = asyncio.Lock()

        async with self._target_locks[target_openid]:
            # 1. 发送频率控制：对同一目标连续推文加入 0.4 秒微缓冲，避免触发 QQ 服务器风控去重
            now_t = time.time()
            last_t = self._last_send_times.get(target_openid, 0)
            if now_t - last_t < 0.4:
                await asyncio.sleep(0.4 - (now_t - last_t))
            self._last_send_times[target_openid] = time.time()

            # 2. 目标与消息 ID 绑定的严格单调递增 msg_seq 维护 (从 1 开始)
            current_seq = self.msg_seq_counters.get(seq_key, 0) + 1
            self.msg_seq_counters[seq_key] = current_seq

            # 将递增 msg_seq 注入解析结果
            if isinstance(parsed_res, dict):
                parsed_res["msg_seq"] = current_seq

            try:
                logging.info(f"🚀 [Yunzai 常驻自由推文] -> 真实 TargetOpenID: {target_openid} (is_c2c={is_c2c}, msg_seq={current_seq})")
                client_target = getattr(self, "bot", None)
                if client_target and hasattr(client_target, "send_reply"):
                    await self._send_with_retry(
                        client_target,
                        parsed_res,
                        target_openid,
                        raw_msg_id,
                        is_c2c,
                        current_seq,
                        fake_key=fake_key,
                        seq_key=seq_key,
                    )
            except Exception as e:
                logging.error(f"❌ 自动发送推文给 {target_openid} 失败: {e}")

    async def _send_with_retry(
        self,
        client_target,
        parsed_res,
        target_openid,
        raw_msg_id,
        is_c2c,
        msg_seq,
        fake_key="",
        seq_key="",
    ):
        """发送消息并支持链式消息 ID 更新与 40054005 去重自增重试"""
        try:
            try:
                res = await client_target.send_reply(
                    parsed_res, target_openid, raw_msg_id, is_c2c=is_c2c, msg_seq=msg_seq
                )
            except TypeError:
                res = await client_target.send_reply(
                    parsed_res, target_openid, raw_msg_id, is_c2c=is_c2c
                )

            # 优化方案：若成功拿到发送返回结果，尝试更新 recent_msg_ids 实现链式引用 ID 刷新
            new_id = None
            if isinstance(res, dict) and res.get("id"):
                new_id = res["id"]
            elif hasattr(res, "id") and getattr(res, "id"):
                new_id = getattr(res, "id")

            if new_id and fake_key:
                self.recent_msg_ids[fake_key] = new_id

        except Exception as e:
            err_str = str(e)
            if "40054005" in err_str or "msgseq" in err_str or "去重" in err_str:
                # 延时 0.5 秒避开并发时间窗，递增 msg_seq 重试
                await asyncio.sleep(0.5)
                retry_seq = (self.msg_seq_counters.get(seq_key, msg_seq) or msg_seq) + 1
                self.msg_seq_counters[seq_key] = retry_seq
                logging.warning(
                    f"⚠️ 检测到 msg_seq 去重错误 (40054005)，等待 0.5s 重新生成 msg_seq={retry_seq} 进行重试..."
                )
                if isinstance(parsed_res, dict):
                    parsed_res["msg_seq"] = retry_seq
                try:
                    await client_target.send_reply(
                        parsed_res, target_openid, raw_msg_id, is_c2c=is_c2c, msg_seq=retry_seq
                    )
                except TypeError:
                    await client_target.send_reply(
                        parsed_res, target_openid, raw_msg_id, is_c2c=is_c2c
                    )
            else:
                raise e

    async def close_connection(self):
        """主动断开 WebSocket 连接与清理后台任务"""
        if self.listen_task and not self.listen_task.done():
            self.listen_task.cancel()
            self.listen_task = None

        if self.ws and not self.ws.closed:
            await self.ws.close()
            logging.info("🔌 YunzaiBot WebSocket 已主动关闭。")
        self.ws = None

        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None

    async def send_command(
        self,
        command_text: str,
        sender_openid: str,
        raw_message: object,
        group_id: str = "",
        is_c2c: bool = False,
    ) -> None:
        """触发指令时确保常驻连接，构建 OneBot 事件发送给 Yunzai，回复自动由常驻监听器实时接收处理

        :param command_text: 触发指令文本
        :param sender_openid: 发送者的 OpenID
        :param raw_message: 原始消息对象
        :param group_id: 群 OpenID
        :param is_c2c: 是否为私聊消息
        """
        raw_msg_id = getattr(raw_message, "id", raw_message)

        async with self.lock:
            # 1. 确保常驻 WebSocket 正常运行
            if not await self._ensure_connection():
                err_res = {"msg_type": 0, "content": "⚠️ 无法连接至 YunzaiBot 服务，连接失败。"}
                if hasattr(self.bot, "send_reply"):
                    await self.bot.send_reply(err_res, sender_openid if is_c2c else group_id, raw_msg_id, is_c2c=is_c2c)
                return

            fake_user_id = self.get_or_create_fake_user_id(sender_openid)
            fake_group_id = self.get_or_create_fake_group_id(group_id) if not is_c2c else 0
            self_id = self._get_self_id()

            # 记录此 Fake 目标最近触发的消息 ID，方便常驻监听器回带
            if is_c2c:
                fake_key = f"user_{fake_user_id}"
                self.recent_msg_ids[fake_key] = raw_message.id
                self.fake_to_user_openid[fake_user_id] = sender_openid
            else:
                fake_key = f"group_{fake_group_id}"
                self.recent_msg_ids[fake_key] = raw_message.id
                self.fake_to_group_openid[fake_group_id] = group_id

            # 以 raw_message.id 结合目标绑定独立序号计数，新指令触发时重置
            seq_key = f"{fake_key}_{raw_message.id}"
            self.msg_seq_counters[seq_key] = 0

            now = int(time.time())
            msg_id_str = str(raw_msg_id)
            msg_id_num = int(hashlib.md5(msg_id_str.encode()).hexdigest()[:8], 16) % 1000000

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

            try:
                # 发送 OneBot 事件，常驻 _listen_loop 监听器会自动捕获并发送推文
                await self.ws.send_str(json.dumps(onebot_event))
            except Exception as e:
                logging.error(f"❌ 发送 OneBot 事件至 YunzaiBot 失败: {e}")

    async def _send_meta_events(self, ws, self_id: int):
        """发送 Go-CQHTTP 上线与心跳元事件，保证 Yunzai 将本端识别为在线客户端"""
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

    async def _handle_action_request(self, ws, req: dict, self_id: int):
        """自动应答 Yunzai 探查与基础 API"""
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
        elif action in [
            "send_msg",
            "send_group_msg",
            "send_private_msg",
            "send_group_forward_msg",
            "send_forward_msg",
        ]:
            res_data = {"message_id": int(time.time() * 1000) % 1000000}
        elif "list" in action:
            res_data = []

        response_payload = {
            "status": "ok",
            "retcode": 0,
            "data": res_data,
            "echo": echo,
        }
        await ws.send_str(json.dumps(response_payload))

    def _parse_onebot_message(self, params: dict):
        """解析 OneBot API 消息内容，支持普通消息、图片以及合并转发节点(nodes/forward)

        :param params: OneBot API 传参字典
        :return: 转换后的字典结果 `{"msg_type": ..., "content": ...}`
        """
        if not isinstance(params, dict):
            if isinstance(params, str):
                return {"msg_type": 0, "content": params}
            return None

        # 兼顾 message、messages、nodes 以及 content 节点字段
        message_data = (
            params.get("message")
            or params.get("messages")
            or params.get("nodes")
            or params.get("content")
        )
        if not message_data:
            return None

        if isinstance(message_data, str):
            return {"msg_type": 0, "content": message_data}

        if isinstance(message_data, list):
            text_pieces = []
            image_res = None

            for segment in message_data:
                if isinstance(segment, str):
                    text_pieces.append(segment)
                    continue

                if not isinstance(segment, dict):
                    continue

                # 兼容格式如 [{"message": "—— TRSS Yunzai v3.1.3 ——..."}]
                if "message" in segment and segment["message"]:
                    sub_res = self._parse_onebot_message(segment)
                    if isinstance(sub_res, dict):
                        if sub_res.get("msg_type") == 7 and not image_res:
                            image_res = sub_res
                        elif sub_res.get("content"):
                            text_pieces.append(sub_res["content"])
                    continue

                seg_type = segment.get("type")
                seg_data = segment.get("data", {}) if isinstance(segment.get("data"), dict) else {}

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

                elif seg_type in ["node", "message"] or "content" in seg_data or "message" in seg_data:
                    # 递归解析合并转发 (forward) / node 嵌套节点
                    sub_res = self._parse_onebot_message(seg_data)
                    if isinstance(sub_res, dict):
                        if sub_res.get("msg_type") == 7 and not image_res:
                            image_res = sub_res
                        elif sub_res.get("content"):
                            text_pieces.append(sub_res["content"])

            if image_res:
                if text_pieces and not image_res.get("content"):
                    image_res["content"] = "\n".join(text_pieces)
                return image_res

            if text_pieces:
                return {"msg_type": 0, "content": "\n\n".join(text_pieces)}

        return None

    def _save_base64_to_cache(self, base64_str: str) -> str:
        """保存 Base64 格式图片至本地 temp_images/ 路径

        :param base64_str: Base64 编码字符串或 URL
        :return: 保存后的本地图片文件路径
        """
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