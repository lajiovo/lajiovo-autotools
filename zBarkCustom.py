import json
import re
import threading
import urllib.request
from zBark import bark, barkall
from zConfig import get_config
# 设备 Key 列表 (读取出来为 Python list 数组)
DEVICEKEYLIST = get_config("bark.key_list", default=[])

# 音频配置
ALARMSOUND = get_config("bark.alarm")
NORMALSOUND = get_config("bark.normal")

# 图标配置
ICON1 = get_config("bark.icon1")
ICON2 = get_config("bark.icon2")
ICON3 = get_config("bark.icon3")

ONEPUSH_PUSHLOG_ADD = "http://127.0.0.1:25566/pushlog/add"
QBOT_PUSH_URL = "http://127.0.0.1:25567/push"


def markdown_to_plain(text: str) -> str:
    """将 Markdown 转为纯文本，供 Bark 等不支持 Markdown 的通道使用。"""
    if not text:
        return ""
    s = str(text)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"```[\s\S]*?```", lambda m: m.group(0).replace("```", ""), s)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    s = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    s = re.sub(r"^#{1,6}\s*", "", s, flags=re.M)
    s = re.sub(r"(\*\*|__)(.*?)\1", r"\2", s)
    s = re.sub(r"(\*|_)(.*?)\1", r"\2", s)
    s = re.sub(r"^>\s?", "", s, flags=re.M)
    s = re.sub(r"^[\-\*\+]\s+", "", s, flags=re.M)
    s = re.sub(r"^\d+\.\s+", "", s, flags=re.M)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _post_json(url: str, payload: dict, timeout: float = 1.0):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "Mozilla/5.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8")


def _dispatch_markdown(level: str, title: str, markdown: str):
    """将 Markdown 通知写入 OnePush 日志，并转发给 QBot /push。"""
    payload = {
        "level": level,
        "title": title,
        "markdown": markdown,
        "msg": markdown,
    }

    def _run():
        try:
            _post_json(ONEPUSH_PUSHLOG_ADD, payload)
        except Exception as e:
            print(f"提交 /pushlog/add 失败: {e}")
        try:
            _post_json(QBOT_PUSH_URL, payload)
        except Exception as e:
            print(f"提交 QBot /push 失败: {e}")

    threading.Thread(target=_run, daemon=True).start()


def _compose_markdown(title: str, msg: str) -> str:
    body = msg if msg is not None else ""
    if title and body:
        return f"**{title}**\n\n{body}"
    return str(title or body or "")


def PerseusWarningMsg(main: str, msg: str):
    title = f"WARNING:{main}"
    markdown = _compose_markdown(title, msg)
    plain = markdown_to_plain(markdown)
    _dispatch_markdown("warning", title, markdown)
    return barkall(DEVICEKEYLIST,
        title=title,
        body=plain,
        group="Perseus",
        sound=ALARMSOUND,
        level="timesensitive",
        icon=ICON1
        )

def PerseusErrorMsg(main: str, msg: str):
    title = f"ERROR:{main}"
    markdown = _compose_markdown(title, msg)
    plain = markdown_to_plain(markdown)
    _dispatch_markdown("error", title, markdown)
    return barkall(DEVICEKEYLIST,
        title=title,
        body=plain,
        group="Perseus",
        sound=ALARMSOUND,
        level="timesensitive",
        icon=ICON3
        )

def PerseusNotifyMsg(main: str, msg: str):
    title = f"Notice:{main}"
    markdown = _compose_markdown(title, msg)
    _dispatch_markdown("notify", title, markdown)
    """
    return barkall(DEVICEKEYLIST,
        title=title,
        body=msg,
        group="Perseus",
        sound=NORMALSOUND,
        level="passive",
        icon=ICON2
        )
        """
    return []

def CustomMsg(title: str, msg: str, group: str):
    markdown = _compose_markdown(title, msg)
    plain = markdown_to_plain(markdown)
    _dispatch_markdown("notify", title, markdown)
    return barkall(DEVICEKEYLIST,
        title=title,
        body=plain,
        group=group,
        sound=ALARMSOUND,
        level="passive",
        copy=plain,
        icon=ICON2
        )

if __name__ == "__main__":
    PerseusNotifyMsg("Testing", "test3")
