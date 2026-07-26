import json
import os
import re
from playwright.sync_api import sync_playwright

def run():
    auth_file = 'pgrjzauth.json'

    VIEW_WIDTH = 380
    VIEW_HEIGHT = 750

    with sync_playwright() as p:
        iphone_config = {
            'user_agent': (
                'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
                'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'
            ),
            'viewport': {'width': VIEW_WIDTH, 'height': VIEW_HEIGHT},
            'device_scale_factor': 2,
            'is_mobile': True,
            'has_touch': True,
        }

        browser = p.chromium.launch(
            headless=False,
            args=[
                '--window-size=380,800',
                '--force-device-scale-factor=1',
            ]
        )

        has_auth = os.path.exists(auth_file)
        if not has_auth:
            print("未检测到历史凭证！")
            browser.close()
            return

        context = browser.new_context(
            **iphone_config,
            storage_state=auth_file
        )

        context.add_init_script("""
            Object.defineProperty(window.navigator, 'standalone', {
                get: () => true
            });
        """)

        page = context.new_page()

        def navigate_to_points():
            print("正在打开主页 https://www.iios.fun/ ...")
            page.goto('https://www.iios.fun/', wait_until='domcontentloaded')
            page.wait_for_timeout(1000)
            
            print("正在跳转至签到页面 https://www.iios.fun/#/points ...")
            page.goto("https://www.iios.fun/#/points", wait_until='domcontentloaded')

        try:
            # 1. 打开主页与积分页
            navigate_to_points()

            # 2. 等待签到页面关键元素加载完成
            page.wait_for_selector("text=每日签到", timeout=10000)

            # 精确定位“立即签到”这个独立的 DOM 按钮
            btn_sign_in = page.locator(".fPDpFDzb", has_text="立即签到")
            text_completed = page.get_by_text("已完成")

            # 3. 判断签到状态：如果已经没有“立即签到”按钮或显示“已完成”
            if not btn_sign_in.is_visible() or text_completed.is_visible():
                print("【结果】检测到当前已显示『已完成/已签到』，无需重复签到！")
            else:
                print("检测到未签到，正在精准触发点击【立即签到】...")

                # 确保元素可见并滚动到视角
                btn_sign_in.scroll_into_view_if_needed()
                page.wait_for_timeout(500)

                # 优先尝试 tap，失败则尝试 JS 原生 click
                try:
                    btn_sign_in.tap(force=True, timeout=2000)
                except Exception:
                    pass

                # JS 触发 Vue 绑定的原生 click 事件
                btn_sign_in.evaluate("el => el.click()")

                print("已触发点击，停顿 3 秒供观察页面响应...")
                page.wait_for_timeout(3000)

                # 4. 二次验证：重新按照标准流程重新载入页面
                print("重新按照标准流程重新载入页面，确认真实后台签到数据...")
                navigate_to_points()
                page.wait_for_selector("text=每日签到", timeout=10000)

                # 重新校验“立即签到”按钮是否存在/是否变为“已完成”
                btn_sign_in_re = page.locator(".fPDpFDzb", has_text="立即签到")
                if not btn_sign_in_re.is_visible() or page.get_by_text("已完成").is_visible():
                    print("【结果】签到成功！界面已更新为『已完成』状态。")
                else:
                    print("【警告】未检测到状态更新。请检查登录 Cookie 是否有效或是否有弹窗拦截。")

            print("处理完成，保持界面 5 秒后自动退出...")
            page.wait_for_timeout(5000)

        except Exception as e:
            print(f"运行过程中发生异常: {e}")

        finally:
            browser.close()

if __name__ == '__main__':
    run()
