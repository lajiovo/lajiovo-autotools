import zPerseusLogger
import os
import sys
import json
import time
import ctypes
import subprocess
import threading
import multiprocessing
from flask import Flask, request, send_from_directory
from zBarkCustom import PerseusNotifyMsg, PerseusErrorMsg
from zMainHandler import run_alas_mumu_check, handlerun, Handlepush
import zAlas
import zMumu
import zPGRJZ

app = Flask(__name__)
LISTEN_PORT = 25566

# QBot 相关配置
PYTHONW_PATH = r"\Programs\Python\Python314\pythonw.exe"
QBOT_SCRIPT_PATH = r"\QBot\main.py"
# 专用的精准识别标记（写在命令行参数中）
QBOT_IDENTIFIER = "--PERSEUS_QBOT_INSTANCE"

# 全局状态控制与定时器线程锁/事件控制
HANDLEPUSH = True
timer_thread = None
timer_event = threading.Event()  # 用于优雅控制和停止定时器线程

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
    kill_qbot_process()

    if not os.path.exists(PYTHONW_PATH):
        raise FileNotFoundError(f"未找到 pythonw.exe 路径: {PYTHONW_PATH}")
    if not os.path.exists(QBOT_SCRIPT_PATH):
        raise FileNotFoundError(f"未找到脚本文件路径: {QBOT_SCRIPT_PATH}")

    # 2. 构建启动命令，附带 QBOT_IDENTIFIER 参数作为精准定位标记
    cmd = [PYTHONW_PATH, QBOT_SCRIPT_PATH, QBOT_IDENTIFIER]
    working_dir = os.path.dirname(QBOT_SCRIPT_PATH)

    # 3. 设置 Windows 彻底无窗口标志
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
                zPGRJZ.run(headless=True)
            except Exception as e:
                print(f"⚠️ 定时运行 alas_mumu_check 出现异常: {e}")

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
    return format_response({"status": "ok", "message": "服务已重新启动并恢复处理"}, 200)

@app.route("/shutdown", methods=["GET", "POST"])
def handle_shutdown():
    """接收 /shutdown 请求，结束定时检查和自身进程"""
    print("🛑 收到 /shutdown 请求，正在关闭服务自身...")
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
    return format_response(run_result, 200)

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
    print(f"QBot 启动地址：http://127.0.0.1:{LISTEN_PORT}/bot/start")
    print(f"QBot 关闭地址：http://127.0.0.1:{LISTEN_PORT}/bot/shutdown")

    app.run(host="0.0.0.0", port=LISTEN_PORT, debug=False)

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
