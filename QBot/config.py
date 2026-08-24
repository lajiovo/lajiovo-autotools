"""
client.data_mgr 数据读取与保存使用指南

client.data_mgr 是统一数据管理对象（BotDataManager 实例），负责系统配置、用户信息、群聊配置、消息历史、推送记录及扩展数据的本地持久化与读取。

一、 系统配置与 OP 权限 (opsetting)

1. 读取系统完整配置 get_opsetting()

说明：获取当前系统的完整 OP 配置。

参数：无

返回值：dict - 包含 op_list 与 system_active 的字典。

2. 设置并保存系统配置 set_opsetting(setting_dict)

说明：更新并直接落盘保存 opsetting。

参数：

setting_dict (dict): 待更新或覆盖的配置字典。

返回值：无

3. 设置系统激活状态 set_system_active(active)

说明：开启或关闭机器人系统的激活状态并自动落盘。

参数：

active (bool): True 表示激活，False 表示停用。

返回值：无

4. 检查系统激活状态 is_system_active()

说明：判断当前系统是否处于激活状态。

参数：无

返回值：bool

5. 添加管理员 OP add_op(user_id)

说明：将指定用户 ID 添加为管理员 OP 并保存。

参数：

user_id (str | int): 用户 ID。

返回值：无

6. 移除管理员 OP remove_op(user_id)

说明：移除指定用户的管理员 OP 权限并保存。

参数：

user_id (str | int): 用户 ID。

返回值：无

7. 检查用户是否为 OP is_op(user_id)

说明：查询指定用户是否具备管理员权限。

参数：

user_id (str | int): 用户 ID。

返回值：bool

二、 用户信息与数据 (userinfo & userdata)

数据自动落盘保存至 botdata/userinfo/{user_id}.json 或 botdata/userdata/{user_id}.json。

1. 保存/更新用户信息 set_user_info(user_id, info_dict)

说明：更新指定用户的基础信息（如 nickname 等）并落盘。

参数：

user_id (str): 用户 ID。

info_dict (dict): 包含要更新的用户信息键值对。

返回值：无

2. 读取用户信息 get_user_info(user_id)

说明：获取指定用户的个人信息。

参数：

user_id (str): 用户 ID。

返回值：dict - 若不存在则返回空字典 {}。

3. 保存/更新用户数据 set_user_data(user_id, data_dict)

说明：保存用户业务扩展数据（如业务状态、积分等）并落盘。

参数：

user_id (str): 用户 ID。

data_dict (dict): 待保存的数据字典。

返回值：无

4. 读取用户数据 get_user_data(user_id)

说明：获取指定用户的业务数据。

参数：

user_id (str): 用户 ID。

返回值：dict - 若不存在则返回空字典 {}。

三、 群聊信息与设置 (groupinfo)

数据按群 ID 独立存放在 botdata/groupinfo/{group_id}.json 中。

1. 保存/更新群聊信息 set_group_info(group_id, info_dict)

说明：更新指定群聊的信息字段并保存。

参数：

group_id (str): 群聊 ID。

info_dict (dict): 包含群聊配置的字典。

返回值：无

2. 读取群聊信息 get_group_info(group_id)

说明：获取指定群聊的完整配置信息。

参数：

group_id (str): 群聊 ID。

返回值：dict

3. 设置群聊别名/昵称 set_group_nickname(group_id, nickname)

说明：设置群聊的备注名称并落盘。

参数：

group_id (str): 群聊 ID。

nickname (str): 群聊别名。

返回值：无

4. 读取群聊别名/昵称 get_group_nickname(group_id)

说明：读取群聊备注名称（兼容旧版 extra 中的配置）。

参数：

group_id (str): 群聊 ID。

返回值：str - 未设置则返回空字符串。

5. 设置群聊标签/编号 set_group_tag(group_id, grouptag)

说明：设置群聊的自定义 Tag 或编号并落盘。

参数：

group_id (str): 群聊 ID。

grouptag (str): 标签/编号。

返回值：无

6. 读取群聊标签/编号 get_group_tag(group_id)

说明：读取群聊的 Tag 或编号。

参数：

group_id (str): 群聊 ID。

返回值：str

四、 聊天历史记录 (c2chistory & grouphistory)

私聊按用户存入 botdata/c2chistory/{user_id}.json；群聊按群存入 botdata/grouphistory/{group_id}.json。

1. 追加私聊消息 append_c2c_message(user_id, content, user_nickname=None, role="user")

说明：向指定用户的私聊历史中写入一条消息，系统自动追加当前 ISO 时间戳。若传入 user_nickname 则会自动更新该用户的 userinfo。

参数：

user_id (str): 用户 ID。

content (str): 消息文本内容。

user_nickname (str, 可选): 发送者昵称，默认 None。

role (str, 可选): 消息角色，默认为 "user"（AI 回复可设为 "assistant"）。

返回值：无

2. 读取私聊历史 get_c2c_history(user_id)

说明：获取指定用户的私聊历史消息列表。

参数：

user_id (str): 用户 ID。

返回值：list[dict] - 包含 role, content, timestamp 的字典列表。

3. 追加群聊消息 append_group_message(group_id, user_id, content, user_nickname=None, role="user")

说明：向指定群聊历史中追加一条消息，自动补全 ISO 时间戳。

参数：

group_id (str): 群聊 ID。

user_id (str): 发送者用户 ID。

content (str): 消息内容。

user_nickname (str, 可选): 发送者昵称，默认 None。

role (str, 可选): 消息角色，默认 "user"。

返回值：无

4. 读取群聊历史 get_group_history(group_id)

说明：获取指定群聊的历史消息列表。

参数：

group_id (str): 群聊 ID。

返回值：list[dict] - 包含 user_id, role, content, timestamp 的字典列表。

5. 通用读取历史记录 get_chat_history(target_id, is_group=False)

说明：统一读取私聊或群聊历史。

参数：

target_id (str): 用户 ID 或群聊 ID。

is_group (bool, 可选): True 读取群聊历史，False 读取私聊历史，默认 False。

返回值：list[dict]

五、 推送历史 (pushhistory)

保存至 botdata/pushhistory.json。

1. 追加推送记录 append_push_history(content)

说明：写入一条推送日志，系统会自动注入 timestamp 字段并自动落盘。

参数：

content (str | dict): 可以直接传入字符串内容，也可以传入字典对象。

返回值：dict - 补全 timestamp 后的最终入库对象。

2. 读取推送历史 get_pushhistory()

说明：获取全量推送历史。

参数：无

返回值：list 或 dict（取决于存入的历史数据结构）。

3. 覆盖/重置推送历史 save_pushhistory(push_data)

说明：用新的数据替换现有推送历史并落盘。

参数：

push_data (list | dict): 全量推送历史数据。

返回值：无

六、 自定义扩展数据 (extra)

保存至 botdata/extra.json，用于存储不属于用户信息或群信息的临时/自定义键值数据。

1. 设置扩展数据 set_extra_data(key, value)

说明：写入扩展键值并保存到磁盘。

参数：

key (str): 键名。

value (Any): 可被 JSON 序列化的值。

返回值：无

2. 读取扩展数据 get_extra_data(key, default=None)

说明：读取扩展键值。

参数：

key (str): 键名。

default (Any, 可选): 当键不存在时的默认返回值，默认为 None。

返回值：Any

七、 辅助与列表查询接口

1. 获取昵称 get_nickname(target_id, is_group=False)

说明：获取指定群或用户的显示昵称。

参数：

target_id (str): 群 ID 或 用户 ID。

is_group (bool): 是否为群组。

返回值：str

2. 获取已知用户列表 get_user_list()

说明：列出所有产生过私聊记录或设置过 UserInfo 的用户列表。

参数：无

返回值：list[dict] - 项格式为 {"user_id": ..., "nickname": ...}

3. 获取已知群聊列表 get_group_list()

说明：列出所有产生过群聊记录、设置过群昵称或群标签的群聊列表。

参数：无

返回值：list[dict] - 项格式为 {"group_id": ..., "nickname": ..., "grouptag": ..., "tag_num": ...}

4. 检查新消息标记 check_has_new_message(reset=True)

说明：检查自上次重置以来是否有新消息追加。

参数：

reset (bool): 是否在检查完后重置标记为 False，默认 True。

返回值：bool
"""
import sys
import os
import io
import logging
from logging.handlers import RotatingFileHandler
import importlib.util
from pathlib import Path

# 防护措施：必须放在代码最最顶部（在导入任何第三方库或日志模块前）
# 若当前运行环境无控制台 (sys.stdout/stderr 为 None)，填充 devnull 空流
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

# 当前脚本所在目录及日志文件夹设置
current_dir = Path(__file__).resolve().parent
log_dir = current_dir / "log"
log_dir.mkdir(parents=True, exist_ok=True)

# 轮转日志 Handler，限制单文件不超过 512KB (512 * 1024 bytes)
log_file = log_dir / "app.log"
file_handler = RotatingFileHandler(
    log_file,
    maxBytes=512 * 1024,  # 512 KB
    backupCount=5,        # 最多保留 5 个历史归档文件
    encoding="utf-8"
)
file_handler.setFormatter(
    logging.Formatter("%(asctime)s - [%(levelname)s] - %(name)s - %(message)s")
)

# 配置根 Logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(file_handler)

# 获取上一级目录路径
parent_dir = current_dir.parent

from pathlib import Path

# 防护措施：必须放在代码最最顶部（在导入任何第三方库或日志模块前）
# 若当前运行环境无控制台 (sys.stdout/stderr 为 None)，填充 devnull 空流
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

# 获取上一级目录路径
parent_dir = Path(__file__).resolve().parent.parent

def load_module_from_parent(module_name: str):
    """动态加载上级目录中的 Python 模块"""
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

# 修复：Python 内置 logging 模块正确方法为 getLogger()，而非 get_logger()
_log = logging.getLogger(__name__)

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

# 确保主数据目录及各模块独立子目录存在
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "userinfo"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "userdata"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "groupinfo"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "grouphistory"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "c2chistory"), exist_ok=True)

# Bot 配置读取
APP_ID = zConfig.get_config("bot.app_id")
APP_SECRET = zConfig.get_config("bot.app_secret")

# 并发限制信号量
RUN_TASK_SEMAPHORE = threading.Semaphore(2)


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
    - opsetting, pushhistory, extra 按独立文件保存
    - userinfo, userdata, groupinfo 按 ID 分文件存储至独立文件夹
    - grouphistory, c2chistory 按照群 ID 和人 ID 分文件单独存储
    - pushhistory 写入仅需传入内容，自动补充 timestamp 字段
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
        self.userinfo = {}      # user_id -> dict
        self.userdata = {}      # user_id -> dict
        self.groupinfo = {}     # group_id -> dict
        self.grouphistory = {}  # group_id -> list of msgs
        self.c2chistory = {}     # user_id -> list of msgs
        self.pushhistory = []   # 推送历史列表
        self.extra = {}         # 自定义扩展数据

        self.load_all()

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

    def load_all(self):
        """全面加载全部本地文件数据"""
        with self._lock:
            # 1. 通用文件
            self.opsetting = self._read_json(
                os.path.join(self.data_dir, "opsetting.json"), 
                {"op_list": [str(self.DEFAULT_OP)] if self.DEFAULT_OP else [], "system_active": True}
            )
            self.pushhistory = self._read_json(os.path.join(self.data_dir, "pushhistory.json"), [])
            self.extra = self._read_json(os.path.join(self.data_dir, "extra.json"), {})

            # 确保默认 OP 权限存在
            if self.DEFAULT_OP and str(self.DEFAULT_OP) not in self.opsetting.get("op_list", []):
                self.opsetting.setdefault("op_list", []).append(str(self.DEFAULT_OP))

            # 2. userinfo (按 ID 分文件夹读取)
            userinfo_dir = os.path.join(self.data_dir, "userinfo")
            if os.path.exists(userinfo_dir):
                for filename in os.listdir(userinfo_dir):
                    if filename.endswith(".json"):
                        u_id = filename[:-5]
                        self.userinfo[u_id] = self._read_json(os.path.join(userinfo_dir, filename), {})

            # 3. userdata (按 ID 分文件夹读取)
            userdata_dir = os.path.join(self.data_dir, "userdata")
            if os.path.exists(userdata_dir):
                for filename in os.listdir(userdata_dir):
                    if filename.endswith(".json"):
                        u_id = filename[:-5]
                        self.userdata[u_id] = self._read_json(os.path.join(userdata_dir, filename), {})

            # 4. groupinfo (按 ID 分文件夹读取)
            groupinfo_dir = os.path.join(self.data_dir, "groupinfo")
            if os.path.exists(groupinfo_dir):
                for filename in os.listdir(groupinfo_dir):
                    if filename.endswith(".json"):
                        g_id = filename[:-5]
                        self.groupinfo[g_id] = self._read_json(os.path.join(groupinfo_dir, filename), {})

            # 5. grouphistory (按群分文件读取)
            grouphistory_dir = os.path.join(self.data_dir, "grouphistory")
            if os.path.exists(grouphistory_dir):
                for filename in os.listdir(grouphistory_dir):
                    if filename.endswith(".json"):
                        g_id = filename[:-5]
                        self.grouphistory[g_id] = self._read_json(os.path.join(grouphistory_dir, filename), [])

            # 6. c2chistory (按人分文件读取)
            c2chistory_dir = os.path.join(self.data_dir, "c2chistory")
            if os.path.exists(c2chistory_dir):
                for filename in os.listdir(c2chistory_dir):
                    if filename.endswith(".json"):
                        u_id = filename[:-5]
                        self.c2chistory[u_id] = self._read_json(os.path.join(c2chistory_dir, filename), [])

    def get_opsetting(self) -> dict:
        """获取整个 opsetting 配置"""
        with self._lock:
            return dict(self.opsetting)

    def set_opsetting(self, setting_dict: dict):
        """覆盖并保存 opsetting 配置"""
        with self._lock:
            self.opsetting.update(setting_dict)
            self.save_opsetting()

    def save_opsetting(self):
        """保存 opsetting 到本地"""
        file_path = os.path.join(self.data_dir, "opsetting.json")
        self._write_json(file_path, self.opsetting)

    def set_system_active(self, active: bool):
        """设置系统激活状态"""
        with self._lock:
            self.opsetting["system_active"] = bool(active)
            self.save_opsetting()

    def is_system_active(self) -> bool:
        """检查系统是否处于激活状态"""
        with self._lock:
            return bool(self.opsetting.get("system_active", True))

    def add_op(self, user_id: str):
        """添加管理员 OP"""
        u_id = str(user_id)
        with self._lock:
            if u_id not in self.opsetting.get("op_list", []):
                self.opsetting.setdefault("op_list", []).append(u_id)
                self.save_opsetting()

    def remove_op(self, user_id: str):
        """移除管理员 OP"""
        u_id = str(user_id)
        with self._lock:
            if u_id in self.opsetting.get("op_list", []):
                self.opsetting["op_list"].remove(u_id)
                self.save_opsetting()

    def is_op(self, user_id: str) -> bool:
        """检查用户是否是管理员"""
        u_id = str(user_id)
        with self._lock:
            return u_id in self.opsetting.get("op_list", [])

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
        """获取指定 ID 的 userinfo"""
        with self._lock:
            return dict(self.userinfo.get(str(user_id), {}))

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
        """获取指定 ID 的 userdata"""
        with self._lock:
            return dict(self.userdata.get(str(user_id), {}))

    def set_group_info(self, group_id: str, info_dict: dict):
        """保存/更新指定群聊的 groupinfo"""
        g_id = str(group_id)
        with self._lock:
            if g_id not in self.groupinfo:
                self.groupinfo[g_id] = {}
            self.groupinfo[g_id].update(info_dict)

            file_path = os.path.join(self.data_dir, "groupinfo", f"{g_id}.json")
            self._write_json(file_path, self.groupinfo[g_id])

    def get_group_info(self, group_id: str) -> dict:
        """获取指定群聊的 groupinfo"""
        with self._lock:
            return dict(self.groupinfo.get(str(group_id), {}))

    def set_group_nickname(self, group_id: str, nickname: str):
        """设置群聊 nickname"""
        self.set_group_info(group_id, {"nickname": nickname})

    def get_group_nickname(self, group_id: str) -> str:
        """获取群聊 nickname"""
        info = self.get_group_info(group_id)
        if info.get("nickname"):
            return str(info["nickname"])
        # 回退逻辑：兼容旧 extra 配置
        with self._lock:
            group_nicknames = self.extra.get("group_nicknames", {})
            if isinstance(group_nicknames, dict) and str(group_id) in group_nicknames:
                return str(group_nicknames[str(group_id)])
            return str(self.extra.get(f"group_nickname_{group_id}", ""))

    def set_group_tag(self, group_id: str, grouptag: str):
        """设置群聊 grouptag"""
        self.set_group_info(group_id, {"grouptag": grouptag})

    def get_group_tag(self, group_id: str) -> str:
        """获取群聊 grouptag"""
        info = self.get_group_info(group_id)
        if info.get("grouptag") is not None:
            return str(info["grouptag"])
        # 回退逻辑：兼容旧 group_tags 配置
        with self._lock:
            group_tags = getattr(self, "group_tags", {})
            if isinstance(group_tags, dict) and str(group_id) in group_tags:
                return str(group_tags[str(group_id)])
            return ""

    def get_nickname(self, target_id: str, is_group: bool = False) -> str:
        """获取指定群或用户的昵称 (Group 优先从 groupinfo/extra 读取，User 从 userinfo 读取)"""
        target_id = str(target_id)
        if is_group:
            return self.get_group_nickname(target_id)
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
        with self._lock:
            if isinstance(self.c2chistory, dict):
                user_ids.update(self.c2chistory.keys())

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
        """获取所有已产生群聊记录/设置昵称/设置标签的群聊列表"""
        group_ids = set()
        with self._lock:
            if isinstance(self.grouphistory, dict):
                group_ids.update(self.grouphistory.keys())
            if isinstance(self.groupinfo, dict):
                group_ids.update(self.groupinfo.keys())

            group_tags = getattr(self, "group_tags", {})
            if isinstance(group_tags, dict):
                group_ids.update(group_tags.keys())

            group_nicknames = self.extra.get("group_nicknames", {})
            if isinstance(group_nicknames, dict):
                group_ids.update(group_nicknames.keys())

        result = []
        for gid in group_ids:
            nickname = self.get_nickname(gid, is_group=True)
            grouptag = self.get_group_tag(gid)
            result.append({
                "group_id": gid,
                "nickname": nickname,
                "grouptag": grouptag,
                "tag_num": grouptag  # 兼容旧参数名
            })
        return result

    def append_c2c_message(
        self,
        user_id: str,
        content: str,
        user_nickname: str = None,
        role: str = "user",
    ):
        """追加私聊历史，记录消息时间（按 user_id 单独落盘，若传入 user_nickname 则自动更新 userinfo）"""
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
            file_path = os.path.join(self.data_dir, "c2chistory", f"{u_id}.json")
            self._write_json(file_path, self.c2chistory[u_id])

    def append_group_message(
        self,
        group_id: str,
        user_id: str,
        content: str,
        user_nickname: str = None,
        role: str = "user",
    ):
        """追加群聊历史，记录消息时间（按 group_id 单独落盘，若传入 user_nickname 则自动更新发送者的 userinfo）"""
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
            file_path = os.path.join(self.data_dir, "grouphistory", f"{g_id}.json")
            self._write_json(file_path, self.grouphistory[g_id])

    def get_c2c_history(self, user_id: str) -> list:
        """获取指定用户的私聊历史"""
        with self._lock:
            return list(self.c2chistory.get(str(user_id), []))

    def get_group_history(self, group_id: str) -> list:
        """获取指定群聊的历史记录"""
        with self._lock:
            return list(self.grouphistory.get(str(group_id), []))

    def check_has_new_message(self, reset: bool = True) -> bool:
        """检查是否有新消息，根据 reset 参数决定是否重置标记"""
        with self._lock:
            flag = self.has_new_msg
            if reset:
                self.has_new_msg = False
            return flag

    def append_push_history(self, content):
        """
        写入推送历史，仅需要传入消息内容 (str 或 dict)，自动补充 timestamp 字段
        """
        now_time = datetime.now().isoformat()
        with self._lock:
            if isinstance(content, dict):
                entry = dict(content)
                if "timestamp" not in entry:
                    entry["timestamp"] = now_time
            else:
                entry = {
                    "content": str(content),
                    "timestamp": now_time
                }

            if isinstance(self.pushhistory, list):
                self.pushhistory.append(entry)
            elif isinstance(self.pushhistory, dict):
                p_id = f"push_{int(time.time() * 1000)}"
                self.pushhistory[p_id] = entry
            else:
                self.pushhistory = [entry]

            self._write_json(os.path.join(self.data_dir, "pushhistory.json"), self.pushhistory)
            return entry

    def save_pushhistory(self, push_data):
        """直接保存/替换推送历史数据"""
        with self._lock:
            self.pushhistory = push_data
            self._write_json(os.path.join(self.data_dir, "pushhistory.json"), self.pushhistory)

    def get_pushhistory(self):
        """获取推送历史记录"""
        with self._lock:
            return self.pushhistory

    def set_extra_data(self, key: str, value):
        """自定义扩展数据读写"""
        with self._lock:
            self.extra[key] = value
            self._write_json(os.path.join(self.data_dir, "extra.json"), self.extra)

    def get_extra_data(self, key: str, default=None):
        """获取扩展数据"""
        with self._lock:
            return self.extra.get(key, default)