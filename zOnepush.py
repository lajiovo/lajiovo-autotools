import zPerseusLogger
import os
import sys
import datetime
import re
import json
import time
import ctypes
import subprocess
import threading
import multiprocessing
from flask import Flask, request, send_from_directory,abort
from zBarkCustom import PerseusNotifyMsg, PerseusErrorMsg,PerseusWarningMsg
from zMainHandler import run_alas_mumu_check, handlerun, Handlepush
import zAlas
import zMumu
import zPGRJZ
import zMusicDL
import win32gui
import win32con
import win32clipboard
from zFfmpeg import process_audio as ffmrun
import asyncio
import zCpolar
from zLK import crawl_lightnovel_to_epub
from zConfig import get_config
app = Flask(__name__)

# 监听端口
LISTEN_PORT = get_config("pushserver.listen_port", default=25566)

# QBot 相关配置
PYTHONW_PATH = get_config("pushserver.qbot.pythonw_path")
QBOT_SCRIPT_PATH = get_config("pushserver.qbot.script_path")
QBOT_IDENTIFIER = get_config("pushserver.qbot.identifier")

# 全局状态控制与定时器线程锁/事件控制
HANDLEPUSH = True
timer_thread = None
timer_event = threading.Event()  # 用于优雅控制和停止定时器线程

# 2. 新增 MusicDL 相关配置与全局变量
# MusicDL 配置
MUSIC_EXE_PATH = get_config("pushserver.music.exe_path")
MUSIC_PORT = get_config("pushserver.music.port", default=37777)
musicdl_thread = None
# 2. 全局线程控制对象增加 ffm_thread
ffmpeg_thread = None

# 全局变量：存储当前唯一正在运行的任务信息
current_task = {
    "book_id": None,
    "loop": None,
    "task": None
}
task_lock = threading.Lock()

# 定义全局变量存储定时器与端口转发 Server 任务
auto_stop_timer = None
timer_lock = threading.Lock()
forwarding_servers = []  # 存储端口转发服务器实例

# 假设 webassets 文件夹与当前脚本文件在同一目录下
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEBASSETS_DIR = os.path.join(BASE_DIR, "webassets")

cpurls = []

def parse_bool(val):
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("true", "1", "yes")
    return bool(val)

def auto_stop_task():
    """后台延时执行的关闭函数"""
    global auto_stop_timer
    try:
        print("⏰ 30分钟倒计时已到，正在自动停止 Cpolar 隧道及端口转发...")
        stop_port_forwarding()  # 停止端口转发
        zCpolar.stop_cpolar_tunnel()
        msg = "Cpolar 隧道及端口转发已在运行 30 分钟后自动停止"
        PerseusNotifyMsg(msg, "")
    except Exception as e:
        print(f"❌ Cpolar 自动停止异常: {e}")
        PerseusErrorMsg("Cpolar 自动停止异常", str(e))
    finally:
        with timer_lock:
            auto_stop_timer = None

def cancel_existing_timer():
    """取消已存在的定时器"""
    global auto_stop_timer
    with timer_lock:
        if auto_stop_timer is not None:
            auto_stop_timer.cancel()
            auto_stop_timer = None

# ==================== 端口转发的核心逻辑 ====================

async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """处理传入的 HTTP 连接，根据路径前缀路由分发至对应本地端口"""
    try:
        # 读取 HTTP 请求头（最多 8KB）
        header_data = await reader.read(8192)
        if not header_data:
            writer.close()
            await writer.wait_closed()
            return

        request_str = header_data.decode('utf-8', errors='ignore')
        first_line = request_str.split('\r\n')[0] if '\r\n' in request_str else ""
        parts = first_line.split(' ')

        if len(parts) < 2:
            writer.close()
            await writer.wait_closed()
            return

        path = parts[1]

        # 2. 规则 2: 根据路径判断转发目标端口
        if path == "/main" or path.startswith("/main/"):
            target_port = 25566
        elif path == "/bot" or path.startswith("/bot/"):
            target_port = 25567
        else:
            target_port = 22267

        # 3. 建立与本地目标端口的连接并直接透传数据
        target_reader, target_writer = await asyncio.open_connection('127.0.0.1', target_port)
        
        # 将原始 Header 直接发给目标服务器
        target_writer.write(header_data)
        await target_writer.drain()

        # 建立双向流量透传管线
        async def pipe(src_reader, dst_writer):
            try:
                while True:
                    data = await src_reader.read(4096)
                    if not data:
                        break
                    dst_writer.write(data)
                    await dst_writer.drain()
            except Exception:
                pass
            finally:
                try:
                    dst_writer.close()
                    await dst_writer.wait_closed()
                except Exception:
                    pass

        await asyncio.gather(
            pipe(reader, target_writer),
            pipe(target_reader, writer),
            return_exceptions=True
        )

    except Exception:
        pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


def start_port_forwarding(port=25568):
    """在后台独立线程中启动 25568 监听任务"""
    stop_port_forwarding()  # 启动前先确保旧的已关闭

    def run_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def main():
            server = await asyncio.start_server(handle_client, '0.0.0.0', port)
            forwarding_servers.append((server, loop))
            async with server:
                await server.serve_forever()

        try:
            loop.run_until_complete(main())
        except asyncio.CancelledError:
            pass
        finally:
            loop.close()

    t = threading.Thread(target=run_loop, daemon=True)
    t.start()
    print(f"🚀 端口转发服务已在 0.0.0.0:{port} 启动")

def stop_port_forwarding():
    """停止并关闭端口转发服务器"""
    global forwarding_servers
    for server, loop in forwarding_servers:
        try:
            server.close()
            loop.call_soon_threadsafe(loop.stop)
        except Exception as e:
            print(f"关闭端口转发服务出错: {e}")
    forwarding_servers.clear()
    print("🛑 端口转发服务已关闭")


def is_admin():
    """检查当前进程是否具有管理员权限"""
    if sys.platform.startswith("win"):
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False
    return True

def request_admin_privileges(max_retries=5):
    """请求管理员权限，若未获得则重新尝试拉起自身，最多尝试 max_retries 次"""
    if is_admin():
        return True

    try:
        retry_count = int(os.environ.get("ADMIN_RETRY_COUNT", "0"))
    except ValueError:
        retry_count = 0

    if retry_count >= max_retries:
        print(f"❌ 尝试请求管理员权限超过最大次数 ({max_retries} 次)，程序退出！")
        sys.exit(1)

    retry_count += 1
    print(f"⚠️ 当前未获取管理员权限，正在请求提权 (第 {retry_count}/{max_retries} 次尝试)...")

    if sys.platform.startswith("win"):
        env = os.environ.copy()
        env["ADMIN_RETRY_COUNT"] = str(retry_count)

        script = os.path.abspath(sys.argv[0])
        params = " ".join([f'"{arg}"' for arg in sys.argv[1:]])
        
        try:
            ctypes.windll.shell32.ShellExecuteW(
                None, 
                "runas", 
                sys.executable, 
                f'"{script}" {params}', 
                None, 
                1
            )
            sys.exit(0)
        except Exception as e:
            print(f"❌ 请求管理员权限失败: {e}")
            sys.exit(1)
    else:
        print("⚠️ 当前非 Windows 环境，无法使用 runas 请求权限。")
        return False

def kill_port_process(port):
    """启动时结束指定端口的原有占用进程"""
    try:
        if sys.platform.startswith("win"):
            cmd = f"netstat -ano | findstr :{port}"
            try:
                output = subprocess.check_output(cmd, shell=True).decode('gbk', errors='ignore')
            except subprocess.CalledProcessError:
                return

            pids = set()
            for line in output.strip().splitlines():
                parts = line.split()
                if len(parts) >= 5 and "LISTENING" in parts:
                    pids.add(parts[-1])
            for pid in pids:
                if pid != '0':
                    print(f"🧹 检测到端口 {port} 被进程 {pid} 占用，正在结束该进程...")
                    subprocess.call(f"taskkill /F /PID {pid}", shell=True)
        else:
            cmd = f"lsof -i:{port} -t"
            try:
                pids = subprocess.check_output(cmd, shell=True).decode().strip().splitlines()
                for pid in pids:
                    print(f"🧹 检测到端口 {port} 被进程 {pid} 占用，正在结束该进程...")
                    subprocess.call(f"kill -9 {pid}", shell=True)
            except subprocess.CalledProcessError:
                pass
    except Exception as e:
        print(f"⚠️ 尝试清理端口 {port} 占用进程时遇到问题: {e}")

# 3. 新增 MusicDL 管理辅助函数
def hide_window_by_process_name(exe_name="music-dl-desktop-rust.exe", timeout=20):
    """查找并隐藏指定进程名的 Webview/GUI 窗口，最长重试 timeout 秒"""
    start_time = time.time()
    
    # 获取该进程名的 PID 集合
    def get_target_pids():
        pids = set()
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            
            output = subprocess.check_output(
                f'tasklist /FI "IMAGENAME eq {exe_name}" /FO CSV /NH',
                shell=True,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW
            ).decode('gbk', errors='ignore')
            
            for line in output.strip().splitlines():
                parts = line.split(',')
                if len(parts) >= 2:
                    pid_str = parts[1].replace('"', '').strip()
                    if pid_str.isdigit():
                        pids.add(int(pid_str))
        except Exception:
            pass
        return pids

    print(f"🔍 正在检索并寻找 {exe_name} 窗口，最长等待 {timeout} 秒...")
    
    while time.time() - start_time < timeout:
        target_pids = get_target_pids()
        if target_pids:
            found_hwnds = []

            def enum_windows_callback(hwnd, _):
                if win32gui.IsWindowVisible(hwnd):
                    _, pid = win32process.GetWindowThreadProcessId(hwnd) if 'win32process' in globals() else (None, None)
                    # 也可以使用 ctypes 替代 win32process 避开额外 import
                    if pid is None:
                        pid_val = ctypes.c_ulong()
                        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_val))
                        pid = pid_val.value
                        
                    if pid in target_pids:
                        found_hwnds.append(hwnd)

            win32gui.EnumWindows(enum_windows_callback, None)

            if found_hwnds:
                for hwnd in found_hwnds:
                    win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
                    print(f"🙈 已成功找到并隐藏窗口 (HWND: {hwnd}, PID: {target_pids})")
                return True

        time.sleep(0.5)

    print(f"⚠️ 超过 {timeout} 秒未捕获到可见的 {exe_name} 窗口，跳过隐藏步骤。")
    return False

def start_musicdl_services():
    """正常/前台启动程序 -> 20s内查找并隐藏其Webview窗口 -> 单开线程运行 zMusicDL.main()"""
    global musicdl_thread
    stop_musicdl_services()

    if not os.path.exists(MUSIC_EXE_PATH):
        raise FileNotFoundError(f"未找到路径: {MUSIC_EXE_PATH}")

    # 1. 普通拉起进程，不带SW_HIDE，以便其渲染加载 Webview 窗口
    print(f"🚀 正在启动音乐客户端程序: {MUSIC_EXE_PATH}")
    subprocess.Popen(
        [MUSIC_EXE_PATH],
        cwd=os.path.dirname(MUSIC_EXE_PATH)
    )

    # 2. 单开独立后台线程轮询20s来查找并隐藏窗口
    threading.Thread(
        target=hide_window_by_process_name, 
        args=("music-dl-desktop-rust.exe", 20), 
        daemon=True
    ).start()

    # 3. 单开独立线程运行 zMusicDL.main()
    print("🧵 正在单开线程运行 zMusicDL.main()...")
    musicdl_thread = threading.Thread(target=zMusicDL.main, daemon=True)
    musicdl_thread.start()

def stop_musicdl_services():
    """清理 37777 端口，强杀进程，并关闭 musicdl 及 ffm 线程"""
    global musicdl_thread, ffmpeg_thread
    
    # print("🧹 正在清理 37777 端口进程...")
    # kill_port_process(MUSIC_PORT)
    
    try:
        if sys.platform.startswith("win"):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            creationflags = subprocess.CREATE_NO_WINDOW
            
            print("🧹 正在清杀 music-dl-desktop-rust.exe 进程...")
            subprocess.run(
                ["taskkill", "/F", "/IM", "music-dl-desktop-rust.exe"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                startupinfo=startupinfo,
                creationflags=creationflags
            )
    except Exception as e:
        print(f"⚠️ 清理 music-dl 进程发生异常: {e}")

    if musicdl_thread and musicdl_thread.is_alive():
        print("⏸️ 正在关闭/重置 musicdl 线程引用...")
        musicdl_thread = None

    if ffmpeg_thread and ffmpeg_thread.is_alive():
        print("⏸️ 正在关闭/重置 ffm 线程引用...")
        ffmpeg_thread = None

# ==================== QBot 进程精准查杀与无窗口启动 ====================

# ==================== QBot 进程精准查杀与无窗口启动（零弹窗版） ====================

def kill_qbot_process():
    """查找并精准查杀带有识别标记的 QBot 进程（彻底无弹窗）"""
    if not sys.platform.startswith("win"):
        return

    try:
        # 1. 设置静默运行参数，彻底隐藏子进程控制台窗口
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0  # SW_HIDE
        creationflags = subprocess.CREATE_NO_WINDOW

        ps_command = f'Get-CimInstance Win32_Process | Where-Object {{ $_.CommandLine -like "*{QBOT_IDENTIFIER}*" }} | Select-Object -ExpandProperty ProcessId'
        
        proc = subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_command],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            startupinfo=startupinfo,
            creationflags=creationflags,
            text=True
        )
        output, _ = proc.communicate()

        if output and output.strip():
            pids = output.strip().splitlines()
            for pid in pids:
                pid = pid.strip()
                if pid.isdigit():
                    print(f"🧹 找到指定的 QBot 进程 (PID: {pid})，正在静默结束...")
                    # 杀进程同样传入静默参数，防止 taskkill 弹窗
                    subprocess.run(
                        ["taskkill", "/F", "/PID", pid],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        startupinfo=startupinfo,
                        creationflags=creationflags
                    )
            time.sleep(0.5)
        else:
            print("🔍 未检测到正在运行的 QBot 目标进程。")
    except Exception as e:
        print(f"⚠️ 清理 QBot 进程时发生异常: {e}")

def start_qbot_process():
    """先精准清理，然后使用 pythonw 无窗口启动 QBot"""
    # 1. 启动前先精准查杀旧进程
    try:
        kill_qbot_process()
    except Exception as e:
        print(f"❌ 清理旧进程时发生错误: {e}")

    # 2. 检查路径有效性
    if not os.path.exists(PYTHONW_PATH):
        print(f"❌ 未找到 pythonw.exe 路径: {PYTHONW_PATH}")
        raise FileNotFoundError(f"未找到 pythonw.exe 路径: {PYTHONW_PATH}")
    if not os.path.exists(QBOT_SCRIPT_PATH):
        print(f"❌ 未找到脚本文件路径: {QBOT_SCRIPT_PATH}")
        raise FileNotFoundError(f"未找到脚本文件路径: {QBOT_SCRIPT_PATH}")

    try:
        # 3. 构建启动命令（确保在启动尝试前定义 cmd）
        cmd = [PYTHONW_PATH, QBOT_SCRIPT_PATH, QBOT_IDENTIFIER]
        working_dir = os.path.dirname(QBOT_SCRIPT_PATH)

        # 4. 设置 Windows 彻底无窗口标志
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        creationflags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS

        print(f"🚀 正在使用 pythonw 后台静默启动 QBot: {QBOT_SCRIPT_PATH}")
        subprocess.Popen(
            cmd,
            cwd=working_dir,
            startupinfo=startupinfo,
            creationflags=creationflags,
            close_fds=True
        )
    except Exception as e:
        print(f"❌ 启动 QBot 进程失败: {e}")


# ==================== 定时器及基础状态管理 ====================

def stop_timer():
    """停止后台定时检查线程"""
    global timer_event
    timer_event.set()

def start_alas_mumu_check_timer():
    """启动/重启后台定时任务线程：每半小时自动执行一次 alas_mumu_check"""
    global timer_thread, timer_event
    stop_timer()
    
    timer_event = threading.Event()
    
    def timer_loop():
        while not timer_event.is_set():
            if timer_event.wait(1800):
                break
            try:
                print("⏰ 触发定时任务: 正在运行 alas_mumu_check...")
                run_alas_mumu_check()
                # 1. 运行前检查签到记录文件
                log_path = 'last_checkin.txt'
                today_str = datetime.date.today().isoformat()  # YYYY-MM-DD

                # 如果文件不存在，新建空文件
                if not os.path.exists(log_path):
                    with open(log_path, 'w', encoding='utf-8') as f:
                        pass
                    last_date = ''
                else:
                    with open(log_path, 'r', encoding='utf-8') as f:
                        last_date = f.read().strip()

                # 如果记录的时间是今天，直接跳过任务并返回 True
                if last_date == today_str:
                    print("今日已重启过qbot")
                else:
                    try:
                        print("今日尚未重启过qbot")
                        start_qbot_process()
                    except Exception as e :
                        print(e)
                    
                zPGRJZ.run(headless=True)
                with open(log_path, 'w', encoding='utf-8') as f:
                    f.write(today_str)
                print("已更新今日签到记录文件。")
            except Exception as e:
                print(f"⚠️ 定时运行 alas_mumu_check 出现异常: {e}")
                PerseusErrorMsg("定时运行 alas_mumu_check 出现异常",str(e))

    timer_thread = threading.Thread(target=timer_loop, daemon=True)
    timer_thread.start()

def enter_standby():
    """进入待机状态：停止 handlepush，清理进程，停用定时任务"""
    global HANDLEPUSH
    HANDLEPUSH = False
    stop_timer()
    
    try:
        print("🧹 正在执行 zAlas.cleanup()...")
        zAlas.cleanup()
    except Exception as e:
        print(f"⚠️ zAlas.cleanup() 执行失败: {e}")
        
    try:
        print("🧹 正在执行 zMumu.cleanup()...")
        zMumu.cleanup()
    except Exception as e:
        print(f"⚠️ zMumu.cleanup() 执行失败: {e}")
        
    print("⏸️ 已切换至待机状态。")

def format_response(result_data, status_code=200):
    """统一构建 JSON 响应"""
    if isinstance(result_data, (dict, list)):
        body = json.dumps(result_data, ensure_ascii=False)
    else:
        body = str(result_data)
    return body, status_code, {"Content-Type": "application/json"}

# ==================== Push 日志缓存（三级 + 自动轮转） ====================

PUSHLOG_LEVELS = ("notify", "warning", "error")
PUSHLOG_MAX_RECORDS = 100
PUSHLOG_DIR = os.path.join(BASE_DIR, "servercache", "pushlog")
pushlog_lock = threading.Lock()


def _collect_request_dict():
    msg_dict = {}
    msg_dict.update(request.args.to_dict())
    msg_dict.update(request.form.to_dict())
    if request.is_json:
        json_data = request.get_json(silent=True)
        if json_data and isinstance(json_data, dict):
            msg_dict.update(json_data)
    return msg_dict


def _normalize_pushlog_level(level):
    if not level:
        return None
    name = str(level).strip().lower()
    aliases = {"notice": "notify", "warn": "warning", "err": "error"}
    name = aliases.get(name, name)
    return name if name in PUSHLOG_LEVELS else None


def _pushlog_file(level):
    return os.path.join(PUSHLOG_DIR, level, "records.json")


def _read_pushlog(level):
    path = _pushlog_file(level)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write_pushlog(level, records):
    folder = os.path.join(PUSHLOG_DIR, level)
    os.makedirs(folder, exist_ok=True)
    path = _pushlog_file(level)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def append_pushlog(level, title, markdown, extra=None):
    """追加一条推送记录并按上限自动轮转（丢弃最旧记录）。"""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = {
        "time": now,
        "title": title or "",
        "markdown": markdown or "",
        "content": markdown or "",
    }
    if isinstance(extra, dict):
        for k, v in extra.items():
            if k not in entry:
                entry[k] = v

    with pushlog_lock:
        records = _read_pushlog(level)
        records.append(entry)
        if len(records) > PUSHLOG_MAX_RECORDS:
            records = records[-PUSHLOG_MAX_RECORDS:]
        _write_pushlog(level, records)
        total = len(records)
    return entry, total


def slice_pushlog(level, start_idx, end_idx):
    """按从新到旧的 1-based 区间读取记录。"""
    with pushlog_lock:
        records = list(_read_pushlog(level))
    newest_first = list(reversed(records))
    total = len(newest_first)
    if total == 0:
        return [], 0, start_idx, end_idx
    if start_idx < 1:
        start_idx = 1
    if end_idx < start_idx:
        end_idx = start_idx
    if start_idx > total:
        return [], total, start_idx, end_idx
    if end_idx > total:
        end_idx = total
    return newest_first[start_idx - 1 : end_idx], total, start_idx, end_idx


def parse_pushlog_span(span):
    """解析 xx 或 xx-xx 区间。"""
    text = str(span or "").strip()
    if not text:
        return 1, 1
    if "-" in text:
        left, right = text.split("-", 1)
        if left.strip().isdigit() and right.strip().isdigit():
            return int(left.strip()), int(right.strip())
        return None, None
    if text.isdigit():
        n = int(text)
        return n, n
    return None, None

# ==================== 剪切板缓存与文件管理 (servercache/clipboard) ====================

CLIPBOARD_DIR = os.path.join(BASE_DIR, "servercache", "clipboard")
os.makedirs(CLIPBOARD_DIR, exist_ok=True)

def get_clipboard_text_path():
    return os.path.join(CLIPBOARD_DIR, "content.txt")

def read_clipboard_cache():
    text_path = get_clipboard_text_path()
    text_content = ""
    if os.path.exists(text_path):
        try:
            with open(text_path, "r", encoding="utf-8") as f:
                text_content = f.read()
        except Exception:
            pass
            
    images = []
    if os.path.exists(CLIPBOARD_DIR):
        try:
            valid_exts = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
            files = sorted(os.listdir(CLIPBOARD_DIR), key=lambda x: os.path.getmtime(os.path.join(CLIPBOARD_DIR, x)), reverse=True)
            for f in files:
                if f.lower().endswith(valid_exts):
                    images.append(f)
        except Exception:
            pass
            
    return {"text": text_content, "images": images}

@app.route("/clipboard/file/<path:filename>", methods=["GET"])
def serve_clipboard_file(filename):
    """访问 servercache/clipboard 文件夹中的缓存图片/文件"""
    return send_from_directory(CLIPBOARD_DIR, filename)

@app.route("/clipboard", methods=["GET", "POST"])
def handle_clipboard():
    """
    剪贴板与缓存路由 /clipboard：
    GET: 返回当前缓存的文本内容与图片列表
    POST: 
      - 保存文本: 传 text 或 content
      - 上传图片: multipart/form-data 文件域 file
      - 删除文件: action=delete & filename=xxx
    """
    if request.method == "GET":
        data = read_clipboard_cache()
        return format_response({"status": "ok", **data}, 200)
    else:
        req_data = _collect_request_dict()
        action = req_data.get("action")
        
        # 1. 删除文件请求
        if action == "delete":
            filename = req_data.get("filename")
            if filename:
                # 防止目录遍历攻击
                safe_name = os.path.basename(filename)
                target_file = os.path.join(CLIPBOARD_DIR, safe_name)
                if os.path.exists(target_file) and os.path.isfile(target_file):
                    try:
                        os.remove(target_file)
                        return format_response({"status": "ok", "message": f"文件 {safe_name} 已删除", **read_clipboard_cache()}, 200)
                    except Exception as e:
                        return format_response({"status": "error", "message": f"删除文件失败: {e}"}, 500)
            return format_response({"status": "error", "message": "未指定有效文件名"}, 400)

        # 2. 处理文件上传（图片）
        if 'file' in request.files:
            file = request.files['file']
            if file and file.filename:
                original_name = file.filename
                ext = os.path.splitext(original_name)[1]
                timestamp_name = f"{int(time.time() * 1000)}{ext}"
                save_path = os.path.join(CLIPBOARD_DIR, timestamp_name)
                try:
                    file.save(save_path)
                    return format_response({"status": "ok", "message": "图片上传成功", "filename": timestamp_name, **read_clipboard_cache()}, 200)
                except Exception as e:
                    return format_response({"status": "error", "message": f"图片保存失败: {e}"}, 500)

        # 3. 处理文本更新
        text = req_data.get("text")
        if text is None:
            text = req_data.get("content")
            
        if text is not None:
            text_path = get_clipboard_text_path()
            try:
                with open(text_path, "w", encoding="utf-8") as f:
                    f.write(str(text))
                return format_response({"status": "ok", "message": "文本缓存更新成功", **read_clipboard_cache()}, 200)
            except Exception as e:
                return format_response({"status": "error", "message": f"文本保存失败: {e}"}, 500)

        return format_response({"status": "error", "message": "无效的请求参数或没有提供有效负载"}, 400)

# 推送接收接口
@app.route("/push", methods=["GET", "POST"])
def receive_push():
    msg_dict = {}
    msg_dict.update(request.args.to_dict())
    msg_dict.update(request.form.to_dict())
    if request.is_json:
        json_data = request.get_json(silent=True)
        if json_data:
            msg_dict.update(json_data)

    print("\n========================================")
    print(f"【新OnePush推送】时间：{str(request.args)}")
    print("消息完整字典：")
    print(json.dumps(msg_dict, ensure_ascii=False, indent=4))
    print("========================================\n")

    if HANDLEPUSH:
        push_res = Handlepush(msg_dict)
        if not push_res:
            print("❌ Handlepush 处理失败，进入待机状态...")
            enter_standby()
            
            PerseusErrorMsg(
                "Handlepush 处理失败", 
                "Push 消息处理异常，服务已自动进入待机状态并清理进程！"
            )
            
            fail_resp = push_res if push_res is not None else {
                "status": "error",
                "code": 500,
                "message": "推送处理失败，服务已转入待机状态",
                "data": msg_dict
            }
            return format_response(fail_resp, 500)
        
        return format_response(push_res, 200)

    title = msg_dict.get("title", "")
    body = msg_dict.get("body", "")
    PerseusNotifyMsg(title, body)

    default_resp = {
        "status": "ok",
        "code": 200,
        "message": "消息已转发（处于待机状态，未开启 Handlepush）",
        "data": msg_dict
    }
    return format_response(default_resp, 200)

# ==================== 控制路由命令 ====================

@app.route("/stop", methods=["GET", "POST"])
def handle_stop():
    """接收 /stop 请求，进入待机状态"""
    enter_standby()
    PerseusNotifyMsg(str({"status": "ok", "message": "服务已进入待机状态"}),"")
    return format_response({"status": "ok", "message": "服务已进入待机状态"}, 200)

@app.route("/start", methods=["GET", "POST"])
def handle_start():
    """接收 /start 请求，恢复运行状态"""
    global HANDLEPUSH
    HANDLEPUSH = True
    
    try:
        print("▶️ 收到 /start 请求，正在运行 run_alas_mumu_check...")
        run_alas_mumu_check()
    except Exception as e:
        print(f"⚠️ 运行 run_alas_mumu_check 出现异常: {e}")
        
    start_alas_mumu_check_timer()
    PerseusNotifyMsg(str({"status": "ok", "message": "服务已重新启动并恢复处理"}),"")
    return format_response({"status": "ok", "message": "服务已重新启动并恢复处理"}, 200)

@app.route("/shutdown", methods=["GET", "POST"])
def handle_shutdown():
    """接收 /shutdown 请求，结束定时检查和自身进程"""
    print("🛑 收到 /shutdown 请求，正在关闭服务自身...")
    PerseusNotifyMsg("🛑 收到 /shutdown 请求，正在关闭服务自身...","")
    stop_timer()
    
    def delayed_exit():
        time.sleep(0.5)
        os._exit(0)
        
    threading.Thread(target=delayed_exit, daemon=True).start()
    return format_response({"status": "ok", "message": "定时检查已终止，接收服务正在退出..."}, 200)

# ==================== 新增：Bot 启动与关闭路由 ====================

@app.route("/bot/start", methods=["GET", "POST"])
def handle_bot_start():
    """接收 /bot/start 请求：先杀死旧的 QBot 进程，再用 pythonw 后台无窗口拉起"""
    try:
        start_qbot_process()
        return format_response({
            "status": "ok", 
            "message": "QBot 启动成功（已完成启动前旧进程清理，无窗口运行中）"
        }, 200)
    except Exception as e:
        print(f"❌ QBot 启动失败: {e}")
        return format_response({
            "status": "error", 
            "message": f"QBot 启动失败: {str(e)}"
        }, 500)

@app.route("/bot/shutdown", methods=["GET", "POST"])
def handle_bot_shutdown():
    """接收 /bot/shutdown 请求：精准结束 QBot 进程"""
    try:
        kill_qbot_process()
        return format_response({
            "status": "ok", 
            "message": "QBot 进程已精准清理/关闭"
        }, 200)
    except Exception as e:
        print(f"❌ QBot 查杀关闭失败: {e}")
        return format_response({
            "status": "error", 
            "message": f"QBot 查杀失败: {str(e)}"
        }, 500)

# ==================== Web 帮助与运行路由 ====================

@app.route("/pushlog/add", methods=["GET", "POST"])
def handle_pushlog_add():
    """接收推送记录并按 notify/warning/error 三级写入 servercache/pushlog。"""
    req_data = _collect_request_dict()
    level = _normalize_pushlog_level(req_data.get("level") or req_data.get("type") or "notify")
    if not level:
        return format_response({"status": "error", "message": "level 必须为 notify/warning/error"}, 400)

    title = req_data.get("title", "")
    markdown = req_data.get("markdown") or req_data.get("msg") or req_data.get("content") or req_data.get("body") or ""
    extra = {k: v for k, v in req_data.items() if k not in ("level", "type", "title", "markdown", "msg", "content", "body")}
    entry, total = append_pushlog(level, str(title), str(markdown), extra)
    return format_response({
        "status": "ok",
        "message": "pushlog 已写入",
        "level": level,
        "total": total,
        "data": entry,
    }, 200)


@app.route("/pushlog/get/<level>/<span>", methods=["GET", "POST"])
def handle_pushlog_get(level, span):
    """读取记录：/pushlog/get/<notify,warning,error>/xx-xx （从新到旧，1-based）。"""
    norm_level = _normalize_pushlog_level(level)
    if not norm_level:
        return format_response({"status": "error", "message": "level 必须为 notify/warning/error"}, 400)

    start_idx, end_idx = parse_pushlog_span(span)
    if start_idx is None:
        return format_response({"status": "error", "message": "区间格式无效，应为 xx 或 xx-xx"}, 400)

    items, total, start_idx, end_idx = slice_pushlog(norm_level, start_idx, end_idx)
    if total == 0:
        return format_response({
            "status": "ok",
            "level": norm_level,
            "total": 0,
            "start": start_idx,
            "end": end_idx,
            "data": [],
            "message": "暂无记录",
        }, 200)
    if start_idx > total:
        return format_response({
            "status": "error",
            "level": norm_level,
            "total": total,
            "message": f"序号超出范围 (共 {total} 条)",
        }, 400)

    return format_response({
        "status": "ok",
        "level": norm_level,
        "total": total,
        "start": start_idx,
        "end": end_idx,
        "data": items,
    }, 200)


@app.route("/ping", methods=["GET", "POST"])
def handle_ping():
    return format_response({"handlepush": HANDLEPUSH}, 200)

@app.route("/help", methods=["GET"])
def get_help():
    html_dir = os.path.dirname(os.path.abspath(__file__))
    html_filename = "WebHome.html"
    
    if not os.path.exists(os.path.join(html_dir, html_filename)):
        return f"HTML文件未找到: {html_filename}", 404
        
    return send_from_directory(html_dir, html_filename)

@app.route("/run", methods=["GET", "POST"])
def handle_run():
    req_data = {}
    req_data.update(request.args.to_dict())
    req_data.update(request.form.to_dict())
    if request.is_json:
        json_data = request.get_json(silent=True)
        if json_data:
            req_data.update(json_data)

    print("\n========================================")
    print("【/run 收到消息】内容：")
    print(json.dumps(req_data, ensure_ascii=False, indent=4))
    print("========================================\n")

    run_result = handlerun(req_data)
    PerseusNotifyMsg(str(run_result),"")
    return format_response(run_result, 200)


# 1. 路由添加 default 参数，并同时匹配 /main/ 与 /main/<filename>
@app.route("/main/", defaults={"filename": ""}, methods=["GET"])
@app.route("/main/<path:filename>", methods=["GET"])
def serve_webassets(filename):
    """
    接收 /main/xxx 请求，安全返回 webassets 目录下的文件；
    若未指定文件名或文件不存在，则返回 index.html
    """
    # 2. 如果路径为空，默认指向 index.html
    if not filename:
        filename = "index.html"
        
    target_path = os.path.join(WEBASSETS_DIR, filename)
    
    # 3. 校验目标是否为实际存在的文件
    if os.path.isfile(target_path):
        return send_from_directory(WEBASSETS_DIR, filename)
    
    # 4. 如果请求的文件不存在（例如 SPA 单页路由刷新），统一回退到 index.html
    return send_from_directory(WEBASSETS_DIR, "index.html")

# 4. 新增路由响应接口
# 4. 新增与修改路由控制

@app.route("/music/start", methods=["GET", "POST"])
def handle_music_start():
    """接收 /music/start 请求：启动程序、20s内寻找并隐藏窗口，运行 zMusicDL.main()"""
    try:
        start_musicdl_services()
        PerseusNotifyMsg(str({
            "status": "ok",
            "message": "MusicDL 已启动，正在轮询隐藏 Webview 窗口并拉起主逻辑"
        }),"")
        return format_response({
            "status": "ok",
            "message": "MusicDL 已启动，正在轮询隐藏 Webview 窗口并拉起主逻辑"
        }, 200)
    except Exception as e:
        print(f"❌ MusicDL 启动失败: {e}")
        PerseusErrorMsg(str({
            "status": "error",
            "message": f"MusicDL 启动失败: {str(e)}"
        }),"")
        return format_response({
            "status": "error",
            "message": f"MusicDL 启动失败: {str(e)}"
        }, 500)

@app.route("/music/ffm", methods=["GET", "POST"])
def handle_music_ffm():
    """接收 /music/ffm 请求：单开线程执行 ffmrun()"""
    global ffmpeg_thread
    try:
        print("🧵 正在单开线程运行 ffmrun()...")
        ffmpeg_thread = threading.Thread(target=ffmrun, daemon=True)
        ffmpeg_thread.start()
        return format_response({
            "status": "ok",
            "message": "ffmrun() 已在后台单开线程成功启动"
        }, 200)
    except Exception as e:
        print(f"❌ ffmrun 启动失败: {e}")
        return format_response({
            "status": "error",
            "message": f"ffmrun 启动失败: {str(e)}"
        }, 500)

@app.route("/music/stop", methods=["GET", "POST"])
def handle_music_stop():
    """接收 /music/stop 请求：清理端口、强杀进程、关闭 musicdl 线程及 ffm 线程"""
    try:
        stop_musicdl_services()
        return format_response({
            "status": "ok",
            "message": "MusicDL 进程及 37777 端口已清理，MusicDL 与 ffm 线程已停止"
        }, 200)
    except Exception as e:
        print(f"❌ MusicDL 终止失败: {e}")
        return format_response({
            "status": "error",
            "message": f"MusicDL 终止失败: {str(e)}"
        }, 500)

# ==================== 新增：Cpolar 控制路由 ====================

@app.route("/cp/start", methods=["GET", "POST"])
def handle_cp_start():
    """接收 /cp/start 请求：启动隧道、开启端口转发并等待公网地址上线，设置 30 分钟自动关闭"""
    global auto_stop_timer ,cpurls
    try:
        # 1. 启动本地 25568 端口转发路由任务
        start_port_forwarding(port=25568)

        # 2. 使用 asyncio.run 驱动异步独立函数
        urls = zCpolar.start_cpolar_tunnel(port=25568)
        if urls != []:
            
            cpurls = urls
            # 先取消之前的定时器
            cancel_existing_timer()
            
            # 设置 30 分钟 (1800 秒) 自动停止定时器
            with timer_lock:
                auto_stop_timer = threading.Timer(1800, auto_stop_task)
                auto_stop_timer.daemon = True
                auto_stop_timer.start()

            msg = f"Cpolar 隧道启动成功，当前公网地址: {urls} (将在 30 分钟后自动关闭)"
            PerseusNotifyMsg(msg, "")
            PerseusNotifyMsg(f"\n Alas:\n {urls[0]} \n Bot \n{urls[0]+"/assets/index.html"}","")
            return format_response({"status": "ok", "message": msg, "urls": urls}, 200)
        else:
            stop_port_forwarding()  # 启动失败时回滚端口转发
            PerseusWarningMsg(str({"status": "error", "message": "Cpolar 隧道启动失败或未响应"}),"")
            return format_response({"status": "error", "message": "Cpolar 隧道启动失败或未响应"}, 500)
    except Exception as e:
        stop_port_forwarding()  # 发生异常时回滚端口转发
        print(f"❌ Cpolar 启动异常: {e}")
        PerseusErrorMsg("Cpolar 启动异常", str(e))
        return format_response({"status": "error", "message": f"Cpolar 启动失败: {str(e)}"}, 500)

@app.route("/cp/stop", methods=["GET", "POST"])
def handle_cp_stop():
    """接收 /cp/stop 请求：停止隧道并结束端口转发任务"""
    try:
        # 1. 取消倒计时定时器
        cancel_existing_timer()

        # 2. 关闭端口转发任务
        stop_port_forwarding()

        # 3. 关闭 Cpolar 隧道
        zCpolar.stop_cpolar_tunnel()
        msg = "Cpolar 隧道及端口转发已成功停止"
        PerseusNotifyMsg(msg, "")
        return format_response({"status": "ok", "message": msg}, 200)
    except Exception as e:
        print(f"❌ Cpolar 停止异常: {e}")
        PerseusErrorMsg("Cpolar 停止异常", str(e))
        return format_response({"status": "error", "message": f"Cpolar 停止失败: {str(e)}"}, 500)

@app.route("/cp/get", methods=["GET", "POST"])
def handle_cp_get():
    """接收 /cp/get 请求：单纯查询当前公网地址"""
    try:
        global cpurls
        urls = cpurls
        PerseusNotifyMsg(f"\n Alas:\n {urls[0]} \n Bot \n{urls[0]+"/assets/index.html"}","")
        return format_response({"status": "ok", "urls": f"\n Alas:\n {urls[0]} \n Bot \n{urls[0]+"/assets/index.html"}"}, 200)
    except Exception as e:
        print(f"❌ Cpolar 地址获取异常: {e}")
        return format_response({"status": "error", "message": f"获取公网地址失败: {str(e)}"}, 500)


# 太好了，是LK，我们没救了
# 支持缺省参数的路由配置
@app.route("/lk", defaults={"book_id": None, "only": None, "cache": None}, methods=["GET", "POST"])
@app.route("/lk/<book_id>", defaults={"only": None, "cache": None}, methods=["GET", "POST"])
@app.route("/lk/<book_id>/<only>", defaults={"cache": None}, methods=["GET", "POST"])
@app.route("/lk/<book_id>/<only>/<cache>", methods=["GET", "POST"])
def handle_lk_crawl(book_id, only, cache):
    # 缺少 book_id 直接拒绝
    if not book_id:
        return format_response({"status": "error", "message": "缺少必要的 book_id 参数"}, 400)

    req_data = {}

    # 第一层 try：解析请求参数
    try:
        req_data.update(request.args.to_dict())
        req_data.update(request.form.to_dict())
        if request.is_json:
            json_data = request.get_json(silent=True)
            if json_data and isinstance(json_data, dict):
                req_data.update(json_data)

        # 解析 bool 参数：优先读取 URL Path，如果未指定则读取 query/body 中的参数，默认 False
        only_redownload_images = parse_bool(
            only if only is not None else req_data.get("only_redownload_images", False)
        )
        use_cache_only = parse_bool(
            cache if cache is not None else req_data.get("use_cache_only", False)
        )

        print("\n========================================")
        print(f"【/lk/{book_id} 收到消息】内容：")
        print(f"book_id: {book_id}, only_redownload_images: {only_redownload_images}, use_cache_only: {use_cache_only}")
        print(json.dumps(req_data, ensure_ascii=False, indent=4))
        print("========================================\n")

        # 第二层 try：独占控制与开启后台线程
        try:
            str_book_id = str(book_id)

            with task_lock:
                # 检查是否存在正在运行的任务
                if current_task["task"] is not None and not current_task["task"].done():
                    running_id = current_task["book_id"]
                    
                    # 相同 ID：不重复启动
                    if running_id == str_book_id:
                        return format_response({
                            "status": "warning", 
                            "message": f"book_id: {str_book_id} 已经在运行中，请勿重复发起"
                        }, 200)
                    
                    # 不同 ID：先停止正在运行的旧任务
                    print(f"【检测到新任务】自动取消旧任务 book_id: {running_id}")
                    old_loop = current_task["loop"]
                    old_task = current_task["task"]
                    if old_loop and old_task:
                        old_loop.call_soon_threadsafe(old_task.cancel)

            # 任务执行体
            def async_task():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                async_job = loop.create_task(
                    crawl_lightnovel_to_epub(
                        book_id=str_book_id,
                        only_redownload_images=only_redownload_images,
                        use_cache_only=use_cache_only,
                    )
                )

                # 更新全局独占句柄
                with task_lock:
                    current_task["book_id"] = str_book_id
                    current_task["loop"] = loop
                    current_task["task"] = async_job

                try:
                    run_result = loop.run_until_complete(async_job)
                    PerseusNotifyMsg(str(run_result), "")
                except asyncio.CancelledError:
                    print(f"【后台任务已被手动/抢占终止】book_id: {str_book_id}")
                    PerseusNotifyMsg(f"book_id {str_book_id} 任务已终止", "")
                except Exception as inner_e:
                    print(f"【后台异步任务执行失败】: {inner_e}")
                    PerseusNotifyMsg(f"爬取失败: {inner_e}", "")
                finally:
                    # 运行结束或中断后，清理当前独占记录
                    with task_lock:
                        if current_task["book_id"] == str_book_id:
                            current_task["book_id"] = None
                            current_task["loop"] = None
                            current_task["task"] = None
                    loop.close()

            # 启动独立线程
            thread = threading.Thread(target=async_task)
            thread.daemon = True
            thread.start()

        except Exception as task_e:
            print(f"【创建/启动异步线程失败】: {task_e}")
            return format_response(
                {"status": "error", "message": f"开启异步任务失败: {task_e}"}, 500
            )

    except Exception as req_e:
        print(f"【请求参数解析失败】: {req_e}")
        return format_response(
            {"status": "error", "message": f"请求解析异常: {req_e}"}, 400
        )

    # 及时返回
    return format_response(
        {"status": "success", "message": f"已成功提交后台任务，book_id: {book_id}"}, 200
    )


@app.route("/lk/stop", methods=["GET", "POST"])
def handle_lk_stop():
    """直接结束当前正在运行的任务"""
    try:
        with task_lock:
            running_id = current_task["book_id"]
            loop = current_task["loop"]
            task = current_task["task"]

            if task is None or task.done():
                return format_response(
                    {"status": "info", "message": "当前没有正在运行的爬取任务"}, 200
                )

            # 触发异步取消
            loop.call_soon_threadsafe(task.cancel)

        return format_response(
            {"status": "success", "message": f"已成功发送停止信号，结束任务 book_id: {running_id}"}, 200
        )

    except Exception as e:
        print(f"【停止任务失败】: {e}")
        return format_response(
            {"status": "error", "message": f"停止任务操作异常: {e}"}, 500
        )


def main():
    request_admin_privileges(max_retries=5)
    kill_port_process(LISTEN_PORT)
    start_alas_mumu_check_timer()

    print(f"OnePush接收服务已启动（已获取管理员权限），监听端口：{LISTEN_PORT}")
    PerseusNotifyMsg(
        "OnePush 服务启动成功", 
        f"服务已成功绑定端口 {LISTEN_PORT} 并开始监听请求。"
    )
    print(f"访问地址示例：http://127.0.0.1:{LISTEN_PORT}/push")
    print("Server,启动启动启动")
    app.run(host="0.0.0.0", port=LISTEN_PORT, debug=False)

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
