import asyncio
import re
import botpy
from botpy import logging
from botpy.message import Message, GroupMessage

_log = logging.get_logger()

# ==================== 安全的 SDK 兼容补丁 (Patch) ====================
try:
    from botpy.connection import ConnectionState
    if not hasattr(ConnectionState, "parse_group_message_create"):
        def parse_group_message_create(self, payload):
            _message = GroupMessage(self.api, payload.get("id", None), payload.get("d", {}))
            self._dispatch("group_message_create", _message)
        ConnectionState.parse_group_message_create = parse_group_message_create
except Exception:
    pass
# ====================================================================


class MyClient(botpy.Client):

    async def on_ready(self):
        _log.info(f"机器人已成功上线！账号: {self.robot.name}")

    async def _process_content(self, message):
        content = getattr(message, "content", "").strip()

        # 获取消息来源信息
        guild_id = getattr(message, "guild_id", None)          # 频道 ID (群聊时为 None)
        group_id = getattr(message, "group_openid", None)       # 群 ID
        author = getattr(message, "author", None)

        # 检查是否带有 userid 指令
        if "userid" in content.lower():
            match = re.search(r"userid[:\s=]*([^\s]+)", content, re.IGNORECASE)
            target_user_id = match.group(1) if match else "（未提供）"

            # 判断当前是【频道】还是【群聊】
            if guild_id:
                # 频道场景：调用 get_guild_member 获取频道成员详情
                try:
                    member = await self.api.get_guild_member(guild_id=guild_id, user_id=target_user_id)
                    user_info = member.get("user", {}) if isinstance(member, dict) else getattr(member, "user", {})
                    username = user_info.get("username", "未知") if isinstance(user_info, dict) else getattr(user_info, "username", "未知")
                    nick = member.get("nick", "") if isinstance(member, dict) else getattr(member, "nick", "")

                    reply_text = (
                        f"【频道成员查询】\n"
                        f"UserID: {target_user_id}\n"
                        f"用户名: {username}\n"
                        f"频道昵称: {nick if nick else '无'}"
                    )
                except Exception as e:
                    reply_text = f"查询频道用户 [{target_user_id}] 失败，可能不在该频道。"
            else:
                # 群聊场景：直接读取 message.author 中的 member_openid
                sender_openid = getattr(author, "member_openid", "未知OpenID") if author else "未知OpenID"
                reply_text = (
                    f"【群聊用户数据】\n"
                    f"群 OpenID: {group_id}\n"
                    f"发送者 OpenID: {sender_openid}\n"
                    f"指令截取的 UserID 参数: {target_user_id}"
                )

            await message.reply(content=reply_text)
        else:
            await message.reply(content=f"收到消息: {content}")

    # ------------------ 事件监听 ------------------
    async def on_at_message_create(self, message: Message):
        """频道 @ 消息"""
        await self._process_content(message)

    async def on_group_at_message_create(self, message: GroupMessage):
        """群聊 @ 消息"""
        await self._process_content(message)

    async def on_group_message_create(self, message: GroupMessage):
        """群聊普通消息"""
        await self._process_content(message)


if __name__ == "__main__":
    intents = botpy.Intents(public_messages=True, public_guild_messages=True)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    client = MyClient(intents=intents)
    client.run(appid="", secret="")
