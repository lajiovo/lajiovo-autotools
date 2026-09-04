import os
import re
import json
import time
import subprocess
import urllib.parse
import urllib.request
import psutil
from botpy.message import GroupMessage
from config import BotDataManager, zConfig

# ------------------- 配置读取 -------------------
PRESET_LOG_PATHS = zConfig.get_config("bot.opcmd.preset_log_paths", default=[])
ALAS_ERROR_LOG_PATH = zConfig.get_config("bot.opcmd.alas_error_log_path")
SENSITIVE_PATTERNS = zConfig.get_config("bot.opcmd.sensitive_patterns", default=[])
MASK_REPLACEMENT = zConfig.get_config("bot.opcmd.mask_replacement")
BEGINVBS = zConfig.get_config("bot.opcmd.beginvbs")

# 动态配置 Node.js 路径及 Yunzai 目录
NODEEXE = zConfig.get_config("bot.opcmd.node")
YZDIR = zConfig.get_config("bot.opcmd.yzdir")

# 内存中缓存日志查看状态与全局 PID 记录
LOG_STATE_CACHE = {}
YZ_PID = None


# ------------------- DataMgr 数据适配层 -------------------
class DataMgrAdapter:
    """封装与规范化 DataMgr 接口调用，保证数据落盘至对应配置块"""

    @staticmethod
    def get_opsetting(data_mgr) -> dict:
        """读取系统完整配置 opsetting"""
        if hasattr(data_mgr, "get_opsetting"):
            try:
                res = data_mgr.get_opsetting()
                if isinstance(res, dict):
                    return res
            except Exception:
                pass

        op_list = data_mgr.get_extra_data("op_list", [BotDataManager.DEFAULT_OP])
        system_active = data_mgr.get_extra_data("system_active", True)
        notify_group_num = data_mgr.get_extra_data("notify_group_num", 2)
        push_target_group = data_mgr.get_extra_data("push_target_group", 1)
        push_active = data_mgr.get_extra_data("push_active", True)
        group_tags = data_mgr.get_extra_data("group_tags", {})

        return {
            "op_list": list(op_list),
            "system_active": system_active,
            "notify_group_num": notify_group_num,
            "push_target_group": push_target_group,
            "push_active": push_active,
            "group_tags": group_tags,
        }

    @staticmethod
    def set_opsetting(data_mgr, setting_dict: dict):
        """设置并直接落盘保存 opsetting"""
        if hasattr(data_mgr, "set_opsetting"):
            try:
                data_mgr.set_opsetting(setting_dict)
                return
            except Exception:
                pass

        for k, v in setting_dict.items():
            data_mgr.set_extra_data(k, v)
        if hasattr(data_mgr, "save_opsetting"):
            data_mgr.save_opsetting()

    @classmethod
    def get_op_list(cls, data_mgr) -> set:
        setting = cls.get_opsetting(data_mgr)
        return set(setting.get("op_list", [BotDataManager.DEFAULT_OP]))

    @classmethod
    def add_op(cls, data_mgr, op_id: str):
        setting = cls.get_opsetting(data_mgr)
        op_list = set(setting.get("op_list", []))
        op_list.add(op_id.upper())
        setting["op_list"] = list(op_list)
        cls.set_opsetting(data_mgr, setting)

    @classmethod
    def remove_op(cls, data_mgr, op_id: str):
        setting = cls.get_opsetting(data_mgr)
        op_list = set(setting.get("op_list", []))
        op_id_upper = op_id.upper()
        if op_id_upper in op_list:
            op_list.remove(op_id_upper)
            setting["op_list"] = list(op_list)
            cls.set_opsetting(data_mgr, setting)

    @classmethod
    def get_group_tags(cls, data_mgr) -> dict:
        setting = cls.get_opsetting(data_mgr)
        return setting.get("group_tags", {})

    @classmethod
    def set_group_tag(cls, data_mgr, group_id: str, tag_num: int):
        """将 grouptag 同时存入 opsetting 和 groupinfo"""
        setting = cls.get_opsetting(data_mgr)
        group_tags = setting.get("group_tags", {})
        group_tags[group_id] = tag_num
        setting["group_tags"] = group_tags
        cls.set_opsetting(data_mgr, setting)

        if hasattr(data_mgr, "set_groupinfo"):
            try:
                data_mgr.set_groupinfo(group_id, {"tag": tag_num})
            except Exception:
                pass
        if hasattr(data_mgr, "save_groupinfo"):
            try:
                data_mgr.save_groupinfo()
            except Exception:
                pass

    @classmethod
    def set_notify_group_num(cls, data_mgr, num: int):
        """存入 opsetting"""
        setting = cls.get_opsetting(data_mgr)
        setting["notify_group_num"] = num
        cls.set_opsetting(data_mgr, setting)

    @classmethod
    def set_push_target_group(cls, data_mgr, num: int):
        """存入 opsetting"""
        setting = cls.get_opsetting(data_mgr)
        setting["push_target_group"] = num
        cls.set_opsetting(data_mgr, setting)

    @classmethod
    def set_push_active(cls, data_mgr, active: bool):
        setting = cls.get_opsetting(data_mgr)
        setting["push_active"] = active
        cls.set_opsetting(data_mgr, setting)

    @classmethod
    def set_system_active(cls, data_mgr, active: bool):
        setting = cls.get_opsetting(data_mgr)
        setting["system_active"] = active
        cls.set_opsetting(data_mgr, setting)


def _sanitize_path(path_str: str) -> str:
    """隐私脱敏处理：从配置中读取敏感目录并隐藏"""
    if not path_str:
        return ""
    sanitized = path_str
    for pattern in SENSITIVE_PATTERNS:
        sanitized = sanitized.replace(pattern, MASK_REPLACEMENT)
    return sanitized


def import_time_format(timestamp: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))


# ------------------- 辅助函数：构建 Keyboard 数据结构 -------------------
def _make_button(label: str, action_data: str, is_url: bool = False, style: int = 1) -> dict:
    """构建标准单按钮格式"""
    if is_url:
        return {
            "render_data": {"label": label, "style": style},
            "action": {
                "type": 0,  # 网页跳转
                "permission": {"type": 2},
                "data": action_data,
            },
        }
    return {
        "render_data": {"label": label, "style": style},
        "action": {
            "type": 2,  # 填字并直接发送指令
            "permission": {"type": 2},
            "data": action_data,
            "enter": True,
        },
    }


def _build_keyboard(button_rows: list) -> dict:
    """构建包含多行按钮的 inline keyboard 数据结构"""
    rows = []
    for row in button_rows:
        buttons = []
        for b in row:
            if isinstance(b, dict):
                buttons.append(b)
            elif isinstance(b, tuple) and len(b) >= 2:
                label, act = b[0], b[1]
                is_url = b[2] if len(b) > 2 and isinstance(b[2], bool) else False
                style = b[3] if len(b) > 3 else (1 if not is_url else 0)
                buttons.append(_make_button(label, act, is_url, style))
        rows.append({"buttons": buttons})
    return {"content": {"rows": rows}}


def _format_msg_type_2(content: str, keyboard_rows: list = None) -> dict:
    """返回规范 msg_type: 2 结构"""
    res = {"msg_type": 2, "content": content}
    if keyboard_rows:
        res["keyboard"] = _build_keyboard(keyboard_rows)
    return res


def _confirm_c_dialog(prompt_msg: str, real_cmd: str) -> dict:
    """带 -c 时发消息确认，提供极简二次确认框"""
    content = f"⚠️ **操作确认提示**\n即将执行：`{prompt_msg}`\n点击下方按钮进行确认："
    kb = [
        [("确认执行", real_cmd)],
        [("取消", "#op help")],
    ]
    return _format_msg_type_2(content, kb)


# ------------------- 主命令处理逻辑 -------------------
async def handle_op_command(
    client,
    args: list,
    sender_openid: str,
    raw_message: GroupMessage,
    group_id: str,
):
    data_mgr = client.data_mgr
    op_list = DataMgrAdapter.get_op_list(data_mgr)
    group_tags = DataMgrAdapter.get_group_tags(data_mgr)

    sender_openid_upper = sender_openid.upper() if sender_openid else ""
    is_op = sender_openid_upper in op_list

    # 无参数引导：仅提供菜单 1-4
    if not args:
        group_tag_info = (
            f"（当前群编号：群 {group_tags[group_id]}）"
            if group_id in group_tags
            else ""
        )
        if is_op:
            content = f"👑 **OP 管理系统** {group_tag_info}\n请选择分类："
            kb = [
                [("📖Page①", "#op help 1"), ("📖Page②", "#op help 2")],
                [("📖Page③", "#op help 3"), ("📖Page④", "#op help 4")],
            ]
        else:
            content = f"👋 **你好呀！快去试试玩吧！** {group_tag_info}"
            kb = [
                [("🎣打捞", "#打捞"), ("🔮运势", "#运势")],
                [("❓帮助", "#help")],
            ]
        return _format_msg_type_2(content, kb)

    # 🛑 权限控制：非 OP 拒绝响应
    if not is_op:
        return _format_msg_type_2("❌ **权限不足！** 只有授权 OP 才能执行。")

    sub_cmd = args[0].lower()

    # ------------------- 1. 主菜单与帮助 (#op help / #op 1-4) -------------------
    if sub_cmd in ["help", "?", "帮助", "1", "2", "3", "4"]:
        page = 1
        if sub_cmd in ["1", "2", "3", "4"]:
            page = int(sub_cmd)
        elif len(args) > 1 and args[1].isdigit():
            page = int(args[1])
        return _render_help_page(page)

    # ------------------- 2. 系统硬件信息 (#op sys) -------------------
    elif sub_cmd in ["sys", "status", "cpu", "sysinfo"]:
        try:
            cpu_usage = psutil.cpu_percent(interval=0.3)
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()

            disk_lines = []
            for part in psutil.disk_partitions(all=False):
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    disk_lines.append(f"`{part.mountpoint}` {usage.percent}%")
                except Exception:
                    pass
            disk_str = " | ".join(disk_lines[:3]) if disk_lines else "无"

            content = (
                "🖥️ **系统占用状态**\n"
                f"• CPU 占用: `{cpu_usage}%`\n"
                f"• 内存占用: `{mem.percent}%` ({mem.used/(1024**3):.1f}G/{mem.total/(1024**3):.1f}G)\n"
                f"• Swap 占用: `{swap.percent}%`\n"
                f"• 磁盘占用: {disk_str}"
            )
            kb = [
                [("🔄刷新", "#op sys"), ("🔙返回", "#op help 1")]
            ]
            return _format_msg_type_2(content, kb)
        except Exception as e:
            return _format_msg_type_2(f"❌ **获取系统资源占用失败**: `{e}`")

    # ------------------- 3. 进程管理 Yunzai (#op yz) -------------------
    elif sub_cmd == "yz":
        global YZ_PID
        yz_action = args[1].lower() if len(args) > 1 else ""

        if yz_action == "start":
            # 查重进程
            running_proc = None
            for p in psutil.process_iter(["pid", "name", "cwd", "cmdline"]):
                try:
                    if p.info["name"] and "node" in p.info["name"].lower():
                        cwd = p.info["cwd"] or ""
                        cmdline = " ".join(p.info["cmdline"] or [])
                        if YZDIR.lower() in cwd.lower() or "app" in cmdline:
                            running_proc = p
                            break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            if running_proc:
                content = f"⚠️ **Yunzai 运行中** (PID: `{running_proc.pid}`)"
                kb = [[("🛑终止", "#op yz kill"), ("🔙返回", "#op help 4")]]
                return _format_msg_type_2(content, kb)

            if not os.path.exists(NODEEXE) or not os.path.exists(YZDIR):
                return _format_msg_type_2("❌ **Node 或 Yunzai 路径配置无效！**")

            try:
                creationflags = 0x08000000  # 静默无窗口运行
                proc = subprocess.Popen(
                    [NODEEXE, "app"],
                    cwd=YZDIR,
                    creationflags=creationflags,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                YZ_PID = proc.pid
                content = f"🚀 **Yunzai 已无窗口启动** (PID: `{YZ_PID}`)"
                kb = [[("🛑终止", "#op yz kill"), ("🔙返回", "#op help 4")]]
                return _format_msg_type_2(content, kb)
            except Exception as e:
                return _format_msg_type_2(f"❌ **启动失败**: `{e}`")

        elif yz_action == "kill":
            killed_count = 0
            for p in psutil.process_iter(["pid", "name", "cwd"]):
                try:
                    if p.info["name"] and "node" in p.info["name"].lower():
                        cwd = p.info["cwd"] or ""
                        if YZDIR.lower() in cwd.lower():
                            p.kill()
                            killed_count += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            if YZ_PID:
                try:
                    subprocess.run(["taskkill", "/F", "/PID", str(YZ_PID)], capture_output=True)
                    killed_count += 1
                except Exception:
                    pass
                YZ_PID = None

            content = f"🛑 **已终止 `{killed_count}` 个 Yunzai 进程**" if killed_count else "ℹ️ **未发现运行中的 Yunzai 进程**"
            kb = [[("🚀启动", "#op yz start"), ("🔙返回", "#op help 4")]]
            return _format_msg_type_2(content, kb)

        elif yz_action == "status":
            is_running = False
            proc_pid = None
            for p in psutil.process_iter(["pid", "name", "cwd"]):
                try:
                    if p.info["name"] and "node" in p.info["name"].lower():
                        cwd = p.info["cwd"] or ""
                        if YZDIR.lower() in cwd.lower():
                            is_running = True
                            proc_pid = p.pid
                            break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            status_txt = f"运行中 (PID: `{proc_pid}`)" if is_running else "未运行"
            content = f"📊 **Yunzai 状态**: {status_txt}"
            kb = [[("🚀启动", "#op yz start"), ("🛑终止", "#op yz kill")]]
            return _format_msg_type_2(content, kb)

        content = "⚠️ 请指定正确参数：`start` / `kill` / `status`"
        kb = [[("🚀启动", "#op yz start"), ("🛑终止", "#op yz kill")]]
        return _format_msg_type_2(content, kb)

    # ------------------- 4. 面板与菜单管理 (#op panel / #op menu) -------------------
    elif sub_cmd == "panel":
        scope = args[1].lower() if len(args) > 1 else "group"
        if scope not in ["c2c", "group"]:
            return _format_msg_type_2("⚠️ 作用域仅支持 `c2c` 或 `group`！")

        target_type = "specific" if scope == "group" and group_id else "all"
        group_openids = [group_id] if scope == "group" and group_id else None
        user_openids = [sender_openid] if scope == "c2c" else None

        panel_payload = {
            "items": [
                {"type": "command", "name": "#ping", "desc": "检查机器人状态"},
                {"type": "command", "name": "#help", "desc": "获取菜单帮助说明"},
                {"type": "command", "name": "#打捞", "desc": "运行打捞玩法"},
                {"type": "command", "name": "#运势", "desc": "查看今日运势"},
                {"type": "command", "name": "#op", "desc": "OP 管理员控制"},
            ],
            "remark": f"系统{scope.upper()}面板",
        }

        try:
            res = await client.create_panel(
                scope=scope,
                panel=panel_payload,
                target_type=target_type,
                user_openids=user_openids,
                group_openids=group_openids,
            )
            panel_id = res.get("panel_id", "未知")
            return _format_msg_type_2(f"✅ 面板创建成功 ID: `{panel_id}`")
        except Exception as e:
            return _format_msg_type_2(f"❌ 创建面板失败: `{e}`")

    elif sub_cmd == "menu":
        menu_payload = {
            "items": [
                {"type": "send_message", "name": "状态查询", "send_message": "#ping"},
                {"type": "send_message", "name": "帮助", "send_message": "#help"},
                {
                    "type": "menu",
                    "name": "日常功能",
                    "sub_menu_items": [
                        {"type": "send_message", "name": "打捞", "send_message": "#打捞"},
                        {"type": "send_message", "name": "运势", "send_message": "#运势"},
                    ],
                },
                {"type": "send_message", "name": "管理员", "send_message": "#op"},
            ]
        }
        try:
            res = await client.set_c2c_menu(menu=menu_payload)
            version = res.get("version", "未知")
            return _format_msg_type_2(f"✅ 自定义菜单修改成功 版本: `{version}`")
        except Exception as e:
            return _format_msg_type_2(f"❌ 修改菜单失败: `{e}`")

    # ------------------- 5. 日志查看接口 (#op log) -------------------
    elif sub_cmd == "log":
        log_args = args[1:]
        state_key = f"{group_id}_{sender_openid}"

        # log 主菜单
        if not log_args:
            content = "📂 **【日志目录选择】**\n请选择需要查看的预设日志："
            kb = [
                [("📂预设①", "#op log get 1"), ("📂预设②", "#op log get 2")],
                [("📂预设③", "#op log get 3"), ("📂预设④", "#op log get 4")],
                [("⚠️错误集", "#op log find 1")],
            ]
            return _format_msg_type_2(content, kb)

        action = log_args[0].lower()

        # #op log find 1 特殊处理 Alas 错误日志文件夹
        if action == "find" and len(log_args) > 1 and log_args[1] == "1":
            target_dir = ALAS_ERROR_LOG_PATH
            if not os.path.exists(target_dir):
                return _format_msg_type_2(f"❌ 错误日志路径不存在: `{_sanitize_path(target_dir)}`")

            try:
                subfolders = []
                for entry in os.scandir(target_dir):
                    if entry.is_dir():
                        subfolders.append((entry.path, entry.stat().st_mtime))

                subfolders.sort(key=lambda x: x[1], reverse=True)
                folder_list = [f[0] for f in subfolders]

                LOG_STATE_CACHE[state_key] = {
                    "mode": "folder",
                    "dir": target_dir,
                    "items": folder_list,
                    "page": 1,
                    "page_size": 5,
                    "current_file": None,
                    "image_path": None,
                    "lines": [],
                    "log_page": 1,
                }
                return _render_item_list(state_key, 1)
            except Exception as e:
                return _format_msg_type_2(f"❌ 读取错误日志目录失败: `{e}`")

        elif action == "get":
            path_idx = (
                int(log_args[1]) - 1
                if len(log_args) > 1 and log_args[1].isdigit()
                else 0
            )
            if path_idx < 0 or path_idx >= len(PRESET_LOG_PATHS):
                return _format_msg_type_2(f"⚠️ 预设序号无效，可选 1 ~ {len(PRESET_LOG_PATHS)}")

            target_dir = PRESET_LOG_PATHS[path_idx]
            if not os.path.exists(target_dir):
                return _format_msg_type_2(f"❌ 日志路径不存在: `{_sanitize_path(target_dir)}`")

            try:
                all_files = []
                for root, _, files in os.walk(target_dir):
                    for f in files:
                        full_path = os.path.join(root, f)
                        try:
                            mtime = os.path.getmtime(full_path)
                            all_files.append((full_path, mtime))
                        except Exception:
                            pass

                all_files.sort(key=lambda x: x[1], reverse=True)
                file_list = [f[0] for f in all_files]

                LOG_STATE_CACHE[state_key] = {
                    "mode": "file",
                    "dir": target_dir,
                    "items": file_list,
                    "page": 1,
                    "page_size": 5,
                    "current_file": None,
                    "image_path": None,
                    "lines": [],
                    "log_page": 1,
                }
                return _render_item_list(state_key, 1)
            except Exception as e:
                return _format_msg_type_2(f"❌ 读取日志文件列表失败: `{e}`")

        elif action == "page":
            if state_key not in LOG_STATE_CACHE:
                return _format_msg_type_2("⚠️ 请先读取日志目录！", [[("📂日志", "#op log")]])

            page_num = (
                int(log_args[1])
                if len(log_args) > 1 and log_args[1].isdigit()
                else LOG_STATE_CACHE[state_key]["page"] + 1
            )
            return _render_item_list(state_key, page_num)

        elif action == "open":
            if state_key not in LOG_STATE_CACHE or not LOG_STATE_CACHE[state_key]["items"]:
                return _format_msg_type_2("⚠️ 当前无可用列表！", [[("📂日志", "#op log")]])

            state = LOG_STATE_CACHE[state_key]
            items = state["items"]
            mode = state.get("mode", "file")
            current_page = state.get("page", 1)
            page_size = state.get("page_size", 5)

            input_num = (
                int(log_args[1])
                if len(log_args) > 1 and log_args[1].isdigit()
                else 1
            )

            start_idx = (current_page - 1) * page_size
            if 1 <= input_num <= page_size:
                target_idx = start_idx + (input_num - 1)
            else:
                target_idx = input_num - 1

            if target_idx < 0 or target_idx >= len(items):
                return _format_msg_type_2(f"⚠️ 序号超出范围 (1 ~ {len(items)})")

            target_item = items[target_idx]
            target_file = target_item
            found_img = None

            if mode == "folder":
                if not os.path.isdir(target_item):
                    return _format_msg_type_2(f"❌ 找不到对应目录: `{_sanitize_path(target_item)}`")

                log_txt_path = os.path.join(target_item, "log.txt")
                if not os.path.exists(log_txt_path):
                    txt_files = [
                        os.path.join(target_item, f)
                        for f in os.listdir(target_item)
                        if f.lower().endswith(".txt")
                    ]
                    target_file = txt_files[0] if txt_files else None
                else:
                    target_file = log_txt_path

                img_files = [
                    os.path.join(target_item, f)
                    for f in os.listdir(target_item)
                    if f.lower().endswith((".png", ".jpg", ".jpeg"))
                ]
                if img_files:
                    found_img = img_files[0]

            if not target_file or not os.path.exists(target_file):
                return _format_msg_type_2("❌ 日志文本不存在")

            try:
                try:
                    with open(target_file, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                except UnicodeDecodeError:
                    with open(target_file, "r", encoding="gbk", errors="ignore") as f:
                        lines = f.readlines()

                state["current_file"] = target_file
                state["image_path"] = found_img
                state["lines"] = lines
                state["last_open_num"] = input_num  # 记住上次打开的序号用于刷新
                state["log_page"] = 1

                return _render_log_content(state_key, 1)
            except Exception as e:
                return _format_msg_type_2(f"❌ 读取日志失败: `{e}`")

        elif action == "goto":
            if state_key not in LOG_STATE_CACHE or not LOG_STATE_CACHE[state_key]["current_file"]:
                return _format_msg_type_2("⚠️ 当前未打开日志！")

            goto_page = (
                int(log_args[1])
                if len(log_args) > 1 and log_args[1].isdigit()
                else LOG_STATE_CACHE[state_key]["log_page"] + 1
            )

            if goto_page == 0:
                img_path = LOG_STATE_CACHE[state_key].get("image_path")
                if img_path and os.path.exists(img_path):
                    filename = os.path.basename(img_path)
                    return {
                        "msg_type": 7,
                        "file_path": img_path,
                        "content": f"🖼️ 错误截图: {filename}",
                    }
                return _format_msg_type_2("⚠️ 未找到截图！")

            return _render_log_content(state_key, goto_page)

        return _format_msg_type_2("⚠️ 未知的 log 指令")

    # ------------------- 6. 系统重启 / 关闭 / 分离启动 -------------------
    elif sub_cmd == "restart":
        has_c = len(args) > 1 and args[1].lower() == "-c"
        if has_c:
            return _confirm_c_dialog("#op restart 重启程序", "#op restart")

        target_port = client.data_mgr.get_extra_data("target_port", 25566)
        url = f"http://127.0.0.1:{target_port}/bot/start"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            res = urllib.request.urlopen(req, timeout=3).read().decode("utf-8")
            return _format_msg_type_2(f"🔄 **机器人重启响应**:\n```\n{res}\n```")
        except Exception as e:
            return _format_msg_type_2(f"❌ 重启失败: `{e}`")

    elif sub_cmd == "shutdown":
        if client.bot_loop:
            import asyncio
            asyncio.run_coroutine_threadsafe(
                client.shutdown_system("OP 指令触发"), client.bot_loop
            )
        setting = DataMgrAdapter.get_opsetting(data_mgr)
        notify_num = setting.get("notify_group_num", 2)
        return _format_msg_type_2(f"🛑 **正关闭程序并通知群 {notify_num}...**")

    elif sub_cmd == "ex":
        if len(args) > 1 and args[1].lower() == "start":
            has_c = len(args) > 2 and args[2].lower() == "-c"
            if has_c:
                return _confirm_c_dialog("#op ex start 主分离服务", "#op ex start")

            try:
                subprocess.Popen(["wscript.exe", BEGINVBS])
                return _format_msg_type_2("🚀 **已成功发起分离运行！**")
            except Exception as e:
                return _format_msg_type_2(f"❌ 运行失败: `{e}`")
        return _format_msg_type_2("⚠️ 格式：`#op ex start`")

    # ------------------- 7. 后台服务控制 (#op sv) -------------------
    elif sub_cmd == "sv":
        if len(args) < 2:
            content = "⚙️ **【后台服务控制】**\n请选择操作："
            kb = [
                [("📡ping", "#op sv ping"), ("🚀start", "#op sv start"), ("🛑stop", "#op sv stop -c")],
                [("🔌cp/start", "#op sv cp/start -c"), ("🌐cp/get", "#op sv cp/get"), ("🔌cp/stop", "#op sv cp/stop")],
            ]
            return _format_msg_type_2(content, kb)

        sv_action = args[1].lower()

        # 带 -c 触发确认对话框，不带直接执行
        has_c = len(args) > 2 and args[2].lower() == "-c"
        if has_c:
            return _confirm_c_dialog(f"#op sv {sv_action}", f"#op sv {sv_action}")

        extra_params = " ".join([a for a in args[2:] if a.lower() != "-c"])

        target_port = client.data_mgr.get_extra_data("target_port", 25566)
        url = f"http://127.0.0.1:{target_port}/{sv_action}"
        if extra_params:
            url += f"?task={urllib.parse.quote(extra_params)}"

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            res = urllib.request.urlopen(req, timeout=3).read().decode("utf-8")
            content = f"🌐 **[响应]** `/{sv_action}`:\n```\n{res}\n```"

            # sv cp/get 解析网页地址生成 4 个链接跳转按钮
            if sv_action in ["cp/get", "cp/start"]:
                match = re.search(r"https?://[a-zA-Z0-9.-]+\.cpolar\.[a-zA-Z0-9]+|https?://[a-zA-Z0-9.-]+", res)
                if match:
                    base_url = match.group(0).rstrip("/")
                    link_kb = [
                        [
                            ("🏠主页", f"{base_url}/main", True),
                            ("🎛️控制", f"{base_url}/main/dash.html", True)
                        ],
                        [
                            ("🌐根域", f"{base_url}/", True),
                            ("🤖Bot", f"{base_url}/bot", True)
                        ]
                    ]
                    return _format_msg_type_2(content, link_kb)

            return _format_msg_type_2(content)
        except Exception as e:
            return _format_msg_type_2(f"❌ 调用 `/{sv_action}` 失败: `{e}`")

    # ------------------- 8. 隐藏的任务运行菜单 (#op run) -------------------
    elif sub_cmd == "run":
        if len(args) < 2:
            content = "🤖 **【任务控制菜单】**\n请选择需控制的进程与操作："
            kb = [
                [("📱mumu启动", "#op run mumu start -c"), ("📱mumu强杀", "#op run mumu kill -c"), ("📱mumu在线", "#op run mumu online")],
                [("🚢alas启动", "#op run alas start -c"), ("🚢alas强杀", "#op run alas kill -c"), ("🚢alas在线", "#op run alas online")],
            ]
            return _format_msg_type_2(content, kb)

        task_type = args[1].lower() if len(args) > 1 else ""
        sub_action = args[2].lower() if len(args) > 2 else ""

        # 带 -c 触发确认对话框，不带直接执行
        has_c = len(args) > 3 and args[3].lower() == "-c"
        if has_c:
            return _confirm_c_dialog(f"#op run {task_type} {sub_action}", f"#op run {task_type} {sub_action}")

        # 过滤掉 -c 构建真正的请求参数
        real_task_args = " ".join([a for a in args[1:] if a.lower() != "-c"])
        try:
            target_port = client.data_mgr.get_extra_data("target_port", 25566)
            url = f"http://127.0.0.1:{target_port}/run?task={urllib.parse.quote(real_task_args)}"

            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            res = urllib.request.urlopen(req, timeout=3).read().decode("utf-8")
            return _format_msg_type_2(f"🚀 **任务响应**: `{res}`")
        except Exception as e:
            return _format_msg_type_2(f"❌ 调用 `/run` 失败: `{e}`")

    # ------------------- 9. Push 消息历史与设置 (#op push) -------------------
    elif sub_cmd == "push":
        push_args = args[1:]
        if not push_args:
            content = "📬 **【Push 推送选择】**\n请选择级别与读取范围："
            kb = [
                [("📢通知", "#op push get notify 1-3"), ("⚠️警告", "#op push get warning 1-3"), ("❌错误", "#op push get error 1-3")],
                [("📩最新", "#op push get notify 1"), ("📩前二", "#op push get notify 1-2"), ("📩前三", "#op push get notify 1-3")],
                [("📩四五", "#op push get notify 4-5"), ("📩六七", "#op push get notify 6-7")],
            ]
            return _format_msg_type_2(content, kb)

        p_action = push_args[0].lower()

        if p_action == "set":
            if len(push_args) > 1 and push_args[1].isdigit():
                target_num = int(push_args[1])
                DataMgrAdapter.set_push_target_group(data_mgr, target_num)
                return _format_msg_type_2(f"✅ Push 目标群已设置为：【群 {target_num}】")
            return _format_msg_type_2("⚠️ 请提供群编号数字")

        elif p_action == "start":
            DataMgrAdapter.set_push_active(data_mgr, True)
            return _format_msg_type_2("🚀 已开启 Push 转发！")

        elif p_action == "stop":
            DataMgrAdapter.set_push_active(data_mgr, False)
            return _format_msg_type_2("🛑 已关闭 Push 转发！")

        elif p_action == "get":
            PUSH_LEVELS = ("notify", "warning", "error")
            level = "notify"
            range_token = None
            extra_args = push_args[1:]

            if extra_args:
                first = extra_args[0].lower()
                aliases = {"notice": "notify", "warn": "warning", "err": "error"}
                first = aliases.get(first, first)
                if first in PUSH_LEVELS:
                    level = first
                    if len(extra_args) > 1:
                        range_token = extra_args[1]
                else:
                    range_token = extra_args[0]

            start_idx, end_idx = 1, 1
            if range_token:
                if "-" in range_token:
                    parts = range_token.split("-")
                    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                        start_idx = int(parts[0])
                        end_idx = int(parts[1])
                elif range_token.isdigit():
                    start_idx = end_idx = int(range_token)

            if start_idx < 1:
                start_idx = 1
            if end_idx < start_idx:
                end_idx = start_idx

            target_port = client.data_mgr.get_extra_data("target_port", 25566)
            url = f"http://127.0.0.1:{target_port}/pushlog/get/{level}/{start_idx}-{end_idx}"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                raw = urllib.request.urlopen(req, timeout=3).read().decode("utf-8")
                payload = json.loads(raw)
            except Exception as e:
                return _format_msg_type_2(f"❌ 读取 25566 Push 日志失败: `{e}`")

            if payload.get("status") not in ("ok", "success"):
                return _format_msg_type_2(f"⚠️ {payload.get('message', '读取失败')}")

            push_history = payload.get("data") or []
            total = int(payload.get("total") or 0)
            start_idx = int(payload.get("start") or start_idx)
            end_idx = int(payload.get("end") or end_idx)

            if not push_history:
                return _format_msg_type_2(f"📭 暂无 `{level}` Push 历史记录。")

            res_lines = [f"📬 **Push 历史 [{level}]** ({start_idx}-{end_idx} / 共 {total} 条)\n"]
            for idx, item in enumerate(push_history, start=start_idx):
                if isinstance(item, dict):
                    time_str = item.get("time") or item.get("timestamp") or "未知时间"
                    msg_content = item.get("markdown") or item.get("content") or item.get("title") or str(item)
                    title = item.get("title") or ""
                else:
                    time_str = "未知时间"
                    msg_content = str(item)
                    title = ""
                head = f"📌 [#{idx}] `{time_str}`"
                if title:
                    head += f" **{title}**"
                res_lines.append(f"{head}\n{msg_content}")

            kb = [
                [
                    ("📢通知", f"#op push get notify {start_idx}-{end_idx}"),
                    ("⚠️警告", f"#op push get warning {start_idx}-{end_idx}"),
                    ("❌错误", f"#op push get error {start_idx}-{end_idx}"),
                ]
            ]
            row_nav = []
            if start_idx > 1:
                prev_target = max(1, start_idx - 1)
                row_nav.append(("⬅️上一条", f"#op push get {level} {prev_target}"))
            if end_idx < total:
                next_target = end_idx + 1
                row_nav.append(("➡️下一条", f"#op push get {level} {next_target}"))
            if row_nav:
                kb.append(row_nav)

            return _format_msg_type_2("\n".join(res_lines), kb)

        return _format_msg_type_2("⚠️ 未知的 push 指令")

    # ------------------- 10. 群绑定管理 (#op group) -------------------
    elif sub_cmd == "group":
        group_args = args[1:]
        if not group_args or group_args[0].isdigit():
            target_num = group_args[0] if group_args else None
            if not target_num:
                return _format_msg_type_2("⚠️ 请提供群编号数字")
            tag_val = int(target_num)
            DataMgrAdapter.set_group_tag(data_mgr, group_id, tag_val)
            return _format_msg_type_2(f"✅ 当前群已标记为：【群 {target_num}】")

        action = group_args[0].lower()
        if action == "list":
            lines = [
                f"- 群 `{num}`: `{gid}`"
                for gid, num in sorted(group_tags.items(), key=lambda x: x[1])
            ]
            content = "📋 **【群编号绑定列表】**\n" + ("\n".join(lines) if lines else "暂无")
            return _format_msg_type_2(content)
        elif action == "get":
            return _format_msg_type_2(f"📌 当前群已被标记为：【群 {group_tags.get(group_id, '未绑定')}】")

    # ------------------- 11. 通知群设置 -------------------
    elif sub_cmd == "notify":
        notify_args = args[1:]
        if len(notify_args) > 1 and notify_args[0].lower() == "set" and notify_args[1].isdigit():
            target_num = int(notify_args[1])
            DataMgrAdapter.set_notify_group_num(data_mgr, target_num)
            return _format_msg_type_2(f"✅ 通知群已设置为：【群 {target_num}】")
        return _format_msg_type_2("⚠️ 格式：`#op notify set <数字>`")

    # ------------------- 12. 管理员权限变更 -------------------
    elif sub_cmd == "list":
        lines = [f"- `{op_id[:6]}...` (`{op_id}`)" for op_id in op_list]
        return _format_msg_type_2("👑 **【OP 管理员列表】**\n" + "\n".join(lines))

    elif sub_cmd == "stop":
        DataMgrAdapter.set_system_active(data_mgr, False)
        return _format_msg_type_2("🛑 已暂停机器人功能")

    elif sub_cmd == "start":
        DataMgrAdapter.set_system_active(data_mgr, True)
        return _format_msg_type_2("🚀 已恢复机器人功能")

    elif sub_cmd == "add":
        if sender_openid_upper != BotDataManager.DEFAULT_OP:
            return _format_msg_type_2("❌ 只有超级管理员才有权限提权！")
        mentions = getattr(raw_message, "mentions", [])
        target_id = (
            (getattr(mentions[0], "member_openid", None) or getattr(mentions[0], "id", None))
            if mentions
            else (args[1].strip() if len(args) > 1 else None)
        )
        if not target_id:
            return _format_msg_type_2("⚠️ 请 @某人 或提供 OpenID")
        DataMgrAdapter.add_op(data_mgr, target_id)
        return _format_msg_type_2(f"✅ 已添加 OP 用户 [{target_id[:6]}...]")

    elif sub_cmd in ["remove", "del", "rm"]:
        if sender_openid_upper != BotDataManager.DEFAULT_OP:
            return _format_msg_type_2("❌ 只有超级管理员才有权限撤权！")
        mentions = getattr(raw_message, "mentions", [])
        target_id = (
            (getattr(mentions[0], "member_openid", None) or getattr(mentions[0], "id", None))
            if mentions
            else (args[1].strip() if len(args) > 1 else None)
        )
        if not target_id or target_id.upper() == BotDataManager.DEFAULT_OP:
            return _format_msg_type_2("❌ 操作受限")
        DataMgrAdapter.remove_op(data_mgr, target_id)
        return _format_msg_type_2(f"🗑️ 已取消用户 [{target_id[:6]}...] 的 OP 权限")

    return _format_msg_type_2("⚠️ 未知的 OP 命令", [[("📖Page①", "#op help 1")]])


# ------------------- 界面渲染私有辅助函数 -------------------
def _render_help_page(page: int = 1) -> dict:
    """分发渲染分页式 OP 主菜单"""
    if page < 1:
        page = 1
    if page > 4:
        page = 4

    # 构建第一排：另外三页按钮（带 Emoji 且精简到 2 字）
    row1 = []
    page_labels = {1: "📖Page①", 2: "📖Page②", 3: "📖Page③", 4: "📖Page④"}
    for p in range(1, 5):
        if p != page:
            row1.append((page_labels[p], f"#op help {p}"))

    # 第二排：push 和 log（精简 label）
    row2 = [("📬推送", "#op push"), ("📂日志", "#op log")]

    if page == 1:
        content = (
            "👑 **【OP 菜单 - 第一页：基础控制】**\n"
            "-----------------------------------\n"
            "• `#op help` - 选项菜单列表\n"
            "• `#op sys` - 电脑资源占用\n"
            "• `#op stop` / `#op start` - 暂停/恢复功能\n"
            "• `#op restart` - 重启机器人 (带 -c 确认)\n"
            "• `#op shutdown` - 关闭程序\n"
            "• `#op list` - 管理员列表"
        )
        row3 = [("📊sys", "#op sys"), ("🔄重启", "#op restart -c")]
        kb = [row1, row2, row3]

    elif page == 2:
        content = (
            "👑 **【OP 菜单 - 第二页：绑定与推送】**\n"
            "-----------------------------------\n"
            "• `#op group <n>/list/get` - 群绑定标记管理\n"
            "• `#op push set <n>/start/stop/get` - 推送目标与控制\n"
            "• `#op notify set <数字>` - 设置通知接收群"
        )
        # 第二页规则：keyboard 无第三排
        kb = [row1, row2]

    elif page == 3:
        content = (
            "👑 **【OP 菜单 - 第三页：后台服务】**\n"
            "-----------------------------------\n"
            "• `#op sv ping/start/stop` - 25566 后台控制\n"
            "• `#op sv cp/start,get,stop` - Cpolar 管理\n"
            "• `#op ex start` - 发起分离运行 (带 -c 确认)"
        )
        row3 = [("⚙️sv", "#op sv"), ("🚀ex", "#op ex start -c")]
        kb = [row1, row2, row3]

    else:
        content = (
            "👑 **【OP 菜单 - 第四页：Yunzai 进程】**\n"
            "-----------------------------------\n"
            "• `#op yz start` - 静默无窗口启动 云崽\n"
            "• `#op yz kill` - 强杀 云崽 进程\n"
            "• `#op yz status` - 查询 云崽 运行状态"
        )
        row3 = [("🚀启动", "#op yz start"), ("🛑终止", "#op yz kill"), ("📊状态", "#op yz status")]
        kb = [row1, row2, row3]

    return _format_msg_type_2(content, kb)


def _render_item_list(state_key: str, page: int) -> dict:
    """格式化渲染二级菜单：文件/文件夹列表"""
    state = LOG_STATE_CACHE[state_key]
    items = state["items"]
    mode = state.get("mode", "file")
    page_size = state.get("page_size", 5)
    total_pages = max(1, (len(items) + page_size - 1) // page_size)

    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages

    state["page"] = page
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    current_items = items[start_idx:end_idx]

    title_prefix = "📂 错误日志集" if mode == "folder" else "📁 日志文件集"
    safe_dir_str = _sanitize_path(state["dir"])

    if not current_items:
        content = f"## {title_prefix}\n> 路径: `{safe_dir_str}`\n\n暂无数据。"
        kb = [[("⬅️前页", f"#op log page {max(1, page-1)}"), ("➡️后页", f"#op log page {page+1}")]]
    else:
        list_lines = []
        open_btns_row1 = []
        open_btns_row2 = []

        for idx, item_path in enumerate(current_items, start=start_idx + 1):
            name = os.path.basename(item_path)
            mtime_str = (
                import_time_format(os.path.getmtime(item_path))
                if os.path.exists(item_path)
                else "未知"
            )
            icon = "📁" if mode == "folder" else "📄"
            rel_idx = idx - start_idx
            list_lines.append(f"[{rel_idx}] {icon} **{name}** (`{mtime_str}`)")

            btn_item = (f"📄打开{rel_idx}", f"#op log open {rel_idx}")
            if len(open_btns_row1) < 3:
                open_btns_row1.append(btn_item)
            else:
                open_btns_row2.append(btn_item)

        content = (
            f"## {title_prefix} ({page}/{total_pages} 页)\n"
            f"`{safe_dir_str}`\n\n"
            + "\n".join(list_lines)
        )

        row3 = [("⬅️前页", f"#op log page {max(1, page - 1)}"), ("➡️后页", f"#op log page {min(total_pages, page + 1)}")]
        kb = [open_btns_row1]
        if open_btns_row2:
            kb.append(open_btns_row2)
        kb.append(row3)

    return _format_msg_type_2(content, kb)


def _render_log_content(state_key: str, page: int) -> dict:
    """格式化渲染三级菜单：日志文件内容"""
    state = LOG_STATE_CACHE[state_key]
    lines = state["lines"]
    filename = os.path.basename(state["current_file"])
    has_img = state.get("image_path") is not None
    last_open_num = state.get("last_open_num", 1)

    page_size = 10
    total_lines = len(lines)
    total_pages = max(1, (total_lines + page_size - 1) // page_size)

    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages

    state["log_page"] = page

    end_line = total_lines - (page - 1) * page_size
    start_line = max(0, end_line - page_size)

    selected_lines = lines[start_line:end_line]
    content_text = "".join(selected_lines).strip() if selected_lines else "（空内容）"

    md_content = (
        f"## 📄 `{filename}` ({page}/{total_pages} 页)\n"
        f"```log\n{content_text}\n```"
    )

    # 第一排：上翻、下翻
    row1 = [
        ("⬆️上翻", f"#op log goto {min(total_pages, page + 1)}"),
        ("⬇️下翻", f"#op log goto {max(1, page - 1)}"),
    ]
    # 第二排：刷新（重新 open 读取最新文件）
    row2 = [("🔄刷新", f"#op log open {last_open_num}")]

    kb = [row1, row2]

    # 第三排：如果有截图则显示 goto0 按钮
    if has_img:
        kb.append([("🖼️截图", "#op log goto 0")])

    return _format_msg_type_2(md_content, kb)

