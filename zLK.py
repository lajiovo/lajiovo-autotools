import asyncio
import hashlib
import html
import json
import os
import re
import sys
from datetime import datetime
from urllib.parse import urljoin

from ebooklib import epub
from playwright.async_api import async_playwright
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib3

import zBarkCustom

# 尝试导入 opencc，如未安装则提供基础回退
try:
    import opencc
    cc_converter = opencc.OpenCC('t2s')
except ImportError:
    cc_converter = None

import zPerseusLogger
from zConfig import get_config

# 禁用 requests/urllib3 的 SSL 警告提示
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 伪装 iPhone 15 配置及全套 HTTP Headers，防止被 TLS/WAF 阻断
USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)

HTTP_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Fetch-Dest": "image",
    "Sec-Fetch-Mode": "no-cors",
    "Sec-Fetch-Site": "cross-site",
}

# 基础配置
VIEWPORT = get_config("lk.site.viewport")
DOMAIN = get_config("lk.site.domain")
AUTH_FILE = get_config("lk.site.auth_file")
CACHE_DIR = get_config("lk.site.cache_dir")

# Shadowrocket 代理设置
PROXY_SERVER = get_config("lk.network.proxy_server")
PROXIES_DICT = (
    {"http": PROXY_SERVER, "https": PROXY_SERVER} if PROXY_SERVER else {}
)

def get_request_session():
    """创建一个带有防断连重试和长连接 Keep-Alive 的 Requests Session"""
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

def convert_t2s(text: str, enabled: bool = True) -> str:
    """繁体转简体函数"""
    if not text or not enabled:
        return text
    if cc_converter:
        return cc_converter.convert(text)
    return text

def sanitize_filename(name: str) -> str:
    """清理非法文件名字符"""
    return re.sub(r'[\\/*?:"<>|]', "_", name)

def get_url_hash(url: str) -> str:
    """获取 URL 的 MD5 哈希作为图片本地唯一标识"""
    return hashlib.md5(url.encode("utf-8")).hexdigest()

def get_book_dir(book_title: str) -> str:
    """获取小说一级缓存目录"""
    safe_book = sanitize_filename(book_title)
    dir_path = os.path.join(CACHE_DIR, safe_book)
    os.makedirs(dir_path, exist_ok=True)
    return dir_path

def save_book_metadata(book_title: str, metadata: dict):
    """保存小说一级目录下的说明元数据 metadata.json"""
    book_dir = get_book_dir(book_title)
    meta_path = os.path.join(book_dir, "metadata.json")
    try:
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"  [!] 保存书籍元数据失败: {e}")

def get_chapter_dir(book_title: str, vol_name: str) -> str:
    """获取章节所在分卷的路径"""
    safe_vol = sanitize_filename(vol_name)
    dir_path = os.path.join(get_book_dir(book_title), safe_vol)
    os.makedirs(dir_path, exist_ok=True)
    return dir_path

def get_chapter_cache_path(book_title: str, vol_name: str, ch_title: str) -> str:
    """根据书名、卷名、章节名生成对应的 JSON 缓存文件路径"""
    dir_path = get_chapter_dir(book_title, vol_name)
    safe_ch = sanitize_filename(ch_title)
    return os.path.join(dir_path, f"{safe_ch}.json")

def get_image_save_dir(book_title: str, vol_name: str = None) -> str:
    """获取图片的保存目录: 
    如果不指定 vol_name，存一级目录: lkcache/书名/images_mapped
    如果指定 vol_name，存分卷目录: lkcache/书名/分卷名/images_mapped
    """
    if vol_name:
        dir_path = os.path.join(get_chapter_dir(book_title, vol_name), "images_mapped")
    else:
        dir_path = os.path.join(get_book_dir(book_title), "images_mapped")
    os.makedirs(dir_path, exist_ok=True)
    return dir_path

def load_chapter_cache(book_title: str, vol_name: str, ch_title: str) -> dict:
    """从分类目录读取指定章节的缓存"""
    path = get_chapter_cache_path(book_title, vol_name, ch_title)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_chapter_cache(book_title: str, vol_name: str, ch_title: str, ch_data: dict):
    """写入指定章节数据到对应的缓存文件"""
    path = get_chapter_cache_path(book_title, vol_name, ch_title)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(ch_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"  [!] 写入缓存失败: {e}")

def is_image_valid(file_path: str) -> bool:
    """校验图片文件是否存在且未损坏（大小 > 0 字节，并检测魔数 Header）"""
    if not file_path or not os.path.exists(file_path):
        return False
    if os.path.getsize(file_path) == 0:
        return False
    try:
        with open(file_path, "rb") as f:
            header = f.read(10)
            if header.startswith(b'\xff\xd8\xff'):  # JPEG
                return True
            if header.startswith(b'\x89PNG\r\n\x1a\n'):  # PNG
                return True
            if header.startswith(b'GIF87a') or header.startswith(b'GIF89a'):  # GIF
                return True
            if header.startswith(b'RIFF') and header[8:12] == b'WEBP':  # WEBP
                return True
    except Exception:
        return False
    return False

def download_image(url: str, headers: dict = None, cookies_dict: dict = None, retries: int = 3):
    """下载图片并返回字节数据与扩展名"""
    url = urljoin(DOMAIN, html.unescape(url))
    req_headers = HTTP_HEADERS.copy()
    if headers:
        req_headers.update(headers)
    req_headers["Referer"] = DOMAIN

    session = get_request_session()
    modes = ["proxy", "direct"] if PROXIES_DICT else ["direct"]

    for mode in modes:
        current_proxies = PROXIES_DICT if mode == "proxy" else None
        for attempt in range(retries):
            try:
                resp = session.get(
                    url,
                    headers=req_headers,
                    cookies=cookies_dict,
                    proxies=current_proxies,
                    timeout=20,
                    verify=False,
                )
                # 必须大于 100 字节，防止保存几字节的空响应或报错文本
                if resp.status_code == 200 and len(resp.content) > 100:
                    header = resp.content[:10]
                    ext = None
                    if header.startswith(b'\xff\xd8\xff'):
                        ext = ".jpg"
                    elif header.startswith(b'\x89PNG\r\n\x1a\n'):
                        ext = ".png"
                    elif header.startswith(b'GIF87a') or header.startswith(b'GIF89a'):
                        ext = ".gif"
                    elif header.startswith(b'RIFF') and header[8:12] == b'WEBP':
                        ext = ".webp"

                    # 只有确认是合法图片格式数据才返回
                    if ext:
                        return resp.content, ext
                    else:
                        print(f"    [!] 响应内容不是有效图片格式 (魔数校验失败)，重试 ({attempt + 1}/{retries})...")
                else:
                    print(f"    [!] 状态码错误或数据过于微小 ({resp.status_code})，重试 ({attempt + 1}/{retries})...")
            except Exception as e:
                if attempt == retries - 1 and mode == modes[-1]:
                    print(f"  [!] 图片下载失败 {url}: {e}")
            time.sleep(1)
    return None, None

async def safe_goto(page, url: str, retries: int = 3):
    """安全的页面加载函数，防止网络重置 (Connection Reset)"""
    for attempt in range(retries):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(3000)
            return True
        except Exception as e:
            print(f"  [!] 加载页面失败 ({attempt + 1}/{retries}): {url} -> {e}")
            if attempt < retries - 1:
                await asyncio.sleep(3)
            else:
                raise e

async def crawl_lightnovel_to_epub(
    book_id: str = None,
    output_dir: str = ".",
    headless: bool = True,
    only_redownload_images: bool = False,
    to_simplified: bool = True,
    use_cache_only: bool = False,
):
    """轻之国度小说爬取并合成 EPUB 主模块函数"""
    headers = {"User-Agent": USER_AGENT, "Referer": DOMAIN}

    # 逻辑联动：若开启仅补齐图片，强制自动开启 pure_cache_only
    if only_redownload_images:
        use_cache_only = True
        print("[!] 检测到仅补齐图片模式 (only_redownload_images=True)，已自动强行切换 use_cache_only=True")

    async with async_playwright() as p:
        # 1. 登录模式（没有输入 ID）
        if not book_id:
            print("[+] 未指定 book_id，进入登录模式...")
            browser = await p.chromium.launch(
                headless=False, proxy={"server": PROXY_SERVER} if PROXY_SERVER else None
            )
            context = await browser.new_context(
                user_agent=USER_AGENT, viewport=VIEWPORT, is_mobile=True, has_touch=True
            )
            if os.path.exists(AUTH_FILE):
                try:
                    await context.add_cookies(
                        json.load(open(AUTH_FILE, "r", encoding="utf-8")).get("cookies", [])
                    )
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

        # 2. 爬取/合成模式
        base_url = f"https://www.lightnovel.fun/cn/book/{book_id}"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        book_title = f"Book_{book_id}"
        author = "未知"
        cover_url = ""
        volumes_data = []

        cookies_dict = {}

        if not use_cache_only:
            # 在线爬取模式
            browser = await p.chromium.launch(
                headless=headless, proxy={"server": PROXY_SERVER} if PROXY_SERVER else None
            )
            context_kwargs = {
                "user_agent": USER_AGENT,
                "viewport": VIEWPORT,
                "is_mobile": True,
                "has_touch": True,
            }
            if os.path.exists(AUTH_FILE):
                context_kwargs["storage_state"] = AUTH_FILE
                print(f"[+] 已加载登录状态文件: {AUTH_FILE}")

            context = await browser.new_context(**context_kwargs)
            page = await context.new_page()

            cookies_list = await context.cookies()
            cookies_dict = {c["name"]: c["value"] for c in cookies_list}

            print(f"[+] 正在请求主页: {base_url}")
            await safe_goto(page, base_url)

            # 获取主书名
            try:
                raw_title = await page.inner_text(".book-detail-title", timeout=5000)
                book_title = convert_t2s(raw_title.strip(), to_simplified)
            except Exception:
                pass

            # 获取作者
            try:
                raw_author = await page.inner_text(".book-detail-author", timeout=3000)
                author = convert_t2s(raw_author.strip(), to_simplified)
            except Exception:
                pass

            # 获取封面 URL
            try:
                cover_url = await page.get_attribute(".book-cover img", "src", timeout=3000)
            except Exception:
                pass

            # 保存 metadata.json
            save_book_metadata(
                book_title,
                {
                    "book_id": book_id,
                    "title": book_title,
                    "author": author,
                    "cover_url": cover_url,
                    "crawled_at": datetime.now().isoformat(),
                },
            )

            print(f"[✓] 书名: {book_title} | 作者: {author}")

            # 解析分卷和章节目录
            vol_elements = await page.query_selector_all(".catalog-volume, .volume-item")
            if not vol_elements:
                vol_elements = [page]  # 如果没找到分卷元素，退化为全局提取

            for v_idx, vol in enumerate(vol_elements):
                try:
                    raw_vol_title = await vol.inner_text(".volume-title", timeout=1000)
                    vol_title = convert_t2s(raw_vol_title.strip(), to_simplified)
                except Exception:
                    vol_title = f"第{v_idx + 1}卷"

                ch_links = await vol.query_selector_all("a[href*='/chapter/']")
                chapters = []
                for c_link in ch_links:
                    href = await c_link.get_attribute("href")
                    raw_c_title = await c_link.inner_text()
                    c_title = convert_t2s(raw_c_title.strip(), to_simplified)
                    full_url = urljoin(DOMAIN, href)
                    chapters.append({"title": c_title, "url": full_url})

                if chapters:
                    volumes_data.append({"vol_title": vol_title, "chapters": chapters})

        else:
            # 本地纯缓存读取模式
            print("[+] 已开启纯缓存提取模式 (use_cache_only=True)...")
            target_book_dir = None
            for dname in os.listdir(CACHE_DIR):
                dpath = os.path.join(CACHE_DIR, dname)
                if os.path.isdir(dpath):
                    meta_p = os.path.join(dpath, "metadata.json")
                    if os.path.exists(meta_p):
                        try:
                            meta = json.load(open(meta_p, "r", encoding="utf-8"))
                            if str(meta.get("book_id")) == str(book_id):
                                target_book_dir = dpath
                                book_title = meta.get("title", dname)
                                author = meta.get("author", "未知")
                                cover_url = meta.get("cover_url", "")
                                break
                        except Exception:
                            pass

            if not target_book_dir:
                for dname in os.listdir(CACHE_DIR):
                    if book_id in dname:
                        target_book_dir = os.path.join(CACHE_DIR, dname)
                        book_title = dname
                        break

            if not target_book_dir or not os.path.exists(target_book_dir):
                print(f"[!] 错误: 未能在本地缓存目录中找到 Book ID [{book_id}] 的缓存文件夹！")
                return []

            print(f"[✓] 已定位本地缓存路径: {target_book_dir}")
            for vol_dname in sorted(os.listdir(target_book_dir)):
                vol_dpath = os.path.join(target_book_dir, vol_dname)
                if os.path.isdir(vol_dpath) and vol_dname != "images_mapped":
                    vol_ch_list = []
                    for fname in sorted(os.listdir(vol_dpath)):
                        if fname.endswith(".json"):
                            ch_title = fname[:-5]
                            vol_ch_list.append({"title": ch_title, "url": ""})
                    if vol_ch_list:
                        volumes_data.append({"vol_title": vol_dname, "chapters": vol_ch_list})

        downloaded_epubs = []

        # 优先处理并缓存封面图到一级 images_mapped 目录
        cover_img_data = None
        cover_ext = ".jpg"
        if cover_url:
            root_img_dir = get_image_save_dir(book_title)
            cover_hash = get_url_hash(cover_url)

            # 先检查 images_mapped 目录下已保存的封面
            existing_cover_file = None
            for ext in [".jpg", ".png", ".gif", ".webp"]:
                test_cover_p = os.path.join(root_img_dir, f"cover_{cover_hash}{ext}")
                if is_image_valid(test_cover_p):
                    existing_cover_file = test_cover_p
                    break

            if existing_cover_file:
                print(f"[✓] 封面使用本地已缓存图片: {os.path.basename(existing_cover_file)}")
                with open(existing_cover_file, "rb") as f:
                    cover_img_data = f.read()
                cover_ext = os.path.splitext(existing_cover_file)[1] or ".jpg"
            else:
                print(f"[+] 正在下载封面图片: {cover_url}")
                c_data, c_ext = download_image(cover_url, headers, cookies_dict)
                if c_data:
                    cover_img_data = c_data
                    cover_ext = c_ext or ".jpg"
                    local_cover_filename = f"cover_{cover_hash}{cover_ext}"
                    local_cover_path = os.path.join(root_img_dir, local_cover_filename)
                    with open(local_cover_path, "wb") as f:
                        f.write(c_data)
                    print(f"  [✓] 封面图片已持久化缓存: {local_cover_filename}")

        # 开始遍历各大分卷处理
        for v_idx, vol in enumerate(volumes_data):
            vol_title = vol["vol_title"]
            chapters = vol["chapters"]
            print(f"\n======== 处理分卷 ({v_idx+1}/{len(volumes_data)}): {vol_title} ========")

            book = epub.EpubBook()
            book.set_identifier(f"lk-{book_id}-v{v_idx+1}")
            book.set_title(f"{book_title} - {vol_title}")
            book.set_language("zh")
            book.add_author(author)

            if cover_img_data:
                book.set_cover(f"cover{cover_ext}", cover_img_data)

            epub_chapters = []
            vol_image_map = {}  # original_url_or_hash -> (local_filename, full_path)

            for c_idx, ch in enumerate(chapters):
                ch_title = ch["title"]
                ch_url = ch["url"]

                cached_data = load_chapter_cache(book_title, vol_title, ch_title)
                ch_html_content = ""
                images_info = []

                if cached_data and "content" in cached_data:
                    print(f"  [✓] 读入章节本地缓存 [{c_idx+1}/{len(chapters)}]: {ch_title}")
                    ch_html_content = cached_data["content"]
                    images_info = cached_data.get("images", [])

                    # 如果 images 列表为空，从 HTML 中再匹配补齐一次 images_info
                    if not images_info:
                        found_srcs = re.findall(r'src=["\']([^"\']+)["\']', ch_html_content)
                        for src in found_srcs:
                            if "http" in src or "upload-files" in src:
                                full_u = urljoin(DOMAIN, src)
                                images_info.append({"url": full_u, "hash": get_url_hash(full_u)})

                elif not use_cache_only:
                    print(f"  [+] 抓取网页章节 [{c_idx+1}/{len(chapters)}]: {ch_title} ({ch_url})")
                    await safe_goto(page, ch_url)

                    try:
                        read_more = await page.query_selector(".read-more, .expand-btn")
                        if read_more:
                            await read_more.click()
                            await page.wait_for_timeout(1000)
                    except Exception:
                        pass

                    content_el = await page.query_selector(".chapter-content, #article-content, .read-content")
                    if content_el:
                        raw_html = await content_el.inner_html()
                        ch_html_content = convert_t2s(raw_html, to_simplified)

                        img_els = await content_el.query_selector_all("img")
                        for img in img_els:
                            src = await img.get_attribute("src") or await img.get_attribute("data-src")
                            if src:
                                full_img_url = urljoin(DOMAIN, src)
                                img_hash = get_url_hash(full_img_url)
                                images_info.append({"url": full_img_url, "hash": img_hash})

                        save_chapter_cache(
                            book_title,
                            vol_title,
                            ch_title,
                            {"title": ch_title, "url": ch_url, "content": ch_html_content, "images": images_info},
                        )

                ch_img_dir = get_image_save_dir(book_title, vol_title)

                # 提取正文中所有可能存在的原始图片 URL / Hash 列表
                for img_item in images_info:
                    img_url = img_item["url"]
                    img_hash = img_item["hash"]

                    local_img_name = None
                    for ext in [".jpg", ".png", ".gif", ".webp"]:
                        test_path = os.path.join(ch_img_dir, f"{img_hash}{ext}")
                        if is_image_valid(test_path):
                            local_img_name = f"{img_hash}{ext}"
                            break

                    # 图片不存在或文件校验损坏（如被写成了0字节/HTML报错页），进行补下
                    if not local_img_name:
                        print(f"    [+] 补齐/重新下载图片 ({img_hash}): {img_url}")
                        img_data, img_ext = download_image(img_url, headers, cookies_dict)
                        if img_data:
                            img_ext = img_ext or ".jpg"
                            local_img_name = f"{img_hash}{img_ext}"
                            save_p = os.path.join(ch_img_dir, local_img_name)
                            with open(save_p, "wb") as f:
                                f.write(img_data)
                        else:
                            print(f"    [!] 图片下载失败，跳过: {img_url}")
                            continue

                    if local_img_name:
                        img_full_path = os.path.join(ch_img_dir, local_img_name)
                        if is_image_valid(img_full_path):
                            # 使用字典绑定 hash，保证格式一致
                            vol_image_map[img_hash] = (local_img_name, img_full_path)

# 精准将 HTML 中的图片 src 路径替换为标准相对路径 images/hash.ext
                processed_html = ch_html_content
                for img_hash, (img_filename, _) in vol_image_map.items():
                    # 匹配所有包含该 32位 Hash 的 src 链接并精准替换
                    processed_html = re.sub(
                        rf'src=["\'][^"\']*?{img_hash}[^"\']*?["\']',
                        f'src="images/{img_filename}"',
                        processed_html
                    )

                c_item = epub.EpubHtml(
                    title=ch_title,
                    file_name=f"chap_{c_idx+1}.xhtml",
                    lang="zh",
                )
                c_item.content = f"<h2>{ch_title}</h2>\n<div>{processed_html}</div>"
                book.add_item(c_item)
                epub_chapters.append(c_item)

            # 将分卷图片统一打包注入 EPUB
            for img_hash, (img_filename, img_full_path) in vol_image_map.items():
                if not is_image_valid(img_full_path):
                    print(f"  [!] 文件损坏，跳过打包进 EPUB: {img_filename}")
                    continue

                try:
                    with open(img_full_path, "rb") as f:
                        i_data = f.read()

                    ext = os.path.splitext(img_filename)[1].lower()
                    media_type = "image/jpeg"
                    if "png" in ext:
                        media_type = "image/png"
                    elif "gif" in ext:
                        media_type = "image/gif"
                    elif "webp" in ext:
                        media_type = "image/webp"

                    # 规范 uid 避免非法字符导致 EPUB 解析器崩溃
                    safe_uid = re.sub(r'[^a-zA-Z0-9_\-]', '_', f"img_{img_hash}")

                    img_item = epub.EpubItem(
                        uid=safe_uid,
                        file_name=f"images/{img_filename}",  # 保证与 HTML 内 src="images/xxx" 绝对对应
                        media_type=media_type,
                        content=i_data,
                    )
                    book.add_item(img_item)
                except Exception as e:
                    print(f"  [!] 写入图片到 EPUB 失败 ({img_filename}): {e}")
            # 封装生成目录与 Spine
            book.toc = tuple(epub_chapters)
            book.add_item(epub.EpubNcx())
            book.add_item(epub.EpubNav())
            book.spine = ["nav"] + epub_chapters

            # 输出合成文件
            safe_book_name = sanitize_filename(book_title)
            safe_vol_name = sanitize_filename(vol_title)
            out_epub_name = f"{safe_book_name} - {safe_vol_name}.epub"
            out_epub_path = os.path.join(output_dir, out_epub_name)

            epub.write_epub(out_epub_path, book)
            print(f"[✓] 分卷 EPUB 生成成功: {out_epub_path}")
            downloaded_epubs.append(out_epub_path)

        if not use_cache_only:
            await browser.close()

        print(f"\n[✓] 所有任务完成，共打包导出 {len(downloaded_epubs)} 个 EPUB 文件。")
        return downloaded_epubs

if __name__ == "__main__":
    bid = sys.argv[1] if len(sys.argv) > 1 else "10312"
    asyncio.run(
        crawl_lightnovel_to_epub(
            book_id=bid,
            headless=False,
            only_redownload_images=False,
            to_simplified=True,     # 默认开启繁转简
            use_cache_only=False,   # 重新爬取开启（True 则直接读取现有缓存合成）
        )
    )