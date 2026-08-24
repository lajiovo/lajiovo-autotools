import os
import platform
import subprocess
import time
import urllib.parse
import urllib.request
from botpy.message import GroupMessage
from config import BotDataManager, zConfig,_log

# 尝试导入 psutil 获取系统资源，若未安装则自动降级处理
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

# ------------------- 预设日志路径配置 -------------------
PRESET_LOG_PATHS = zConfig.get_config("bot.opcmd.preset_log_paths", default=[])
ALAS_ERROR_LOG_PATH = zConfig.get_config("bot.opcmd.alas_error_log_path")

SENSITIVE_PATTERNS = zConfig.get_config("bot.opcmd.sensitive_patterns", default=[])
MASK_REPLACEMENT = zConfig.get_config("bot.opcmd.mask_replacement", default=r"D:\***")
BEGINVBS = zConfig.get_config("bot.opcmd.beginvbs")

# 用于内存中缓存各群/用户当前的日志选择与文件读取位置 (状态记录)
LOG_STATE_CACHE = {}


class DataMgrAdapter:
    """对 BotDataManager 接口进行统一适配，确保数据读取与保存的安全兼容"""

    @staticmethod
    def get_opsetting(data_mgr) -> dict:
        """获取当前系统的完整 OP 配置 (opsetting)"""
        if hasattr(data_mgr, "get_opsetting"):
            return data_mgr.get_opsetting() or {}
        return {}

    @staticmethod
    def set_opsetting(data_mgr, setting_dict: dict):
        """更新并直接落盘保存 opsetting"""
        if hasattr(data_mgr, "set_opsetting"):
            data_mgr.set_opsetting(setting_dict)
        else:
            for k, v in setting_dict.items():
                if hasattr(data_mgr, "set_extra_data"):
                    data_mgr.set_extra_data(k, v)
            DataMgrAdapter.save_opsetting(data_mgr)

    @staticmethod
    def save_opsetting(data_mgr):
        """统一保存 OP 设置数据 (opsetting)"""
        if hasattr(data_mgr, "save_opsetting"):
            data_mgr.save_opsetting()
        elif hasattr(data_mgr, "save_op_setting"):
            data_mgr.save_op_setting()
        elif hasattr(data_mgr, "save"):
            data_mgr.save()

    @staticmethod
    def save_groupinfo(data_mgr):
        """统一保存群组信息 (groupinfo)"""
        if hasattr(data_mgr, "save_groupinfo"):
            data_mgr.save_groupinfo()
        elif hasattr(data_mgr, "save_group_info"):
            data_mgr.save_group_info()
        elif hasattr(data_mgr, "save"):
            data_mgr.save()

    @staticmethod
    def get_op_list(data_mgr) -> set:
        """获取 OP 管理员集合"""
        if hasattr(data_mgr, "get_opsetting"):
            setting = data_mgr.get_opsetting()
            if setting and "op_list" in setting:
                return set(setting.get("op_list", []))
        if hasattr(data_mgr, "get_op_list"):
            return set(data_mgr.get_op_list())
        raw = data_mgr.get_extra_data("op_list", [BotDataManager.DEFAULT_OP])
        return set(raw)

    @staticmethod
    def is_op(data_mgr, openid: str) -> bool:
        """判断 OpenID 是否具有 OP 权限"""
        if hasattr(data_mgr, "is_op"):
            return data_mgr.is_op(openid)
        op_set = DataMgrAdapter.get_op_list(data_mgr)
        return (openid.upper() if openid else "") in op_set

    @staticmethod
    def add_op(data_mgr, openid: str):
        """添加新 OP 管理员并保存至 opsetting"""
        if hasattr(data_mgr, "get_opsetting") and hasattr(data_mgr, "set_opsetting"):
            setting = data_mgr.get_opsetting() or {}
            op_set = set(setting.get("op_list", []))
            op_set.add(openid.upper())
            setting["op_list"] = list(op_set)
            data_mgr.set_opsetting(setting)
        elif hasattr(data_mgr, "add_op"):
            data_mgr.add_op(openid)
        else:
            op_set = DataMgrAdapter.get_op_list(data_mgr)
            op_set.add(openid.upper())
            data_mgr.set_extra_data("op_list", list(op_set))
            DataMgrAdapter.save_opsetting(data_mgr)

    @staticmethod
    def remove_op(data_mgr, openid: str):
        """移除 OP 管理员并保存至 opsetting"""
        if hasattr(data_mgr, "get_opsetting") and hasattr(data_mgr, "set_opsetting"):
            setting = data_mgr.get_opsetting() or {}
            op_set = set(setting.get("op_list", []))
            op_set.discard(openid.upper())
            setting["op_list"] = list(op_set)
            data_mgr.set_opsetting(setting)
        elif hasattr(data_mgr, "remove_op"):
            data_mgr.remove_op(openid)
        elif hasattr(data_mgr, "del_op"):
            data_mgr.del_op(openid)
        else:
            op_set = DataMgrAdapter.get_op_list(data_mgr)
            op_set.discard(openid.upper())
            data_mgr.set_extra_data("op_list", list(op_set))
            DataMgrAdapter.save_opsetting(data_mgr)

    @staticmethod
    def get_group_tags(data_mgr) -> dict:
        """获取群编号绑定映射字典"""
        if hasattr(data_mgr, "get_opsetting"):
            setting = data_mgr.get_opsetting()
            if setting and "group_tags" in setting:
                return setting.get("group_tags", {})
        if hasattr(data_mgr, "get_group_tags"):
            return data_mgr.get_group_tags()
        return data_mgr.get_extra_data("group_tags", {})

    @staticmethod
    def set_group_tag(data_mgr, group_id: str, tag_num: int):
        """设置群编号绑定记录（同时存入 opsetting 和 groupinfo）"""
        tags = DataMgrAdapter.get_group_tags(data_mgr)
        tags[group_id] = tag_num

        # 持久化至 opsetting
        if hasattr(data_mgr, "get_opsetting") and hasattr(data_mgr, "set_opsetting"):
            setting = data_mgr.get_opsetting() or {}
            setting["group_tags"] = tags
            data_mgr.set_opsetting(setting)
        elif hasattr(data_mgr, "set_group_tags"):
            data_mgr.set_group_tags(tags)
            DataMgrAdapter.save_opsetting(data_mgr)
        else:
            data_mgr.set_extra_data("group_tags", tags)
            DataMgrAdapter.save_opsetting(data_mgr)

        # 同时持久化至 groupinfo
        DataMgrAdapter.save_groupinfo(data_mgr)

    @staticmethod
    def get_target_port(data_mgr, default: int = 25566) -> int:
        """获取后台服务通讯端口"""
        if hasattr(data_mgr, "get_opsetting"):
            setting = data_mgr.get_opsetting()
            if setting and "target_port" in setting:
                return setting.get("target_port", default)
        if hasattr(data_mgr, "get_target_port"):
            return data_mgr.get_target_port()
        return data_mgr.get_extra_data("target_port", default)

    @staticmethod
    def get_notify_group_num(data_mgr, default: int = 2) -> int:
        """获取上下线通知群编号"""
        if hasattr(data_mgr, "get_opsetting"):
            setting = data_mgr.get_opsetting()
            if setting and "notify_group_num" in setting:
                return setting.get("notify_group_num", default)
        if hasattr(data_mgr, "get_notify_group_num"):
            return data_mgr.get_notify_group_num()
        return data_mgr.get_extra_data("notify_group_num", default)

    @staticmethod
    def set_notify_group_num(data_mgr, num: int):
        """设置上下线通知群编号（存入 opsetting）"""
        if hasattr(data_mgr, "get_opsetting") and hasattr(data_mgr, "set_opsetting"):
            setting = data_mgr.get_opsetting() or {}
            setting["notify_group_num"] = num
            data_mgr.set_opsetting(setting)
        elif hasattr(data_mgr, "set_notify_group_num"):
            data_mgr.set_notify_group_num(num)
            DataMgrAdapter.save_opsetting(data_mgr)
        else:
            data_mgr.set_extra_data("notify_group_num", num)
            DataMgrAdapter.save_opsetting(data_mgr)

    @staticmethod
    def set_system_active(data_mgr, active: bool):
        """设置系统运行/维护状态（存入 opsetting）"""
        if hasattr(data_mgr, "get_opsetting") and hasattr(data_mgr, "set_opsetting"):
            setting = data_mgr.get_opsetting() or {}
            setting["system_active"] = active
            data_mgr.set_opsetting(setting)
        elif hasattr(data_mgr, "set_system_active"):
            data_mgr.set_system_active(active)
            DataMgrAdapter.save_opsetting(data_mgr)
        else:
            data_mgr.set_extra_data("system_active", active)
            DataMgrAdapter.save_opsetting(data_mgr)

    @staticmethod
    def set_push_target_group(data_mgr, num: int):
        """设置 Push 转发接收群编号（存入 opsetting）"""
        if hasattr(data_mgr, "get_opsetting") and hasattr(data_mgr, "set_opsetting"):
            setting = data_mgr.get_opsetting() or {}
            setting["push_target_group"] = num
            data_mgr.set_opsetting(setting)
        elif hasattr(data_mgr, "set_push_target_group"):
            data_mgr.set_push_target_group(num)
            DataMgrAdapter.save_opsetting(data_mgr)
        else:
            data_mgr.set_extra_data("push_target_group", num)
            DataMgrAdapter.save_opsetting(data_mgr)

    @staticmethod
    def set_push_active(data_mgr, active: bool):
        """设置 Push 转发开启/关闭（存入 opsetting）"""
        if hasattr(data_mgr, "get_opsetting") and hasattr(data_mgr, "set_opsetting"):
            setting = data_mgr.get_opsetting() or {}
            setting["push_active"] = active
            data_mgr.set_opsetting(setting)
        elif hasattr(data_mgr, "set_push_active"):
            data_mgr.set_push_active(active)
            DataMgrAdapter.save_opsetting(data_mgr)
        else:
            data_mgr.set_extra_data("push_active", active)
            DataMgrAdapter.save_opsetting(data_mgr)

    @staticmethod
    def get_push_history(data_mgr):
        """获取 Push 历史消息列表"""
        if hasattr(data_mgr, "get_push_history"):
            return data_mgr.get_push_history()
        if hasattr(data_mgr, "get_pushhistory"):
            return data_mgr.get_pushhistory()
        return data_mgr.get_extra_data("push_history", [])

    @staticmethod
    def save(data_mgr):
        """统一持久化数据保存"""
        DataMgrAdapter.save_opsetting(data_mgr)


def _sanitize_path(path_str: str) -> str:
    """隐私脱敏处理：从配置中读取敏感目录并隐藏"""
    if not path_str:
        return ""
    sanitized = path_str
    for pattern in SENSITIVE_PATTERNS:
        sanitized = sanitized.replace(pattern, MASK_REPLACEMENT)
    return sanitized


def _get_system_status() -> str:
    """获取电脑 CPU、内存、磁盘等基础占用信息"""
    lines = ["💻 【硬件资源与系统状态】", "-------------------------"]

    sys_name = platform.system()
    sys_ver = platform.release()
    lines.append(f"🖥️ 操作系统: {sys_name} ({sys_ver})")

    if HAS_PSUTIL:
        # CPU 占用
        cpu_percent = psutil.cpu_percent(interval=0.5)
        cpu_count = psutil.cpu_count(logical=True)
        cpu_freq = psutil.cpu_freq()
        freq_str = f" @ {cpu_freq.current:.0f}MHz" if cpu_freq else ""
        lines.append(f"⚡ CPU 使用率: {cpu_percent}% ({cpu_count} 逻辑核心{freq_str})")

        # 内存占用
        mem = psutil.virtual_memory()
        mem_used_gb = mem.used / (1024 ** 3)
        mem_total_gb = mem.total / (1024 ** 3)
        lines.append(
            f"🧠 内存占用: {mem.percent}% ({mem_used_gb:.2f} GB / {mem_total_gb:.2f} GB)"
        )

        # 交换内存 (Swap)
        swap = psutil.swap_memory()
        if swap.total > 0:
            swap_used_gb = swap.used / (1024 ** 3)
            swap_total_gb = swap.total / (1024 ** 3)
            lines.append(
                f"💾 Swap 占用: {swap.percent}% ({swap_used_gb:.2f} GB / {swap_total_gb:.2f} GB)"
            )

        # 磁盘占用
        try:
            disk = psutil.disk_usage(os.getcwd())
            disk_used_gb = disk.used / (1024 ** 3)
            disk_total_gb = disk.total / (1024 ** 3)
            lines.append(
                f"💽 当前磁盘: {disk.percent}% ({disk_used_gb:.2f} GB / {disk_total_gb:.2f} GB)"
            )
        except Exception:
            pass

        # 开机运行时间
        boot_time = psutil.boot_time()
        uptime_sec = int(time.time() - boot_time)
        days, rem = divmod(uptime_sec, 86400)
        hours, rem = divmod(rem, 3600)
        mins, _ = divmod(rem, 60)
        uptime_str = f"{days}天 {hours}小时 {mins}分钟" if days else f"{hours}小时 {mins}分钟"
        lines.append(f"⏱️ 连续运行: {uptime_str}")
    else:
        lines.append("⚠️ 系统未安装 `psutil` 模块，未能获取详细资源数据。")

    lines.append("-------------------------")
    return "\n".join(lines)


async def handle_op_command(
    client,
    args: list,
    sender_openid: str,
    raw_message: GroupMessage,
    group_id: str,
):
    """OP 管理员核心指令处理入口"""
    data_mgr = client.data_mgr

    # ------------------- 对接新 DataMgr 接口获取数据 -------------------
    op_list = DataMgrAdapter.get_op_list(data_mgr)
    group_tags = DataMgrAdapter.get_group_tags(data_mgr)

    sender_openid_upper = sender_openid.upper() if sender_openid else ""
    is_op = DataMgrAdapter.is_op(data_mgr, sender_openid)

    if not args:
        group_tag_info = (
            f"（当前群编号：群 {group_tags[group_id]}）"
            if group_id in group_tags
            else ""
        )
        return (
            f"👑 欢迎，尊贵的管理员！当前系统运行正常。{group_tag_info}"
            if is_op
            else f"👋 你好呀！快去试试 #钓鱼 或 #打捞 吧！{group_tag_info}"
        )

    # 🛑 权限硬锁：非 OP 拒绝一切子命令响应
    if not is_op:
        return "❌ 权限不足！只有授权的 OP 管理员才能执行此操作。"

    sub_cmd = args[0].lower()

    # ------------------- 帮助指令 -------------------
    if sub_cmd in ["help", "?", "帮助"]:
        return (
            "👑 【OP 管理员指令列表】\n"
            "-------------------------\n"
            "📌 【机器人基础控制】\n"
            "• #op help - 查看所有 OP 指令\n"
            "• #op sys (或 status/cpu) - 查询服务器 CPU、内存等基础资源占用\n"
            "• #op stop - 暂停机器人功能 (维护模式，屏蔽消息回复)\n"
            "• #op start - 恢复机器人功能\n"
            "• #op restart - 重新无窗口启动 QBot (执行 sv bot/start)\n"
            "• #op shutdown - 关闭机器人程序并通知指定的通知群\n"
            "• #op list - 查看所有 OP 管理员\n"
            "• #op add [@某人/OpenID] - [主管理员] 添加管理员\n"
            "• #op del/remove [@某人/OpenID] - [主管理员] 移除管理员\n\n"
            "📌 【面板与菜单管理】\n"
            "• #op panel [c2c/group] - 创建包含预设指令(#ping, #help, #打捞, #运势, #op)的指令面板\n"
            "• #op menu - 创建 C2C 全局自定义菜单\n\n"
            "📌 【群绑定与 通知/Push 管理】\n"
            "• #op group <数字> - 标记当前群编号 (例: #op group 1)\n"
            "• #op group list - 查看所有群编号绑定\n"
            "• #op group get - 查看当前群编号\n"
            "• #op notify set <数字> - 设置上下线通知的接收群编号\n"
            "• #op push set <数字> - 设置 Push 消息的目标推送群\n"
            "• #op push start - 开启 Push 转发\n"
            "• #op push stop - 关闭 Push 转发\n"
            "• #op push get [num] - 读取最新的 N 条 push 历史消息 (默认 1 条)\n"
            "• #op push get [start]-[end] - 读取指定范围的 push 历史消息 (如 1-3)\n\n"
            "📌 【日志查看接口 (#op log)】\n"
            "• #op log get [num] - 选择预设目录并列出最新 5 个文件 (1~3)\n"
            "• #op log find 4 - 查看 Alas 错误日志文件夹列表\n"
            "• #op log page [num] - 列表翻页\n"
            "• #op log open [num] - 打开当前列表展示的序号(如 1~5 或全局序号)\n"
            "• #op log goto [num] - 向上翻页查看日志(支持 #op log goto 0 查看错误截图)\n\n"
            "📌 【25566 后台服务控制 (#op sv <指令>)】\n"
            "• #op sv ping - 检查后台服务状态及 Handlepush 开关\n"
            "• #op sv start - 恢复后台服务及定时检查 (run_alas_mumu_check)\n"
            "• #op sv stop - 暂停后台推送并释放 Alas/Mumu 进程\n"
            "• #op sv shutdown - 关闭 25566 后台接收服务\n"
            "• #op sv bot/start,shutdown - QBot\n"
            "• #op sv music/start,ffm,stop - MusicDL与ffmpeg\n"
            "• #op sv lk/book-id - LK->Epub\n"
            "• #op sv cp/start,get,stop - Cpolar\n"
            "• #op ex start - 启动主服务\n\n"
            "📌 【单独任务运行接口 (#op run <任务>)】\n"
            "• #op run ikun - 执行 alas与mumu 双向状态检查与恢复\n"
            "• #op run alas <start/restart/kill/hide/online> - 控制 Alas 进程\n"
            "• #op run mumu <start/kill/hide/online> - 控制 MuMu 模拟器进程\n"
            "• #op run pw 或 playwright - 启动 Playwright 自动化任务\n"
            "• #op run pg 或 pgrjz - 启动 PGRJZ 自动化运行\n"
            "-------------------------\n"
            "⚠ 注意：不懂别乱用\n"
        )

    # ------------------- #op sys 查询系统占用状态 -------------------
    elif sub_cmd in ["sys", "status", "sysinfo", "system", "cpu"]:
        return _get_system_status()

    # ------------------- #op panel 指令面板交互接口 -------------------
    elif sub_cmd == "panel":
        scope = args[1].lower() if len(args) > 1 else "group"
        if scope not in ["c2c", "group"]:
            return "⚠️ 作用域仅支持 `c2c` 或 `group`！例：`#op panel group` 或 `#op panel c2c`"

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
            "remark": f"自动化系统{scope.upper()}指令面板",
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
            return f"✅ 指令面板创建成功！\n- 生效场景: {scope}\n- 面板 ID: {panel_id}"
        except Exception as e:
            return f"❌ 创建指令面板失败: {e}"

    # ------------------- #op menu C2C自定义菜单接口 -------------------
    elif sub_cmd == "menu":
        menu_payload = {
            "items": [
                {
                    "type": "send_message",
                    "name": "状态查询",
                    "send_message": "#ping",
                },
                {
                    "type": "send_message",
                    "name": "帮助",
                    "send_message": "#help",
                },
                {
                    "type": "menu",
                    "name": "日常功能",
                    "sub_menu_items": [
                        {"type": "send_message", "name": "打捞", "send_message": "#打捞"},
                        {"type": "send_message", "name": "运势", "send_message": "#运势"},
                        {"type": "send_message", "name": "船坞", "send_message": "#船坞"},
                    ],
                },
                {
                    "type": "send_message",
                    "name": "管理员",
                    "send_message": "#op",
                },
            ]
        }

        try:
            res = await client.set_c2c_menu(menu=menu_payload)
            version = res.get("version", "未知")
            return f"✅ C2C 自定义菜单修改成功！\n- 当前菜单版本号: {version}"
        except Exception as e:
            return f"❌ 修改自定义菜单失败: {e}"

    # ------------------- #op log 日志查看相关指令 -------------------
    elif sub_cmd == "log":
        log_args = args[1:]
        if not log_args:
            paths_str = "\n".join([
                f"[{i+1}] {_sanitize_path(p)}"
                for i, p in enumerate(PRESET_LOG_PATHS)
            ])
            return (
                f"📂 【日志查看帮助】\n"
                f"预设目录列表：\n{paths_str}\n"
                f"[4] {_sanitize_path(ALAS_ERROR_LOG_PATH)} (Alas 错误日志目录)\n\n"
                f"用法：\n"
                f"• `#op log get [1-3]` : 获取指定目录的最新 5 个文件\n"
                f"• `#op log find 4` : 特殊查找 Alas 错误日志文件夹列表\n"
                f"• `#op log page [页码]` : 翻页查看文件/文件夹列表\n"
                f"• `#op log open [序号]` : 打开当前列表中的指定项(默认倒数10行)\n"
                f"• `#op log goto [页码]` : 倒着向前翻页(输入 0 可查看错误截图)"
            )

        action = log_args[0].lower()
        state_key = f"{group_id}_{sender_openid}"

        # #op log find 4 特殊处理逻辑
        if action == "find" and len(log_args) > 1 and log_args[1] == "4":
            target_dir = ALAS_ERROR_LOG_PATH
            if not os.path.exists(target_dir):
                return (
                    f"❌ 目标 Alas 错误日志路径不存在: `{_sanitize_path(target_dir)}`"
                )

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
                return f"❌ 读取错误日志目录失败: {e}"

        # 1. 获取指定预设路径的文件列表 (#op log get [1-3])
        elif action == "get":
            path_idx = (
                int(log_args[1]) - 1
                if len(log_args) > 1 and log_args[1].isdigit()
                else 0
            )
            if path_idx < 0 or path_idx >= len(PRESET_LOG_PATHS):
                return f"⚠️ 预设路径序号无效，可选范围为 1 ~ {len(PRESET_LOG_PATHS)}"

            target_dir = PRESET_LOG_PATHS[path_idx]
            if not os.path.exists(target_dir):
                return f"❌ 目标日志路径不存在: `{_sanitize_path(target_dir)}`"

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
                return f"❌ 读取日志目录失败: {e}"

        # 2. 文件/文件夹列表翻页
        elif action == "page":
            if state_key not in LOG_STATE_CACHE:
                return (
                    "⚠️ 请先使用 `#op log get [num]` 或 `#op log find 4` 初始化列表！"
                )

            page_num = (
                int(log_args[1])
                if len(log_args) > 1 and log_args[1].isdigit()
                else LOG_STATE_CACHE[state_key]["page"] + 1
            )
            return _render_item_list(state_key, page_num)

        # 3. 打开指定的日志文件或错误日志文件夹
        elif action == "open":
            if (
                state_key not in LOG_STATE_CACHE
                or not LOG_STATE_CACHE[state_key]["items"]
            ):
                return "⚠️ 当前无可用列表，请先执行 `#op log get [num]` 或 `#op log find 4`！"

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
                return (
                    f"⚠️ 序号超出范围，当前页范围: {start_idx + 1} ~"
                    f" {min(start_idx + page_size, len(items))}，列表总计 {len(items)} 项。"
                )

            target_item = items[target_idx]
            target_file = target_item
            found_img = None

            if mode == "folder":
                if not os.path.isdir(target_item):
                    return f"❌ 找不到对应目录: `{_sanitize_path(target_item)}`"

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
                return (
                    f"❌ 未在该文件夹下找到可读的文本日志 (log.txt)！"
                    if mode == "folder"
                    else f"❌ 日志文件不存在: `{_sanitize_path(target_file)}`"
                )

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
                state["log_page"] = 1

                return _render_log_content(state_key, 1)
            except Exception as e:
                return f"❌ 读取日志文件失败: {e}"

        # 4. 日志内容倒着翻页 & 响应 goto 0 返回图片
        elif action == "goto":
            if (
                state_key not in LOG_STATE_CACHE
                or not LOG_STATE_CACHE[state_key]["current_file"]
            ):
                return "⚠️ 当前未打开任何日志文件，请先使用 `#op log open [num]` 打开日志！"

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
                        "content": f"🖼️ 对应错误日志截图: {filename}",
                    }
                else:
                    return "⚠️ 当前打开的日志目录中未找到相关的图片截图！"

            return _render_log_content(state_key, goto_page)

        return "⚠️ 未知的 log 子指令，可选：`get`, `find 4`, `page`, `open`, `goto`"

    elif sub_cmd == "restart":
        target_port = DataMgrAdapter.get_target_port(data_mgr, 25566)
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
        notify_num = DataMgrAdapter.get_notify_group_num(data_mgr, 2)
        return f"🛑 正在准备关闭程序并通知群 {notify_num}..."

    elif sub_cmd == "notify":
        notify_args = args[1:]
        if not notify_args:
            return "⚠️ 请提供 notify 参数，例如：`#op notify set 2`"

        n_action = notify_args[0].lower()
        if n_action == "set":
            if len(notify_args) > 1 and notify_args[1].isdigit():
                target_num = int(notify_args[1])
                DataMgrAdapter.set_notify_group_num(data_mgr, target_num)
                return f"✅ 已将上下线通知群设置为：【群 {target_num}】"
            return "⚠️ 请提供要设置的群编号数字，例如：`#op notify set 2`"

        return "⚠️ 未知的 notify 子指令。可使用 `#op notify set [num]`"

    elif sub_cmd == "ex":
        if len(args) > 1 and args[1].lower() == "start":
            try:
                subprocess.Popen(["wscript.exe", BEGINVBS])
                return "🚀 已成功发起分离运行指令！"
            except Exception as e:
                return f"❌ 运行失败: {e}"
        return "⚠️ 请使用正确格式：`#op ex start`"

    elif sub_cmd == "run":
        if len(args) < 2:
            return "⚠️ 请提供运行参数，例如：`#op run task1,task2`"
        try:
            target_port = DataMgrAdapter.get_target_port(data_mgr, 25566)
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

        target_port = DataMgrAdapter.get_target_port(data_mgr, 25566)
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
            [f"- {op_id[:6]}... ({op_id})" for op_id in op_list]
        )

    elif sub_cmd == "stop":
        DataMgrAdapter.set_system_active(data_mgr, False)
        return "🛑 已成功暂停娱乐与辅助功能！"

    elif sub_cmd == "start":
        DataMgrAdapter.set_system_active(data_mgr, True)
        return "🚀 已成功重新启用功能！"

    elif sub_cmd == "push":
        push_args = args[1:]
        if not push_args:
            return "⚠️ 请提供 push 参数，例如：`#op push set 1` / `#op push start` / `#op push stop` / `#op push get 1`"

        p_action = push_args[0].lower()

        if p_action == "set":
            if len(push_args) > 1 and push_args[1].isdigit():
                target_num = int(push_args[1])
                DataMgrAdapter.set_push_target_group(data_mgr, target_num)
                return f"✅ 已将 Push 消息的默认推送群设置为：【群 {target_num}】"
            return "⚠️ 请提供要设置的群编号数字，例如：`#op push set 1`"

        elif p_action == "start":
            DataMgrAdapter.set_push_active(data_mgr, True)
            return "🚀 已成功开启 Push 消息转发！"

        elif p_action == "stop":
            DataMgrAdapter.set_push_active(data_mgr, False)
            return "🛑 已成功关闭 Push 消息转发！"

        elif p_action == "get":
            raw_push_history = DataMgrAdapter.get_push_history(data_mgr)
            if isinstance(raw_push_history, dict):
                push_history = raw_push_history.get(
                    "history", raw_push_history.get("push", [])
                )
            elif isinstance(raw_push_history, list):
                push_history = raw_push_history
            else:
                push_history = []

            if not push_history:
                return "📭 当前暂无任何 Push 历史消息记录。"

            reversed_history = list(reversed(push_history))
            total = len(reversed_history)

            start_idx = 1
            end_idx = 1

            if len(push_args) > 1:
                param = push_args[1]
                if "-" in param:
                    parts = param.split("-")
                    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                        start_idx = int(parts[0])
                        end_idx = int(parts[1])
                elif param.isdigit():
                    num = int(param)
                    start_idx = 1
                    end_idx = num

            if start_idx < 1:
                start_idx = 1
            if end_idx < start_idx:
                end_idx = start_idx
            if start_idx > total:
                return f"⚠️ 请求的起始序号超出历史记录总数（当前共 {total} 条）。"
            if end_idx > total:
                end_idx = total

            selected_items = reversed_history[start_idx - 1 : end_idx]

            res_lines = [
                f"📬 【Push 历史消息读取】 (展示第 {start_idx} ~ {end_idx} 条 / 共 {total} 条)\n"
            ]
            for idx, item in enumerate(selected_items, start=start_idx):
                time_str = (
                    item.get("time", "未知时间")
                    if isinstance(item, dict)
                    else "未知时间"
                )
                msg_content = (
                    item.get("content", str(item))
                    if isinstance(item, dict)
                    else str(item)
                )
                res_lines.append(
                    f"-------------------------\n📌 [#{idx}] 🕒 {time_str}\n{msg_content}"
                )

            return "\n".join(res_lines)

        return "⚠️ 未知的 push 子指令。可使用 `#op push set [num]`、`#op push start`、`#op push stop` 或 `#op push get [num]`"

    elif sub_cmd == "group":
        group_args = args[1:]
        if not group_args or group_args[0].isdigit():
            target_num = group_args[0] if group_args else None
            if not target_num:
                return "⚠️ 请提供群编号数字，例如：`#op group 1`"
            DataMgrAdapter.set_group_tag(data_mgr, group_id, int(target_num))
            return f"✅ 已成功将当前群标记为：【群 {target_num}】！"

        action = group_args[0].lower()
        if action == "list":
            lines = [
                f"- 群 {num}: {gid}"
                for gid, num in sorted(group_tags.items(), key=lambda x: x[1])
            ]
            return "📋 【群编号绑定列表】\n" + ("\n".join(lines) if lines else "暂无")
        elif action == "get":
            return f"📌 当前群已被标记为：【群 {group_tags.get(group_id, '未绑定')}】"

    # 🛑 权限加固：只有系统主管理员具备提权/撤权操作的能力
    elif sub_cmd == "add":
        if sender_openid_upper != BotDataManager.DEFAULT_OP:
            return "❌ 拒绝执行：只有超级管理员才有权限赋予新的 OP 权限！"

        mentions = getattr(raw_message, "mentions", [])
        target_id = (
            (
                getattr(mentions[0], "member_openid", None)
                or getattr(mentions[0], "id", None)
            )
            if mentions
            else (args[1].strip() if len(args) > 1 else None)
        )
        if not target_id:
            return "⚠️ 请 @某人 或提供 OpenID"
        target_id = target_id.upper()

        DataMgrAdapter.add_op(data_mgr, target_id)
        return f"✅ 用户 [{target_id[:6]}...] 已提权为 OP。"

    elif sub_cmd in ["remove", "del", "rm"]:
        if sender_openid_upper != BotDataManager.DEFAULT_OP:
            return "❌ 拒绝执行：只有超级管理员才有权限剥夺 OP 权限！"

        mentions = getattr(raw_message, "mentions", [])
        target_id = (
            (
                getattr(mentions[0], "member_openid", None)
                or getattr(mentions[0], "id", None)
            )
            if mentions
            else (args[1].strip() if len(args) > 1 else None)
        )
        if not target_id or target_id.upper() == BotDataManager.DEFAULT_OP:
            return "❌ 操作受限或未识别到有效目标"
        target_id = target_id.upper()
        if target_id in op_list:
            DataMgrAdapter.remove_op(data_mgr, target_id)
            return f"🗑️ 已取消用户 [{target_id[:6]}...] 的 OP 权限。"
        return "ℹ️ 该用户不是 OP。"

    return "⚠️ 未知的 OP 命令。可使用 `#op help` 查看帮助。"


def _render_item_list(state_key: str, page: int) -> dict:
    """格式化渲染文件/文件夹列表 (脱敏路径 + 记住当前页码)"""
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

    title_prefix = "📂 错误日志文件夹列表" if mode == "folder" else "📁 目录文件列表"
    safe_dir_str = _sanitize_path(state["dir"])

    if not current_items:
        content = f"## {title_prefix}\n> 路径: `{safe_dir_str}`\n\n该目录下暂无任何数据。"
    else:
        list_lines = []
        for idx, item_path in enumerate(current_items, start=start_idx + 1):
            name = os.path.basename(item_path)
            mtime_str = (
                import_time_format(os.path.getmtime(item_path))
                if os.path.exists(item_path)
                else "未知"
            )
            icon = "📁" if mode == "folder" else "📄"
            rel_idx = idx - start_idx
            list_lines.append(
                f"[{rel_idx}] {icon} **{name}** (全局#{idx} | `{mtime_str}`)"
            )

        content = (
            f"## {title_prefix} (第 {page}/{total_pages} 页)\n"
            f"**目标路径**：`{safe_dir_str}`\n\n"
            + "\n".join(list_lines)
            + "\n\n"
            f"💡 使用 `#op log open [1-{len(current_items)}]` 打开当前页对应项，或使用 `#op log page [页码]` 翻页。"
        )

    return {"msg_type": 2, "content": content}


def _render_log_content(state_key: str, page: int) -> dict:
    """倒序格式化渲染日志文件内容"""
    state = LOG_STATE_CACHE[state_key]
    lines = state["lines"]
    filename = os.path.basename(state["current_file"])
    has_img = state.get("image_path") is not None

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
    content_text = (
        "".join(selected_lines).strip() if selected_lines else "（该部分无内容）"
    )

    img_tip = (
        "\n🖼️ **检测到对应错误截图**！输入 `#op log goto 0` 可直接发送图片。\n"
        if has_img
        else ""
    )

    md_content = (
        f"## 📄 日志文件: `{filename}`\n"
        f"**倒数页码**：第 {page}/{total_pages} 页（行范围: {start_line+1} ~ {end_line} / 共"
        f" {total_lines} 行）\n"
        f"{img_tip}\n"
        f"```log\n{content_text}\n```\n\n"
        "💡 使用 `#op log goto [页码]` 继续向上翻页。"
    )

    return {"msg_type": 2, "content": md_content}


def import_time_format(timestamp: float) -> str:
    """格式化时间戳转换函数"""
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))