import json
import urllib.parse
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

def forward_push(title: str, msg: str):
    """额外转发消息至本地推送接口 (使用 GET 请求匹配 25567 端口)"""
    # 标题和内容拼接在一起
    full_msg = f"{title}\n{msg}"
    
    # 将 msg 和 group 拼接为 URL 查询参数并进行安全转码
    params = urllib.parse.urlencode({
        "msg": full_msg
    })
    
    url = f"http://127.0.0.1:25567/push?{params}"
    
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        # 发送标准 GET 请求
        with urllib.request.urlopen(req, timeout=0.2) as response:
            return response.read().decode('utf-8')
    except Exception as e:
        print(f"转发消息失败: {e}")
        return None

def PerseusWarningMsg(main: str, msg: str):
    title = f"WARNING:{main}"
    forward_push(title, msg)
    return barkall(DEVICEKEYLIST,
        title=title,
        body=msg,
        group="Perseus",
        sound=ALARMSOUND,
        level="timesensitive",
        icon=ICON1
        )

def PerseusErrorMsg(main: str, msg: str):
    title = f"ERROR:{main}"
    forward_push(title, msg)
    return barkall(DEVICEKEYLIST,
        title=title,
        body=msg,
        group="Perseus",
        sound=ALARMSOUND,
        level="timesensitive",
        icon=ICON3
        )

def PerseusNotifyMsg(main: str, msg: str):
    title = f"Notice:{main}"
    # forward_push(title, msg)
    return barkall(DEVICEKEYLIST,
        title=title,
        body=msg,
        group="Perseus",
        sound=NORMALSOUND,
        level="passive",
        icon=ICON2
        )

def CustomMsg(title: str, msg: str, group: str):
    forward_push(title, msg)
    return barkall(DEVICEKEYLIST,
        title=title,
        body=msg,
        group=group,
        sound=ALARMSOUND,
        level="passive",
        copy=msg,
        icon=ICON2
        )

if __name__ == "__main__":
    PerseusNotifyMsg("Testing", "test3")
