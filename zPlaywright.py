import json
import os
import re
import time
import urllib.request
from playwright.sync_api import expect, sync_playwright

from zBarkCustom import PerseusErrorMsg, PerseusWarningMsg
import zPerseusLogger


def is_site_accessible(url="http://127.0.0.1:22267"):
    """
    轻量级检查目标网页是否可访问
    """
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return response.status in (200, 301, 302, 401, 403)
    except Exception:
        return False


def wait_for_site_ready(url, max_wait_sec=180):
    """
    循环检查网页状态，在最长 3 分钟内等待网页在线。
    """
    if is_site_accessible(url):
        print("🌐 检测到 127.0.0.1:22267 已在线。")
        return True

    print("⌛ 未检测到网页服务在线，等待恢复中...")

    start_time = time.time()
    while time.time() - start_time < max_wait_sec:
        elapsed = int(time.time() - start_time)
        print(f"⏳ 正在等待网页响应...（已等待 {elapsed} 秒 / 最多 {max_wait_sec} 秒）")

        if is_site_accessible(url):
            print("🎉 检测到网页已恢复在线状态！")
            return True

        time.sleep(3)

    print("🚨 错误：已超过 3 分钟网页依然无响应，任务终止。")
    return False


def fix_and_load_storage(json_path):
    """
    读取并修正 auth.json 的格式问题，确保所有的 localStorage value 都是字符串。
    """
    if not os.path.exists(json_path):
        return None

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if "origins" in data:
            for origin in data["origins"]:
                if "localStorage" in origin:
                    for item in origin["localStorage"]:
                        if not isinstance(item.get("value"), str):
                            item["value"] = json.dumps(
                                item["value"], ensure_ascii=False
                            )

        return data
    except Exception as e:
        print(f"解析 auth.json 失败: {e}")
        return None


def handle_initial_notices(page):
    """
    初始弹窗处理：
    1. 检查并关闭公告弹窗
    2. 如果有新版本更新提示弹窗，点击【稍后再说】解除阻挡
    3. 屏蔽/注入 CSS 隐藏 Toastify 通知条（消除 pointer events 拦截）
    """
    # --- 1. 处理公告弹窗 ---
    confirm_regex = re.compile(r"确认|Confirm", re.I)
    title_regex = re.compile(r"QQ群|QQ\s*Group", re.I)

    modal_btn_with_id = page.locator(
        "#alas-announcement-modal button", has_text=confirm_regex
    )
    modal_btn_by_text = page.locator(
        "div", has=page.locator("h3", has_text=title_regex)
    ).locator("button", has_text=confirm_regex)

    try:
        target_btn = modal_btn_with_id.or_(modal_btn_by_text)
        target_btn.wait_for(state="visible", timeout=2000)
        target_btn.click()
        print("🎉 检测到公告弹窗，已点击【确认/Confirm】关闭！")
        page.wait_for_timeout(500)
    except Exception:
        pass

    announcement_modal = page.locator("#alas-announcement-modal")
    try:
        announcement_modal.wait_for(state="visible", timeout=2000)
        confirm_btn = announcement_modal.get_by_text("确认", exact=True)
        confirm_btn.click()
        announcement_modal.wait_for(state="hidden", timeout=2000)
        print("[弹窗处理] 公告弹窗已关闭")
    except Exception:
        pass

    # --- 2. 处理更新弹窗 -> 点击稍后再说 ---
    later_btn = page.locator(
        "#alas-update-notice button",
        has_text=re.compile(r"稍后再说|Later", re.I),
    )
    try:
        later_btn.wait_for(state="visible", timeout=3000)
        later_btn.click()
        print("📢 检测到更新提示弹窗，已点击【稍后再说】关闭。")
        page.wait_for_timeout(500)
    except Exception:
        pass

    # --- 3. 隐藏可能遮挡按钮的 Toast 浮窗 ---
    try:
        page.add_style_tag(
            content=".toastify { display: none !important; pointer-events: none !important; }"
        )
    except Exception:
        pass


def ensure_alas_overview(page):
    """
    检测当前页面顶部标题，如果是“主页”或“Home”，则点击侧边栏 #pywebio-scope-alas-instance-0 切换回总览
    """
    header_locator = page.locator("#pywebio-scope-header_title p")
    try:
        header_locator.wait_for(state="visible", timeout=3000)
        title_text = header_locator.text_content().strip()
        print(f"当前页面标题为: '{title_text}'")

        if title_text in ["主页", "Home"]:
            print("当前在主页/Home界面，正在点击 alas 实例图标跳转至总览界面...")
            instance_btn = page.locator(
                "#pywebio-scope-alas-instance-0 button.btn-aside"
            )
            instance_btn.wait_for(state="visible", timeout=5000)
            instance_btn.click(force=True)
            page.wait_for_timeout(1000)
            print("已成功切换回总览界面。")
    except Exception as e:
        print(f"确认总览界面时出现提示/异常(可能已在总览): {e}")


def handle_update_notice(page, target_url):
    """
    更新流程：
    1. 点击侧边栏【主页/Home】
    2. 点击菜单【更新器/Updater】
    3. 检查更新状态
    4. 返回【alas】实例页面
    返回格式: (success: bool, code: str, msg: str)
    """
    try:
        print("正在前往【主页】与【更新器】页面...")

        # 1. 点击侧边栏中的“主页”/“Home”
        aside_home_btn = page.locator(
            "#pywebio-scope-aside button.btn-aside",
            has_text=re.compile(r"主页|Home", re.I),
        )
        aside_home_btn.wait_for(state="visible", timeout=5000)
        aside_home_btn.click(force=True)
        page.wait_for_timeout(500)

        # 2. 点击菜单栏中的“更新器”/“Updater”
        menu_updater_btn = page.locator(
            "#pywebio-scope-menu button.btn-menu",
            has_text=re.compile(r"更新器|Updater", re.I),
        )
        menu_updater_btn.wait_for(state="visible", timeout=5000)
        menu_updater_btn.click(force=True)

        # 3. 检查更新页面状态
        updater_state = page.locator("#pywebio-scope-updater_state")
        updater_state.wait_for(state="visible", timeout=10000)
        state_text = updater_state.text_content().strip()
        print(f"当前更新状态信息: '{state_text}'")

        def back_to_alas():
            back_btn = page.locator(
                "#pywebio-scope-aside_instance button.btn-aside",
                has_text=re.compile(r"alas", re.I),
            )
            if back_btn.is_visible():
                back_btn.click(force=True)

        # 情况 A: 等待所有 AzurPilot 完成当前任务
        if re.search(r"等待所有\s*AzurPilot\s*完成当前任务", state_text, re.I):
            print("⌛ 检测到正在等待 AzurPilot 任务完成，无须再次点击更新。")
            back_to_alas()
            return True, "0018", "Update 检查完成：等待所有 AzurPilot 完成当前任务"

        # 情况 B: 已是最新版本
        if re.search(
            r"已是最新版本|Already the latest version", state_text, re.I
        ):
            print("✨ 已经是最新版本，无须更新。")
            back_to_alas()
            return True, "0019", "Update 检查完成：已是最新版本"

        # 情况 C: 有新版本可用 -> 点击进行更新
        if re.search(
            r"有新版本可用|A new version is available", state_text, re.I
        ) or page.locator("#pywebio-scope-updater_btn button").is_visible():
            start_update_btn = page.locator(
                "#pywebio-scope-updater_btn button",
                has_text=re.compile(r"进行更新|Update\s*Now|Update", re.I),
            )

            try:
                start_update_btn.wait_for(state="visible", timeout=5000)
                print("🚀 发现可更新版本，点击【进行更新】...")

                try:
                    start_update_btn.click(force=True)
                except Exception:
                    start_update_btn.evaluate("el => el.click()")

                updating_svg = page.locator("svg.aside-icon.icon-run-update-fly")
                try:
                    updating_svg.wait_for(state="visible", timeout=5000)
                    print("⏳ Alas 正在执行重启更新，等待响应中...")

                    reboot_timeout = 300
                    start_reboot_time = time.time()
                    reboot_success = False

                    while time.time() - start_reboot_time < reboot_timeout:
                        if is_site_accessible(target_url):
                            print("🎉 检测到 Alas 服务已成功重启在线！")
                            reboot_success = True
                            break
                        time.sleep(3)

                    if not reboot_success:
                        print("🚨 警告：更新后服务超时未重新在线！将直接尝试刷新页面...")

                    page.reload()
                    handle_initial_notices(page)
                    page.wait_for_load_state("networkidle")

                except Exception:
                    print("未检测到更新重启动画，常规等待 2 秒...")
                    page.wait_for_timeout(2000)

                back_to_alas()
                print("🔙 已点击返回 alas 实例界面。")
                return True, "0020", "Update 成功：已完成更新并返回 alas 界面"

            except Exception as btn_err:
                print(f"点击【进行更新】按钮出错: {btn_err}")
                back_to_alas()
                return True, "0021", "Update 检查完成：未能够成功点击更新按钮"

        back_to_alas()
        return True, "0022", f"Update 检查完成：当前更新状态为 [{state_text}]"

    except Exception as e:
        msg = f"Update 流程执行异常: {e}"
        print(f"⚠️ {msg}")
        return False, "0023", msg


def handle_restart_alas(page):
    """
    重启 Alas 流程：
    返回格式: (success: bool, code: str, msg: str)
    """
    try:
        print("正在前往【主页】与【开发者工具】页面...")
        aside_home_btn = page.locator(
            "#pywebio-scope-aside button.btn-aside",
            has_text=re.compile(r"主页|Home", re.I),
        )
        aside_home_btn.wait_for(state="visible", timeout=5000)
        aside_home_btn.click(force=True)
        page.wait_for_timeout(500)

        # 点击开发者工具
        menu_utils_btn = page.locator(
            "#pywebio-scope-menu button.btn-menu",
            has_text=re.compile(r"开发者工具|Utils", re.I),
        )
        menu_utils_btn.wait_for(state="visible", timeout=5000)
        menu_utils_btn.click(force=True)
        page.wait_for_timeout(500)

        # 点击 pywebio-scope-develop_detail 中的 "重启Alas" 按钮
        restart_btn = page.locator(
            "#pywebio-scope-develop_detail button",
            has_text=re.compile(r"重启Alas|Restart\s*Alas", re.I),
        )
        restart_btn.wait_for(state="visible", timeout=5000)
        restart_btn.click(force=True)
        print("🚀 已点击【重启Alas】按钮。")
        page.wait_for_timeout(2000)

        # 点击返回总览
        instance_btn = page.locator(
            "#pywebio-scope-alas-instance-0 button.btn-aside"
        )
        instance_btn.wait_for(state="visible", timeout=5000)
        instance_btn.click(force=True)
        print("🔙 已点击返回 alas 总览界面。")
        return True, "0024", "Restart 成功：已触发重启 Alas 并返回总览"
    except Exception as e:
        msg = f"Restart 流程执行异常: {e}"
        print(f"⚠️ {msg}")
        return False, "0025", msg


def check_error_status(page):
    """
    检查错误状态
    返回: (has_error: bool, code: str, msg: str)
    """
    error_svg = page.locator("svg.aside-icon.icon-run-error")
    try:
        error_svg.wait_for(state="visible", timeout=3000)
        print("🚨 检测到 Alas 处于运行错误状态 (icon-run-error)！")
        return True, "0026", "Check：检测到错误图标"
    except Exception:
        print("✨ 未检测到运行错误图标，状态正常。")
        return False, "0027", "Check：未发现错误图标"


def start_scheduler(page):
    """
    启动调度器逻辑
    返回: (success: bool, code: str, msg: str)
    """
    target_locator = page.locator("#pywebio-scope-scheduler_btn button")
    try:
        target_locator.wait_for(state="visible", timeout=5000)
        btn_text = target_locator.text_content().strip()
        print(f"当前主界面按钮状态为: '{btn_text}'")

        if btn_text.lower() in ["停止", "stop"]:
            print(f"当前状态为【{btn_text}】，无需点击。")
            return True, "0028", "Start 成功：调度器当前已处于运行中(停止状态)"
        elif btn_text.lower() in ["启动", "start"]:
            print("检测到状态为【启动/Start】，正在点击按钮...")
            target_locator.click(force=True)
            stop_btn_locator = page.locator(
                "#pywebio-scope-scheduler_btn button",
                has_text=re.compile(r"停止|stop", re.IGNORECASE),
            )
            try:
                stop_btn_locator.wait_for(state="visible", timeout=8000)
                print("👉 确认切换：检测到了【停止/stop】按钮！")
                return True, "0029", "Start 成功：已成功点击启动并切换状态"
            except Exception:
                msg = f"Start 失败：等待超时，状态未成功切换为停止。当前按钮文本: '{target_locator.text_content().strip()}'"
                print(f"⚠️ {msg}")
                PerseusWarningMsg("Scheduler Start Failed", "[0030]")
                return False, "0030", msg
        else:
            msg = f"Start 失败：未知按键状态 '{btn_text}'"
            print(msg)
            PerseusWarningMsg("Unknown Scheduler Button", f"[0031] 内容为{btn_text}")
            return False, "0031", msg
    except Exception as e:
        msg = f"Start 失败：操作启动按钮异常: {e}"
        print(msg)
        return False, "0032", msg


def main(
    headless: bool = True,
    task_list: list = None,
):
    """
    主控流程函数
    返回格式: [is_all_success: bool, task_results: list[list[bool, str, str]]]
    内部每一个子任务结果格式: [is_success: bool, code: str, msg: str]
    """
    if task_list is None:
        task_list = ["update", "check", "start"]

    target_url = "http://127.0.0.1:22267"

    if not wait_for_site_ready(target_url, max_wait_sec=300):
        return [False, [[False, "0016", "错误：已超过 5 分钟网页依然无响应，任务终止。"]]]

    task_results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)

        current_dir = os.path.dirname(os.path.abspath(__file__))
        auth_json_path = os.path.join(current_dir, "auth.json")

        storage_data = fix_and_load_storage(auth_json_path)
        if storage_data:
            print("正在加载登录凭证...")
            context = browser.new_context(storage_state=storage_data)
        else:
            print("❌ 未在同目录下找到有效 auth.json，将以默认状态打开...")
            context = browser.new_context()

        page = context.new_page()

        try:
            page.goto(target_url, timeout=30000)
        except Exception as load_err:
            print(f"🚨 打开网页超时或异常: {load_err}")
            browser.close()
            return [False, [[False, "0017", f"页面无法正常打开: {load_err}"]]]

        # 默认统一处理初始弹窗
        handle_initial_notices(page)

        # 顺序执行任务列表
        for task in task_list:
            ensure_alas_overview(page)

            if task == "update":
                print("--- 执行任务: update (检查与升级版本) ---")
                success, code, msg = handle_update_notice(page, target_url)
                task_results.append([success, code, msg])

            elif task == "check":
                print("--- 执行任务: check (错误图标检查) ---")
                detected_error, code, msg = check_error_status(page)
                # check 任务检测到错误图标代表其监测出异常
                task_results.append([not detected_error, code, msg])

            elif task == "start":
                print("--- 执行任务: start (启动调度器) ---")
                success, code, msg = start_scheduler(page)
                task_results.append([success, code, msg])

            elif task == "wait":
                print("--- 执行任务: wait (等待 10 秒并刷新界面) ---")
                try:
                    time.sleep(10)
                    page.reload(timeout=30000)
                    handle_initial_notices(page)
                    print("🎉 刷新成功并已清理弹窗。")
                    task_results.append(
                        [True, "0033", "Wait 成功：等待 10s 刷新完毕"]
                    )
                except Exception as wait_err:
                    msg = f"Wait 任务刷新异常: {wait_err}"
                    print(f"⚠️ {msg}")
                    task_results.append([False, "0034", msg])

            elif task == "restart":
                print("--- 执行任务: restart (在开发者工具中重启 Alas) ---")
                success, code, msg = handle_restart_alas(page)
                task_results.append([success, code, msg])

        if not headless:
            page.wait_for_timeout(2000)
        else:
            page.wait_for_timeout(200)

        browser.close()

    # 统计除了 check 之外的任务是否都成功（check 只作为信息收集，不阻断总体成功判定）
    non_check_success = all(
        item[0]
        for idx, item in enumerate(task_results)
        if task_list[idx] != "check"
    )

    return [non_check_success, task_results]


if __name__ == "__main__":
    result = main(
        headless=False,
        task_list=["check", "start", "wait","check","update"],
    )
    print("\n最终运行结果:")
    print(f"整体是否成功: {result[0]}")
    print(f"详细任务日志: {result[1]}")
