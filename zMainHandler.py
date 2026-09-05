import zPerseusLogger
import traceback
import zAlas
import zMumu
import zPlaywright
import zPGRJZ
import re
from zBarkCustom import PerseusErrorMsg, PerseusWarningMsg,PerseusNotifyMsg

def _md_original(title, body):
    """将原始推送附为 Markdown 代码块。"""
    title = title or ""
    body = body or ""
    raw_text = f"Title: {title}\nBody: {body}" if title and body else (title or body)
    return f"\n\n```text\n{raw_text}\n```"


def run_alas_mumu_check():
    """
    通用检查与恢复函数
    按 ["check", "start", "wait", "check", "update"] 顺序执行 Playwright 操作并根据返回状态自动恢复。
    """
    # 0. 初始检测：若 MuMu 未运行，则拉起并隐藏（不计数）
    if not zMumu.is_mumu_running():
        print("[Info] 检测到 MuMu 未运行")
    print("不管那么多了，先尝试隐藏再说")
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
                f"❌ **[严重错误]** 重启次数达到上限，已停止重试并清除进程。\n\n"
                f"- **Alas软重启:** `{alas_soft_restart_count}/{max_soft_restarts}`\n"
                f"- **Alas硬重启:** `{alas_hard_restart_count}/{max_hard_restarts}`\n"
                f"- **MuMu重启:** `{mumu_restart_count}/{max_mumu_restarts}`"
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
            PerseusErrorMsg("检查脚本运行异常", f"❌ **[运行异常]** 执行过程中发生未捕获异常：\n> `{e}`")

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

        raw_msg = _md_original(title, body)

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
                        f"🔄 **[自动重启]** **AzurPilot** 正在自动重启游戏...\n\n{raw_msg}",
                    )
                    print("保险起见，确保隐藏窗口先")
                    if not zMumu.hidemumu():
                        print("wtf,这也报错，为什么隐藏失败")
                        PerseusWarningMsg(
                            "Failed to hide mumu window",
                            f"⚠️ **[隐藏失败]** 尝试隐藏 MuMu 窗口失败，请检查模拟器状态。\n\n{raw_msg}",
                        )
                    else:
                        print("已确保窗口无问题")

                elif (
                    "RequestHumanTakeover" in body
                    or "RequestHumanTakeover" in title
                ):
                    print(" -> 触发机制: 需要人工接管 (RequestHumanTakeover)")
                    PerseusWarningMsg(
                        "Human Takeover Requested",
                        f"⚠️ **[接管请求]** AzurPilot 请求人工干预。\n\n> 🔄 **正在尝试自动恢复流程...**\n\n{raw_msg}",
                    )

                    print("[执行动作] 调用 Alas & MuMu 检查恢复流程...")
                    if not run_alas_mumu_check():
                        print("[修复结果] ❌ 修复失败，需人工干预")
                        PerseusErrorMsg(
                            "Recovery Failed",
                            f"❌ **[恢复失败]** 自动恢复流程已结束，但未能解决问题，需人工干预！\n\n{raw_msg}",
                        )
                        return False
                    else:
                        print("[修复结果] 清除障碍，运行恢复正常！")
                        PerseusNotifyMsg(
                            "Recovery Successful",
                            f"✅ **[恢复成功]** AzurPilot 问题已成功解决，恢复正常运行。\n\n{raw_msg}",
                        )

                elif (
                    "EmulatorNotRunningError" in body
                    or "EmulatorNotRunningError" in title
                ):
                    print(" -> 触发机制: 模拟器未运行 (EmulatorNotRunningError)")
                    PerseusWarningMsg(
                        "Emulator Stopped",
                        f"⚠️ **[模拟器异常]** 检测到模拟器停止运行，正在尝试重启并检查状态...\n\n{raw_msg}",
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
                            f"❌ **[恢复失败]** 模拟器自动拉起/修复失败，需人工干预。\n\n{raw_msg}",
                        )
                        return False
                    else:
                        print("[修复结果] 模拟器已成功拉起并修复！")
                        PerseusNotifyMsg(
                            "Emulator Recovered",
                            f"✅ **[模拟器恢复]** **Emulator** 已经成功重启并恢复运行。\n\n{raw_msg}",
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
                        f"⚠️ **[模拟器离线]** 检测到模拟器已离线，正在重新拉起...\n\n{raw_msg}",
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
                            f"❌ **[恢复失败]** 模拟器自动拉起/修复失败，需人工干预。\n\n{raw_msg}",
                        )
                        return False
                    else:
                        print("[修复结果] 模拟器已成功拉起并修复！")
                        PerseusNotifyMsg(
                            "Emulator Recovered",
                            f"✅ **[模拟器恢复]** **Emulator** 已经成功重启并恢复运行。\n\n{raw_msg}",
                        )

                else:
                    print(" -> 触发机制: 未知警告/错误")
                    PerseusWarningMsg(
                        "Unknown Error Detected",
                        f"⚠️ **[未知异常]** 检测到非预期错误，正在尝试通用的自动恢复流程...\n\n{raw_msg}",
                    )

                    print("[执行动作] 调用 Alas & MuMu 检查恢复流程...")
                    if not run_alas_mumu_check():
                        print("[修复结果] ❌ 未知错误修复失败")
                        PerseusErrorMsg(
                            "Recovery Failed",
                            f"❌ **[恢复失败]** 无法自动解决该未知错误，请手动检查日志。\n\n{raw_msg}",
                        )
                        return False
                    else:
                        print("[修复结果] 异常已顺利排查！")
                        PerseusNotifyMsg(
                            "Recovery Successful",
                            f"✅ **[恢复成功]** **Unknown error** 已经排查并解决成功。\n\n{raw_msg}",
                        )

            else:
                if "顶级奖励" in title or "钻石" in body:
                    print("Good News!💎红尖尖委托大成功！")
                    match = re.search(r"本次获得钻石\s*\*\s*(\d+)", body)
                    if match:
                        diamond_count = match.group(1)
                        print(f" -> 解析成功: 获得钻石 * {diamond_count}")
                        PerseusNotifyMsg(
                            "Gems Obtained!",
                            f"💎 **[委托大成功]** **Gems commission successful!**\n\n- **获得奖励**: 💎 `x{diamond_count}`",
                        )
                    else:
                        print(" -> 解析成功: 获得钻石奖励（未匹配到具体数值）")
                        PerseusNotifyMsg(
                            "Gems Obtained!",
                            f"💎 **[委托大成功]** **Gems commission successful!**\n\n{raw_msg}",
                        )

                # 2. 判定行动力数值变化通知
                elif "行动力出现变化" in title or ("行动力" in title and ("下跌" in body or "上涨" in body)):
                    print("[AP Update] 收到行动力变化通知")
                    # 匹配格式: 总行动力: 1976 下跌79行动力 或 总行动力: 1369 上涨141行动力
                    match = re.search(r"总行动力:\s*(\d+)\s*(上涨|下跌)\s*(\d+)行动力", body)
                    if match:
                        total_ap = match.group(1)
                        direction = match.group(2)
                        change_amount = match.group(3)
                        symbol = "-" if direction == "下跌" else "+"

                        notify_title = f"⚡ 行动力变化 ({symbol}{change_amount})"
                        notify_body = (
                            f"⚡ **[AP 状态更新]**\n"
                            f"- **当前总行动力**: `{total_ap}`\n"
                            f"- **变动明细**: 较上次{direction} `{change_amount}` AP\n\n"
                            f"{raw_msg}"
                        )

                        print(f" -> 解析成功: 总AP {total_ap}, {direction} {change_amount}")
                        PerseusNotifyMsg(notify_title, notify_body)
                    else:
                        print(" -> 行动力变化未精确匹配，发送默认格式")
                        PerseusNotifyMsg("⚡ 行动力出现变化", f"{body}\n\n{raw_msg}")

                # 3. 判定行动力不足 / 低于最低保留通知
                elif "行动力不足" in title or "低于最低保留" in title or "行动力不足" in body or "低于最低保留" in body:
                    print("[AP Alert] 收到行动力不足/推迟任务通知")
                    # 匹配格式: 总行动力 428 低于最低保留 500，推迟任务 / 已推迟任务
                    match = re.search(r"总行动力\s*(\d+)\s*低于最低保留\s*(\d+)[，,]?\s*(.*)", body)
                    if match:
                        total_ap = match.group(1)
                        min_reserve = match.group(2)
                        action_taken = match.group(3).strip()

                        notify_title = "⚠️ 行动力低于最低保留"
                        notify_body = (
                            f"⚠️ **[行动力不足预警]**\n"
                            f"- **当前总行动力**: `{total_ap}`\n"
                            f"- **最低保留限额**: `{min_reserve}`\n"
                            f"- **已采取操作**: {action_taken}"
                        )

                        print(f" -> 解析成功: 当前AP={total_ap}, 保留上限={min_reserve}, 处置={action_taken}")
                        PerseusNotifyMsg(notify_title, notify_body)
                    else:
                        print(" -> 低于保留值未精确匹配，发送默认通知")
                        PerseusNotifyMsg("⚠️ 行动力低于最低保留", f"{body}\n\n{raw_msg}")

                # 4. 判定舰船经验检测报告
                elif "舰船经验检测报告" in title:
                    print("[EXP Report] 收到舰船经验检测报告")
                    fleet_match = re.search(r"检测舰队:\s*(.+)", body)
                    unfilled_match = re.search(r"未满经验舰位:\s*(\d+)\s*艘", body)

                    fleet_name = fleet_match.group(1).strip() if fleet_match else "未知舰队"
                    unfilled_count = unfilled_match.group(1) if unfilled_match else "0"

                    # 提取各个舰位未满船只的情况
                    ship_matches = re.findall(
                        r"舰位(\d+):\s*(Lv\.\d+)\s*\|\s*经验：([^\|]+)\s*\|\s*进度：([^│\|]+)\s*│\s*预计时间：([^\n]+)",
                        body
                    )

                    details = []
                    for pos, lv, exp, progress, eta in ship_matches:
                        progress_clean = progress.strip()
                        if progress_clean != "已满":
                            details.append(f"  • **舰位 {pos}** (`{lv}`): 进度 `{progress_clean}` | ⏱️ 预计剩余 `{eta.strip()}`")

                    detail_text = "\n".join(details) if details else "  • ✨ 全员经验已满"

                    notify_title = f"📊 经验检测报告 ({fleet_name})"
                    notify_body = (
                        f"📊 **[舰船经验检测报告]**\n"
                        f"- **检测舰队**: `{fleet_name}`\n"
                        f"- **未满经验舰位**: `{unfilled_count}` 艘\n\n"
                        f"**详细进度**: \n{detail_text}"
                    )

                    print(f" -> 解析成功: 舰队={fleet_name}, 未满={unfilled_count}艘")
                    PerseusNotifyMsg(notify_title, notify_body)

                # 5. 判定常规任务完成/成功（如月度Boss、重启设置等）
                elif "成功" in title or "成功" in body:
                    print("[Task Complete] 收到任务完成通知")
                    has_warning = "有可恢复错误" in title or "有可恢复错误" in body

                    # 尝试匹配任务名称: 任务 月度Boss ——成功
                    task_match = re.search(r"任务\s*([^\s—–-]+)", body)
                    if not task_match:
                        task_match = re.search(r"<alas>\s*([^\s—–-]+)\s*成功", title)

                    task_name = task_match.group(1).strip() if task_match else "自动化任务"

                    status_str = "成功 (存在待关注的可恢复错误)" if has_warning else "顺利完成"
                    icon = "⚠️" if has_warning else "✅"

                    notify_title = f"{icon} 任务完成: {task_name}"
                    notify_body = (
                        f"📌 **[任务执行报告]**\n"
                        f"- **任务名称**: `{task_name}`\n"
                        f"- **执行状态**: {status_str}"
                    )

                    print(f" -> 解析成功: 任务={task_name}, 存在警告={has_warning}")
                    PerseusNotifyMsg(notify_title, notify_body)

                # 6. 常规未特殊匹配消息，原样转发
                else:
                    print("[日常通知] 常规推送消息，原样转发")
                    PerseusNotifyMsg(title, f"{body}")
        else:
            print("[未知通知] ，原样转发")
            PerseusNotifyMsg(title, f"{body}")

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
            f"❌ **[推送处理异常]** 处理消息时发生错误：\n> `{error_detail}`\n\n**原始消息：**\n- **标题:** {msg_dict.get('title', '')}\n- **内容:** {msg_dict.get('body', '')}",
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
                res = zAlas.is_process_running()
                return [True, f"zAlas.is_process_running() -> {res}"]
            elif "ping" in task:
                res = zAlas.is_site_accessible()
                return [True, f"zAlas.is_site_accessible() -> {res}"]

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