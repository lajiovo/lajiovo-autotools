import subprocess
import urllib.parse
import urllib.request
from botpy.message import GroupMessage
from config import DataManager


def handle_op_command(
    client,
    args: list,
    sender_openid: str,
    raw_message: GroupMessage,
    group_id: str,
) -> str:
  is_op = sender_openid in client.data_mgr.op_list

  if not args:
    group_tag_info = (
        f"（当前群编号：群 {client.data_mgr.group_tags[group_id]}）"
        if group_id in client.data_mgr.group_tags
        else ""
    )
    return (
        f"👑 欢迎，尊贵的管理员！当前系统运行正常。{group_tag_info}"
        if is_op
        else f"👋 你好呀！快去试试 #钓鱼 或 #打捞 吧！{group_tag_info}"
    )

  sub_cmd = args[0].lower()
  if not is_op:
    return "❌ 权限不足！只有现有的 OP 管理员才能执行 OP 管理指令。"

  # ------------------- 帮助指令 -------------------
  if sub_cmd in ["help", "?", "帮助"]:
    return (
        "👑 【OP 管理员指令列表】\n"
        "-------------------------\n"
        "📌 【机器人基础控制】\n"
        "• #op help - 查看所有 OP 指令\n"
        "• #op stop - 暂停机器人功能 (维护模式，屏蔽消息回复)\n"
        "• #op start - 恢复机器人功能\n"
        "• #op restart - 重新无窗口启动 QBot (执行 sv bot/start)\n"
        "• #op shutdown - 关闭机器人程序并通知指定的通知群\n"
        "• #op list - 查看所有 OP 管理员\n"
        "• #op add [@某人/OpenID] - 添加管理员\n"
        "• #op del/remove [@某人/OpenID] - 移除管理员\n\n"
        "📌 【群绑定与 通知/Push 管理】\n"
        "• #op group <数字> - 标记当前群编号 (例: #op group 1)\n"
        "• #op group list - 查看所有群编号绑定\n"
        "• #op group get - 查看当前群编号\n"
        "• #op notify set <数字> - 设置上下线通知的接收群编号\n"
        "• #op push set <数字> - 设置 Push 消息的目标推送群\n"
        "• #op push start - 开启 Push 转发\n"
        "• #op push stop - 关闭 Push 转发\n\n"
        "📌 【任务运行接口 (#op run <任务>)】\n"
        "• #op run ikun - 执行 alas与mumu 双向状态检查与恢复\n"
        "• #op run alas <start/restart/kill/hide/online> - 控制 Alas 进程\n"
        "• #op run mumu <start/kill/hide/online> - 控制 MuMu 模拟器进程\n"
        "• #op run pw 或 playwright - 启动 Playwright 自动化任务\n"
        "• #op run pg 或 pgrjz - 启动 PGRJZ 自动化运行\n"
        "• #op ex start - 运行外部 begin.vbs 启动脚本\n\n"
        "📌 【25566 后台服务控制 (#op sv <指令>)】\n"
        "• #op sv ping - 检查后台服务状态及 Handlepush 开关\n"
        "• #op sv start - 恢复后台服务及定时检查 (run_alas_mumu_check)\n"
        "• #op sv stop - 暂停后台推送并释放 Alas/Mumu 进程\n"
        "• #op sv shutdown - 关闭 25566 后台接收服务\n"
        "• #op sv bot/start - 重新无窗口启动 QBot\n"
        "• #op sv bot/shutdown - 精准清理/关闭 QBot 进程\n"
        "• #op sv music/start - 后台启动 MusicDL 服务并隐藏窗口\n"
        "• #op sv music/ffm - 单开线程运行音频处理任务 (ffmpeg)\n"
        "• #op sv music/stop - 停止 MusicDL 服务及清理 37777 端口"
    )

  elif sub_cmd == "restart":
    target_port = getattr(client.data_mgr, "target_port", 25566)
    url = f"http://127.0.0.1:{target_port}/bot/start"
    try:
      req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
      res = urllib.request.urlopen(req, timeout=3).read().decode("utf-8")
      return f"🔄 已触发机器人重启指令 (/{target_port}/bot/start)，响应：\n{res}"
    except Exception as e:
      return f"❌ 触发重启指令失败: {e}"

  elif sub_cmd == "shutdown":
    if client.bot_loop:
      import asyncio

      asyncio.run_coroutine_threadsafe(
          client.shutdown_system("OP 指令触发"), client.bot_loop
      )
    notify_num = getattr(client.data_mgr, "notify_group_num", 2)
    return f"🛑 正在准备关闭程序并通知群 {notify_num}..."

  elif sub_cmd == "notify":
    notify_args = args[1:]
    if not notify_args:
      return "⚠️ 请提供 notify 参数，例如：`#op notify set 2`"

    n_action = notify_args[0].lower()
    if n_action == "set":
      if len(notify_args) > 1 and notify_args[1].isdigit():
        target_num = int(notify_args[1])
        setattr(client.data_mgr, "notify_group_num", target_num)
        client.data_mgr.save_data()
        return f"✅ 已将上下线通知群设置为：【群 {target_num}】"
      return "⚠️ 请提供要设置的群编号数字，例如：`#op notify set 2`"

    return "⚠️ 未知的 notify 子指令。可使用 `#op notify set [num]`"

  elif sub_cmd == "ex":
    if len(args) > 1 and args[1].lower() == "start":
      try:
        subprocess.Popen(
            ["wscript.exe", r"Perseus\begin.vbs"]
        )
        return "🚀 已成功发起分离运行指令！"
      except Exception as e:
        return f"❌ 运行失败: {e}"
    return "⚠️ 请使用正确格式：`#op ex start`"

  elif sub_cmd == "run":
    if len(args) < 2:
      return "⚠️ 请提供运行参数，例如：`#op run task1,task2`"
    try:
      target_port = getattr(client.data_mgr, "target_port", 25566)
      url = f"http://127.0.0.1:{target_port}/run?task={urllib.parse.quote(' '.join(args[1:]))}"

      req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
      res = urllib.request.urlopen(req, timeout=3).read().decode("utf-8")
      return f"🚀 已发送请求至 {target_port} 端口，响应：{res}"
    except Exception as e:
      return f"❌ 调用目标 /run 接口失败: {e}"

  elif sub_cmd == "sv":
    if len(args) < 2:
      return "⚠️ 请提供服务器操作指令，例如：`#op sv ping` 或 `#op sv stop`"

    sv_action = args[1].lower()
    extra_params = " ".join(args[2:]) if len(args) > 2 else ""

    target_port = getattr(client.data_mgr, "target_port", 25566)
    url = f"http://127.0.0.1:{target_port}/{sv_action}"
    if extra_params:
      url += f"?task={urllib.parse.quote(extra_params)}"

    try:
      req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
      res = urllib.request.urlopen(req, timeout=3).read().decode("utf-8")
      return f"🌐 [{target_port} 服务响应] /{sv_action}:\n{res}"
    except Exception as e:
      return f"❌ 调用 {target_port} /{sv_action} 接口失败: {e}"

  elif sub_cmd == "list":
    return "👑 【管理员 OP 名单】\n" + "\n".join(
        [f"- {op_id[:6]}... ({op_id})" for op_id in client.data_mgr.op_list]
    )

  elif sub_cmd == "stop":
    client.data_mgr.system_active = False
    client.data_mgr.save_data()
    return "🛑 已成功暂停娱乐与辅助功能！"

  elif sub_cmd == "start":
    client.data_mgr.system_active = True
    client.data_mgr.save_data()
    return "🚀 已成功重新启用功能！"

  elif sub_cmd == "push":
    push_args = args[1:]
    if not push_args:
      return "⚠️ 请提供 push 参数，例如：`#op push set 1` / `#op push start` / `#op push stop`"

    p_action = push_args[0].lower()
    if p_action == "set":
      if len(push_args) > 1 and push_args[1].isdigit():
        target_num = int(push_args[1])
        setattr(client.data_mgr, "push_target_group", target_num)
        client.data_mgr.save_data()
        return f"✅ 已将 Push 消息的默认推送群设置为：【群 {target_num}】"
      return "⚠️ 请提供要设置的群编号数字，例如：`#op push set 1`"

    elif p_action == "start":
      setattr(client.data_mgr, "push_active", True)
      client.data_mgr.save_data()
      return "🚀 已成功开启 Push 消息转发！"

    elif p_action == "stop":
      setattr(client.data_mgr, "push_active", False)
      client.data_mgr.save_data()
      return "🛑 已成功关闭 Push 消息转发！"

    return "⚠️ 未知的 push 子指令。可使用 `#op push set [num]`、`#op push start` 或 `#op push stop`"

  elif sub_cmd == "group":
    group_args = args[1:]
    if not group_args or group_args[0].isdigit():
      target_num = group_args[0] if group_args else None
      if not target_num:
        return "⚠️ 请提供群编号数字，例如：`#op group 1`"
      client.data_mgr.group_tags[group_id] = int(target_num)
      client.data_mgr.save_data()
      return f"✅ 已成功将当前群标记为：【群 {target_num}】！"

    action = group_args[0].lower()
    if action == "list":
      lines = [
          f"- 群 {num}: {gid}"
          for gid, num in sorted(
              client.data_mgr.group_tags.items(), key=lambda x: x[1]
          )
      ]
      return "📋 【群编号绑定列表】\n" + ("\n".join(lines) if lines else "暂无")
    elif action == "get":
      return f"📌 当前群已被标记为：【群 {client.data_mgr.group_tags.get(group_id, '未绑定')}】"

  elif sub_cmd == "add":
    mentions = getattr(raw_message, "mentions", [])
    target_id = (
        (getattr(mentions[0], "member_openid", None) or getattr(mentions[0], "id", None))
        if mentions
        else (args[1].strip() if len(args) > 1 else None)
    )
    if not target_id:
      return "⚠️ 请 @某人 或提供 OpenID"
    target_id = target_id.upper()
    client.data_mgr.op_list.add(target_id)
    client.data_mgr.save_data()
    return f"✅ 用户 [{target_id[:6]}...] 已提权为 OP。"

  elif sub_cmd in ["remove", "del", "rm"]:
    mentions = getattr(raw_message, "mentions", [])
    target_id = (
        (getattr(mentions[0], "member_openid", None) or getattr(mentions[0], "id", None))
        if mentions
        else (args[1].strip() if len(args) > 1 else None)
    )
    if not target_id or target_id.upper() == DataManager.DEFAULT_OP:
      return "❌ 操作受限或未识别到有效目标"
    target_id = target_id.upper()
    if target_id in client.data_mgr.op_list:
      client.data_mgr.op_list.remove(target_id)
      client.data_mgr.save_data()
      return f"🗑️ 已取消用户 [{target_id[:6]}...] 的 OP 权限。"
    return "ℹ️ 该用户不是 OP。"

  return "⚠️ 未知的 OP 命令。可使用 `#op help` 查看帮助。"
