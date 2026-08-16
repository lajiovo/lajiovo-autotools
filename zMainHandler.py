import zPerseusLogger
import traceback
import zAlas
import zMumu
import zPlaywright
import zPGRJZ
import re
from zBarkCustom import PerseusErrorMsg, PerseusWarningMsg,PerseusNotifyMsg

def run_alas_mumu_check():
    """
    通用检查与恢复函数
    按 ["check", "start", "wait", "check", "update"] 顺序执行 Playwright 操作并根据返回状态自动恢复。
    """
    # 0. 初始检测：若 MuMu 未运行，则拉起并隐藏（不计数）
    if not zMumu.is_mumu_running():
        print("[Info] 检测到 MuMu 未运行，正在启动并隐藏 MuMu...")
        zMumu.hidemumu()

    alas_soft_restart_count = 0  # Alas 软重启 (Playwright ["restart"]) 计数
    alas_hard_restart_count = 0  # Alas 硬重启 (cleanup + start) 计数
    mumu_restart_count = 0       # MuMu 重启计数

    max_soft_restarts = 2
    max_hard_restarts = 2
    max_mumu_restarts = 2

    # 标准执行任务队列
    standard_task_list = ["check", "start", "wait", "check", "update"]

    print("[Info] 开始执行 Alas & MuMu 状态自动化检查流程...")

    while True:
        # 0. 校验硬重启与 MuMu 重启上限
        if (
            alas_hard_restart_count >= max_hard_restarts
            or mumu_restart_count >= max_mumu_restarts
        ):
            err_title = "Alas/MuMu 自动恢复失败"
            err_body = (
                f"重启次数达到上限 (Alas软重启: {alas_soft_restart_count}/{max_soft_restarts}, "
                f"Alas硬重启: {alas_hard_restart_count}/{max_hard_restarts}, "
                f"MuMu重启: {mumu_restart_count}/{max_mumu_restarts})，已停止重试并清除进程。"
            )
            print(f"[Fatal] {err_title}: {err_body}")
            PerseusErrorMsg(err_title, err_body)

            # 达到次数限制，直接结束二者进程
            try:
                zAlas.cleanup()
                zMumu.mumu_kill()
            except Exception as e:
                print(f"[Error] 清理进程时出现异常: {e}")

            return False

        print(
            f"[Info] 运行 Playwright 任务... (Alas 软重启: {alas_soft_restart_count}/{max_soft_restarts}, "
            f"硬重启: {alas_hard_restart_count}/{max_hard_restarts}, MuMu 重启: {mumu_restart_count}/{max_mumu_restarts})"
        )

        try:
            # 1. 调用 zPlaywright 主函数进行常规检查
            is_all_success, task_results = zPlaywright.main(
                headless=True,
                task_list=standard_task_list,
            )

            print(f"[Info] Playwright 返回结果: {task_results}")

            # 提取所有返回的状态码
            codes = [item[1] for item in task_results]

            # Helper 函数：统一处理 Alas 重启（优先软重启，额度用尽则硬重启）
            def handle_alas_restart(reason_msg):
                nonlocal alas_soft_restart_count, alas_hard_restart_count

                if alas_soft_restart_count < max_soft_restarts:
                    print(
                        f"[Action] [{reason_msg}] 尝试第 {alas_soft_restart_count + 1} 次软重启 Alas (Playwright restart)..."
                    )
                    restart_ok, restart_results = zPlaywright.main(
                        headless=True,
                        task_list=["restart"],
                    )
                    restart_codes = [item[1] for item in restart_results]

                    if "0024" in restart_codes:
                        alas_soft_restart_count += 1
                        print("[Info] 软重启指令触发成功 [0024]，重新进入检查循环。")
                        return

                    print("[Warning] 软重启触发失败，将直接尝试硬重启 Alas...")

                # 软重启额度用尽或软重启失败，进入硬重启
                print(
                    f"[Action] [{reason_msg}] 尝试第 {alas_hard_restart_count + 1} 次硬重启 Alas (cleanup + start)..."
                )
                zAlas.cleanup()
                zAlas.start()
                alas_hard_restart_count += 1

            # 2. 检查是否有 0016 或 0017 (网页超时/无法访问)
            if "0016" in codes or "0017" in codes:
                print(
                    f"[Warning] 检测到页面无响应/无法访问状态码 ({[c for c in codes if c in ('0016', '0017')]})，触发 Alas 重启..."
                )
                handle_alas_restart("页面无法访问")
                continue

            # 3. 提取两次 check 任务的状态码 (分别对应索引 0 和 3)
            first_check_code = task_results[0][1] if len(task_results) > 0 else None
            second_check_code = task_results[3][1] if len(task_results) > 3 else None

            # 优先判定第一次 check：若检测到错误图标 (0026) -> 清理并重启 MuMu
            if first_check_code == "0026":
                print("[Warning] 第一次 Check 结果为 [0026] (检测到运行错误图标)，准备重启 MuMu...")
                zMumu.mumu_kill()
                zMumu.hidemumu()
                mumu_restart_count += 1
                continue

            # 校验第二次 check：若等待后再次检测到错误图标 (0026) -> 清理并重启 MuMu
            if second_check_code == "0026":
                print("[Warning] 第二次 Check 结果为 [0026] (检测到运行错误图标)，准备重启 MuMu...")
                zMumu.mumu_kill()
                zMumu.hidemumu()
                mumu_restart_count += 1
                continue

            # 4. 如果两次 Check 均正常 (均为 0027 或非 0026 异常) 且包含 0027
            if first_check_code == "0027" or second_check_code == "0027":
                print("[Success] Check 结果通过 (正常)，所有检查流程成功完成！")
                return True

            # 5. 未命中预期状态码，尝试软/硬重启 Alas 恢复
            print(
                f"[Warning] 未检测到明确的 0026 或 0027 状态码，当前状态码: {codes}，尝试重启 Alas..."
            )
            handle_alas_restart("未检测到有效状态码")

        except Exception as e:
            error_details = traceback.format_exc()
            print(f"[Error] 执行检查逻辑时发生未知异常: {e}\n{error_details}")
            PerseusErrorMsg("检查脚本运行异常", f"执行过程发生未捕获异常: {e}")

            # 遇到严重异常时进行 Alas 重启尝试恢复
            if alas_soft_restart_count < max_soft_restarts:
                try:
                    zPlaywright.main(headless=True, task_list=["restart"])
                    alas_soft_restart_count += 1
                except Exception:
                    zAlas.cleanup()
                    zAlas.start()
                    alas_hard_restart_count += 1
            else:
                zAlas.cleanup()
                zAlas.start()
                alas_hard_restart_count += 1

def Handlepush(msg_dict: dict):
    try:
        title = msg_dict.get("title", "")
        body = msg_dict.get("body", "")

        # 格式化接收到的原始推送文本，供后续拼接到 body 中
        raw_msg = f"\n[Original Push]\nTitle: {title}\nBody: {body}"

        print(f"\n[消息接收] 收到新推送通知 | 标题: 『{title}』")

        if "AzurPilot" in title:
            print("[状态检测] 判定为 AzurPilot 相关消息，正在解析...")

            # 1. 判定 body 或 title 中是否包含 "警告" 或 "崩溃"
            if "警告" in body or "崩溃" in body or "警告" in title or "崩溃" in title:
                print("[风险预警] 检测到运行异常状态！")

                if "自动重启" in body:
                    print(" -> 触发机制: 自动重启流程（轻度异常）")
                    PerseusNotifyMsg(
                        "Auto-restart Triggered",
                        f"AzurPilot is auto-restarting the game.{raw_msg}",
                    )

                elif (
                    "RequestHumanTakeover" in body
                    or "RequestHumanTakeover" in title
                ):
                    print(" -> 触发机制: 需要人工接管 (RequestHumanTakeover)")
                    PerseusWarningMsg(
                        "Human Takeover Requested",
                        f"AzurPilot requested human takeover. Attempting auto-recovery...{raw_msg}",
                    )

                    print("[执行动作] 调用 Alas & MuMu 检查恢复流程...")
                    if not run_alas_mumu_check():
                        print("[修复结果] ❌ 修复失败，需人工干预")
                        PerseusErrorMsg(
                            "Recovery Failed",
                            f"Auto-recovery failed. Manual intervention required.{raw_msg}",
                        )
                        return False
                    else:
                        print("[修复结果] 清除障碍，运行恢复正常！")
                        PerseusNotifyMsg(
                            "Recovery Successful",
                            f"AzurPilot issue resolved successfully.{raw_msg}",
                        )

                elif (
                    "EmulatorNotRunningError" in body
                    or "EmulatorNotRunningError" in title
                ):
                    print(" -> 触发机制: 模拟器未运行 (EmulatorNotRunningError)")
                    PerseusWarningMsg(
                        "Emulator Stopped",
                        f"Emulator error detected. Restarting emulator and checking status...{raw_msg}",
                    )

                    print("[执行动作] 清理并重启隐藏 MuMu 模拟器...")
                    zMumu.mumu_kill()
                    zMumu.hidemumu()
                    zPlaywright.main(task_list=["start"])

                    print("[执行动作] 调用 Alas & MuMu 检查恢复流程...")
                    if not run_alas_mumu_check():
                        print("[修复结果] ❌ 模拟器拉起/修复失败")
                        PerseusErrorMsg(
                            "Emulator Recovery Failed",
                            f"Failed to restart emulator. Manual intervention required.{raw_msg}",
                        )
                        return False
                    else:
                        print("[修复结果] 模拟器已成功拉起并修复！")
                        PerseusNotifyMsg(
                            "Emulator Recovered",
                            f"Emulator successfully restarted and running.{raw_msg}",
                        )
                elif (
                    "模拟器离线" in body
                    or "正在尝试重启模拟器" in body
                ):
                    """
                    AzurPilot <alas> 警告
                    <alas> 模拟器离线 - 正在尝试重启模拟器
                    """
                    print(" -> 触发机制:模拟器离线")
                    PerseusWarningMsg(
                        "Emulator offline",
                        f"Emulator error detected. Restarting emulator and checking status...{raw_msg}",
                    )

                    print("[执行动作] 清理并重启隐藏 MuMu 模拟器...")
                    zMumu.mumu_kill()
                    zMumu.hidemumu()
                    zPlaywright.main(task_list=["start"])

                    print("[执行动作] 调用 Alas & MuMu 检查恢复流程...")
                    if not run_alas_mumu_check():
                        print("[修复结果] ❌ 模拟器拉起/修复失败")
                        PerseusErrorMsg(
                            "Emulator Recovery Failed",
                            f"Failed to restart emulator. Manual intervention required.{raw_msg}",
                        )
                        return False
                    else:
                        print("[修复结果] 模拟器已成功拉起并修复！")
                        PerseusNotifyMsg(
                            "Emulator Recovered",
                            f"Emulator successfully restarted and running.{raw_msg}",
                        )

                else:
                    print(" -> 触发机制: 未知警告/错误")
                    PerseusWarningMsg(
                        "Unknown Error Detected",
                        f"Unexpected error detected. Attempting auto-recovery...{raw_msg}",
                    )

                    print("[执行动作] 调用 Alas & MuMu 检查恢复流程...")
                    if not run_alas_mumu_check():
                        print("[修复结果] ❌ 未知错误修复失败")
                        PerseusErrorMsg(
                            "Recovery Failed",
                            f"Failed to resolve unknown error. Please check system logs.{raw_msg}",
                        )
                        return False
                    else:
                        print("[修复结果] 异常已顺利排查！")
                        PerseusNotifyMsg(
                            "Recovery Successful",
                            f"Unknown error resolved successfully.{raw_msg}",
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
                            "Gems Obtained!",
                            f"Gems commission successful! Obtained Gems x{diamond_count}.{raw_msg}",
                        )
                    else:
                        print(" -> 解析成功: 获得钻石奖励（未匹配到具体数值）")
                        PerseusNotifyMsg(
                            "Gems Obtained!",
                            f"Gems commission successful!{raw_msg}",
                        )
                else:
                    print("[日常通知] 常规推送消息，原样转发")
                    PerseusNotifyMsg(title, f"{body}{raw_msg}")
        else:
            print("[未知通知] ，原样转发")
            PerseusNotifyMsg(title, f"{body}{raw_msg}")

        return True

    except Exception as e:
        # 捕捉 Handlepush 函数内部自身发生的任何脚本运行报错
        error_type = type(e).__name__
        error_detail = str(e)

        print("\n[💥 函数报错] Handlepush 执行过程中抛出异常！")
        print(f"错误类型: {error_type}")
        print(f"详细信息: {error_detail}")
        print("完整追踪日志:")
        traceback.print_exc()

        # 发送报错内容通知
        PerseusErrorMsg(
            f"Handlepush Script Error [{error_type}]",
            f"Error processing push message: {error_detail}\n\n[Original Push]\nTitle: {msg_dict.get('title', '')}\nBody: {msg_dict.get('body', '')}",
        )
        return False

def parse_task_list(arg):
    """
    将传入的 arg 解析并强转为包含字符串的 list
    """
    default_list = ["check", "start", "wait", "check", "update"]

    if not arg:
        return default_list

    # 1. 如果已经是 list，过滤确保元素全为 str
    if isinstance(arg, list):
        res = [str(x).strip() for x in arg if str(x).strip()]
        return res if res else default_list

    # 2. 如果是字符串，尝试解析
    if isinstance(arg, str):
        arg_str = arg.strip()
        # 尝试解析 JSON 格式的列表字符串，例如 '["check", "start"]'
        if arg_str.startswith("[") and arg_str.endswith("]"):
            try:
                parsed = json.loads(arg_str)
                if isinstance(parsed, list):
                    res = [str(x).strip() for x in parsed if str(x).strip()]
                    return res if res else default_list
            except Exception:
                pass

        # 否则按逗号/空格分隔处理，例如 "check, start, wait"
        res = [x.strip() for x in arg_str.replace(",", " ").split() if x.strip()]
        return res if res else default_list

    return default_list

def handlerun(data: dict):
    """
    用于处理 /run 收到的指令数据
    :data: 解析后的消息字典/数据结构
    :return: [bool, msg/result]
    """
    try:
        task = data.get("task", "")

        # 0. 特殊快捷任务：ikun -> 直接调用 run_alas_mumu_check()
        if "ikun" in task:
            res = run_alas_mumu_check()
            return [True, f"run_alas_mumu_check() -> {res}"]
        elif "admin" in task:
            res = zAlas.is_admin()
            return [True, f"zAlas.is_admin() -> {res}"]

        # 1. 处理 Alas 相关任务
        elif "alas" in task:
            if "kill" in task or "cleanup" in task:
                res = zAlas.cleanup()
                return [True, f"zAlas.cleanup() -> {res}"]
            elif "start" in task:
                res = zAlas.start()
                return [True, f"zAlas.start() -> {res}"]
            elif "restart" in task:
                res_cleanup = zAlas.cleanup()
                res_start = zAlas.start()
                return [True, f"zAlas.cleanup() -> {res_cleanup}, zAlas.start() -> {res_start}"]
            elif "hide" in task:
                res = zAlas.hide()
                return [True, f"zAlas.hide() -> {res}"]
            elif "online" in task:
                res = zAlas.is_site_accessible()
                return [True, f"zAlas.is_process_running() -> {res}"]

        # 2. 处理 MuMu 相关任务
        elif "mumu" in task:
            if "kill" in task:
                res = zMumu.mumu_kill()
                return [True, f"zMumu.mumu_kill() -> {res}"]
            elif "start" in task or "hide" in task:
                res = zMumu.hidemumu()
                return [True, f"zMumu.hidemumu() -> {res}"]
            elif "online" in task:
                res = zMumu.is_mumu_running()
                return [True, f"zMumu.is_mumu_running() -> {res}"]

        # 3. 处理 Playwright 相关任务（支持 playwright 和 pw）
        elif "playwright" in task or "pw" in task:
            arg = data.get("arg")
            task_list = parse_task_list(arg)

            res = zPlaywright.main(headless=True, task_list=task_list)
            return [True, f"zPlaywright.main(task_list={task_list}) -> {res}"]

        # 4. 处理 PGRJZ 相关任务（支持 pgrjz 和 pg）
        elif "pgrjz" in task or "pg" in task:
            res = zPGRJZ.run()
            return [True, f"zPGRJZ.run() -> {res}"]

    except Exception as e:
        error_type = type(e).__name__
        error_detail = str(e)
        print(f"\n[💥 函数报错] handlerun 执行过程中抛出异常！")
        print(f"错误类型: {error_type}")
        print(f"详细信息: {error_detail}")
        traceback.print_exc()
        return [False, f"Handlerun Error ({error_type}): {error_detail}"]

    return [False, f"Unknown Task: {data.get('task')}"]


if __name__ == "__main__":
    Handlepush({"title":"AzurPilot <alas> 委托获得顶级奖励喵！",
                "body":"本次获得钻石 * 20今.日累计: 20本周累计: 95本月累计: 20"})
