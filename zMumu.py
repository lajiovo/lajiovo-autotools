import os
import sys
import time
import subprocess
import pyautogui
import psutil
import win32gui

# ==================== 配置常量 ====================
MUMU_MAIN_PATH = r"\MuMuPlayer\nx_main\MuMuNxMain.exe"
MUMU_DEVICE_PATH = r"\MuMuPlayer\nx_device\12.0\shell\MuMuNxDevice.exe"

# 是否隐藏窗口控制 (True = 隐藏启动, False = 正常显示启动)
HIDE_MUMU = False

# 核心参数设置
LOOP_MIN_DURATIONmax = 20  # 窗口检测循环的最少持续时间（秒）
LOOP_MIN_DURATIONmin = 10
CHECK_INTERVAL = 2      # 严格间隔 2 秒
# ==================================================

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
        print(f"启动进程失败 {path}: {e}")

def has_real_mumu_window():
    """使用 Windows API 过滤：必须是含关键词、肉眼可见、真实大小，且排除 AIoT IDE 的窗口"""
    window_keywords = ["MuMu", "MuMuPlayer", "MuMuNxMain"]
    black_keywords = ["aiot ide"]  # 排除黑名单
    found_real_window = False

    def enum_windows_callback(hwnd, extra):
        nonlocal found_real_window
        # 1. 过滤掉不可见的窗口
        if not win32gui.IsWindowVisible(hwnd):
            return True
            
        title = win32gui.GetWindowText(hwnd).strip()
        if not title:
            return True
            
        title_lower = title.lower()

        # 2. 核心：如果命中黑名单，直接排除
        if any(blk in title_lower for blk in black_keywords):
            return True

        # 3. 检查是否满足 MuMu 的关键词
        if any(kw.lower() in title_lower for kw in window_keywords):
            # 4. 检查窗口大小，排除无画面的后台组件
            rect = win32gui.GetWindowRect(hwnd)
            width = rect[2] - rect[0]
            height = rect[3] - rect[1]
            if width > 100 and height > 100:
                print(f"-> 成功捕捉到真实可见窗口: '{title}' [{width}x{height}]")
                found_real_window = True
                return False  # 找到了，停止枚举
        return True

    try:
        win32gui.EnumWindows(enum_windows_callback, None)
    except Exception:
        pass
        
    return found_real_window

def hidemumu():
    """启动 MuMu 并检测窗口进行隐藏快捷键操作"""
    global HIDE_MUMU
    
    # 1. 检查关键进程是否在运行
    if not is_mumu_running():
        print("检测到 mumumain 或 mumudevice 未在运行")
        LOOP_MIN_DURATION = LOOP_MIN_DURATIONmax
        # 2. 启动 MuMu Main 和 Device
        print(f"开始处理 MuMu 自动化启动（隐藏模式: {HIDE_MUMU}）...")
        start_process(MUMU_MAIN_PATH, hide=HIDE_MUMU)
        start_process(MUMU_DEVICE_PATH, hide=HIDE_MUMU)
    else:
        LOOP_MIN_DURATION = LOOP_MIN_DURATIONmin
    
    # 3. 循环检测窗口并发送快捷键
    print(f"进入窗口检测循环，检测间隔 {CHECK_INTERVAL}s，至少持续 {LOOP_MIN_DURATION} 秒...")
    
    start_time = time.time()
    
    while True:
        elapsed_time = time.time() - start_time
        
        # 精确检查是否存在肉眼可见的 MuMu 窗口
        window_exists = has_real_mumu_window()
        
        if window_exists:
            print(f"[{int(elapsed_time)}s] 确实存在 MuMu 实体窗口，正在发送快捷键: Ctrl + Alt + Right")
            pyautogui.hotkey('ctrl', 'alt', 'right')
        else:
            print(f"[{int(elapsed_time)}s] 当前未检测到真实的 MuMu 实体窗口...")
            # 如果已经超过最少持续时间且无窗口，退出循环
            if elapsed_time >= LOOP_MIN_DURATION:
                print(f"已满 {LOOP_MIN_DURATION} 秒且未检测到窗口，安全退出循环。")
                break
                
        # 严格保持每次检测/操作间隔 2 秒
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    # 如果需要先清理环境，可以在这里手动调用 mumu_kill()
    # mumu_kill()
    
    hidemumu()
    print("脚本执行完毕。")
