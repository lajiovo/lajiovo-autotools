import json
import os
import re
import time
import urllib.request
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright

# 导入您写好的 alas 启动模块与 Mumu 管理模块
from zAlas import alas_start ,alas_cleanup
from zMumu import hidemumu, mumu_kill


def is_site_accessible(url):
    """
    轻量级检查目标网页是否可访问
    """
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return response.status in (200, 301, 302, 401, 403)
    except Exception:
        return False


def wait_for_site_ready(url, max_wait_sec=300):
    """
    循环检查网页状态。如果未启动则调用 alas_start()，并在最长 5 分钟内等待恢复。
    """
    if is_site_accessible(url):
        print("🌐 检测到 127.0.0.1:22267 已在线，无需额外启动。")
        return True

    print("❌ 未检测到网页服务，正在调用 alas_start() 启动后台程序...")
    alas_start()

    start_time = time.time()
    while time.time() - start_time < max_wait_sec:
        elapsed = int(time.time() - start_time)
        print(f"⏳ 正在等待网页响应...（已等待 {elapsed} 秒 / 最多 300 秒）")

        if is_site_accessible(url):
            print("🎉 检测到网页已恢复在线状态！")
            return True

        time.sleep(5)

    print("🚨 错误：已超过 5 分钟网页依然无响应，任务终止。")
    alas_cleanup()
    print("🚨 警告,结束了azurpilot进程")
    mumu_kill()
    print("🚨 警告,结束了mumu进程")
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


def handle_announcement_modal(page):
    """
    1. 检查并处理可能出现的公告弹窗（宽判中英文）
    """
    # 宽判匹配：“确认” 或 “Confirm”
    confirm_regex = re.compile(r"确认|Confirm", re.I)
    # 宽判匹配标题：“QQ群” 或 “QQ Group” / “QQ”
    title_regex = re.compile(r"QQ群|QQ\s*Group", re.I)

    # 策略 1：带 ID 的传统定位
    modal_btn_with_id = page.locator("#alas-announcement-modal button", has_text=confirm_regex)

    # 策略 2：不带 ID，通过标题反向定位按钮
    modal_btn_by_text = (
        page.locator("div", has=page.locator("h3", has_text=title_regex))
        .locator("button", has_text=confirm_regex)
    )

    try:
        print("正在检查是否有公告弹窗...")
        target_btn = modal_btn_with_id.or_(modal_btn_by_text)
        target_btn.wait_for(state="visible", timeout=2000)
        target_btn.click()
        print("🎉 检测到公告弹窗，已点击【确认/Confirm】关闭！")
        page.wait_for_timeout(500)
    except Exception:
        print(" 没有检测到公告弹窗，继续。")


def handle_update_notice(page, target_url):
    """
    2. 检查并执行更新流程（包含对更新重启重载页面的检测，宽判中英文）
    """
    update_notice = page.locator("#alas-update-notice")
    
    # 宽判匹配：“立即更新” 或 “Update Now”
    update_btn = page.locator("#alas-update-notice button", has_text=re.compile(r"立即更新|Update\s*Now", re.I))

    try:
        print("正在检查是否有新版本更新提示...")
        update_notice.wait_for(state="visible", timeout=2000)
        print("📢 发现新版本更新提示！正在点击【立即更新/Update Now】...")
        update_btn.click()

        # 进入更新页面，等待状态显示
        updater_state = page.locator("#pywebio-scope-updater_state")
        updater_state.wait_for(state="visible", timeout=5000)
        print(f"当前更新页面状态: {updater_state.text_content().strip()}")

        # 宽判匹配：“进行更新” 或 “Run Update” 或 “Update”
        start_update_btn = page.locator(
            "#pywebio-scope-updater_btn button", 
            has_text=re.compile(r"进行更新|Run\s*Update|Update", re.I)
        )
        start_update_btn.wait_for(state="visible", timeout=3000)
        start_update_btn.click()
        print("🚀 已点击【进行更新/Run Update】，开始检测是否启动更新重启...")

        updating_svg = page.locator("svg.aside-icon.icon-run-update-fly")

        try:
            updating_svg.wait_for(state="visible", timeout=3000)
            print("⏳ 检测到更新动画 SVG (icon-run-update-fly)，Alas 正在执行重启更新...")
            page.wait_for_timeout(3000)

            reboot_timeout = 300
            start_reboot_time = time.time()
            reboot_success = False

            while time.time() - start_reboot_time < reboot_timeout:
                elapsed = int(time.time() - start_reboot_time)
                if is_site_accessible(target_url):
                    print(f"🎉 经过 {elapsed} 秒，检测到 Alas 服务已成功重启在线！")
                    reboot_success = True
                    break
                print(f"  └─ 正在等待后台服务重启中...（已等待 {elapsed} 秒）")
                time.sleep(3)

            if not reboot_success:
                print("🚨 警告：更新后服务超时未重新在线！将直接尝试刷新页面...")

            print("🔄 正在刷新页面以重载页面状态...")
            page.reload()
            page.wait_for_load_state("networkidle")

        except Exception:
            print(" 未检测到更新重启动画，进行常规等待 3 秒。")
            page.wait_for_timeout(3000)

        # 返回 alas 主界面（宽判匹配：不区分大小写的 "alas"）
        back_to_alas_btn = page.locator("button.btn-aside", has_text=re.compile(r"alas", re.I))
        back_to_alas_btn.wait_for(state="visible", timeout=5000)
        back_to_alas_btn.click()
        print("🔙 已点击返回 alas 主界面。")
        page.wait_for_timeout(1000)

    except Exception as e:
        print(f" 未检测到更新提示、无需更新或执行出错: {e}")


def check_mumu_kill_interval(current_dir):
    """
    检查同目录下 latest_mumu_kill.txt 记录的时间是否超过2天。
    """
    record_file = os.path.join(current_dir, "latest_mumu_kill.txt")
    time_format = "%Y-%m-%d %H:%M:%S"
    now = datetime.now()

    if os.path.exists(record_file):
        try:
            with open(record_file, "r", encoding="utf-8") as f:
                last_time_str = f.read().strip()
            last_time = datetime.strptime(last_time_str, time_format)
            
            if now - last_time >= timedelta(days=2):
                print(f"🕒 上次执行 mumu_kill 时间为 {last_time_str}，已超过 2 天。")
                need_kill = True
            else:
                print(f"🕒 上次执行 mumu_kill 时间为 {last_time_str}，未满 2 天，略过重启 MuMu。")
                need_kill = False
        except Exception as e:
            print(f"⚠️ 解析记录文件失败（格式有误），将默认执行重启: {e}")
            need_kill = True
    else:
        print("📄 未检测到 latest_mumu_kill.txt 历史记录，将执行首次重启记录。")
        need_kill = True

    if need_kill:
        try:
            with open(record_file, "w", encoding="utf-8") as f:
                f.write(now.strftime(time_format))
        except Exception as e:
            print(f"⚠️ 写入 latest_mumu_kill.txt 失败: {e}")
            
    return need_kill


def check_and_start(page, current_dir):
    """
    3. 检查异常错误状态与按钮状态，并执行启动（宽判中英文按钮状态）
    """
    error_svg = page.locator("svg.aside-icon.icon-run-error")
    erroricon = False
    
    try:
        error_svg.wait_for(state="visible", timeout=2000)
        print("🚨 检测到 Alas 处于运行错误状态 (icon-run-error)！")
        erroricon = True
        
        if check_mumu_kill_interval(current_dir):
            print("💀 触发 Mumu 重启逻辑，正在执行 mumu_kill()...")
            mumu_kill()
            page.wait_for_timeout(2000)
            print("🖥️ 正在调用 hidemumu() 重新隐藏/拉起...")
            hidemumu()
            page.wait_for_timeout(20000)
        
    except Exception:
        print("✨ 未检测到运行错误图标，状态正常。")
        erroricon = False

    # 检测并启动
    target_locator = page.locator("#pywebio-scope-scheduler_btn button")
    try:
        target_locator.wait_for(state="visible", timeout=5000)
        btn_text = target_locator.text_content().strip()
        print(f"当前主界面按钮状态为: '{btn_text}'")

        # 宽判支持：匹配 "启动" 或 "Start" (不区分大小写)
        if btn_text.lower() in ["启动", "Start"]:
            print("检测到状态为【启动/Start】，正在点击按钮...")
            target_locator.click()
            print("👉 已成功点击启动！")
        else:
            print(f"当前状态为【{btn_text}】，无需点击。")

    except Exception as e:
        print(f"操作启动按钮失败，原因: {e}")
    return erroricon


def main(headless: bool = False):
    """
    主控流程函数
    :param headless: 是否采用无头模式（后台打开浏览器）。True 为后台静默运行，False 为显示浏览器界面。
    """
    target_url = "http://127.0.0.1:22267"
    errorcount = 0
    errorsolved = True
    while True:
        if not wait_for_site_ready(target_url, max_wait_sec=300):
            return

        with sync_playwright() as p:
            # 🌟 核心：通过参数 headless 决定是否在后台静默运行
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
            page.goto(target_url)

            # 1. 处理公告
            handle_announcement_modal(page)

            # 2. 检查更新流程
            handle_update_notice(page, target_url)

            # 3. 检查错误状态并检查启动
            if check_and_start(page, current_dir):
                print("大概是有什么错误，让我们等一下吧,10s")
                errorcount += 1
                page.wait_for_timeout(10000)
                if check_and_start(page, current_dir) :
                    print("看起来还是不行欸，让我们重启alas试试吧")
                    errorcount += 1
                    alas_cleanup()
                    if errorcount <= 2 :
                        print("将再次进入main循环")
                    else: 
                        print("我们放弃吧")
                        errorsolved = False
                        break
                else:
                    break
            else:
                print("Great! Now we skip checking again.")
                break

            if not headless :
                page.wait_for_timeout(2000)
            else:
                page.wait_for_timeout(200)
            browser.close()
    return errorsolved

if __name__ == "__main__":
    # 如果想在后台静默运行，传入 True 即可：main(headless=True)
    main(headless=True)