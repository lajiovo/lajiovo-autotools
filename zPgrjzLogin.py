"""
运行这个代码来登入你的pgrjz账号
"""
import json
import os
from playwright.sync_api import sync_playwright

def run():
    auth_file = 'pgrjzauth.json'

    # 定义 iPhone 15 的原始逻辑分辨率
    IPHONE_WIDTH = 430
    IPHONE_HEIGHT = 932
    # 缩放比例 (0.75 缩放后高度约为 699px，适合 800px 高度的窗口)
    SCALE = 0.75 

    with sync_playwright() as p:
        # 1. 配置基础参数
        iphone_15_config = {
            'user_agent': (
                'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
                'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'
            ),
            'viewport': {'width': IPHONE_WIDTH, 'height': IPHONE_HEIGHT},
            'device_scale_factor': 3,
            'is_mobile': True,
            'has_touch': True,
        }

        # 2. 启动浏览器：窗口高度固定为 800
        # 宽度设为 380px 左右，配合 0.75 的缩放效果最佳
        browser = p.chromium.launch(
            headless=False,
            args=[
                '--window-size=380,800',
                '--force-device-scale-factor=1', # 保持 PC 桌面缩放一致
            ]
        )

        # 自动读取历史 auth 凭证
        has_auth = os.path.exists(auth_file)
        storage_state_arg = auth_file if has_auth else None
        
        if has_auth:
            print(f"检测到已有凭证，正在从 '{auth_file}' 自动加载登录状态...")
        else:
            print("未检测到历史凭证，本次运行后将在退出时自动保存登录状态。")

        context = browser.new_context(
            **iphone_15_config,
            storage_state=storage_state_arg
        )

        # 3. 注入模拟 iOS standalone (Web App) 标识
        context.add_init_script("""
            Object.defineProperty(window.navigator, 'standalone', {
                get: () => true
            });
        """)

        page = context.new_page()

        # 4. 通过 CDP 实现等比缩小渲染与 standalone 模式
        cdp_session = context.new_cdp_session(page)
        
        # 4.1 开启 display-mode: standalone
        cdp_session.send('Emulation.setEmulatedMedia', {
            'features': [{'name': 'display-mode', 'value': 'standalone'}]
        })

        # 4.2 核心：等比缩放移动端视口以完全放入 800px 高度的窗口中
        cdp_session.send('Emulation.setDeviceMetricsOverride', {
            'width': IPHONE_WIDTH,
            'height': IPHONE_HEIGHT,
            'deviceScaleFactor': 3,
            'mobile': True,
            'scale': SCALE,  # 0.75 倍等比缩放
        })

        try:
            print("正在打开 https://iios.fun ...")
            page.goto('https://iios.fun')

            print("\n==================================================")
            print(f"已应用 800px 窗口高度 + {int(SCALE*100)}% 等比缩放模式。")
            print("页面与底部按钮现已完全缩放并展示在窗口内。")
            print("关闭窗口或按 Ctrl+C 将自动保存/更新凭证。")
            print("==================================================\n")

            # 等待窗口关闭
            page.wait_for_event('close', timeout=0)

        except Exception:
            pass

        finally:
            # 5. 退出时提取并保存 Cookie / LocalStorage
            print(f"\n正在保存登录凭证至 '{auth_file}' ...")
            try:
                state = context.storage_state()
                with open(auth_file, 'w', encoding='utf-8') as f:
                    json.dump(state, f, ensure_ascii=False, indent=2)
                print("凭证已成功保存。")
            except Exception as e:
                print(f"保存凭证失败: {e}")

            browser.close()

if __name__ == '__main__':
    run()
