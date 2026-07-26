import os
import sys
import time
import subprocess
import traceback
import psutil
import win32gui
from pynput.keyboard import Key, Controller
import zPerseusLogger

# 初始化 pynput 键盘控制器
keyboard = Controller()

# ==================== 配置常量 ====================
MUMU_MAIN_PATH = r"\MuMuPlayer\nx_main\MuMuNxMain.exe"
MUMU_DEVICE_PATH = r"\MuMuPlayer\nx_device\12.0\shell\MuMuNxDevice.exe"

# 是否隐藏窗口控制 (True = 隐藏启动, False = 正常显示启动)
HIDE_MUMU = False

# 核心参数设置
LOOP_MIN_DURATIONmax = 20  # 窗口检测循环的最少持续时间（秒）
LOOP_MIN_DURATIONmin = 10
CHECK_INTERVAL = 2       # 严格间隔 2 秒
HIDE_TIMEOUT = 30        # 尝试隐藏超时限制（秒）
MAX_ATTEMPTS = 2         # 最多尝试次数（初始 1 次 + kill 后重试 1 次）
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

def send_hide_hotkey():
    """使用 pynput 安全发送 Ctrl + Alt + Right 快捷键"""
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
    
    # 3. 循环检测窗口并发送快捷键
    print(f"进入窗口检测循环，检测间隔 {CHECK_INTERVAL}s，最少持续 {loop_min_duration}s，超时限制 {HIDE_TIMEOUT}s...")
    
    start_time = time.time()
    
    while True:
        elapsed_time = time.time() - start_time
        
        # 30 秒超时判定
        if elapsed_time > HIDE_TIMEOUT:
            print(f"⚠️ [警告] 尝试隐藏超时（已耗时 {int(elapsed_time)}s > {HIDE_TIMEOUT}s），本次隐藏失败！")
            return False

        # 精确检查是否存在肉眼可见的 MuMu 窗口
        window_exists = has_real_mumu_window()
        
        if window_exists:
            print(f"[{int(elapsed_time)}s] 确实存在 MuMu 实体窗口，正在发送快捷键: Ctrl + Alt + Right")
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
    返回值：[bool (是否成功), str (详细描述信息/报错 Traceback)]
    """
    try:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            print(f"\n==================== 开始第 {attempt}/{MAX_ATTEMPTS} 次尝试隐藏 MuMu ====================")
            
            success = hidemumu_attempt()
            if success:
                msg = f"第 {attempt} 次尝试即成功隐藏 MuMu。"
                print(msg)
                return [True, msg]
            
            # 如果超时且还有剩余重试次数，执行 kill 并准备下一次重试
            if attempt < MAX_ATTEMPTS:
                print(f"第 {attempt} 次隐藏超时，准备清理进程并进行下一次重试...")
                mumu_kill()
                time.sleep(1)
            else:
                msg = f"已达到最大重试次数 ({MAX_ATTEMPTS} 次)，依然未能成功隐藏窗口。"
                print(msg)
                return [False, msg]

        return [False, "未知错误：未执行任何尝试。"]

    except Exception as e:
        err_detail = traceback.format_exc()
        print("❌ [错误] hidemumu 执行过程中发生异常:")
        print(err_detail)
        return [False, f"程序抛出异常: {e}\n详细堆栈信息:\n{err_detail}"]

if __name__ == "__main__":
    result = hidemumu()
    print("\n---------------- 执行结果 ----------------")
    print(f"是否成功: {result[0]}")
    print(f"说明信息:\n{result[1]}")
    print("------------------------------------------")
    print("脚本执行完毕。")
