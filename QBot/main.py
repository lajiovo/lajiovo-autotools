import asyncio
import base64
import os
import time
import traceback

import botpy
from botpy.message import C2CMessage, GroupMessage
from botpy.types.message import MarkdownPayload, MessageMarkdownParams

from config import (
    APP_ID,
    APP_SECRET,
    DataManager,
    ChatHistoryManager,
    _log,
    apply_sdk_patch,
)
from game import GameSystem
from opcmd import handle_op_command
from server import start_http_servers

# ------------------- 文件配置区 -------------------
TARGET_BOT_PREFIX = "<@>"
# --------------------------------------------------

apply_sdk_patch()


class MyClient(botpy.Client):

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.start_time = time.time()  # 记录程序初始化开机时间戳
    self.bot_loop = None
    self.data_mgr = DataManager()
    self.chat_mgr = ChatHistoryManager()  # 初始化聊天记录管理器
    self.game_sys = GameSystem(self.data_mgr)
    
    # 消息跟踪标记（用于轮询获取新消息）
    self._last_msg_time = time.time()
    self._has_new_message = False

  async def on_ready(self):
    _log.info(f"robot 「{self.robot.name}」 已成功上线！")
    self.bot_loop = asyncio.get_running_loop()
    start_http_servers(self)
    await self.notify_group_3("🟢 机器人已上线并准备就绪！")

  def _update_msg_tracker(self):
    """私有辅助函数：当接收到新消息时更新状态"""
    self._last_msg_time = time.time()
    self._has_new_message = True

  # ------------------- 核心 HTTP 底层请求封装 -------------------
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

  # ------------------- 1. 文本/引用消息发送接口 -------------------
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
    _log.info(f"💬 [文本/引用消息发送成功] OpenID: {group_openid}")

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
    _log.info(f"💬 [单聊文本消息发送成功] UserOpenID: {user_openid}")

  # ------------------- SERVER 专供对外调用接口 -------------------
  async def api_send_c2c_text(self, user_openid: str, content: str):
    """供 Server 调用的主动发送私聊纯文本消息接口，并同步写入聊天记录（含异常捕获）"""
    try:
      await self.send_c2c_text(user_openid=user_openid, content=content)
      self.chat_mgr.append_private_message(
          user_id=user_openid, content=content, role="bot"
      )
      return True
    except Exception as e:
      _log.error(f"❌ [Server 发送 C2C 消息被拒收/报错] UserOpenID: {user_openid}, 原因: {e}")
      return False

  async def api_send_group_text(self, group_openid: str, content: str):
    """供 Server 调用的主动发送群聊纯文本消息接口，并同步写入聊天记录（含异常捕获）"""
    try:
      await self.send_group_text(group_openid=group_openid, content=content)
      self.chat_mgr.append_group_message(
          group_id=group_openid, user_id="BOT", content=content, role="bot"
      )
      return True
    except Exception as e:
      _log.error(f"❌ [Server 发送 Group 消息被拒收/报错] GroupOpenID: {group_openid}, 原因: {e}")
      return False

  def get_chat_history(self, target_id: str, is_group: bool = False):
    """获取指定群或用户的聊天历史记录"""
    if is_group:
      return self.chat_mgr.get_group_history(target_id)
    return self.chat_mgr.get_private_history(target_id)

  def get_nickname(self, target_id: str, is_group: bool = False):
    """获取指定群或用户的昵称"""
    target_id = str(target_id)
    if is_group:
      return self.chat_mgr.group_nicknames.get(target_id, "")
    return self.chat_mgr.user_nicknames.get(target_id, "")

  def get_user_list(self):
    """获取所有已产生私聊记录/设置昵称的用户列表及其昵称 mapping"""
    user_ids = set(self.chat_mgr.private_history.keys()) | set(self.chat_mgr.user_nicknames.keys())
    return [
        {
            "user_id": uid,
            "nickname": self.chat_mgr.user_nicknames.get(uid, "")
        }
        for uid in user_ids
    ]

  def get_group_list(self):
    """获取所有已产生群聊记录/设置昵称的群聊列表及其昵称/编号 mapping"""
    group_ids = set(self.chat_mgr.group_history.keys()) | set(self.chat_mgr.group_nicknames.keys()) | set(self.data_mgr.group_tags.keys())
    return [
        {
            "group_id": gid,
            "nickname": self.chat_mgr.group_nicknames.get(gid, ""),
            "tag_num": self.data_mgr.group_tags.get(gid, None)
        }
        for gid in group_ids
    ]

  def check_has_new_message(self, reset: bool = True):
    """
    获取是否有新消息产生
    :param reset: 是否在检查后重置状态，默认为 True（即消费式查询）
    :return: dict 包含状态标志和最后收到消息的时间戳
    """
    has_new = self._has_new_message
    last_time = self._last_msg_time
    if reset and has_new:
      self._has_new_message = False
    return {
        "has_new": has_new,
        "last_msg_time": last_time
    }

  # ------------------- 2. Markdown & 内嵌键盘接口 -------------------
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
    _log.info(f"📢 [Markdown 发送成功] OpenID: {group_openid}")

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
    _log.info(f"📢 [单聊 Markdown 发送成功] UserOpenID: {user_openid}")

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
    _log.info(f"📢 [Markdown 模板发送成功] OpenID: {group_openid}")

  # ------------------- 3. 本地/网络富媒体图片发送接口 -------------------
  async def send_group_image(
      self,
      group_openid: str,
      file_path_or_url: str,
      content: str = "",
      msg_id: str = "",
      ref_msg_id: str = None,
  ):
    """支持本地路径或网络 URL 发送群图片 (msg_type=7)"""
    _log.info(f"🖼️ 正在处理群图片发送: {file_path_or_url}")

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
    _log.info(f"🖼️ [富媒体图片发送成功] OpenID: {group_openid}")

  async def send_c2c_image(
      self,
      user_openid: str,
      file_path_or_url: str,
      content: str = "",
      msg_id: str = "",
      ref_msg_id: str = None,
  ):
    """支持本地路径或网络 URL 发送单聊图片 (msg_type=7)"""
    _log.info(f"🖼️ 正在处理单聊图片发送: {file_path_or_url}")

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
    _log.info(f"🖼️ [单聊富媒体图片发送成功] UserOpenID: {user_openid}")

  # ------------------- 4. 图文卡片消息发送接口 -------------------
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
    _log.info(f"🃏 [图文卡片发送成功] OpenID: {group_openid}")

  # ------------------- 5. 指令面板 & 自定义菜单接口 -------------------
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
    _log.info(f"📋 [创建指令面板成功] Scope: {scope}, Response: {res}")
    return res

  async def set_c2c_menu(self, menu: dict):
    """修改 C2C 全局自定义菜单"""
    payload = {"menu": menu}
    res = await self._raw_put("/v2/menu", payload)
    _log.info(f"📌 [修改C2C自定义菜单成功] Response: {res}")
    return res

  # ---------------------------------------------------------

  async def notify_group_3(self, message: str):
    """上下线通知群（默认群 3）"""
    target_group_num = getattr(self.data_mgr, "notify_group_num", 3)
    target_openid = next(
        (
            gid
            for gid, num in self.data_mgr.group_tags.items()
            if num == target_group_num
        ),
        None,
    )

    if target_openid:
      try:
        await self.api.post_group_message(
            group_openid=target_openid, msg_type=0, content=message
        )
        _log.info(f"📢 [群{target_group_num}通知成功] 内容: {message}")
      except Exception as e:
        _log.error(f"❌ 发送群 {target_group_num} 通知失败: {e}")
    else:
      _log.info(f"ℹ️ 未绑定【群 {target_group_num}】，跳过通知。")

  async def shutdown_system(self, reason: str = "系统下线"):
    _log.info(f"🛑 正在执行系统退出程序... 原因: {reason}")
    await self.notify_group_3(
        f"🔴 机器人收到下线指令 ({reason})，正在退出..."
    )
    await asyncio.sleep(1)
    os._exit(0)

  async def push_message_to_group(
      self, msg_content: str, target_group_num: str
  ):
    push_active = getattr(self.data_mgr, "push_active", True)
    if not push_active:
      _log.info("ℹ️ Push 功能已关闭，跳过推送。")
      return

    target_openid, warning_msg = None, ""
    effective_group_num = target_group_num or getattr(
        self.data_mgr, "push_target_group", None
    )

    if effective_group_num and str(effective_group_num).isdigit():
      num_int = int(effective_group_num)
      target_openid = next(
          (
              gid
              for gid, num in self.data_mgr.group_tags.items()
              if num == num_int
          ),
          None,
      )

    if not target_openid:
      target_openid = next(
          (gid for gid, num in self.data_mgr.group_tags.items() if num == 1),
          None,
      )
      if effective_group_num:
        warning_msg = (
            f"\n\n⚠️ [系统提示] 未找到绑定的群 {effective_group_num}，已默认推送至群 1"
        )

    if not target_openid:
      _log.error(
          f"❌ 推送失败：未找到群 {effective_group_num}，且数据库中未绑定【群 1】。"
      )
      return

    full_content = f"{msg_content}{warning_msg}"

    # 1. 【第一次记录】收到 Push 请求，准备发送前记录一次
    self.chat_mgr.append_group_message(
        group_id="push",
        user_id="bot",
        content=f"[Push 接收] {full_content}",
        role="push",
    )

    try:
      await self.api.post_group_message(
          group_openid=target_openid,
          msg_type=0,
          content=full_content,
      )
      _log.info(f"📢 [推送成功] OpenID: {target_openid}")

    except Exception as e:
      _log.error(f"❌ 推送消息被拒收/失败: {e}")


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

    # 自动记录机器人的回复
    if reply_content:
      if is_c2c:
        self.chat_mgr.append_private_message(
            user_id=target_id, content=reply_content, role="bot"
        )
      else:
        self.chat_mgr.append_group_message(
            group_id=target_id, user_id="BOT", content=reply_content, role="bot"
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

      status_text = (
          "正常开启" if self.data_mgr.system_active else "暂停维护中"
      )
      return (
          f"Pong! 机器人正常运行中 ⚡\n当前服务状态：{status_text}\n已连续运行：{uptime_str}"
      )

    # 维护状态下，直接返回 None，不响应其他指令
    if not self.data_mgr.system_active:
      return None

    # ------------------- #game 等其他指令分发与动态消息类型处理 -------------------
    game_res = self.game_sys.handle_command(cmd, parts, sender_openid)

    # 支持 handle_command 返回字典格式，灵活判定 msg_type
    if isinstance(game_res, dict):
      await self.send_reply(game_res, target_id, raw_message.id, is_c2c=is_c2c)
      return None

    # 若返回普通字符串，则交给 _handle_group_msg / _handle_c2c_msg 发送纯文本消息
    return game_res

  async def _handle_group_msg(self, message: GroupMessage, event_name: str):
    content = getattr(message, "content", "").strip()
    group_id = getattr(message, "group_openid", "")
    msg_id = getattr(message, "id", "")
    author = getattr(message, "author", None)
    sender_openid = (
        getattr(author, "member_openid", "未知用户") if author else "未知用户"
    )
    sender_openid = sender_openid.upper()

    _log.info(
        f"[{event_name}] 群消息 | 群ID: {group_id} | 发送者: {sender_openid} |"
        f" 内容: {content}"
    )

    # 自动记录接收到的群聊消息并更新消息标记
    if content:
      self._update_msg_tracker()
      self.chat_mgr.append_group_message(
          group_id=group_id, user_id=sender_openid, content=content, role="user"
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
          self.chat_mgr.append_group_message(
              group_id=group_id, user_id="BOT", content=reply_text, role="bot"
          )
        except Exception as e:
          _log.error(f"指令回复失败: {e}")

  async def _handle_c2c_msg(self, message: C2CMessage, event_name: str):
    content = getattr(message, "content", "").strip()
    msg_id = getattr(message, "id", "")
    author = getattr(message, "author", None)
    sender_openid = (
        getattr(author, "user_openid", "未知用户") if author else "未知用户"
    )
    sender_openid = sender_openid.upper()

    _log.info(
        f"[{event_name}] 单聊消息 | 发送者: {sender_openid} | 内容: {content}"
    )

    # 自动记录接收到的私聊消息并更新消息标记
    if content:
      self._update_msg_tracker()
      self.chat_mgr.append_private_message(
          user_id=sender_openid, content=content, role="user"
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
          self.chat_mgr.append_private_message(
              user_id=sender_openid, content=reply_text, role="bot"
          )
        except Exception as e:
          _log.error(f"单聊指令回复失败: {e}")

  async def on_c2c_message_create(self, message: C2CMessage):
    await self._handle_c2c_msg(message, "on_c2c_message_create")

  async def on_group_at_message_create(self, message: GroupMessage):
    await self._handle_group_msg(message, "on_group_at_message_create")

  async def on_group_message_create(self, message: GroupMessage):
    await self._handle_group_msg(message, "on_group_message_create")


if __name__ == "__main__":
  intents = botpy.Intents(public_messages=True, direct_message=True)
  loop = asyncio.new_event_loop()
  asyncio.set_event_loop(loop)

  client = MyClient(intents=intents)
  client.run(appid=APP_ID, secret=APP_SECRET)
