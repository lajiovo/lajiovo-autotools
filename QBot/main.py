import asyncio
import base64
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
# --------------------------------------------------

apply_sdk_patch()


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

    async def on_ready(self):
        logging.info(f"robot 「{self.robot.name}」 已成功上线！")
        self.bot_loop = asyncio.get_running_loop()
        start_http_servers(self)
        await self.notify_group_3("🟢 机器人已上线并准备就绪！")

    # =========================================================================
    # 2. 核心 HTTP 底层请求封装
    # =========================================================================
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
        """支持本地路径或网络 URL 发送群图片 (msg_type=7)"""
        logging.info(f"🖼️ 正在处理群图片发送: {file_path_or_url}")

        if file_path_or_url.startswith("http://") or file_path_or_url.startswith(
            "https://"
        ):
            upload_res = await self.api.post_group_file(
                group_openid=group_openid, file_type=1, url=file_path_or_url
            )
        else:
            if not os.path.exists(file_path_or_url):
                raise FileNotFoundError(f"本地图片不存在: {file_path_or_url}")

            with open(file_path_or_url, "rb") as f:
                file_base64 = base64.b64encode(f.read()).decode("utf-8")

            upload_payload = {"file_type": 1, "file_data": file_base64}
            upload_res = await self._raw_post(
                "/v2/groups/{group_openid}/files",
                upload_payload,
                group_openid=group_openid,
            )

        file_info = (
            upload_res.get("file_info")
            if isinstance(upload_res, dict)
            else getattr(upload_res, "file_info", upload_res)
        )

        kwargs = {
            "group_openid": group_openid,
            "msg_type": 7,
            "msg_id": msg_id,
            "media": {"file_info": file_info},
        }
        if ref_msg_id:
            kwargs["message_reference"] = {"message_id": ref_msg_id}

        await self.api.post_group_message(**kwargs)
        logging.info(f"🖼️ [富媒体图片发送成功] OpenID: {group_openid}")

    async def send_c2c_image(
        self,
        user_openid: str,
        file_path_or_url: str,
        content: str = "",
        msg_id: str = "",
        ref_msg_id: str = None,
    ):
        """支持本地路径或网络 URL 发送单聊图片 (msg_type=7)"""
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

        payload = {
            "msg_type": 7,
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

        # 1. 尝试从 user_info 中读取已保存的 fake_user_id
        user_info = self.data_mgr.get_user_info(user_openid) or {}
        fake_id = user_info.get("fake_user_id")

        # 2. 若不存在，随机生成 8 位符合条件的假数字 ID 并写入 user_info 与 user_data
        if not fake_id:
            import random
            fake_id = random.randint(10000000, 99999999)

            # 更新用户信息落盘
            user_info["fake_user_id"] = fake_id
            self.data_mgr.set_user_info(user_openid, user_info)

            # 更新用户扩展数据落盘
            user_data = self.data_mgr.get_user_data(user_openid) or {}
            user_data["fake_user_id"] = fake_id
            self.data_mgr.set_user_data(user_openid, user_data)

        return int(fake_id)

    async def api_send_c2c_text(self, user_openid: str, content: str):
        """供 Server 调用的主动发送私聊纯文本消息接口，并同步写入聊天记录"""
    async def call_youzaibot(
        self,
        youzai_cmd: str,
        sender_openid: str,
        group_id: str = "",
        is_c2c: bool = False,
    ):
        """将指令通过 OneBot v11 协议发送至 YouzaiBot (ws://localhost:2536/) 并获取返回消息"""
        ws_urls = [
            "ws://localhost:2536/OneBotv11",
            "ws://localhost:2536/GSUIDCore",
            "ws://localhost:2536/OPQBot",
            "ws://localhost:2536/ComWeChat",
            "ws://localhost:2536/",
        ]

        # 1. 优先读取 opsetting 或 zConfig 中的 youzai_self_id 配置
        opsetting = self.data_mgr.get_opsetting()
        configured_self_id = (
            opsetting.get("youzai_self_id")
            or zConfig.get_config("bot.youzai_self_id", None)
        )

        user_id_num = self._get_or_create_fake_user_id(sender_openid)
        group_id_num = (abs(hash(group_id)) % (10 ** 8) + 10000) if group_id else 0

        responses = []

        try:
            async with aiohttp.ClientSession() as session:
                ws = None
                for url in ws_urls:
                    try:
                        ws = await session.ws_connect(url, timeout=2.0)
                        if ws:
                            break
                    except Exception:
                        continue

                if not ws:
                    return "❌ 无法连接到 YouzaiBot 服务 (ws://localhost:2536/)"

                # 2. self_id 固定为 985211 (或从配置中获取)
                if configured_self_id and str(configured_self_id).isdigit():
                    self_id = int(configured_self_id)
                elif configured_self_id:
                    self_id = configured_self_id
                else:
                    self_id = 985211

                # 3. 仿照 go-cqhttp 协议底层的生命周期 (lifecycle) 与心跳 (heartbeat) 事件，模拟宣告机器人上线登入
                now_ts = int(time.time())
                lifecycle_event = {
                    "time": now_ts,
                    "self_id": self_id,
                    "post_type": "meta_event",
                    "meta_event_type": "lifecycle",
                    "sub_type": "connect",
                }
                heartbeat_event = {
                    "time": now_ts,
                    "self_id": self_id,
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

                await ws.send_str(json.dumps(lifecycle_event))
                await ws.send_str(json.dumps(heartbeat_event))
                await asyncio.sleep(0.05)

                # 4. 构造并发送 OneBot v11 消息事件
                onebot_event = {
                    "time": now_ts,
                    "self_id": self_id,
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
                        "nickname": sender_openid[:8],
                        "card": "",
                        "role": "member",
                    },
                }
                if not is_c2c:
                    onebot_event["group_id"] = group_id_num

                await ws.send_str(json.dumps(onebot_event))

                # 5. 循环接收响应消息，并自动响应 Yunzai 的 API 反向查询 (如 get_login_info)
                start_wait = time.time()
                while time.time() - start_wait < 10.0:
                    try:
                        msg = await asyncio.wait_for(ws.receive(), timeout=3.0)
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = json.loads(msg.data)

                            # 响应 Yunzai 对 go-cqhttp 底层接口的探查请求
                            if isinstance(data, dict) and "action" in data and "echo" in data:
                                action = data.get("action")
                                echo = data.get("echo")
                                if action in ["get_login_info", "get_version_info"]:
                                    res_pkg = {
                                        "status": "ok",
                                        "retcode": 0,
                                        "data": {
                                            "user_id": self_id,
                                            "nickname": "QQBot",
                                            "app_name": "go-cqhttp",
                                            "app_version": "v1.2.0",
                                        },
                                        "echo": echo,
                                    }
                                    await ws.send_str(json.dumps(res_pkg))
                                    continue

                            parsed_reply = self._parse_onebot_message(data)
                            if parsed_reply:
                                responses.append(parsed_reply)
                                await asyncio.sleep(0.5)
                                if ws.closed:
                                    break
                        elif msg.type in (
                            aiohttp.WSMsgType.CLOSED,
                            aiohttp.WSMsgType.ERROR,
                        ):
                            break
                    except asyncio.TimeoutError:
                        if responses:
                            break

                await ws.close()

        except Exception as e:
            logging.error(f"YouzaiBot WebSocket 通信异常: {e}")
            return f"❌ YouzaiBot 通信错误: {e}"

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

        return (
            "\n".join(combined_texts)
            if combined_texts
            else "⚠️ YouzaiBot 未返回有效文本"
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

        # 1. 优先从 opsetting 的 group_tags 读取
        group_tags = opsetting.get("group_tags", {})
        if isinstance(group_tags, dict):
            # 兼容 {"1": "openid_xxx"} 格式
            if eff_str in group_tags and isinstance(group_tags[eff_str], str):
                return group_tags[eff_str]
            # 兼容 {"openid_xxx": 1} 或 {"openid_xxx": "1"} 格式
            for gid, tag in group_tags.items():
                if str(tag) == eff_str:
                    return gid

        # 2. 其次从 groupinfo (get_group_list / get_group_tag) 中读取
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
        # 1. 从 opsetting 中读取提醒群编号
        opsetting = self.data_mgr.get_opsetting()
        target_group_num = opsetting.get("notify_group_num", 3)

        # 2. 定位 OpenID：优先 opsetting["group_tags"]，其次 groupinfo
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

        # 1. 从 opsetting 读取默认推送群配置
        opsetting = self.data_mgr.get_opsetting()
        default_push_group = opsetting.get("push_target_group", None)

        target_openid, warning_msg = None, ""
        effective_group_num = target_group_num or default_push_group

        # 2. 定位 OpenID：优先 opsetting["group_tags"]，其次 groupinfo
        if effective_group_num:
            target_openid = self._get_group_openid_by_num(effective_group_num, opsetting)

        # 3. 如果未定位到对应的群，降级寻找绑定的群 1
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

        # 4. 使用标准的 append_push_history 接口追加记录
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

        # 自动记录机器人的回复 ( role 使用 assistant )
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

        # #op 指令分发与动态消息类型处理
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

            # 使用标准的 is_system_active 检查激活状态
            system_active = self.data_mgr.is_system_active()
            status_text = "正常开启" if system_active else "暂停维护中"
            return (
                f"Pong! 机器人正常运行中 ⚡\n当前服务状态：{status_text}\n已连续运行：{uptime_str}"
            )

        # 维护状态下，直接返回 None，不响应其他指令
        if not self.data_mgr.is_system_active():
            return None

        # ------------------- #game 等其他指令分发与动态消息类型处理 -------------------
        game_res = self.game_sys.handle_command(cmd, parts, sender_openid)

        # 支持 handle_command 返回字典格式，灵活判定 msg_type
        if isinstance(game_res, dict):
            await self.send_reply(game_res, target_id, raw_message.id, is_c2c=is_c2c)
            return None

        # 若返回普通字符串，则交给 _handle_group_msg / _handle_c2c_msg 发送纯文本消息
        return game_res

    # =========================================================================
    # 6. 事件接收与回调处理 (群消息 & 私聊消息)
    # =========================================================================
    def _extract_message_extra(self, message: object) -> dict:
        """从单聊/群聊消息事件对象中提取丰富的结构化元数据
        包含: message_type, member_role, mentions, scene_ext (msg_idx, ref_msg_idx), attachments, ark_data, msg_elements, username
        """
        def _to_dict(obj):
            if isinstance(obj, dict):
                return obj
            if hasattr(obj, "__dict__"):
                return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
            return {}

        raw = _to_dict(message)
        
        # 1. 基础字段解析
        msg_type = getattr(message, "message_type", raw.get("message_type", 0)) or 0
        timestamp = getattr(message, "timestamp", raw.get("timestamp", ""))
        
        # 2. 解析 message_scene 中的 ext 列表 (key=value 格式)
        scene_obj = getattr(message, "message_scene", raw.get("message_scene"))
        scene_dict = _to_dict(scene_obj) if scene_obj else {}
        ext_list = getattr(scene_obj, "ext", scene_dict.get("ext", [])) or []
        scene_ext = {}
        for item in ext_list:
            if isinstance(item, str) and "=" in item:
                k, v = item.split("=", 1)
                scene_ext[k.strip()] = v.strip()

        # 3. 解析作者信息与群身份
        author_obj = getattr(message, "author", raw.get("author"))
        author_dict = _to_dict(author_obj) if author_obj else {}
        username = getattr(author_obj, "username", author_dict.get("username", ""))
        member_role = getattr(author_obj, "member_role", author_dict.get("member_role", "member"))
        is_bot = getattr(author_obj, "bot", author_dict.get("bot", False))

        # 4. 解析 @成员列表 mentions
        mentions_raw = getattr(message, "mentions", raw.get("mentions", [])) or []
        mentions = []
        for m in mentions_raw:
            m_dict = _to_dict(m)
            mentions.append({
                "id": getattr(m, "id", m_dict.get("id", "")),
                "username": getattr(m, "username", m_dict.get("username", "")),
                "bot": getattr(m, "bot", m_dict.get("bot", False)),
            })

        # 5. 解析附件 attachments
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

        # 6. 解析结构化卡片 ark_data
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

        # 7. 解析引用/合并消息元素 msg_elements
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
        author = getattr(message, "author", None)
        sender_openid = (
            getattr(author, "member_openid", "未知用户") if author else "未知用户"
        )
        sender_openid = sender_openid.upper()

        # 提取扩展信息
        extra = self._extract_message_extra(message)
        
        # 若正文为空，根据卡片/附件/引用/合并消息生成丰富可读的内容描述
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

        # 自动记录接收到的群聊消息（传入 sender_openid 自动记录/更新用户信息）
        if full_content:
            self.data_mgr.append_group_message(
                group_id=group_id, user_id=sender_openid, content=full_content, role="user"
            )

        # 如果消息开头为 TARGET_BOT_PREFIX，移除 @ 后自动去除开头的多余空格
        if content.startswith(TARGET_BOT_PREFIX):
            content = content[len(TARGET_BOT_PREFIX) :].strip()

        # 校验并归一化指令前缀，支持 #、/、/# 开头
        if content.startswith("/#"):
            content = "#" + content[2:].lstrip("#").strip()
        elif content.startswith(("#", "/")):
            content = "#" + content[1:].lstrip("#").strip()

        if content.startswith("#"):
            reply_text = await self.process_command(
                content, sender_openid, message, group_id, is_c2c=False
            )
            if reply_text:  # 仅在有返回文字时才进行普通消息发送
                try:
                    await self.api.post_group_message(
                        group_openid=group_id, msg_type=0, msg_id=msg_id, content=reply_text
                    )
                    # 自动记录机器人的文本回复
                    self.data_mgr.append_group_message(
                        group_id=group_id, user_id="BOT", content=reply_text, role="assistant"
                    )
                except Exception as e:
                    logging.error(f"指令回复失败: {e}")

    async def _handle_c2c_msg(self, message: C2CMessage, event_name: str):
        content = getattr(message, "content", "").strip()
        msg_id = getattr(message, "id", "")
        author = getattr(message, "author", None)
        sender_openid = (
            getattr(author, "user_openid", "未知用户") if author else "未知用户"
        )
        sender_openid = sender_openid.upper()

        # 提取扩展信息
        extra = self._extract_message_extra(message)
        
        # 若正文为空，根据卡片/附件/引用/合并消息生成丰富可读的内容描述
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

        # 自动记录接收到的私聊消息
        if full_content:
            self.data_mgr.append_c2c_message(
                user_id=sender_openid, content=full_content, role="user"
            )

        # 校验并归一化指令前缀，支持 #、/、/# 开头
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
                    # 自动记录机器人的文本回复
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