import asyncio
from pathlib import Path
from playwright.async_api import async_playwright
from zConfig import get_config

async def run():
    current_dir = Path(__file__).parent.resolve()
    user_data_dir = current_dir / "brocache"
    
    # 确保下载目录为绝对路径并自动创建，防止因目录不存在导致下载失败
    download_dir = current_dir / "browser_downloads"
    download_dir.mkdir(parents=True, exist_ok=True)
    
    # 针对 1920x1080 (125% 缩放) 的精准计算：
    # 0.8 倍窗口尺寸 = 1536 x 864
    win_w, win_h = 1536, 864
    pos_x, pos_y = 192, 108
    
    # 扣除浏览器顶部标签栏+地址栏（约 80px），锁定网页实际可视区域
    view_w, view_h = win_w, win_h - 80

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=False,
            args=[
                f"--window-size={win_w},{win_h}",
                f"--window-position={pos_x},{pos_y}",
                "--force-device-scale-factor=1",  # 关键修复：强制忽略 Windows 的 125% DPI 缩放
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--ignore-certificate-errors",
                "--disable-ssl-trace"
            ],
            ignore_default_args=["--enable-automation"],
            viewport={"width": view_w, "height": view_h},  # 显式锁死视口，不再使用 None 让系统滥算
            proxy={
                "server": get_config("proxy.socks")
            },
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            device_scale_factor=1,
            is_mobile=False,
            has_touch=False,
            locale="zh-CN",
            extra_http_headers={
                "Accept-Language": "zh-CN,zh;q=0.9,ja;q=0.8,en;q=0.7"
            },
            timezone_id="Asia/Tokyo",
            geolocation={"latitude": 35.6762, "longitude": 139.6503},
            # 添加了剪切板读取和写入权限，开启剪切板穿透
            permissions=["geolocation", "clipboard-read", "clipboard-write"],
            accept_downloads=True,  # 显式允许文件下载
            downloads_path=str(download_dir)
        )

        # 注入 JavaScript 防检测脚本
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        page = context.pages[0] if context.pages else await context.new_page()

        try:
            await page.goto("https://gemini.google.com/", wait_until="domcontentloaded", timeout=60000)
            print(f"已成功打开 Gemini，已针对 125% 缩放校准视口，输入框已恢复显示。剪切板穿透权限已生效。")
        except Exception as e:
            print(f"打开页面失败，请检查代理节点连通性: {e}")

        close_event = asyncio.Event()
        context.on("close", lambda _: close_event.set())
        await close_event.wait()

if __name__ == "__main__":
    asyncio.run(run())