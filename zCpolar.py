import json
import asyncio
from typing import List, Optional
from playwright.async_api import async_playwright, Page, BrowserContext, Browser

# ================= 核心工具函数 =================

async def _init_browser(auth_file: str, name: str):
    """内部辅助函数：初始化浏览器并注入身份凭据"""
    headless = (name != "main")
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=headless)
    context = await browser.new_context()
    page = await context.new_page()

    try:
        with open(auth_file, "r", encoding="utf-8") as f:
            auth_data = json.load(f)
            if isinstance(auth_data, list):
                await context.add_cookies(auth_data)
            elif isinstance(auth_data, dict):
                if "cookies" in auth_data:
                    await context.add_cookies(auth_data["cookies"])
                if "origins" in auth_data:
                    await context.add_init_script(f"""
                        const storage = {json.dumps(auth_data)};
                        if (storage.origins) {{
                            storage.origins.forEach(o => {{
                                o.localStorage.forEach(item => {{
                                    localStorage.setItem(item.name, item.value);
                                }});
                            }});
                        }}
                    """)
    except Exception as e:
        print(f"[Warning] 加载凭据文件 {auth_file} 失败或文件不存在: {e}")

    return playwright, browser, context, page

async def _wait_loading(page: Page, timeout: int = 10000):
    """内部辅助函数：等待 Element UI loading 遮罩消失"""
    mask = page.locator(".el-loading-mask")
    if await mask.count() > 0:
        await mask.first.wait_for(state="hidden", timeout=timeout)

async def _close_browser(playwright, browser, context):
    """内部辅助函数：关闭浏览器环境"""
    if context:
        await context.close()
    if browser:
        await browser.close()
    if playwright:
        await playwright.stop()


# ================= 业务独立函数 =================

async def query_public_urls(
    auth_file: str = "cpauth.json", 
    name: str = "worker", 
    proto_filter: Optional[str] = None,
    base_url: str = "http://127.0.0.1:9200"
) -> List[str]:
    """
    【独立函数】单纯查询公网地址列表
    :param auth_file: 凭据路径
    :param name: 为 'main' 时不隐藏界面 (headless=False)
    :param proto_filter: 协议过滤，可选 'http' / 'https' / 'tcp'，传 None 返回全部
    :param base_url: cpolar 本地控制台地址
    :return: 公网 URL 字符串列表
    """
    playwright, browser, context, page = await _init_browser(auth_file, name)
    urls = []
    try:
        await page.goto(f"{base_url.rstrip('/')}/#/status/online")
        await _wait_loading(page)

        # 检查是否为 No Data 空列表
        if not await page.locator(".el-table__empty-block").is_visible():
            rows = page.locator(".el-table__body-wrapper tbody tr.el-table__row")
            count = await rows.count()

            for i in range(count):
                row = rows.nth(i)
                cols = row.locator("td")
                url = (await cols.nth(2).inner_text()).strip()
                proto = (await cols.nth(3).inner_text()).strip().lower()

                if proto_filter is None or proto == proto_filter.lower():
                    urls.append(url)
    finally:
        await _close_browser(playwright, browser, context)

    return urls


async def start_tunnel(
    auth_file: str = "cpauth.json", 
    name: str = "worker", 
    wait_online: bool = True,
    base_url: str = "http://127.0.0.1:9200"
) -> bool:
    """
    【独立函数】启动隧道
    :param wait_online: 是否在启动后自动确认公网地址上线
    :return: 启动成功或已被点击返回 True
    """
    playwright, browser, context, page = await _init_browser(auth_file, name)
    success = False
    try:
        await page.goto(f"{base_url.rstrip('/')}/#/tunnels/list")
        await _wait_loading(page)

        btn = page.locator("button.el-button--success:has-text('启动')").first
        if await btn.is_visible():
            await btn.click()
            await _wait_loading(page)
            success = True

        # 如果需要确认上线，轮询等待状态页刷新出链接
        if success and wait_online:
            for _ in range(15):
                await page.goto(f"{base_url.rstrip('/')}/#/status/online")
                await _wait_loading(page)
                if not await page.locator(".el-table__empty-block").is_visible():
                    break
                await asyncio.sleep(1)
    finally:
        await _close_browser(playwright, browser, context)

    return success


async def stop_tunnel(
    auth_file: str = "cpauth.json", 
    name: str = "worker", 
    base_url: str = "http://127.0.0.1:9200"
) -> bool:
    """
    【独立函数】停止隧道
    :return: 停止成功或已被点击返回 True
    """
    playwright, browser, context, page = await _init_browser(auth_file, name)
    success = False
    try:
        await page.goto(f"{base_url.rstrip('/')}/#/tunnels/list")
        await _wait_loading(page)

        btn = page.locator("button.el-button--primary:has-text('停止')").first
        if await btn.is_visible():
            await btn.click()
            await _wait_loading(page)
            success = True
    finally:
        await _close_browser(playwright, browser, context)

    return success


# ================= 使用测试 =================

async def main():
    # 1. 单纯查询公网地址 (指定 name="main" 可以弹窗看过程，不传或传其他则静默)
    urls = await query_public_urls(auth_file="cpauth.json", name="main")
    print("当前公网地址列表:", urls)

    # 2. 如果无地址，启动隧道
    if not urls:
        print("未检测到公网地址，启动隧道中...")
        is_started = await start_tunnel(auth_file="cpauth.json", name="main", wait_online=True)
        if is_started:
            new_urls = await query_public_urls(auth_file="cpauth.json", name="main")
            print("启动成功，新公网地址:", new_urls)

    # 3. 单纯关闭隧道
    await stop_tunnel(auth_file="cpauth.json", name="main")

if __name__ == "__main__":
    asyncio.run(main())
