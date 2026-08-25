import asyncio
import base64
import logging
import os
import time

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
from yz import YouzaiWSClient

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

        # 消息去重与 API msg_seq 控制
        self.processed_msg_ids = {}
        self.msg_seq_map = {}

        # 实例化 YouzaiWSClient
        self.youzai_mgr = YouzaiWSClient(self)

    async def on_ready(self):
        logging.info(f"robot 「{self.robot.name}」 已成功上线！")
        self.bot_loop = asyncio.get_running_loop()
        start_http_servers(self)
        await self.notify_group_3("🟢 机器人已上线并准备就绪！")

    # =========================================================================
    # 2. 消息去重与 Sequence 控制 (解决消息重复和 40054005 拦截)
    # =========================================================================
    def _is_duplicate_msg(self, msg_id: str) -> bool:
        """检查 60 秒内是否收到过重复的 msg_id，防止公私聊/全量群消息双重回调触发"""
        if not msg_id:
            return False

        now = time.time()
        # 清理 60 秒以前的过期缓存
        expired_keys = [k for k, v in self.processed_msg_ids.items() if now - v > 60]
        for k in expired_keys:
            del self.processed_msg_ids[k]

        if msg_id in self.processed_msg_ids:
            return True

        self.processed_msg_ids[msg_id] = now
        return False

    def _get_next_msg_seq(self, msg_id: str) -> int:
        """获取指定 msg_id 下自增的 msg_seq，避免 API msg_seq 冲突"""
        if not msg_id:
            return 1

        seq = self.msg_seq_map.get(msg_id, 0) + 1
        self.msg_seq_map[msg_id] = seq
        return seq

    # =========================================================================
    # 3. 核心 HTTP 底层请求封装
    # =========================================================================
    async def _raw_post(self, route_path: str, payload: dict, **path_params):
        """通用底层 HTTP POST 请求"""
        route = botpy.http.Route("POST", route_path, **path_params)
        http_client = getattr(self.api, "_http", None) or getattr(self, "_http", None)
        if not http_client:
            raise AttributeError("未能获取到 SDK 底层 _http 请求对象")
        return await http_client.request(route, json=payload)

    async def _raw_put(self, route_path: str, payload: dict, **path_params):
        """通用底层 HTTP PUT 请求"""
        route = botpy.http.Route("PUT", route_path, **path_params)
        http_client = getattr(self.api, "_http", None) or getattr(self, "_http", None)
        if not http_client:
            raise AttributeError("未能获取到 SDK 底层 _http 请求对象")
        return await http_client.request(route, json=payload)

    # =========================================================================
    # 4. 各种类型消息发送接口
    # =========================================================================
    async def send_group_text(
        self,
        group_openid: str,
        content: str,
        msg_id: str = "",
        ref_msg_id: str = None,
    ):
        """发送纯文本消息 (msg_type=0)"""
        kwargs = {
            "group_openid": group_openid,
            "msg_type": 0,
            "content": content,
            "msg_id": msg_id,
        }
        if msg_id:
            kwargs["msg_seq"] = self._get_next_msg_seq(msg_id)
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
        """发送单聊纯文本消息 (msg_type=0)"""
        payload = {
            "msg_type": 0,
            "content": content,
        }
        if msg_id:
            payload["msg_id"] = msg_id
            payload["msg_seq"] = self._get_next_msg_seq(msg_id)
        if ref_msg_id:
            payload["message_reference"] = {"message_id": ref_msg_id}

        await self._raw_post(
            "/v2/users/{user_openid}/messages",
            payload,
            user_openid=user_openid,
        )
        logging.info(f"💬 [单聊文本消息发送成功] UserOpenID: {user_openid}")

    async def send_group_markdown_by_content(
        self,
        group_openid: str,
        content: str,
        msg_id: str = "",
        keyboard: dict = None,
    ):
        """发送群 Markdown 消息 (msg_type=2)"""
        markdown = MarkdownPayload(content=content)
        kwargs = {
            "group_openid": group_openid,
            "msg_type": 2,
            "markdown": markdown,
            "msg_id": msg_id,
        }
        if msg_id:
            kwargs["msg_seq"] = self._get_next_msg_seq(msg_id)
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
        """发送单聊 Markdown 消息 (msg_type=2)"""
        payload = {
            "msg_type": 2,
            "markdown": {"content": content},
        }
        if msg_id:
            payload["msg_id"] = msg_id
            payload["msg_seq"] = self._get_next_msg_seq(msg_id)
        if keyboard:
            payload["keyboard"] = keyboard

        await self._raw_post(
            "/v2/users/{user_openid}/messages",
            payload,
            user_openid=user_openid,
        )
        logging.info(f"📢 [单聊 Markdown 发送成功] UserOpenID: {user_openid}")

    async def send_group_image(
        self,
        group_openid: str,
        file_path_or_url: str,
        content: str = "",
        msg_id: str = "",
        ref_msg_id: str = None,
    ):
        """发送群富媒体图片 (msg_type=7)"""
        logging.info(f"🖼️ 正在处理群图片发送 | OpenID: {group_openid} | 资源: {file_path_or_url[:60]}")

        try:
            if file_path_or_url.startswith("http://") or file_path_or_url.startswith("https://"):
                upload_payload = {"file_type": 1, "url": file_path_or_url, "srv_send_msg": False}
                upload_res = await self._raw_post(
                    "/v2/groups/{group_openid}/files",
                    upload_payload,
                    group_openid=group_openid,
                )
            else:
                if not os.path.exists(file_path_or_url):
                    raise FileNotFoundError(f"本地图片不存在: {file_path_or_url}")

                with open(file_path_or_url, "rb") as f:
                    file_base64 = base64.b64encode(f.read()).decode("utf-8")

                upload_payload = {"file_type": 1, "file_data": file_base64, "srv_send_msg": False}
                upload_res = await self._raw_post(
                    "/v2/groups/{group_openid}/files",
                    upload_payload,
                    group_openid=group_openid,
                )

            file_info = upload_res.get("file_info") if isinstance(upload_res, dict) else getattr(upload_res, "file_info", upload_res)

            seq = self._get_next_msg_seq(msg_id)
            kwargs = {
                "group_openid": group_openid,
                "msg_type": 7,
                "msg_id": msg_id,
                "msg_seq": seq,
                "media": {"file_info": file_info},
            }
            if content:
                kwargs["content"] = content
            if ref_msg_id:
                kwargs["message_reference"] = {"message_id": ref_msg_id}

            await self.api.post_group_message(**kwargs)
            logging.info(f"🖼️ [群富媒体图片发送成功] OpenID: {group_openid}")

        except Exception as e:
            logging.error(f"❌ [群富媒体图片发送失败] OpenID: {group_openid} | 原因: {e}", exc_info=True)
            if content:
                await self.send_group_text(group_openid=group_openid, content=content, msg_id=msg_id)

    async def send_c2c_image(
        self,
        user_openid: str,
        file_path_or_url: str,
        content: str = "",
        msg_id: str = "",
        ref_msg_id: str = None,
    ):
        """发送单聊富媒体图片 (msg_type=7)"""
        logging.info(f"🖼️ 正在处理单聊图片发送: {file_path_or_url[:60]}")

        try:
            if file_path_or_url.startswith("http://") or file_path_or_url.startswith("https://"):
                upload_res = await self._raw_post(
                    "/v2/users/{user_openid}/files",
                    {"file_type": 1, "url": file_path_or_url, "srv_send_msg": False},
                    user_openid=user_openid,
                )
            else:
                if not os.path.exists(file_path_or_url):
                    raise FileNotFoundError(f"本地图片不存在: {file_path_or_url}")

                with open(file_path_or_url, "rb") as f:
                    file_base64 = base64.b64encode(f.read()).decode("utf-8")

                upload_payload = {"file_type": 1, "file_data": file_base64, "srv_send_msg": False}
                upload_res = await self._raw_post(
                    "/v2/users/{user_openid}/files",
                    upload_payload,
                    user_openid=user_openid,
                )

            file_info = upload_res.get("file_info") if isinstance(upload_res, dict) else getattr(upload_res, "file_info", upload_res)

            seq = self._get_next_msg_seq(msg_id)
            payload = {
                "msg_type": 7,
                "msg_id": msg_id,
                "msg_seq": seq,
                "media": {"file_info": file_info},
            }
            if content:
                payload["content"] = content
            if ref_msg_id:
                payload["message_reference"] = {"message_id": ref_msg_id}

            await self._raw_post(
                "/v2/users/{user_openid}/messages",
                payload,
                user_openid=user_openid,
            )
            logging.info(f"🖼️ [单聊富媒体图片发送成功] UserOpenID: {user_openid}")

        except Exception as e:
            logging.error(f"❌ [单聊图片发送失败] UserOpenID: {user_openid} | 原因: {e}", exc_info=True)
            if content:
                await self.send_c2c_text(user_openid=user_openid, content=content, msg_id=msg_id)

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
            payload["msg_seq"] = self._get_next_msg_seq(msg_id)

        await self._raw_post(
            "/v2/groups/{group_openid}/messages",
            payload,
            group_openid=group_openid,
        )
        logging.info(f"🃏 [图文卡片发送成功] OpenID: {group_openid}")

    # =========================================================================
    # 5. 系统通知与群查找辅助
    # =========================================================================
    def _get_group_openid_by_num(self, target_num: int) -> str:
        """根据群编号查找 群 OpenID"""
        opsetting = self.data_mgr.get_opsetting()
        group_tags = opsetting.get("group_tags", {})

        if isinstance(group_tags, dict):
            for k, v in group_tags.items():
                if str(k).isdigit() and int(k) == target_num:
                    return str(v)
                if str(v).isdigit() and int(v) == target_num:
                    return str(k)

        group_list = self.data_mgr.get_group_list()
        for g in group_list:
            tag_num = g.get("tag_num")
            grouptag = g.get("grouptag")
            if (tag_num is not None and int(tag_num) == target_num) or (
                grouptag and str(grouptag).isdigit() and int(grouptag) == target_num
            ):
                return g.get("group_id", "")

        return ""

    async def notify_group_3(self, message: str):
        """上下线通知群"""
        opsetting = self.data_mgr.get_opsetting()
        notify_group_num = opsetting.get("notify_group_num", 3)

        target_openid = self._get_group_openid_by_num(int(notify_group_num))

        if target_openid:
            try:
                await self.send_group_text(group_openid=target_openid, content=message)
                logging.info(f"📢 [群{notify_group_num}通知成功] 内容: {message}")
            except Exception as e:
                logging.error(f"❌ 发送群 {notify_group_num} 通知失败: {e}")
        else:
            logging.info(f"ℹ️ 未绑定【群 {notify_group_num}】，跳过通知。")

    async def shutdown_system(self, reason: str = "系统下线"):
        logging.info(f"🛑 正在执行系统退出程序... 原因: {reason}")
        await self.notify_group_3(f"🔴 机器人收到下线指令 ({reason})，正在退出...")
        await asyncio.sleep(1)
        os._exit(0)

    # =========================================================================
    # 6. 指令处理与统一回复分发逻辑
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
        """统一合并的回复发送函数"""
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

        cmd_text = content[1:].strip()
        parts = cmd_text.split()
        cmd = parts[0].lower() if parts else ""

        # ------------------- #y / #yxxx 按需连接并转发至 YouzaiBot -------------------
        if cmd_text.startswith("y"):
            yb_command = cmd_text[1:].strip()
            if not yb_command:
                yb_command = "帮助"

            yz_res = await self.youzai_mgr.send_command(
                command_text=yb_command,
                sender_openid=sender_openid,
                raw_message=raw_message,
                group_id=group_id,
                is_c2c=is_c2c,
            )

            if isinstance(yz_res, dict):
                await self.send_reply(yz_res, target_id, raw_message.id, is_c2c=is_c2c)
                return None
            return yz_res

        # ------------------- #op 管理指令 -------------------
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

        # ------------------- #ping 运行状态探针 -------------------
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

        # ------------------- #game 等业务小游戏分发 -------------------
        game_res = self.game_sys.handle_command(cmd, parts, sender_openid)
        if isinstance(game_res, dict):
            await self.send_reply(game_res, target_id, raw_message.id, is_c2c=is_c2c)
            return None

        return game_res

    # =========================================================================
    # 7. 事件接收与回调处理 (直接提取原生 content，简化逻辑)
    # =========================================================================
    async def _handle_group_msg(self, message: GroupMessage, event_name: str):
        msg_id = getattr(message, "id", "")

        # 校验并过滤 60s 内相同 msg_id 的重复事件
        if self._is_duplicate_msg(msg_id):
            logging.info(f"⏭️ [{event_name}] [已跳过重复群消息事件] MsgID: {msg_id}")
            return

        content = getattr(message, "content", "").strip()
        group_id = getattr(message, "group_openid", "")
        author = getattr(message, "author", None)
        sender_openid = getattr(author, "member_openid", "未知用户") if author else "未知用户"
        sender_openid = sender_openid.upper()

        username = getattr(author, "username", "") if author else ""

        logging.info(
            f"[{event_name}] 群消息 | 群ID: {group_id} | 发送者: {sender_openid} "
            f"({username or '无昵称'}) | 内容: {content}"
        )

        if username:
            self.data_mgr.set_user_info(sender_openid, {"nickname": username})

        if content:
            self.data_mgr.append_group_message(
                group_id=group_id, user_id=sender_openid, content=content, user_nickname=username, role="user"
            )

        # 规整指令前缀
        if content.startswith(TARGET_BOT_PREFIX):
            content = content[len(TARGET_BOT_PREFIX):].strip()

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
                    await self.send_group_text(group_openid=group_id, content=reply_text, msg_id=msg_id)
                    self.data_mgr.append_group_message(
                        group_id=group_id, user_id="BOT", content=reply_text, role="assistant"
                    )
                except Exception as e:
                    logging.error(f"群指令回复失败: {e}")

    async def _handle_c2c_msg(self, message: C2CMessage, event_name: str):
        msg_id = getattr(message, "id", "")

        if self._is_duplicate_msg(msg_id):
            logging.info(f"⏭️ [{event_name}] [已跳过重复私聊消息事件] MsgID: {msg_id}")
            return

        content = getattr(message, "content", "").strip()
        author = getattr(message, "author", None)
        sender_openid = getattr(author, "user_openid", "未知用户") if author else "未知用户"
        sender_openid = sender_openid.upper()

        username = getattr(author, "username", "") if author else ""

        logging.info(
            f"[{event_name}] 单聊消息 | 发送者: {sender_openid} ({username or '无昵称'}) | 内容: {content}"
        )

        if username:
            self.data_mgr.set_user_info(sender_openid, {"nickname": username})

        if content:
            self.data_mgr.append_c2c_message(
                user_id=sender_openid, content=content, user_nickname=username, role="user"
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
                    await self.send_c2c_text(user_openid=sender_openid, content=reply_text, msg_id=msg_id)
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