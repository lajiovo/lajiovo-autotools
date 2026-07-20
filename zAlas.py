import os
import sys
import ctypes
import subprocess
import psutil

# ==================== 配置常量 ====================
ALAS_PATH = r"\AzurPilot\alas-launcher.exe"
AZUR_PROCESS_NAME = "alas-launcher.exe"  # AzurPilot 的进程名
# ==================================================

def is_process_running(process_name):
    """检测指定名称的进程是否已经在运行"""
    for proc in psutil.process_iter(['name']):
        try:
            if proc.info['name'].lower() == process_name.lower():
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return False

def launch_alas_with_admin():
    """使用管理员权限拉起 Alas"""
    alas_dir = os.path.dirname(ALAS_PATH)
    print(f"正在请求管理员权限启动 Alas: {ALAS_PATH}")
    try:
        # 使用 Windows Shell 触发 UAC 提权
        ctypes.windll.shell32.ShellExecuteW(None, "runas", ALAS_PATH, None, alas_dir, 1)
        print("Alas 启动命令已发送。")
        return True
    except Exception as e:
        print(f"启动 Alas 失败: {e}")
        return False

def alas_start():
    """主控逻辑：仅检测进程并决定是否启动"""
    print(f"开始检测进程 '{AZUR_PROCESS_NAME}' 是否已在运行...")
    
    # 1. 检测是否已经在运行
    if is_process_running(AZUR_PROCESS_NAME):
        print(f"检测到 {AZUR_PROCESS_NAME} 已经在后台运行，跳过启动，直接结束主程序。")
        return

    # 2. 如果不存在，则启动它
    print(f"未检测到正在运行的 {AZUR_PROCESS_NAME}，准备拉起...")
    launch_alas_with_admin()

if __name__ == "__main__":
    alas_start()
    print("脚本执行完毕，正在安全退出主程序。")
