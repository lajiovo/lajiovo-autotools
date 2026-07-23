import zPerseusLogger
import ctypes
import time
import win32gui
import win32process
import win32con
import win32ui
import psutil
import pyautogui
from PIL import Image
import numpy as np

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

# 目标 RGB 色值 (RGB 格式)
COLOR_BLUE = (59, 130, 246)   # #3B82F6 (蓝色按钮)
COLOR_YELLOW = (254, 188, 46) # #FEBC2E (黄色最小化按钮)


def get_azurpilot_hwnd():
    """获取处于显示状态的窗口句柄"""
    target_hwnd = None
    def enum_windows_callback(hwnd, extra):
        nonlocal target_hwnd
        if win32gui.IsWindow(hwnd) and win32gui.IsWindowVisible(hwnd):
            if win32gui.IsIconic(hwnd):  # 过滤最小化窗口
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
    """通过 BitBlt 将屏幕指定区域一次性拉取到内存中，避免 GetPixel 逐点阻塞卡死"""
    if width <= 0 or height <= 0:
        return None

    hwnd_dc = win32gui.GetDC(0)
    mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
    save_dc = mfc_dc.CreateCompatibleDC()

    save_bitmap = win32ui.CreateBitmap()
    save_bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
    save_dc.SelectObject(save_bitmap)

    # 批量内存拷贝
    save_dc.BitBlt((0, 0), (width, height), mfc_dc, (left, top), win32con.SRCCOPY)

    bmpinfo = save_bitmap.GetInfo()
    bmpstr = save_bitmap.GetBitmapBits(True)

    # 清理 GDI 资源
    win32gui.DeleteObject(save_bitmap.GetHandle())
    save_dc.DeleteDC()
    mfc_dc.DeleteDC()
    win32gui.ReleaseDC(0, hwnd_dc)

    # 转换为 PIL Image (BGRX -> RGB)
    img = Image.frombuffer(
        'RGB',
        (bmpinfo['bmWidth'], bmpinfo['bmHeight']),
        bmpstr, 'raw', 'BGRX', 0, 1
    )
    return img


def find_color_in_image(img, target_rgb, tolerance=8):
    """在 PIL 图片中快速查找目标颜色，找到返回相对坐标 (x, y)"""
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


def hide_azurpilot_window(hwnd=None):
    """
    针对单窗口进行激活、快速内存截图匹配并点击
    返回值:
        0: 未找到/未点击成功
        1: 成功点击蓝色按钮
        2: 成功点击黄色按钮
    """
    if not hwnd:
        hwnd = get_azurpilot_hwnd()

    if not hwnd:
        print("未找到处于显示状态的 AzurPilot 窗口。")
        return 0

    # 1. 激活窗口
    try:
        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.15)
    except Exception:
        pass

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

    # 优先 1：寻找蓝色按键
    print("🔍 [步骤 1] 正在匹配蓝色按键 (#3B82F6)...")
    rel_x, rel_y = find_color_in_image(img, COLOR_BLUE)

    if rel_x is not None:
        click_code = 1
        target_name = "蓝色按键 (#3B82F6)"
    else:
        # 优先 2：寻找黄色按键
        print("⚠️ 未匹配到蓝色，[步骤 2] 正在匹配黄色最小化按键 (#FEBC2E)...")
        rel_x, rel_y = find_color_in_image(img, COLOR_YELLOW)
        if rel_x is not None:
            click_code = 2
            target_name = "黄色最小化按键 (#FEBC2E)"

    if rel_x is not None and rel_y is not None:
        abs_x = left + rel_x
        abs_y = top + rel_y
        print(f"🎉 成功锁定【{target_name}】！物理坐标: ({abs_x}, {abs_y})")

        orig_x, orig_y = pyautogui.position()
        pyautogui.moveTo(abs_x, abs_y, _pause=False)
        time.sleep(0.05)
        pyautogui.click(_pause=False)
        time.sleep(0.03)
        pyautogui.moveTo(orig_x, orig_y, _pause=False)
        print("点击完成！")
        return click_code
    else:
        print("❌ 未在标题栏区域找到蓝色 (#3B82F6) 或黄色 (#FEBC2E) 目标按键。")
        return 0


def cleanup():
    """去初始化清理资源"""
    print("🧹 [去初始化] 模块清理完成。")


def smart_hide_azurpilot(timeout=300, retry_interval=60):
    """
    智能隐藏 AzurPilot 窗口主逻辑：
    - 首个窗口等待与点击享有上限 5 分钟（300s）容错重试。
    - 若首次点击为 1 (蓝色)，成功结束。
    - 若首次点击为 2 (黄色)，继续等待不同尺寸的新 AzurPilot 窗口，并在上限 5 分钟内轮询点击。
    """
    start_time = time.time()
    first_hwnd = None
    first_size = None
    status = 0

    try:
        print("⏳ 开始等待并处理第一个 AzurPilot 窗口（容错上限 5 分钟）...")

        # 阶段 1：等待并成功点击第一个窗口 (超时重试机制)
        while time.time() - start_time < timeout:
            first_hwnd = get_azurpilot_hwnd()
            if first_hwnd:
                r = win32gui.GetWindowRect(first_hwnd)
                first_size = (r[2] - r[0], r[3] - r[1])
                print(f"✅ 捕获到首个窗口，尺寸: {first_size[0]}x{first_size[1]}")

                # 尝试点击首个窗口
                status = hide_azurpilot_window(first_hwnd)
                if status in (1, 2):
                    break  # 成功点击到了按钮，跳出首窗检测循环
                
                print(f"⚠️ 首窗点击未成功(返回 [{status}])，将在 {1} 秒后重试...")
                time.sleep(1)
            else:
                time.sleep(1)

        # 首窗如果在 5 分钟内完全没找到或未能有效点击
        if status == 0:
            print("⏰ 处理第一个窗口超时或未能点击到目标按钮。")
            return 0

        # 情况 A: 首次点击即为 1 (蓝色)，任务直接成功完成
        if status == 1:
            print("✨ 首次点击蓝色按键成功，任务完成！")
            return 1

        # 情况 B: 首次点击为 2 (黄色)，开始等待不同尺寸的新窗口
        if status == 2:
            print("⚠️ 首次点击为黄色按键，准备等待不同尺寸的新窗口出现（总上限 5 分钟）...")

            while time.time() - start_time < timeout:
                time.sleep(1)
                new_hwnd = get_azurpilot_hwnd()
                if new_hwnd:
                    nr = win32gui.GetWindowRect(new_hwnd)
                    new_size = (nr[2] - nr[0], nr[3] - nr[1])

                    # 检测到了尺寸不同的新窗口
                    if new_size != first_size:
                        print(f"🔍 发现新尺寸窗口: {new_size[0]}x{new_size[1]}，开始点击...")
                        retry_status = hide_azurpilot_window(new_hwnd)

                        if retry_status == 1:
                            print("🎉 新窗口点击蓝色按键成功！")
                            return 1
                        else:
                            print(f"⚠️ 新窗口点击结果为 [{retry_status}]，将在 {retry_interval} 秒后重试...")
                            time.sleep(retry_interval)

            print("⏰ 5 分钟超时，未能完成最终的蓝色按键点击。")
            return status

        return status

    finally:
        cleanup()

if __name__ == "__main__":
    smart_hide_azurpilot()
