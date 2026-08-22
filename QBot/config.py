"""
import config
# 实例化数据管理器
1. 基础配置与加载
-------------------------------------------------------------------
- __init__(data_dir=DATA_DIR, max_history_limit=30)
- load_all()

2. 权限与系统配置 (opsetting)
-------------------------------------------------------------------
- save_opsetting()
- set_system_active(active: bool)
- add_op(user_id: str)

3. 用户信息与个人数据 (userinfo & userdata)
-------------------------------------------------------------------
- set_user_info(user_id: str, info_dict: dict)
- get_user_info(user_id: str) -> dict
- set_user_data(user_id: str, data_dict: dict)
- get_user_data(user_id: str) -> dict

4. 消息历史与数据读取 (c2chistory & grouphistory)
-------------------------------------------------------------------
- append_c2c_message(user_id: str, content: str, user_nickname: str = None, role: str = "user")
- append_group_message(group_id: str, user_id: str, content: str, user_nickname: str = None, role: str = "user")
- get_c2c_history(user_id: str) -> list
- get_group_history(group_id: str) -> list
- get_chat_history(target_id: str, is_group: bool = False)
- get_nickname(target_id: str, is_group: bool = False) -> str
- get_user_list() -> list
- get_group_list() -> list
- check_has_new_message(reset: bool = True) -> bool

5. 推送历史与扩展数据 (pushhistory & extra)
-------------------------------------------------------------------
- save_pushhistory(push_data: dict)
- get_pushhistory() -> dict
- set_extra_data(key: str, value)
- get_extra_data(key: str, default=None)

"""

import importlib.util
import sys
from pathlib import Path

# 获取上一级目录路径
parent_dir = Path(__file__).resolve().parent.parent

def load_module_from_parent(module_name: str):
    file_path = parent_dir / f"{module_name}.py"
    if not file_path.exists():
        raise FileNotFoundError(f"未找到模块文件: {file_path}")

    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    module = importlib.util.module_from_spec(spec)
    # 关键：先注册到 sys.modules，防止内部互相 import 时报错
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# 自动按依赖顺序加载上级目录的模块
zConfig = load_module_from_parent("zConfig")
zPerseusLogger = load_module_from_parent("zPerseusLogger")

import os
import json
import time
import threading
from datetime import datetime
from botpy.ext.cog_yaml import read
from botpy.message import GroupMessage

# 基础文件路径
BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "botdata")

# 确保主数据目录及子目录存在
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "userinfo"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "userdata"), exist_ok=True)

# Bot 配置读取
APP_ID = zConfig.get_config("bot.app_id")
APP_SECRET = zConfig.get_config("bot.app_secret")

# 并发限制信号量
RUN_TASK_SEMAPHORE = threading.Semaphore(2)

# SDK 补丁
def apply_sdk_patch():
    try:
        from botpy.connection import ConnectionState
        if not hasattr(ConnectionState, "parse_group_message_create"):
            def parse_group_message_create(self, payload):
                _message = GroupMessage(self.api, payload.get("id", None), payload.get("d", {}))
                self._dispatch("group_message_create", _message)
            ConnectionState.parse_group_message_create = parse_group_message_create
    except Exception:
        pass


class BotDataManager:
    """
    统一数据管理对象
    - opsetting, grouphistory, c2chistory, pushhistory, extra 按文件保存
    - userinfo, userdata 按 ID 分文件保存至子文件夹
    - 历史消息自动包含 timestamp 字段
    """
    DEFAULT_OP = zConfig.get_config("bot.default_op")

    def __init__(self, data_dir=DATA_DIR, max_history_limit=30):
        self.data_dir = data_dir
        self.max_history_limit = max_history_limit
        self._lock = threading.Lock()
        self.has_new_msg = False

        # 核心数据模型初始化
        self.opsetting = {
            "op_list": [self.DEFAULT_OP],
            "system_active": True
        }
        self.userinfo = {}      # dict mapping: user_id -> dict
        self.userdata = {}      # dict mapping: user_id -> dict
        self.grouphistory = {}  # group_id -> list of msgs
        self.c2chistory = {}     # user_id -> list of msgs
        self.pushhistory = {}   # 自定义推送历史
        self.extra = {}         # 自定义扩展数据

        self.load_all()

    # ==================== 通用读写帮助方法 ====================

    def _read_json(self, file_path, default_val):
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return default_val
        return default_val

    def _write_json(self, file_path, data):
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ==================== 加载与全部保存 ====================

    def load_all(self):
        """全面加载全部本地文件数据"""
        with self._lock:
            # 1. 独立文件
            self.opsetting = self._read_json(
                os.path.join(self.data_dir, "opsetting.json"), 
                {"op_list": [self.DEFAULT_OP], "system_active": True}
            )
            self.grouphistory = self._read_json(os.path.join(self.data_dir, "grouphistory.json"), {})
            self.c2chistory = self._read_json(os.path.join(self.data_dir, "c2chistory.json"), {})
            self.pushhistory = self._read_json(os.path.join(self.data_dir, "pushhistory.json"), {})
            self.extra = self._read_json(os.path.join(self.data_dir, "extra.json"), {})

            # 确保默认 OP 权限
            if self.DEFAULT_OP not in self.opsetting.get("op_list", []):
                self.opsetting.setdefault("op_list", []).append(self.DEFAULT_OP)

            # 2. userinfo (按 ID 文件夹读取)
            userinfo_dir = os.path.join(self.data_dir, "userinfo")
            if os.path.exists(userinfo_dir):
                for filename in os.listdir(userinfo_dir):
                    if filename.endswith(".json"):
                        u_id = filename[:-5]
                        self.userinfo[u_id] = self._read_json(os.path.join(userinfo_dir, filename), {})

            # 3. userdata (按 ID 文件夹读取)
            userdata_dir = os.path.join(self.data_dir, "userdata")
            if os.path.exists(userdata_dir):
                for filename in os.listdir(userdata_dir):
                    if filename.endswith(".json"):
                        u_id = filename[:-5]
                        self.userdata[u_id] = self._read_json(os.path.join(userdata_dir, filename), {})

    # ==================== opsetting 模块 ====================

    def save_opsetting(self):
        file_path = os.path.join(self.data_dir, "opsetting.json")
        self._write_json(file_path, self.opsetting)

    def set_system_active(self, active: bool):
        with self._lock:
            self.opsetting["system_active"] = active
            self.save_opsetting()

    def add_op(self, user_id: str):
        with self._lock:
            if user_id not in self.opsetting.get("op_list", []):
                self.opsetting.setdefault("op_list", []).append(str(user_id))
                self.save_opsetting()

    # ==================== userinfo & userdata 模块 (按 ID 分开) ====================

    def set_user_info(self, user_id: str, info_dict: dict):
        """保存/更新指定 ID 的 userinfo"""
        u_id = str(user_id)
        with self._lock:
            if u_id not in self.userinfo:
                self.userinfo[u_id] = {}
            self.userinfo[u_id].update(info_dict)
            
            file_path = os.path.join(self.data_dir, "userinfo", f"{u_id}.json")
            self._write_json(file_path, self.userinfo[u_id])

    def get_user_info(self, user_id: str) -> dict:
        with self._lock:
            return self.userinfo.get(str(user_id), {})

    def set_user_data(self, user_id: str, data_dict: dict):
        """保存/更新指定 ID 的 userdata"""
        u_id = str(user_id)
        with self._lock:
            if u_id not in self.userdata:
                self.userdata[u_id] = {}
            self.userdata[u_id].update(data_dict)
            
            file_path = os.path.join(self.data_dir, "userdata", f"{u_id}.json")
            self._write_json(file_path, self.userdata[u_id])

    def get_user_data(self, user_id: str) -> dict:
        with self._lock:
            return self.userdata.get(str(user_id), {})

    # ==================== 昵称与列表相关函数 ====================

    def get_nickname(self, target_id: str, is_group: bool = False) -> str:
        """获取指定群或用户的昵称 (Group 从 extra 中读取，User 从 userinfo 中读取)"""
        target_id = str(target_id)
        if is_group:
            with self._lock:
                group_nicknames = self.extra.get("group_nicknames", {})
                if isinstance(group_nicknames, dict) and target_id in group_nicknames:
                    return str(group_nicknames[target_id])
                # 支持直接在 extra 中保存单个 key 的情况
                return str(self.extra.get(f"group_nickname_{target_id}", ""))
        else:
            info = self.get_user_info(target_id)
            return info.get("nickname", "") if isinstance(info, dict) else ""

    def get_chat_history(self, target_id: str, is_group: bool = False):
        """获取指定群或用户的聊天历史记录"""
        if is_group:
            return self.get_group_history(target_id)
        return self.get_c2c_history(target_id)

    def get_user_list(self):
        """获取所有已产生私聊记录/设置昵称的用户列表及其昵称 mapping"""
        user_ids = set()
        c2c_hist = getattr(self, "c2chistory", {})
        if isinstance(c2c_hist, dict):
            user_ids.update(c2c_hist.keys())
        
        userinfo_dir = os.path.join(self.data_dir, "userinfo")
        if os.path.exists(userinfo_dir):
            for f in os.listdir(userinfo_dir):
                if f.endswith(".json"):
                    user_ids.add(f[:-5])

        result = []
        for uid in user_ids:
            nickname = self.get_nickname(uid, is_group=False)
            result.append({"user_id": uid, "nickname": nickname})
        return result

    def get_group_list(self):
        """获取所有已产生群聊记录/设置昵称的群聊列表及其昵称/编号 mapping"""
        group_ids = set()
        group_hist = getattr(self, "grouphistory", {})
        if isinstance(group_hist, dict):
            group_ids.update(group_hist.keys())

        group_tags = getattr(self, "group_tags", {})
        if isinstance(group_tags, dict):
            group_ids.update(group_tags.keys())

        group_nicknames = self.extra.get("group_nicknames", {})
        if isinstance(group_nicknames, dict):
            group_ids.update(group_nicknames.keys())

        result = []
        for gid in group_ids:
            nickname = self.get_nickname(gid, is_group=True)
            tag_num = group_tags.get(gid, None) if isinstance(group_tags, dict) else None
            result.append({
                "group_id": gid,
                "nickname": nickname,
                "tag_num": tag_num
            })
        return result

    # ==================== c2chistory & grouphistory 模块 ====================

    def append_c2c_message(
        self,
        user_id: str,
        content: str,
        user_nickname: str = None,
        role: str = "user",
    ):
        """追加私聊历史，记录消息时间（若传入 user_nickname 则自动更新 userinfo）"""
        u_id = str(user_id)
        now_time = datetime.now().isoformat()

        if user_nickname:
            self.set_user_info(u_id, {"nickname": user_nickname})

        with self._lock:
            msg_entry = {
                "role": role,
                "content": content,
                "timestamp": now_time
            }

            if u_id not in self.c2chistory:
                self.c2chistory[u_id] = []

            self.c2chistory[u_id].append(msg_entry)

            if len(self.c2chistory[u_id]) > self.max_history_limit:
                self.c2chistory[u_id] = self.c2chistory[u_id][-self.max_history_limit:]

            self.has_new_msg = True
            self._write_json(os.path.join(self.data_dir, "c2chistory.json"), self.c2chistory)

    def append_group_message(
        self,
        group_id: str,
        user_id: str,
        content: str,
        user_nickname: str = None,
        role: str = "user",
    ):
        """追加群聊历史，记录消息时间（若传入 user_nickname 则自动更新发送者的 userinfo）"""
        g_id = str(group_id)
        u_id = str(user_id)
        now_time = datetime.now().isoformat()

        if user_nickname:
            self.set_user_info(u_id, {"nickname": user_nickname})

        with self._lock:
            msg_entry = {
                "user_id": u_id,
                "role": role,
                "content": content,
                "timestamp": now_time
            }

            if g_id not in self.grouphistory:
                self.grouphistory[g_id] = []

            self.grouphistory[g_id].append(msg_entry)

            if len(self.grouphistory[g_id]) > self.max_history_limit:
                self.grouphistory[g_id] = self.grouphistory[g_id][-self.max_history_limit:]

            self.has_new_msg = True
            self._write_json(os.path.join(self.data_dir, "grouphistory.json"), self.grouphistory)

    def get_c2c_history(self, user_id: str) -> list:
        with self._lock:
            return self.c2chistory.get(str(user_id), [])

    def get_group_history(self, group_id: str) -> list:
        with self._lock:
            return self.grouphistory.get(str(group_id), [])

    def check_has_new_message(self, reset: bool = True) -> bool:
        """检查是否有新消息，根据 reset 参数决定是否重置标记"""
        with self._lock:
            flag = self.has_new_msg
            if reset:
                self.has_new_msg = False
            return flag

    # ==================== pushhistory & extra 模块 ====================

    def save_pushhistory(self, push_data: dict):
        with self._lock:
            self.pushhistory.update(push_data)
            self._write_json(os.path.join(self.data_dir, "pushhistory.json"), self.pushhistory)

    def get_pushhistory(self) -> dict:
        with self._lock:
            return self.pushhistory

    def set_extra_data(self, key: str, value):
        """自定义扩展数据读写"""
        with self._lock:
            self.extra[key] = value
            self._write_json(os.path.join(self.data_dir, "extra.json"), self.extra)

    def get_extra_data(self, key: str, default=None):
        with self._lock:
            return self.extra.get(key, default)