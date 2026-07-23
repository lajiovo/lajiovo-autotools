import zPerseusLogger
import os
import sys
import ctypes
import subprocess
import psutil
from zHideAlas import smart_hide_azurpilot
from zBarkCustom import PerseusErrorMsg,PerseusNotifyMsg

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
    ikun = smart_hide_azurpilot(retry_interval=2)
    if ikun == 1:
        PerseusNotifyMsg("Success with smart_hide_azurpilot()","")
    else:
        PerseusErrorMsg("Bug with smart_hide_azurpilot()",f"{ikun}")


def alas_cleanup():
    """全清逻辑：清理 alas 及 azurpilot 相关的 python 脚本、GUI 界面以及 22267、22268 端口占用"""
    print("开始执行 Alas 后台全清...")
    
    # 排除关键词（黑名单）：带有这些词的进程绝对不杀
    EXCLUDE_KEYWORDS = {'auto', 'aiot', 'ide'}
    # 目标关键词（白名单/必杀词）
    TARGET_KEYWORDS = {'alas', 'azurpilot'}
    
    # 1. 清理包含 alas / azurpilot 的进程，且避开排除项
    print("正在检查相关 Python 进程及 GUI 界面...")
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            name_lower = proc.info['name'].lower()
            cmdline = proc.info['cmdline'] or []
            cmdline_str = " ".join(cmdline).lower()
            
            # 合并进程名和完整命令行进行综合检查
            full_text = f"{name_lower} {cmdline_str}"
            
            # 规则 1：检查是否触碰黑名单关键词
            if any(ex in full_text for ex in EXCLUDE_KEYWORDS):
                continue
            
            # 规则 2：判定是否属于需要清理的目标进程
            # A: Python 进程且命令行带有目标关键词
            is_target_py = name_lower.startswith('python') and any(
                any(kw in arg.lower() for kw in TARGET_KEYWORDS) for arg in cmdline
            )
            
            # B: 进程名或启动命令明确包含目标关键词
            is_target_gui = any(kw in full_text for kw in TARGET_KEYWORDS)

            if is_target_py or is_target_gui:
                print(f"发现目标进程 [{proc.info['name']}] [PID: {proc.pid}]")
                proc.kill()
                print(f"-> 已成功强行终止 PID: {proc.pid}")
                
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    # 2. 清理占用 22267 和 22268 端口的进程
    TARGET_PORTS = {22267, 22268}
    print(f"正在检查本地端口 {TARGET_PORTS} 是否被占用...")
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

                        # 端口清理同样遵循黑名单拦截，避免误杀 IDE 或安全软件
                        if any(ex in p_full for ex in EXCLUDE_KEYWORDS):
                            print(f"端口 {current_port} 占用者 [{p.name()}] 包含排除词，跳过终止。")
                            continue

                        print(f"发现端口 {current_port} 被进程 '{p.name()}' [PID: {port_pid}] 占用，正在终结...")
                        p.kill()
                        print(f"-> 已成功释放端口 {current_port} (终止了 PID: {port_pid})")
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        print(f"尝试终止端口占用进程 [PID: {port_pid}] 时失败，可能权限不足或进程已退出。")
    except psutil.AccessDenied:
        print("获取网络连接列表失败，请确保使用管理员权限运行此脚本以清理端口占用。")

    print("Alas 后台全清完毕。")


if __name__ == "__main__":
    #alas_cleanup()
    alas_start()
    print("脚本执行完毕，正在安全退出主程序。")
