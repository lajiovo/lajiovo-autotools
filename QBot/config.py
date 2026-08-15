import os
import json
import threading
from botpy import logging
from botpy.ext.cog_yaml import read
from botpy.message import GroupMessage

_log = logging.get_logger()

# 基础文件路径
BASE_DIR = os.path.dirname(__file__)
CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")
DATA_FILE_PATH = os.path.join(BASE_DIR, "botdata.json")
CHAT_FILE_PATH = os.path.join(BASE_DIR, "chathistory.json")  # 聊天记录存储文件

# 读取配置
if os.path.exists(CONFIG_PATH):
    test_config = read(CONFIG_PATH)
    APP_ID = test_config["appid"]
    APP_SECRET = test_config["secret"]
else:
    APP_ID = ""
    APP_SECRET = ""

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

# 数据管理类（专职负责持久化与数据库/数据存储操作）
class DataManager:
    DEFAULT_OP = ""

    def __init__(self):
        self.op_list = set()
        self.user_stats = {}
        self.group_tags = {}
        self.system_active = True
        self.load_data()

    def load_data(self):
        if os.path.exists(DATA_FILE_PATH):
            try:
                with open(DATA_FILE_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.op_list = set(data.get("op_list", []))
                    self.user_stats = data.get("user_stats", {})
                    self.group_tags = data.get("group_tags", {})
                    self.system_active = data.get("system_active", True)
                    _log.info(f"✅ 成功从 {DATA_FILE_PATH} 加载数据！")
            except Exception as e:
                _log.error(f"❌ 读取 {DATA_FILE_PATH} 失败: {e}，将使用初始数据。")
                self._reset_defaults()
        else:
            _log.info(f"ℹ️ 未找到 {DATA_FILE_PATH}，正在进行首次初始化...")
            self._reset_defaults()

        self.op_list.add(self.DEFAULT_OP)
        self.save_data()

    def _reset_defaults(self):
        self.op_list = {self.DEFAULT_OP}
        self.user_stats = {}
        self.group_tags = {}
        self.system_active = True

    def save_data(self):
        try:
            data = {
                "op_list": list(self.op_list),
                "user_stats": self.user_stats,
                "group_tags": self.group_tags,
                "system_active": self.system_active
            }
            with open(DATA_FILE_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            #_log.info(f"💾 数据已成功保存至 {DATA_FILE_PATH}")
        except Exception as e:
            _log.error(f"❌ 保存数据到 {DATA_FILE_PATH} 失败: {e}")


# 聊天记录与昵称管理类
class ChatHistoryManager:
    """
    独立管理群聊记录、私聊记录、群昵称与用户昵称
    保存文件路径：同目录下的 chathistory.json
    """

    def __init__(self, file_path=CHAT_FILE_PATH, max_limit=30):
        self.file_path = file_path
        self.max_limit = max_limit
        self._lock = threading.Lock()
        self.user_nicknames = {}
        self.group_nicknames = {}
        self.private_history = {}
        self.group_history = {}
        self.load_data()

    def load_data(self):
        with self._lock:
            if os.path.exists(self.file_path):
                try:
                    with open(self.file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        self.user_nicknames = data.get("user_nicknames", {})
                        self.group_nicknames = data.get("group_nicknames", {})
                        self.private_history = data.get("private_history", {})
                        self.group_history = data.get("group_history", {})
                        _log.info(f"✅ 成功从 {self.file_path} 加载聊天记录！")
                except Exception as e:
                    _log.error(f"❌ 读取 {self.file_path} 失败: {e}，初始化为空。")
                    self._reset_defaults()
            else:
                self._reset_defaults()

    def _reset_defaults(self):
        self.user_nicknames = {}
        self.group_nicknames = {}
        self.private_history = {}
        self.group_history = {}

    def save_data(self):
        try:
            data = {
                "user_nicknames": self.user_nicknames,
                "group_nicknames": self.group_nicknames,
                "private_history": self.private_history,
                "group_history": self.group_history,
            }
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            _log.error(f"❌ 保存聊天记录到 {self.file_path} 失败: {e}")

    # ==================== 昵称修改方法 ====================

    def update_user_nickname(self, user_id: str, nickname: str):
        """仅修改用户昵称"""
        with self._lock:
            self.user_nicknames[str(user_id)] = nickname
            self.save_data()

    def update_group_nickname(self, group_id: str, nickname: str):
        """仅修改群聊昵称"""
        with self._lock:
            self.group_nicknames[str(group_id)] = nickname
            self.save_data()

    # ==================== 记录追加方法 ====================

    def append_private_message(
        self,
        user_id: str,
        content: str,
        user_nickname: str = None,
        role: str = "user",
    ):
        """
        仅追加私聊记录（每个用户上限 30 条）
        若传入 user_nickname 则自动更新用户昵称
        """
        with self._lock:
            u_id = str(user_id)
            if user_nickname:
                self.user_nicknames[u_id] = user_nickname

            msg_entry = {"role": role, "content": content}

            if u_id not in self.private_history:
                self.private_history[u_id] = []

            self.private_history[u_id].append(msg_entry)

            # 超出上限进行截断
            if len(self.private_history[u_id]) > self.max_limit:
                self.private_history[u_id] = self.private_history[u_id][-self.max_limit:]

            self.save_data()

    def append_group_message(
        self,
        group_id: str,
        user_id: str,
        content: str,
        group_nickname: str = None,
        user_nickname: str = None,
        role: str = "user",
    ):
        """
        仅追加群聊记录（每个群聊上限 30 条）
        可选传入 group_nickname 和 user_nickname 进行自动更新
        """
        with self._lock:
            g_id = str(group_id)
            u_id = str(user_id)

            if group_nickname:
                self.group_nicknames[g_id] = group_nickname
            if user_nickname:
                self.user_nicknames[u_id] = user_nickname

            msg_entry = {
                "user_id": u_id,
                "role": role,
                "content": content,
            }

            if g_id not in self.group_history:
                self.group_history[g_id] = []

            self.group_history[g_id].append(msg_entry)

            # 超断控制
            if len(self.group_history[g_id]) > self.max_limit:
                self.group_history[g_id] = self.group_history[g_id][-self.max_limit:]

            self.save_data()

    # ==================== 查询读取接口 ====================

    def get_private_history(self, user_id: str):
        """读取指定用户的私聊记录"""
        with self._lock:
            return self.private_history.get(str(user_id), [])

    def get_group_history(self, group_id: str):
        """读取指定群聊的历史记录"""
        with self._lock:
            return self.group_history.get(str(group_id), [])


# 调用示例：
# chat_mgr = ChatHistoryManager()
# 1. 独立修改昵称
# chat_mgr.update_user_nickname("1001", "张三")
# chat_mgr.update_group_nickname("group_999", "开发交流群")

# 2. 追加私聊消息
# chat_mgr.append_private_message(user_id="1001", content="你好，这是私聊")

# 3. 追加群聊消息
# chat_mgr.append_group_message(group_id="group_999", user_id="1001", content="大家好！")
