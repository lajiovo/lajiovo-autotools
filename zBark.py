import requests
from typing import Optional, Union


def bark(
    device_key: str,
    title: Optional[str] = None,
    body: Optional[str] = None,
    url: Optional[str] = None,
    group: Optional[str] = None,
    icon: Optional[str] = None,
    sound: Optional[str] = None,
    level: Optional[str] = None,
    badge: Optional[int] = None,
    auto_copy: Optional[int] = None,
    copy: Optional[str] = None,
    is_archive: Optional[int] = None,
    api_domain: str = "https://api.day.app",
    timeout: int = 10
) -> dict:
    """
    Bark 推送统一调用函数，实现OnePush Bark全功能推送
    :param device_key: Bark设备密钥（必填，APP内复制）
    :param title: 通知标题
    :param body: 通知正文内容
    :param url: 点击通知跳转链接
    :param group: 消息分组，APP内可按分组归类消息
    :param icon: 自定义通知图标URL（网络图片）
    :param sound: 通知提示音名称，内置音效如: bells, chimes, alarm 等
    :param level: 推送级别：
        active: 默认，正常弹窗
        timeSensitive: 时效性通知（勿扰模式也弹出）
        passive: 仅通知中心，不弹窗
    :param badge: APP角标数字（右上角小红点数字）
    :param auto_copy: 1=自动复制通知正文到剪贴板；0关闭
    :param copy: 指定自定义复制内容，点击通知自动复制这段文本
    :param is_archive: 1=自动归档消息；0不归档
    :param api_domain: Bark服务域名，自建服务可替换为私有地址
    :param timeout: 请求超时时间，单位秒
    :return: 接口返回字典，包含code/message等状态
    """
    # 拼接基础推送地址
    base_url = f"{api_domain}/{device_key}/"
    params = {}

    # 组装基础推送内容
    if title:
        params["title"] = title
    if body:
        params["body"] = body
    if url:
        params["url"] = url

    # 扩展可选参数
    if group:
        params["group"] = group
    if icon:
        params["icon"] = icon
    if sound:
        params["sound"] = sound
    if level in ["active", "timeSensitive", "passive"]:
        params["level"] = level
    if isinstance(badge, int) and badge >= 0:
        params["badge"] = badge
    if auto_copy in (0, 1):
        params["autoCopy"] = auto_copy
    if copy:
        params["copy"] = copy
    if is_archive in (0, 1):
        params["isArchive"] = is_archive

    try:
        resp = requests.get(base_url, params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        return {
            "code": -1,
            "message": f"请求异常: {str(e)}",
            "data": None
        }


# 简易测试入口（单独运行文件时测试）
if __name__ == "__main__":
    # 替换为你自己的Bark设备KEY
    DEVICE_KEY = "xxxxxxxxxxxx"

    # 基础推送示例
    res1 = bark(
        device_key=DEVICE_KEY,
        title="测试通知",
        body="这是一条来自Python库的Bark推送消息"
    )
    print("基础推送结果：", res1)

    # 高级完整参数推送示例
    res2 = bark(
        device_key=DEVICE_KEY,
        title="WARNING",
        body=r"bro'alas broke",
        url="https://192.168.10.3:22267",
        group="Wow",
        sound="alarm",
        level="timeSensitive",
        badge=1,
        auto_copy=1,
        copy="hi",
        is_archive=1
    )
    print("高级推送结果：", res2)
