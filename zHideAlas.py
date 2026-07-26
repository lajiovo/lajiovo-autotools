import sys
import ctypes
import time
import win32gui
import win32process
import win32con
import win32ui
import win32api
import psutil
from PIL import Image
import numpy as np
from zPlaywright import is_site_accessible


# ---------------------------------------------------------------------------
# 0. 管理员权限检查与自动提权
# ---------------------------------------------------------------------------
def is_admin():
    """检查当前进程是否具备管理员权限"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def elevate_privileges():
    """如果不是管理员，自动唤起 UAC 申请管理员权限运行本脚本"""
    if not is_admin():
        print("🔑 检测到当前未开启管理员权限，正在请求提权...")
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(f'"{a}"' for a in sys.argv), None, 1
        )
        sys.exit(0)


# 1. 开启高分屏 DPI 感知
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

TARGET_PROCESS = "alas-launcher.exe"
TARGET_TITLE = "AzurPilot"

COLOR_BLUE = (59, 130, 246)   # #3B82F6 (蓝色按钮)
COLOR_YELLOW = (254, 188, 46) # #FEBC2E (黄色最小化按钮)


def get_azurpilot_hwnd(include_iconic=False):
    """获取 AzurPilot 窗口句柄"""
    target_hwnd = None
    def enum_windows_callback(hwnd, extra):
        nonlocal target_hwnd
        if win32gui.IsWindow(hwnd) and win32gui.IsWindowVisible(hwnd):
            if not include_iconic and win32gui.IsIconic(hwnd):
                return True
            
            title = win32gui.GetWindowText(hwnd)
            if TARGET_TITLE.lower() in title.lower():
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                try:
                    proc = psutil.Process(pid)
                    if proc.name().lower() == TARGET_PROCESS.lower():
                        target_hwnd = win32gui.GetAncestor(hwnd, win32con.GA_ROOT) or hwnd
                        return False
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        return True
    win32gui.EnumWindows(enum_windows_callback, None)
    return target_hwnd


def capture_title_bar(left, top, width, height):
    """通过 BitBlt 将屏幕指定区域一次性拉取到内存中"""
    if width <= 0 or height <= 0:
        return None

    hwnd_dc = win32gui.GetDC(0)
    mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
    save_dc = mfc_dc.CreateCompatibleDC()

    save_bitmap = win32ui.CreateBitmap()
    save_bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
    save_dc.SelectObject(save_bitmap)

    save_dc.BitBlt((0, 0), (width, height), mfc_dc, (left, top), win32con.SRCCOPY)

    bmpinfo = save_bitmap.GetInfo()
    bmpstr = save_bitmap.GetBitmapBits(True)

    win32gui.DeleteObject(save_bitmap.GetHandle())
    save_dc.DeleteDC()
    mfc_dc.DeleteDC()
    win32gui.ReleaseDC(0, hwnd_dc)

    img = Image.frombuffer(
        'RGB',
        (bmpinfo['bmWidth'], bmpinfo['bmHeight']),
        bmpstr, 'raw', 'BGRX', 0, 1
    )
    return img


def find_color_in_image(img, target_rgb, tolerance=15):
    """在 PIL 图片中快速查找目标颜色（容差 tolerance=15）"""
    if not img:
        return None, None

    arr = np.array(img)
    tr, tg, tb = target_rgb

    mask = (
        (np.abs(arr[:, :, 0] - tr) <= tolerance) &
        (np.abs(arr[:, :, 1] - tg) <= tolerance) &
        (np.abs(arr[:, :, 2] - tb) <= tolerance)
    )

    matches = np.argwhere(mask)
    if len(matches) > 0:
        first_match = matches[0]
        return int(first_match[1]), int(first_match[0])
    
    return None, None


def send_click_to_hwnd(hwnd, rel_x, rel_y):
    """
    【方案 1】通过后台 Win32 消息直接注入点击，完全不受物理鼠标移动影响
    """
    if not hwnd or not win32gui.IsWindow(hwnd):
        return False
        
    # 打包坐标：低 16 位为 X 轴相对坐标，高 16 位为 Y 轴相对坐标
    lparam = win32api.MAKELONG(rel_x, rel_y)

    print(f"🎯 [后台点击消息] 正在向 HWND:{hwnd} 相对坐标 ({rel_x}, {rel_y}) 发送后台点击...")

    # 1. 发送鼠标移动/悬停消息
    win32api.PostMessage(hwnd, win32con.WM_MOUSEMOVE, 0, lparam)
    time.sleep(0.02)
    
    # 2. 发送鼠标左键按下消息
    win32api.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lparam)
    time.sleep(0.05)
    
    # 3. 发送鼠标左键抬起消息
    win32api.PostMessage(hwnd, win32con.WM_LBUTTONUP, 0, lparam)
    time.sleep(0.02)
    return True


def force_hide_window(hwnd):
    """【系统级直接隐藏】底层 Win32 API 强制隐藏"""
    if not hwnd or not win32gui.IsWindow(hwnd):
        return False
    
    try:
        print(f"🛡️ 正在使用系统底层 API 直接隐藏窗口 (HWND: {hwnd})...")
        # 1. 异步隐藏 (SW_HIDE = 0)
        ctypes.windll.user32.ShowWindowAsync(hwnd, 0)
        # 2. 兜底直接隐藏
        win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
        # 3. 移出桌面视野
        win32gui.SetWindowPos(
            hwnd, 0, -10000, -10000, 0, 0,
            win32con.SWP_NOSIZE | win32con.SWP_NOZORDER | win32con.SWP_HIDEWINDOW
        )
        print("✅ 系统底层强制隐藏成功！")
        return True
    except Exception as e:
        print(f"❌ 系统隐藏窗口失败: {e}")
        return False


def click_hide_azurpilot_window(hwnd):
    """通过内存截取标题栏，匹配颜色后直接采用 PostMessage 发送后台点击"""
    if not hwnd or not win32gui.IsWindow(hwnd):
        return 0

    rect = win32gui.GetWindowRect(hwnd)
    left, top, right, bottom = rect
    width = right - left
    height = min(60, bottom - top)

    print(f"窗口范围: Left={left}, Top={top}, Right={right}, Bottom={bottom} (截取标题栏: {width}x{height})")

    img = capture_title_bar(left, top, width, height)
    if not img:
        print("❌ 截图失败。")
        return 0

    click_code = 0
    target_name = ""

    # 优先 1：匹配蓝色按键
    print("🔍 [步骤 1] 正在匹配蓝色按键 (#3B82F6)...")
    rel_x, rel_y = find_color_in_image(img, COLOR_BLUE)

    if rel_x is not None:
        click_code = 1
        target_name = "蓝色按键 (#3B82F6)"
    else:
        # 优先 2：匹配黄色按键
        print("⚠️ 未匹配到蓝色，[步骤 2] 正在匹配黄色最小化按键 (#FEBC2E)...")
        rel_x, rel_y = find_color_in_image(img, COLOR_YELLOW)
        if rel_x is not None:
            click_code = 2
            target_name = "黄色最小化按键 (#FEBC2E)"

    if rel_x is not None and rel_y is not None:
        # 计算相对于窗口左上角的点击偏移
        click_x = rel_x + 2
        click_y = rel_y + 2
        print(f"🎉 成功锁定【{target_name}】！窗口内相对坐标: ({click_x}, {click_y})")
        
        # 使用 PostMessage 后台无感点击
        send_click_to_hwnd(hwnd, click_x, click_y)
        print("后台点击消息发送完成！")
        return click_code
    else:
        print("❌ 未在标题栏区域找到蓝色 (#3B82F6) 或黄色 (#FEBC2E) 目标按键。")
        return 0


def process_single_stage_window(hwnd):
    """完整隐藏全套逻辑：后台点击 -> 状态校验 -> 再次后台点击 -> 底层 API 隐藏兜底"""
    print(f"\n--- 开始对窗口 (HWND: {hwnd}) 执行隐藏全套逻辑 ---")
    
    # 1. 首次后台点击尝试
    status = click_hide_azurpilot_window(hwnd)
    time.sleep(0.6)

    # 2. 检查窗口是否依然处于“非最小化”显示状态
    current_hwnd = get_azurpilot_hwnd(include_iconic=False)
    if current_hwnd == hwnd:
        print("⚠️ 检测到窗口依然处于显示状态（非最小化），尝试第二次后台点击...")
        status = click_hide_azurpilot_window(hwnd)
        time.sleep(0.6)

    # 3. 检查窗口是否依然存在（不论展开还是最小化）
    any_hwnd = get_azurpilot_hwnd(include_iconic=True)
    if any_hwnd == hwnd:
        print("⚠️ 后台点击后窗口依然存在，启动系统底层强制隐藏兜底...")
        force_hide_window(hwnd)
    else:
        print("✅ 窗口已通过后台消息成功隐藏/关闭。")

    return status


def cleanup():
    """去初始化清理资源"""
    print("🧹 [去初始化] 模块清理完成。")


def smart_hide_azurpilot(timeout=300, retry_interval=60):
    """智能隐藏 AzurPilot 窗口主逻辑"""
    elevate_privileges()

    start_time = time.time()
    first_hwnd = None
    first_size = None
    status = 0

    try:
        print("⏳ 开始等待并处理第一个 AzurPilot 窗口（超时上限 5 分钟）...")

        # ----------------------------------------------------
        # 阶段 1：首窗检测与处理
        # ----------------------------------------------------
        while time.time() - start_time < timeout:
            first_hwnd = get_azurpilot_hwnd(include_iconic=False)
            if first_hwnd:
                r = win32gui.GetWindowRect(first_hwnd)
                first_size = (r[2] - r[0], r[3] - r[1])
                print(f"✅ 捕获到首个窗口，尺寸: {first_size[0]}x{first_size[1]}")
                
                status = process_single_stage_window(first_hwnd)
                break
            else:
                time.sleep(1)

        if not first_hwnd:
            print("⏰ 等待第一个窗口超时。")
            return 0

        # 如果首窗通过蓝色按钮点击且已被彻底处理，不需要等待第二窗口
        if status == 1 and not get_azurpilot_hwnd(include_iconic=True):
            print("✨ 首窗后台蓝色点击成功，任务完成！")
            return 1

        # ----------------------------------------------------
        # 阶段 2：等待并处理第二个（不同尺寸）窗口
        # ----------------------------------------------------
        print("⚠️ 准备等待不同尺寸的新窗口出现（总上限 5 分钟）...")

        while time.time() - start_time < timeout:
            time.sleep(1)
            new_hwnd = get_azurpilot_hwnd(include_iconic=False)
            if new_hwnd and new_hwnd != first_hwnd:
                nr = win32gui.GetWindowRect(new_hwnd)
                new_size = (nr[2] - nr[0], nr[3] - nr[1])

                if new_size != first_size:
                    print(f"🔍 发现新尺寸窗口: {new_size[0]}x{new_size[1]} (HWND: {new_hwnd})")
                    second_status = process_single_stage_window(new_hwnd)
                    print(f"🎉 第二个窗口处理完毕，结果代码: {second_status}")
                    return second_status

        print("⏰ 5 分钟超时，未检测到第二个新尺寸窗口。")
        return status

    finally:
        cleanup()


if __name__ == "__main__":
    smart_hide_azurpilot()
