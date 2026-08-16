import asyncio
import re
import os
import json
import html
import requests
import urllib3
from urllib.parse import urljoin
from playwright.async_api import async_playwright
from ebooklib import epub

# 禁用 requests/urllib3 的 SSL 警告提示
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 伪装 iPhone 15 配置
USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
VIEWPORT = {"width": 393, "height": 852}  # iPhone 15 屏幕分辨率
DOMAIN = "https://www.lightnovel.fun"
AUTH_FILE = "lkauth.json"
CACHE_DIR = "lkache"

# Shadowrocket 代理设置
PROXY_SERVER = "http://192.168.10.7:1082"
PROXIES_DICT = {
    "http": PROXY_SERVER,
    "https": PROXY_SERVER
}

def sanitize_filename(name):
    """清理非法文件名字符"""
    return re.sub(r'[\\/*?:"<>|]', '_', name)

def get_chapter_dir(book_title, vol_name):
    """获取章节所在分卷的路径"""
    safe_book = sanitize_filename(book_title)
    safe_vol = sanitize_filename(vol_name)
    dir_path = os.path.join(CACHE_DIR, safe_book, safe_vol)
    os.makedirs(dir_path, exist_ok=True)
    return dir_path

def get_chapter_cache_path(book_title, vol_name, ch_title):
    """根据书名、卷名、章节名生成对应的 JSON 缓存文件路径"""
    dir_path = get_chapter_dir(book_title, vol_name)
    safe_ch = sanitize_filename(ch_title)
    return os.path.join(dir_path, f"{safe_ch}.json")

def get_image_save_dir(book_title, vol_name):
    """获取图片的保存目录: lkache/书名/分卷名/images"""
    dir_path = os.path.join(get_chapter_dir(book_title, vol_name), "images")
    os.makedirs(dir_path, exist_ok=True)
    return dir_path

def load_chapter_cache(book_title, vol_name, ch_title):
    """从分类目录读取指定章节的缓存"""
    path = get_chapter_cache_path(book_title, vol_name, ch_title)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_chapter_cache(book_title, vol_name, ch_title, ch_data):
    """写入指定章节数据到对应的缓存文件"""
    path = get_chapter_cache_path(book_title, vol_name, ch_title)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(ch_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"  [!] 写入缓存失败: {e}")

def is_image_valid(file_path):
    """校验图片文件是否存在且未损坏（大小 > 0 字节，并检测魔数 Header）"""
    if not os.path.exists(file_path):
        return False
    if os.path.getsize(file_path) == 0:
        return False
    try:
        with open(file_path, "rb") as f:
            header = f.read(10)
            if header.startswith(b'\xff\xd8\xff'): # JPEG
                return True
            if header.startswith(b'\x89PNG\r\n\x1a\n'): # PNG
                return True
            if header.startswith(b'GIF87a') or header.startswith(b'GIF89a'): # GIF
                return True
            if header.startswith(b'RIFF') and header[8:12] == b'WEBP': # WEBP
                return True
    except Exception:
        return False
    return False

def download_image(url, headers, cookies_dict=None, retries=3):
    """下载图片并返回字节数据与扩展名，支持代理容错与自动退回直连模式"""
    url = urljoin(DOMAIN, html.unescape(url))
    
    req_headers = headers.copy() if headers else {}
    req_headers["User-Agent"] = USER_AGENT
    req_headers["Referer"] = DOMAIN

    for mode in ["proxy", "direct"]:
        current_proxies = PROXIES_DICT if mode == "proxy" else None
        for attempt in range(retries):
            try:
                resp = requests.get(
                    url, 
                    headers=req_headers, 
                    cookies=cookies_dict, 
                    proxies=current_proxies, 
                    timeout=15, 
                    verify=False
                )
                if resp.status_code == 200:
                    content_type = resp.headers.get("Content-Type", "")
                    ext = ".jpg"
                    if "png" in content_type:
                        ext = ".png"
                    elif "gif" in content_type:
                        ext = ".gif"
                    elif "webp" in content_type:
                        ext = ".webp"
                    return resp.content, ext
            except Exception as e:
                if attempt == retries - 1 and mode == "direct":
                    print(f"  [!] 图片下载失败 {url}: {e}")
    return None, None

async def safe_goto(page, url, retries=3):
    """安全的页面加载函数，防止网络重置 (Connection Reset)"""
    for attempt in range(retries):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(2000)
            return True
        except Exception as e:
            print(f"  [!] 加载页面失败 ({attempt + 1}/{retries}): {url} -> {e}")
            if attempt < retries - 1:
                await asyncio.sleep(3)
            else:
                raise e

async def crawl_lightnovel_to_epub(book_id: str = None, output_dir: str = ".", headless: bool = True, force_redownload_images: bool = False):
    """
    轻之国度小说爬取并合成 EPUB 主模块函数[span_0](start_span)[span_0](end_span)
    """
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": DOMAIN
    }

    async with async_playwright() as p:
        # 1. 登录模式（没有输入 ID）
        if not book_id:
            print("[+] 未指定 book_id，进入登录模式...")
            browser = await p.chromium.launch(headless=False, proxy={"server": PROXY_SERVER})
            context = await browser.new_context(
                user_agent=USER_AGENT,
                viewport=VIEWPORT,
                is_mobile=True,
                has_touch=True
            )
            
            if os.path.exists(AUTH_FILE):
                try:
                    await context.add_cookies(json.load(open(AUTH_FILE, "r", encoding="utf-8")).get("cookies", []))
                    print("  [✓] 已加载本地 auth 状态")
                except Exception as e:
                    print(f"  [!] 加载 auth 状态失败: {e}")

            page = await context.new_page()
            await safe_goto(page, DOMAIN)
            print("[!] 请在打开的浏览器中完成登录操作。关闭浏览器窗口后将自动保存登录状态。")
            
            try:
                await page.wait_for_event("close", timeout=0)
            except Exception:
                pass

            try:
                storage = await context.storage_state()
                with open(AUTH_FILE, "w", encoding="utf-8") as f:
                    json.dump(storage, f, ensure_ascii=False, indent=2)
                print(f"[✓] 登录信息已保存至: {AUTH_FILE}")
            except Exception as e:
                print(f"[!] 保存登录状态失败: {e}")

            await browser.close()
            return []

        # 2. 爬取模式（指定了 ID）
        base_url = f"https://www.lightnovel.fun/cn/book/{book_id}"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        browser = await p.chromium.launch(headless=headless, proxy={"server": PROXY_SERVER})
        
        context_kwargs = {
            "user_agent": USER_AGENT,
            "viewport": VIEWPORT,
            "is_mobile": True,
            "has_touch": True
        }
        if os.path.exists(AUTH_FILE):
            context_kwargs["storage_state"] = AUTH_FILE
            print(f"[+] 已加载登录状态文件: {AUTH_FILE}")

        context = await browser.new_context(**context_kwargs)
        page = await context.new_page()

        cookies_list = await context.cookies()
        cookies_dict = {c["name"]: c["value"] for c in cookies_list}

        print(f"[+] 正在访问书籍首页: {base_url}")
        await safe_goto(page, base_url)
        await asyncio.sleep(2)

        # 1. 解析书籍基本信息与封面校验[span_1](start_span)[span_1](end_span)
        cover_url = ""
        for retry_cover in range(4):
            cover_img = await page.query_selector("span.pc-book-cover img")
            if cover_img:
                cover_url = await cover_img.get_attribute("src") or ""
            
            if cover_url and "default" not in cover_url.lower():
                break
                
            if retry_cover < 3:
                print("  [!] 检测到默认封面 (default)，刷新页面重新抓取...")
                await page.reload(wait_until="domcontentloaded")
                await asyncio.sleep(2)

        if cover_url:
            cover_url = urljoin(DOMAIN, cover_url)

        title_el = await page.query_selector(".detail-info h1")
        book_title = await title_el.inner_text() if title_el else "未命名小说"
        book_title = book_title.strip()

        author = "未知"
        author_el = await page.query_selector(".detail-info-line span:has-text('作者') strong")
        if author_el:
            author = (await author_el.inner_text()).strip()

        print(f"[✓] 书名: {book_title}")
        print(f"[✓] 作者: {author}")
        print(f"[✓] 封面URL: {cover_url}")

        # 2. 遍历分卷 (Volume Tabs)[span_2](start_span)[span_2](end_span)
        volume_tabs = await page.query_selector_all(".volume-tabs button.volume-tab")
        if not volume_tabs:
            volume_tabs = [None]

        volumes_data = []

        for idx, tab in enumerate(volume_tabs):
            vol_name = f"第{idx+1}卷"
            if tab:
                vol_name = (await tab.get_attribute("title")) or (await tab.inner_text())
                vol_name = vol_name.strip()
                print(f"\n[+] 切换到分卷: {vol_name}")
                await tab.click()
                await asyncio.sleep(1.5)

            expand_btn = await page.query_selector("button.chapter-expand-button")
            if expand_btn and await expand_btn.is_visible():
                print("  [+] 点击展开全目录...")
                await expand_btn.click()
                await asyncio.sleep(1.5)

            chapter_links = await page.query_selector_all(".chapter-grid a.chapter")
            chapters_info = []

            for link in chapter_links:
                ch_title = (await link.inner_text()).strip()
                ch_href = await link.get_attribute("href")
                if ch_href:
                    ch_url = urljoin(DOMAIN, ch_href)
                    chapters_info.append({"title": ch_title, "url": ch_url})

            print(f"  [✓] 找到 {len(chapters_info)} 个章节")
            volumes_data.append({"volume_name": vol_name, "chapters": chapters_info})

        # 3. 逐卷爬取章节内容并生成 EPUB[span_3](start_span)[span_3](end_span)
        saved_files = []

        for vol in volumes_data:
            vol_name = vol["volume_name"]
            chapters = vol["chapters"]

            if not chapters:
                continue

            print(f"\n================ 开始处理分卷: {vol_name} ================")
            
            book = epub.EpubBook()
            book.set_identifier(f"lightnovel-{book_id}-{sanitize_filename(vol_name)}")
            book.set_title(f"{book_title} - {vol_name}")
            book.set_language("zh")
            book.add_author(author)

            # 下载并设置封面
            if cover_url:
                c_data, c_ext = download_image(cover_url, headers, cookies_dict)
                if c_data:
                    book.set_cover(f"cover{c_ext}", c_data)

            spine = ['nav']
            toc = []
            img_counter = 0

            img_save_dir = get_image_save_dir(book_title, vol_name)

            for ch_idx, ch in enumerate(chapters):
                ch_title = ch["title"]
                ch_url = ch["url"]
                
                # 从分类路径读取 JSON 缓存
                ch_cache = load_chapter_cache(book_title, vol_name, ch_title)
                cached_images = ch_cache.get("images", {})
                
                fetch_needed = not ch_cache.get("content")

                if fetch_needed:
                    print(f"[{ch_idx+1}/{len(chapters)}] 抓取章节: {ch_title} -> {ch_url}")
                    ch_page = await context.new_page()
                    try:
                        await safe_goto(ch_page, ch_url)
                        await asyncio.sleep(2)

                        h1_el = await ch_page.query_selector("h1")
                        if h1_el:
                            real_title = (await h1_el.inner_text()).strip()
                            if real_title:
                                ch_title = real_title

                        reader_el = await ch_page.query_selector(".reader-text")
                        ch_html_content = ""

                        if reader_el:
                            imgs = await reader_el.query_selector_all("img")
                            for img in imgs:
                                img_src = await img.get_attribute("data-src") or await img.get_attribute("src")
                                if img_src:
                                    full_img_url = urljoin(DOMAIN, img_src)
                                    await img.evaluate("(node, newSrc) => node.src = newSrc", full_img_url)

                            ch_html_content = await reader_el.inner_html()

                        ch_cache = {
                            "title": ch_title,
                            "url": ch_url,
                            "content": ch_html_content,
                            "images": cached_images
                        }
                        save_chapter_cache(book_title, vol_name, ch_title, ch_cache)

                    except Exception as e:
                        print(f"  [!] 抓取失败: {e}")
                    finally:
                        await ch_page.close()
                else:
                    print(f"[{ch_idx+1}/{len(chapters)}] 从缓存获取章节: {ch_title}")
                    ch_title = ch_cache.get("title", ch_title)
                    ch_html_content = ch_cache.get("content", "")

                # 独立图片处理与自动修复（图片不进 json，直接单独存储于磁盘）
                img_urls = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', ch_html_content)
                for img_url in img_urls:
                    if img_url.startswith("images/"):
                        continue
                        
                    local_filename = cached_images.get(img_url)
                    full_local_path = os.path.join(img_save_dir, local_filename) if local_filename else None

                    # 触发重新下载的条件：强制重下 / 本地未记录 / 路径不存在 / 图片校验失败（损坏）
                    need_download = (
                        force_redownload_images 
                        or not full_local_path 
                        or not is_image_valid(full_local_path)
                    )

                    if need_download:
                        if full_local_path and not force_redownload_images:
                            print(f"  [!] 检测到图片损坏或缺失，自动修复重新下载: {img_url}")
                        
                        img_bytes, img_ext = download_image(img_url, headers, cookies_dict)
                        if img_bytes:
                            img_counter += 1
                            local_filename = f"img_{img_counter}{img_ext}"
                            full_local_path = os.path.join(img_save_dir, local_filename)

                            with open(full_local_path, "wb") as f:
                                f.write(img_bytes)

                            cached_images[img_url] = local_filename
                            ch_cache["images"] = cached_images
                            save_chapter_cache(book_title, vol_name, ch_title, ch_cache)

                    # 打包进 EPUB
                    if local_filename and is_image_valid(os.path.join(img_save_dir, local_filename)):
                        full_img_path = os.path.join(img_save_dir, local_filename)
                        img_ext = os.path.splitext(local_filename)[1].lower()

                        with open(full_img_path, "rb") as f:
                            img_data = f.read()

                        img_counter += 1
                        epub_img = epub.EpubItem(
                            uid=f"img_{img_counter}",
                            file_name=f"OEBPS/images/{local_filename}",
                            media_type=f"image/{'png' if 'png' in img_ext else 'jpeg'}",
                            content=img_data
                        )
                        book.add_item(epub_img)
                        ch_html_content = ch_html_content.replace(img_url, f"images/{local_filename}")

                c = epub.EpubHtml(
                    title=ch_title,
                    file_name=f"chap_{ch_idx+1}.xhtml",
                    lang="zh"
                )
                c.content = f"<h2>{ch_title}</h2>\n" + ch_html_content
                book.add_item(c)
                
                toc.append(c)
                spine.append(c)

            book.toc = tuple(toc)
            book.add_item(epub.EpubNav())
            book.add_item(epub.EpubNcx())
            
            style = """
            body { font-family: sans-serif; line-height: 1.6; padding: 1em; }
            h2 { text-align: center; margin-bottom: 1.5em; }
            p { text-indent: 2em; margin-bottom: 0.8em; }
            img { max-width: 100%; height: auto; display: block; margin: 1em auto; }
            """
            nav_css = epub.EpubItem(
                uid="style_nav",
                file_name="style/nav.css",
                media_type="text/css",
                content=style
            )
            book.add_item(nav_css)
            book.spine = spine

            out_name = os.path.join(output_dir, f"{sanitize_filename(book_title)}_{sanitize_filename(vol_name)}.epub")
            epub.write_epub(out_name, book, {})
            print(f"[✓] 成功合成 EPUB 文件: {out_name}")
            saved_files.append(out_name)

        await browser.close()
        return saved_files

if __name__ == "__main__":
    import sys
    bid = sys.argv[1] if len(sys.argv) > 1 else None
    #asyncio.run(crawl_lightnovel_to_epub(bid, headless=False, force_redownload_images=False))

    asyncio.run(crawl_lightnovel_to_epub("", headless=False,force_redownload_images=False))
