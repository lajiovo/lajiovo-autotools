import re
import traceback
from zBarkCustom import PerseusErrorMsg, PerseusNotifyMsg, PerseusWarningMsg
from zPlaywright import main as mainplaywright
from zMumu import hidemumu

def Handlepush(msg_dict: dict):
    try:
        title = msg_dict.get("title", "")
        body = msg_dict.get("body", "")

        print(f"\n[消息接收] 收到新推送通知 | 标题: 『{title}』")

        if "AzurPilot" in title:
            print("[状态检测] 判定为 AzurPilot 相关消息，正在解析...")

            # 1. 判定 body 中是否包含 "警告" 或 "崩溃"
            # 替换原来那行if
            if "警告" in body or "崩溃" in body or "警告" in title or "崩溃" in title:
                print("[风险预警] 检测到运行异常状态！")

                if "自动重启" in body:
                    print(" -> 触发机制: 自动重启流程（轻度异常）")
                    PerseusNotifyMsg(
                        "小波动而已~",
                        "Azurpilot 正在自动重启游戏，稍等一下下就好啦！"
                    )

                elif "RequestHumanTakeover" in body or "RequestHumanTakeover" in title :
                    print(" -> 触发机制: 需要人工接管 (RequestHumanTakeover)")
                    PerseusWarningMsg(
                        "遇到了有点棘手的问题",
                        "Azurpilot 似乎卡住了，别慌，Perseus 正在尝试帮您修复！"
                    )
                    
                    print("[执行动作] 调用 Playwright 修复脚本...")
                    if not mainplaywright():
                        print("[修复结果] ❌ 修复失败，需人工干预")
                        PerseusErrorMsg(
                            "哎呀，解决失败了…",
                            "Perseus 尽力了，这次可能需要主人亲自出马了呢。"
                        )
                        return False
                    else:
                        print("[修复结果] 清除障碍，运行恢复正常！")
                        PerseusNotifyMsg(
                            "搞定啦！✨",
                            "成功化解危机！感谢 Perseus 的默默守护，继续安心起飞吧~"
                        )

                elif "EmulatorNotRunningError" in body or "EmulatorNotRunningError" in title:
                    print(" -> 触发机制: 模拟器未运行 (EmulatorNotRunningError)")
                    PerseusWarningMsg(
                        "模拟器偷懒掉线了",
                        "检测到模拟器异常，Perseus 正在尝试隐藏并重新拉起它…"
                    )
                    
                    print("[执行动作] 隐藏 MuMu 模拟器窗口并重新拉起...")
                    hidemumu()
                    
                    print("[执行动作] 调用 Playwright 修复脚本...")
                    if not mainplaywright():
                        print("[修复结果] ❌ 模拟器拉起/修复失败")
                        PerseusErrorMsg(
                            "无法唤醒模拟器",
                            "自动修复没有成功，麻烦主人查看一下系统环境哦。"
                        )
                        return False
                    else:
                        print("[修复结果] 模拟器已成功拉起并修复！")
                        PerseusNotifyMsg(
                            "完美复活！🚀",
                            "模拟器已重新上线并恢复秩序，感谢 Perseus 的辛勤工作~"
                        )

                else:
                    print(" -> 触发机制: 未知警告/错误")
                    PerseusWarningMsg(
                        "捕捉到未知的小情绪",
                        "发现了未预期的异常，Perseus 正在尝试自愈修复…"
                    )
                    
                    print("[执行动作] 调用 Playwright 修复脚本...")
                    if not mainplaywright():
                        print("[修复结果] ❌ 未知错误修复失败")
                        PerseusErrorMsg(
                            "遇到了摸不着头脑的问题",
                            "尝试修复失败了，主人有空的话请检查一下日志吧。"
                        )
                        return False
                    else:
                        print("[修复结果] 异常已顺利排查！")
                        PerseusNotifyMsg(
                            "雨过天晴~ 🌈",
                            "未知问题已轻松搞定！多亏了 Perseus 的及时守护。"
                        )

            else:
                # 2. 判定是否为获得钻石/顶级奖励的通知
                if "顶级奖励" in title or "钻石" in body:
                    print("Good News!💎红尖尖委托大成功！")
                    match = re.search(r"本次获得钻石\s*\*\s*(\d+)", body)
                    if match:
                        diamond_count = match.group(1)
                        print(f" -> 解析成功: 获得钻石 * {diamond_count}")
                        PerseusNotifyMsg(
                            "Good News!💎红尖尖委托大成功！",
                            f"欧气爆棚！本次成功揽获 钻石*{diamond_count}！"
                        )
                    else:
                        print(" -> 解析成功: 获得钻石奖励（未匹配到具体数值）")
                        PerseusNotifyMsg(
                            "Good News!💎红尖尖委托大成功！",
                            "又收获了红尖尖呢，愿这份好运陪伴你一整天！"
                        )
                else:
                    print("[日常通知] 常规推送消息，原样转发")
                    PerseusNotifyMsg(title, body)
        else:
            print("[未知通知] ，原样转发")
            PerseusNotifyMsg(title, body)

        return True

    except Exception as e:
        # 捕捉 Handlepush 函数内部自身发生的任何脚本运行报错
        error_type = type(e).__name__
        error_detail = str(e)
        
        print(f"\n[💥 函数报错] Handlepush 执行过程中抛出异常！")
        print(f"错误类型: {error_type}")
        print(f"详细信息: {error_detail}")
        print("完整追踪日志:")
        traceback.print_exc()

        # 发送报错内容通知
        PerseusErrorMsg(
            f"Handlepush脚本报错 [{error_type}]",
            f"处理消息时发生异常: {error_detail}"
        )
        return False
