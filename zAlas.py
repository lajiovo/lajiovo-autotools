import sys
import os
import ctypes
import time
import subprocess
import urllib.request
import urllib.error
import win32gui
import win32process
import win32con
import psutil

# 导入自定义通知模块
from zBarkCustom import PerseusErrorMsg, PerseusNotifyMsg

# ==================== 配置常量 ====================
ALAS_PATH = r"\AzurPilot\alas-launcher.exe"
TARGET_PROCESS = "alas-launcher.exe"
TARGET_TITLE = "AzurPilot"
# ==================================================


# ---------------------------------------------------------------------------
# 0. 管理员权限检查与自动提权
# ---------------------------------------------------------------------------
def is_admin():
    """检查当前进程是否具备管理员权限"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def elevate_privileges():
    """如果不是管理员，自动唤起 UAC 申请管理员权限运行本脚本"""
    if not is_admin():
        print("🔑 检测到当前未开启管理员权限，正在请求提权...")
        try:
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, " ".join(f'"{a}"' for a in sys.argv), None, 1
            )
        except Exception as e:
            print(f"❌ 请求管理员权限失败: {e}")
        sys.exit(0)


def is_site_accessible(url="http://127.0.0.1:22267"):
    """轻量级检查目标网页是否可访问"""
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return response.status in (200, 301, 302, 401, 403)
    except Exception:
        return False


def get_azurpilot_hwnds():
    """获取所有符合条件的 AzurPilot 可见窗口句柄列表"""
    hwnds = []
    def enum_windows_callback(hwnd, extra):
        if win32gui.IsWindow(hwnd) and win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if TARGET_TITLE.lower() in title.lower():
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                try:
                    proc = psutil.Process(pid)
                    if proc.name().lower() == TARGET_PROCESS.lower():
                        root_hwnd = win32gui.GetAncestor(hwnd, win32con.GA_ROOT) or hwnd
                        if root_hwnd not in hwnds:
                            hwnds.append(root_hwnd)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        return True
    win32gui.EnumWindows(enum_windows_callback, None)
    return hwnds


def force_hide_window(hwnd):
    """【系统级直接隐藏】底层 Win32 API 强制隐藏"""
    if not hwnd or not win32gui.IsWindow(hwnd):
        return False
    
    try:
        print(f"🛡️ 正在使用系统底层 API 直接隐藏窗口 (HWND: {hwnd})...")
        ctypes.windll.user32.ShowWindowAsync(hwnd, 0)
        win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
        win32gui.SetWindowPos(
            hwnd, 0, -10000, -10000, 0, 0,
            win32con.SWP_NOSIZE | win32con.SWP_NOZORDER | win32con.SWP_HIDEWINDOW
        )
        print("✅ 系统底层强制隐藏成功！")
        return True
    except Exception as e:
        err_msg = f"系统隐藏窗口失败 (HWND: {hwnd}): {e}"
        print(f"❌ {err_msg}")
        raise RuntimeError(err_msg)


# ---------------------------------------------------------------------------
# 1. Cleanup 清理逻辑 (包含黑白名单检查与端口清理)
# ---------------------------------------------------------------------------
def cleanup():
    """
    全清逻辑：清理 alas 及 azurpilot 相关的 python 脚本、GUI 界面以及 22267、22268 端口占用
    返回: [bool, str]
    """
    elevate_privileges()
    
    print("🧹 [Cleanup] 开始执行 Alas 后台全清...")
    EXCLUDE_KEYWORDS = {'auto', 'aiot', 'ide'}
    TARGET_KEYWORDS = {'alas', 'azurpilot'}
    killed_count = 0

    try:
        # 1. 清理进程
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                name_lower = proc.info['name'].lower()
                cmdline = proc.info['cmdline'] or []
                cmdline_str = " ".join(cmdline).lower()
                full_text = f"{name_lower} {cmdline_str}"
                
                if any(ex in full_text for ex in EXCLUDE_KEYWORDS):
                    continue
                
                is_target_py = name_lower.startswith('python') and any(
                    any(kw in arg.lower() for kw in TARGET_KEYWORDS) for arg in cmdline
                )
                is_target_gui = any(kw in full_text for kw in TARGET_KEYWORDS)

                if is_target_py or is_target_gui:
                    print(f"发现目标进程 [{proc.info['name']}] [PID: {proc.pid}]")
                    proc.kill()
                    killed_count += 1
                    print(f"-> 已成功强行终止 PID: {proc.pid}")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        # 2. 清理占用端口
        TARGET_PORTS = {22267, 22268}
        try:
            for conn in psutil.net_connections(kind='inet'):
                if conn.laddr and conn.laddr.port in TARGET_PORTS:
                    port_pid = conn.pid
                    current_port = conn.laddr.port
                    if port_pid:
                        try:
                            p = psutil.Process(port_pid)
                            p_name = p.name().lower()
                            p_cmdline = " ".join(p.cmdline() or []).lower()
                            p_full = f"{p_name} {p_cmdline}"

                            if any(ex in p_full for ex in EXCLUDE_KEYWORDS):
                                continue

                            print(f"发现端口 {current_port} 被进程 '{p.name()}' [PID: {port_pid}] 占用，正在终止...")
                            p.kill()
                            killed_count += 1
                            print(f"-> 已成功释放端口 {current_port} (终止 PID: {port_pid})")
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
        except psutil.AccessDenied:
            print("获取网络连接列表失败，请确保使用管理员权限运行此脚本。")

        detail = f"Alas 后台全清完毕，共清理 {killed_count} 个相关进程/端口占用。"
        print(f"✅ {detail}")
        return [True, detail]

    except Exception as e:
        err_msg = f"全清过程出现异常: {e}"
        print(f"❌ {err_msg}")
        try:
            PerseusErrorMsg("Alas Cleanup Error", err_msg)
        except Exception:
            pass
        return [False, err_msg]


# ---------------------------------------------------------------------------
# 2. Hide 监控并强制隐藏窗口
# ---------------------------------------------------------------------------
def hide(target_count=1):
    """
    智能隐藏 AzurPilot 窗口主逻辑
    :param target_count: 期望隐藏的目标窗口数量（1 或 2）
    返回: [bool, str]
    """
    elevate_privileges()

    start_time = time.time()
    total_timeout = 300.0  # 默认 5 分钟超时时间
    
    hidden_hwnds = set()
    reduced_by_count = False
    reduced_by_site_accessible = False

    print(f"⏳ [Hide] 开始监测并强制隐藏 AzurPilot 窗口（目标隐藏至少 {target_count} 个窗口，总超时 5 分钟）...")

    try:
        while True:
            current_time = time.time()
            elapsed_time = current_time - start_time
            remaining_time = total_timeout - elapsed_time

            # 1. 超时检测：倒计时结束时，判定是否达到了指定的窗口数量 target_count
            if remaining_time <= 0:
                is_success = len(hidden_hwnds) >= target_count
                detail = f"监测结束，设定目标为 {target_count} 个窗口，实际隐藏 {len(hidden_hwnds)} 个窗口"
                print(f"{'⏰' if not is_success else '✅'} {detail}")
                return [is_success, detail]

            # 2. 检测并处理出现的窗口
            try:
                visible_hwnds = get_azurpilot_hwnds()
                for hwnd in visible_hwnds:
                    if hwnd not in hidden_hwnds:
                        if force_hide_window(hwnd):
                            hidden_hwnds.add(hwnd)
                            print(f"🎉 成功隐藏第 {len(hidden_hwnds)} 个窗口 (HWND: {hwnd})")
            except Exception as e:
                err_msg = f"窗口检测/隐藏阶段发生错误: {e}"
                print(f"❌ {err_msg}")
                return [False, err_msg]

            # 3. 条件一：隐藏数量达到 target_count -> 剩余时间上限调整为 <= 10s（仅执行一次）
            if len(hidden_hwnds) >= target_count and not reduced_by_count:
                reduced_by_count = True
                new_remaining = min(remaining_time, 10.0)
                total_timeout = elapsed_time + new_remaining
                print(f"⚡ 已成功隐藏达到目标的 {target_count} 个窗口！剩余超时时间收窄为 {new_remaining:.1f} 秒。")

            # 4. 条件二：is_site_accessible 返回 True -> 剩余时间上限调整为 <= 30s（仅执行一次）
            if not reduced_by_site_accessible:
                try:
                    if is_site_accessible():
                        reduced_by_site_accessible = True
                        current_remaining = total_timeout - (time.time() - start_time)
                        new_remaining = min(current_remaining, 30.0)
                        total_timeout = (time.time() - start_time) + new_remaining
                        print(f"🌐 站点可访问检测通过 (True)！剩余超时时间收窄为 {new_remaining:.1f} 秒。")
                except Exception as e:
                    print(f"⚠️ 站点可访问性检查捕获到异常: {e}")

            time.sleep(1)

    except Exception as e:
        detail = f"隐藏过程中出现未捕获的异常: {e}"
        print(f"❌ {detail}")
        return [False, detail]


# ---------------------------------------------------------------------------
# 3. Start 启动程序并自动调用 hide()
# ---------------------------------------------------------------------------
def start(alas_path=ALAS_PATH, show_window=True):
    """
    主控启动逻辑：先检测是否已运行，已运行传入 hide(1)，未运行拉起后传入 hide(2)
    返回: [bool, str]
    """
    elevate_privileges()

    print(f"🚀 [Start] 开始检测进程 '{TARGET_PROCESS}' 是否已在运行...")

    is_running = False
    for proc in psutil.process_iter(['name']):
        try:
            if proc.info['name'] and proc.info['name'].lower() == TARGET_PROCESS.lower():
                is_running = True
                break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    if is_running:
        print(f"ℹ️ 检测到 {TARGET_PROCESS} 已经在后台运行，跳过启动，调用 hide(1)...")
        target_hide_count = 1
    else:
        # 程序未在运行，需拉起程序，期望捕获后续拉起的 2 个不同阶段/尺寸窗口
        target_hide_count = 2
        if not os.path.exists(alas_path):
            err_msg = f"未找到 Alas 可执行文件，路径不存在: {alas_path}"
            print(f"❌ {err_msg}")
            try:
                PerseusErrorMsg("Alas Launch Failed", err_msg)
            except Exception:
                pass
            return [False, err_msg]

        alas_dir = os.path.dirname(os.path.abspath(alas_path))
        CREATE_NEW_CONSOLE = 0x00000010
        DETACHED_PROCESS = 0x00000008
        creationflags = CREATE_NEW_CONSOLE if show_window else DETACHED_PROCESS

        try:
            print(f"▶️ 未检测到运行进程，正在彻底剥离启动 Alas: {alas_path}")
            subprocess.Popen(
                [alas_path],
                cwd=alas_dir,
                creationflags=creationflags,
                close_fds=True,
            )
            print("✅ Alas 已成功发送剥离启动命令，准备调用 hide(2)...")
        except Exception as e:
            err_msg = f"启动 Alas 过程出现异常: {e}"
            print(f"❌ {err_msg}")
            try:
                PerseusErrorMsg("Alas Launch Exception", err_msg)
            except Exception:
                pass
            return [False, err_msg]

    # 根据运行状态，分别向 hide() 传入 1 或 2 作为目标检测窗口数
    hide_result = hide(target_count=target_hide_count)

    # 根据 hide() 最终返回的布尔结果推送通知
    if hide_result[0]:
        try:
            PerseusNotifyMsg("Success with smart_hide_azurpilot()", hide_result[1])
        except Exception:
            pass
    else:
        try:
            PerseusErrorMsg("Bug with smart_hide_azurpilot()", hide_result[1])
        except Exception:
            pass

    return hide_result


if __name__ == "__main__":
    result = start()
    print(f"\n执行结果: {result}")
