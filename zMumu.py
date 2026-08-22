import os
import sys
import time
import ctypes
import subprocess
import traceback
import psutil
import win32gui
import win32con
from pynput.keyboard import Key, Controller
from zBarkCustom import PerseusNotifyMsg, PerseusErrorMsg, PerseusWarningMsg

# 初始化 pynput 键盘控制器
keyboard = Controller()

# ==================== 配置常量 ====================
from zConfig import get_config

# 路径配置
MUMU_MAIN_PATH = get_config("mumu.paths.main_path")
MUMU_DEVICE_PATH = get_config("mumu.paths.device_path")

# 是否隐藏窗口控制 (True = 隐藏启动, False = 正常显示启动)
HIDE_MUMU = get_config("mumu.window.hide_mumu", default=False)

# 核心参数设置
LOOP_MIN_DURATIONmax = get_config("mumu.runtime.loop_min_duration_max")
LOOP_MIN_DURATIONmin = get_config("mumu.runtime.loop_min_duration_min")
CHECK_INTERVAL = get_config("mumu.runtime.check_interval", default=2)
HIDE_TIMEOUT = get_config("mumu.runtime.hide_timeout", default=30)
MAX_ATTEMPTS = get_config("mumu.runtime.max_attempts", default=2)
# ==================================================

def is_admin():
    """检查当前程序是否以系统管理员权限运行"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False

def run_as_admin():
    """如果当前不是管理员权限，重新以管理员身份运行当前脚本"""
    if not is_admin():
        print("正在尝试获取系统管理员权限提权...")
        try:
            # 重新以管理员权限启动当前 python 脚本
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, " ".join(f'"{arg}"' for arg in sys.argv), None, 1
            )
            sys.exit(0)
        except Exception as e:
            print(f"获取管理员权限失败: {e}")

def mumu_kill():
    """强制结束所有含 'mumu' 关键词的进程"""
    print("正在结束所有 MuMu 进程...")
    for proc in psutil.process_iter(['name']):
        try:
            name = proc.info['name'].lower()
            if "mumu" in name:
                proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    time.sleep(2)  # 等待进程彻底释放
    print("MuMu 进程清杀完毕。")

def is_mumu_running():
    """检查 mumumain 和 mumudevice 是否都在运行"""
    running_processes = []
    for proc in psutil.process_iter(['name']):
        try:
            running_processes.append(proc.info['name'].lower())
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
            
    main_running = any("mumunxmain" in p or "mumumain" in p for p in running_processes)
    device_running = any("mumunxdevice" in p or "mumudevice" in p for p in running_processes)
    return main_running and device_running

def start_process(path, hide=False):
    """通用进程启动方法（支持隐藏启动）"""
    try:
        if hide and sys.platform == "win32":
            cmd = f'powershell -ExecutionPolicy Bypass -Command "Start-Process \'{path}\' -WindowStyle Hidden"'
            subprocess.Popen(cmd, shell=True)
        else:
            subprocess.Popen(path)
        print(f"成功启动进程: {path}")
    except Exception as e:
        err_msg = f"启动进程失败 {path}: {e}"
        print(err_msg)
        try:
            PerseusErrorMsg("MuMu Launch Error", f"[0015] {err_msg}")
        except Exception:
            pass

def get_real_mumu_hwnds():
    """获取所有符合条件的真实可见 MuMu 窗口句柄列表"""
    window_keywords = ["MuMu", "MuMuPlayer", "MuMuNxMain"]
    black_keywords = ["aiot ide"]  # 排除黑名单
    hwnds = []

    def enum_windows_callback(hwnd, extra):
        if not win32gui.IsWindowVisible(hwnd):
            return True
            
        title = win32gui.GetWindowText(hwnd).strip()
        if not title:
            return True
            
        title_lower = title.lower()

        # 核心：如果命中黑名单，排除
        if any(blk in title_lower for blk in black_keywords):
            return True

        # 检查是否满足 MuMu 的关键词
        if any(kw.lower() in title_lower for kw in window_keywords):
            # 检查窗口大小，排除无画面的后台组件
            rect = win32gui.GetWindowRect(hwnd)
            width = rect[2] - rect[0]
            height = rect[3] - rect[1]
            if width > 100 and height > 100:
                print(f"-> 捕捉到窗口: '{title}' [{width}x{height}] HWND: {hwnd}")
                hwnds.append(hwnd)
        return True

    try:
        win32gui.EnumWindows(enum_windows_callback, None)
    except Exception:
        pass
        
    return hwnds

def hide_hwnd_admin(hwnd):
    """使用 Win32 API 强制隐藏指定 HWND 的窗口"""
    try:
        # SW_HIDE = 0
        ctypes.windll.user32.ShowWindow(hwnd, win32con.SW_HIDE)
        print(f"  └─ 已调用系统 API 强制隐藏句柄 HWND: {hwnd}")
    except Exception as e:
        print(f"  └─ API 隐藏句柄 {hwnd} 失败: {e}")

def send_hide_hotkey():
    """使用 pynput 发送 Ctrl + Alt + Right 快捷键"""
    with keyboard.pressed(Key.ctrl), keyboard.pressed(Key.alt):
        keyboard.press(Key.right)
        keyboard.release(Key.right)

def hidemumu_attempt():
    """单次启动与隐藏操作，成功返回 True，超时失败返回 False"""
    global HIDE_MUMU
    
    # 1. 检查关键进程是否在运行
    if not is_mumu_running():
        print("检测到 mumumain 或 mumudevice 未在运行")
        loop_min_duration = LOOP_MIN_DURATIONmax
        # 2. 启动 MuMu Main 和 Device
        print(f"开始处理 MuMu 自动化启动（隐藏模式: {HIDE_MUMU}）...")
        start_process(MUMU_MAIN_PATH, hide=HIDE_MUMU)
        start_process(MUMU_DEVICE_PATH, hide=HIDE_MUMU)
    else:
        loop_min_duration = LOOP_MIN_DURATIONmin
    
    # 3. 循环检测窗口并执行组合技
    print(f"进入窗口检测循环，检测间隔 {CHECK_INTERVAL}s，最少持续 {loop_min_duration}s，超时限制 {HIDE_TIMEOUT}s...")
    
    start_time = time.time()
    
    while True:
        elapsed_time = time.time() - start_time
        
        # 30 秒超时判定
        if elapsed_time > HIDE_TIMEOUT:
            print(f"⚠️ [警告] 尝试隐藏超时（已耗时 {int(elapsed_time)}s > {HIDE_TIMEOUT}s），本次隐藏失败！")
            return False

        # 精确获取肉眼可见的 MuMu 窗口句柄
        mumu_hwnds = get_real_mumu_hwnds()
        
        if mumu_hwnds:
            print(f"[{int(elapsed_time)}s] 确实存在 {len(mumu_hwnds)} 个 MuMu 实体窗口，触发组合技 (管理员API隐藏 + 快捷键)...")
            
            # 【组合技 1】：利用管理员 API 权限强制隐藏每一个找到的句柄
            for hwnd in mumu_hwnds:
                hide_hwnd_admin(hwnd)
            
            # 【组合技 2】：发送系统全局快捷键
            print(f"  └─ 发送快捷键: Ctrl + Alt + Right")
            send_hide_hotkey()
        else:
            print(f"[{int(elapsed_time)}s] 当前未检测到真实的 MuMu 实体窗口...")
            # 如果已经超过最少持续时间且无窗口，说明窗口已被成功隐藏/关闭
            if elapsed_time >= loop_min_duration:
                print(f"已满 {loop_min_duration} 秒且无显示窗口，隐藏操作成功完成！")
                return True
                
        # 严格保持每次检测/操作间隔 2 秒
        time.sleep(CHECK_INTERVAL)

def hidemumu() -> list:
    """
    主控制入口：带有 30s 超时 kill 重试机制（最多运行 MAX_ATTEMPTS 次）
    返回值：[bool (是否成功), str (信息代码), str (详细描述信息/报错 Traceback)]
    """
    # 确保拥有管理员权限
    run_as_admin()

    try:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            print(f"\n==================== 开始第 {attempt}/{MAX_ATTEMPTS} 次尝试隐藏 MuMu ====================")
            
            success = hidemumu_attempt()
            if success:
                msg = f"第 {attempt} 次尝试即成功隐藏 MuMu 窗口。"
                print(msg)
                return [True, "0011", msg]
            
            # 如果超时且还有剩余重试次数，执行 kill 并准备下一次重试
            if attempt < MAX_ATTEMPTS:
                warn_msg = f"第 {attempt} 次隐藏超时（>{HIDE_TIMEOUT}s），准备清理进程并进行下一次重试..."
                print(warn_msg)
                
                # 【推送警告通知】
                try:
                    PerseusWarningMsg("MuMu Hide Timeout Warning", warn_msg)
                except Exception:
                    pass
                    
                mumu_kill()
                time.sleep(1)
            else:
                msg = f"已达到最大重试次数 ({MAX_ATTEMPTS} 次)，依然未能成功隐藏 MuMu 窗口。"
                print(msg)
                
                # 【推送失败报错】
                try:
                    PerseusErrorMsg("MuMu Hide Failed", f"[0012] {msg}")
                except Exception:
                    pass
                    
                return [False, "0012", msg]

        msg = "未知错误：未执行任何尝试。"
        try:
            PerseusErrorMsg("MuMu Hide Unknown Error", f"[0013] {msg}")
        except Exception:
            pass
        return [False, "0013", msg]

    except Exception as e:
        err_detail = traceback.format_exc()
        full_err_msg = f"程序抛出异常: {e}\n详细堆栈信息:\n{err_detail}"
        print("❌ [错误] hidemumu 执行过程中发生异常:")
        print(err_detail)
        
        # 【推送致命异常报错】
        try:
            PerseusErrorMsg("MuMu Hide Exception", f"[0014] {full_err_msg}")
        except Exception:
            pass
            
        return [False, "0014", full_err_msg]

if __name__ == "__main__":
    result = hidemumu()
    print("\n---------------- 执行结果 ----------------")
    print(f"是否成功: {result[0]}")
    print(f"信息代码: {result[1]}")
    print(f"说明信息:\n{result[2]}")
    print("------------------------------------------")
    print("脚本执行完毕。")

