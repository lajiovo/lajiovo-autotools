import os
import asyncio
import urllib.parse
import urllib.request
import subprocess

import botpy
from botpy.message import GroupMessage

from config import APP_ID, APP_SECRET, _log, apply_sdk_patch, DataManager
from game import GameSystem
from server import start_http_servers

apply_sdk_patch()

class MyClient(botpy.Client):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot_loop = None
        self.data_mgr = DataManager()
        self.game_sys = GameSystem(self.data_mgr)

    async def on_ready(self):
        _log.info(f"robot 「{self.robot.name}」 已成功上线！")
        self.bot_loop = asyncio.get_running_loop()
        start_http_servers(self)
        await self.notify_group_2("🟢 机器人已上线并准备就绪！")

    async def notify_group_2(self, message: str):
        target_openid = next((gid for gid, num in self.data_mgr.group_tags.items() if num == 2), None)
        if target_openid:
            try:
                await self.api.post_group_message(group_openid=target_openid, msg_type=0, content=message)
                _log.info(f"📢 [群2通知成功] 内容: {message}")
            except Exception as e:
                _log.error(f"❌ 发送群 2 通知失败: {e}")
        else:
            _log.info("ℹ️ 未绑定【群 2】，跳过群 2 通知。")

    async def shutdown_system(self, reason: str = "系统下线"):
        _log.info(f"🛑 正在执行系统退出程序... 原因: {reason}")
        await self.notify_group_2(f"🔴 机器人收到下线指令 ({reason})，正在退出...")
        await asyncio.sleep(1)
        os._exit(0)

    async def push_message_to_group(self, msg_content: str, target_group_num: str):
        target_openid, warning_msg = None, ""

        if target_group_num and str(target_group_num).isdigit():
            num_int = int(target_group_num)
            target_openid = next((gid for gid, num in self.data_mgr.group_tags.items() if num == num_int), None)

        if not target_openid:
            target_openid = next((gid for gid, num in self.data_mgr.group_tags.items() if num == 1), None)
            if target_group_num:
                warning_msg = f"\n\n⚠️ [系统提示] 未找到绑定的群 {target_group_num}，已默认推送至群 1"

        if not target_openid:
            _log.error(f"❌ 推送失败：未找到群 {target_group_num}，且数据库中未绑定【群 1】。")
            return

        try:
            await self.api.post_group_message(group_openid=target_openid, msg_type=0, content=f"{msg_content}{warning_msg}")
            _log.info(f"📢 [推送成功] OpenID: {target_openid}")
        except Exception as e:
            _log.error(f"❌ 推送消息失败: {e}")

    def handle_op_command(self, args: list, sender_openid: str, raw_message: GroupMessage, group_id: str) -> str:
        is_op = sender_openid in self.data_mgr.op_list

        if not args:
            group_tag_info = f"（当前群编号：群 {self.data_mgr.group_tags[group_id]}）" if group_id in self.data_mgr.group_tags else ""
            return f"👑 欢迎，尊贵的管理员！当前系统运行正常。{group_tag_info}" if is_op else f"👋 你好呀！快去试试 #钓鱼 或 #打捞 吧！{group_tag_info}"

        sub_cmd = args[0].lower()
        if not is_op:
            return "❌ 权限不足！只有现有的 OP 管理员才能执行 OP 管理指令。"

        if sub_cmd == "shutdown":
            if self.bot_loop:
                asyncio.run_coroutine_threadsafe(self.shutdown_system("OP 指令触发"), self.bot_loop)
            return "🛑 正在准备关闭程序并通知群 2..."

        elif sub_cmd == "ex":
            if len(args) > 1 and args[1].lower() == "start":
                try:
                    subprocess.Popen(["wscript.exe", r"Perseus\begin.vbs"])
                    return "🚀 已成功发起分离运行指令！"
                except Exception as e:
                    return f"❌ 运行失败: {e}"
            return "⚠️ 请使用正确格式：`#op ex start`"

        elif sub_cmd == "run":
            if len(args) < 2:
                return "⚠️ 请提供运行参数，例如：`#op run task1,task2`"
            try:
                # 💡 修改点 1：如果你想访问外部/自建的目标服务端口，将 TARGET_PORT 改为你自建服务的实际端口（如 25565 等）
                # 如果依然使用本地 25566 端口，直接保证自建服务监听该端口即可
                target_port = getattr(self.data_mgr, "target_port", 25566)
                url = f"http://127.0.0.1:{target_port}/run?task={urllib.parse.quote(' '.join(args[1:]))}"
                
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                res = urllib.request.urlopen(req, timeout=3).read().decode('utf-8')
                return f"🚀 已发送请求至 {target_port} 端口，响应：{res}"
            except Exception as e:
                return f"❌ 调用目标 /run 接口失败: {e}"

        elif sub_cmd == "sv":
            if len(args) < 2:
                return "⚠️ 请提供服务器操作指令，例如：`#op sv ping` 或 `#op sv stop`"
            
            sv_action = args[1].lower()
            extra_params = " ".join(args[2:]) if len(args) > 2 else ""
            
            # 💡 修改点 2：支持灵活配置目标端口，避免混淆“机器人自身监听端口”与“游戏/目标服务器端口”
            target_port = getattr(self.data_mgr, "target_port", 25566)
            url = f"http://127.0.0.1:{target_port}/{sv_action}"
            if extra_params:
                url += f"?task={urllib.parse.quote(extra_params)}"
                
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                res = urllib.request.urlopen(req, timeout=3).read().decode('utf-8')
                return f"🌐 [{target_port} 服务响应] /{sv_action}:\n{res}"
            except Exception as e:
                return f"❌ 调用 {target_port} /{sv_action} 接口失败: {e}"

        elif sub_cmd == "list":
            return "👑 【管理员 OP 名单】\n" + "\n".join([f"- {op_id[:6]}... ({op_id})" for op_id in self.data_mgr.op_list])

        elif sub_cmd == "stop":
            self.data_mgr.system_active = False
            self.data_mgr.save_data()
            return "🛑 已成功暂停娱乐与辅助功能！"

        elif sub_cmd == "start":
            self.data_mgr.system_active = True
            self.data_mgr.save_data()
            return "🚀 已成功重新启用功能！"

        elif sub_cmd == "group":
            group_args = args[1:]
            if not group_args or group_args[0].isdigit():
                target_num = group_args[0] if group_args else None
                if not target_num:
                    return "⚠️ 请提供群编号数字，例如：`#op group 1`"
                self.data_mgr.group_tags[group_id] = int(target_num)
                self.data_mgr.save_data()
                return f"✅ 已成功将当前群标记为：【群 {target_num}】！"

            action = group_args[0].lower()
            if action == "list":
                lines = [f"- 群 {num}: {gid}" for gid, num in sorted(self.data_mgr.group_tags.items(), key=lambda x: x[1])]
                return "📋 【群编号绑定列表】\n" + ("\n".join(lines) if lines else "暂无")
            elif action == "get":
                return f"📌 当前群已被标记为：【群 {self.data_mgr.group_tags.get(group_id, '未绑定')}】"

        elif sub_cmd == "add":
            mentions = getattr(raw_message, "mentions", [])
            target_id = (getattr(mentions[0], "member_openid", None) or getattr(mentions[0], "id", None)) if mentions else (args[1].strip() if len(args) > 1 else None)
            if not target_id: return "⚠️ 请 @某人 或提供 OpenID"
            target_id = target_id.upper()
            self.data_mgr.op_list.add(target_id)
            self.data_mgr.save_data()
            return f"✅ 用户 [{target_id[:6]}...] 已提权为 OP。"

        elif sub_cmd in ["remove", "del", "rm"]:
            mentions = getattr(raw_message, "mentions", [])
            target_id = (getattr(mentions[0], "member_openid", None) or getattr(mentions[0], "id", None)) if mentions else (args[1].strip() if len(args) > 1 else None)
            if not target_id or target_id.upper() == DataManager.DEFAULT_OP:
                return "❌ 操作受限或未识别到有效目标"
            target_id = target_id.upper()
            if target_id in self.data_mgr.op_list:
                self.data_mgr.op_list.remove(target_id)
                self.data_mgr.save_data()
                return f"🗑️ 已取消用户 [{target_id[:6]}...] 的 OP 权限。"
            return "ℹ️ 该用户不是 OP。"

        return "⚠️ 未知的 OP 命令。"


    async def process_command(self, content: str, sender_openid: str, raw_message: GroupMessage, group_id: str) -> str:
        parts = content[1:].strip().split()
        cmd = parts[0].lower() if parts else ""

        # 仅由 main.py 直接响应的核心/运维指令
        if cmd == "op":
            return self.handle_op_command(parts[1:], sender_openid, raw_message, group_id)
        if cmd == "ping":
            return f"Pong! 机器人正常运行中 ⚡\n当前服务状态：{'正常开启' if self.data_mgr.system_active else '暂停维护中'}"

        if not self.data_mgr.system_active:
            return "🛑 机器人当前处于维护状态。"

        # 其余所有指令（包括未知指令/帮助指令）统一移交 game_sys 处理
        return self.game_sys.handle_command(cmd, parts, sender_openid)

    async def _handle_group_msg(self, message: GroupMessage, event_name: str):
        content = getattr(message, "content", "").strip()
        group_id = getattr(message, "group_openid", "")
        msg_id = getattr(message, "id", "")
        author = getattr(message, "author", None)
        sender_openid = getattr(author, "member_openid", "未知用户") if author else "未知用户"
        sender_openid = sender_openid.upper()

        _log.info(f"[{event_name}] 群消息 | 群ID: {group_id} | 发送者: {sender_openid} | 内容: {content}")

        if content.startswith("#"):
            reply_text = await self.process_command(content, sender_openid, message, group_id)
            try:
                await self.api.post_group_message(group_openid=group_id, msg_type=0, msg_id=msg_id, content=reply_text)
            except Exception as e:
                _log.error(f"指令回复失败: {e}")

    async def on_group_at_message_create(self, message: GroupMessage):
        await self._handle_group_msg(message, "on_group_at_message_create")

    async def on_group_message_create(self, message: GroupMessage):
        await self._handle_group_msg(message, "on_group_message_create")


if __name__ == "__main__":
    intents = botpy.Intents(public_messages=True)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    client = MyClient(intents=intents)
    client.run(appid=APP_ID, secret=APP_SECRET)
