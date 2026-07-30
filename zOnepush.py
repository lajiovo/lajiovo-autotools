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
from zMainHandler import run_alas_mumu_check, handlerun
import zAlas
import zMumu
import zPGRJZ

app = Flask(__name__)
LISTEN_PORT = 25566

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
    # 非 Windows 系统默认视为拥有所需权限
    return True

def request_admin_privileges(max_retries=5):
    """请求管理员权限，若未获得则重新尝试拉起自身，最多尝试 max_retries 次"""
    if is_admin():
        return True

    # 尝试读取环境变量中的重试次数
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
        # 将递增后的计数写回环境变量传递给提升权限后的新进程
        env = os.environ.copy()
        env["ADMIN_RETRY_COUNT"] = str(retry_count)

        # 构建命令行参数
        script = os.path.abspath(sys.argv[0])
        params = " ".join([f'"{arg}"' for arg in sys.argv[1:]])
        
        try:
            # 同样在环境变量中把 ADMIN_RETRY_COUNT 传下去，避免多开无序
            # 借由 Windows 注册表或命令传递参数 ShellExecuteW 'runas'
            ctypes.windll.shell32.ShellExecuteW(
                None, 
                "runas", 
                sys.executable, 
                f'"{script}" {params}', 
                None, 
                1
            )
            # 申请提升后，原非管理员进程直接退出
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
            # Windows 平台处理：在 findstr 后面加上 || rem 避免未找到匹配时返回错误码 1
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
            # Linux / macOS 平台处理
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

def stop_timer():
    """停止后台定时检查线程"""
    global timer_event
    timer_event.set()  # 触发事件以打断等待并退出循环

def start_alas_mumu_check_timer():
    """启动/重启后台定时任务线程：每半小时自动执行一次 alas_mumu_check"""
    global timer_thread, timer_event
    # 先停止旧的定时线程（如果存在）
    stop_timer()
    
    timer_event = threading.Event()
    
    def timer_loop():
        while not timer_event.is_set():
            # 使用 timer_event.wait 代替 time.sleep，这样停止时能瞬间响应
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
    
    # 停止定时检查
    stop_timer()
    
    # 清理 zAlas 和 zMumu 进程
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

# 推送接收接口，同时支持 GET / POST
@app.route("/push", methods=["GET", "POST"])
def receive_push():
    # 合并三种传参方式：GET参数、POST表单、POST JSON
    msg_dict = {}
    msg_dict.update(request.args.to_dict())
    msg_dict.update(request.form.to_dict())
    if request.is_json:
        json_data = request.get_json(silent=True)
        if json_data:
            msg_dict.update(json_data)

    # 终端格式化打印完整消息字典
    print("\n========================================")
    print(f"【新OnePush推送】时间：{str(request.args)}")
    print("消息完整字典：")
    print(json.dumps(msg_dict, ensure_ascii=False, indent=4))
    print("========================================\n")

    if HANDLEPUSH:
        push_res = Handlepush(msg_dict)
        if not push_res:
            # push处理失败时进入待机状态
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
        
        # 处理成功，直接返回 Handlepush 的输出结果
        return format_response(push_res, 200)

    # 如果 HANDLEPUSH == False (待机模式下)
    # 转发消息，但不进行处理
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
    
    # 立即运行一次 check
    try:
        print("▶️ 收到 /start 请求，正在运行 run_alas_mumu_check...")
        run_alas_mumu_check()
    except Exception as e:
        print(f"⚠️ 运行 run_alas_mumu_check 出现异常: {e}")
        
    # 重启定时检查进程
    start_alas_mumu_check_timer()
    
    return format_response({"status": "ok", "message": "服务已重新启动并恢复处理"}, 200)

@app.route("/shutdown", methods=["GET", "POST"])
def handle_shutdown():
    """接收 /shutdown 请求，结束定时检查和自身进程（不管 alas 和 mumu）"""
    print("🛑 收到 /shutdown 请求，正在关闭服务自身...")
    stop_timer()
    
    def delayed_exit():
        time.sleep(0.5)
        os._exit(0)
        
    threading.Thread(target=delayed_exit, daemon=True).start()
    return format_response({"status": "ok", "message": "定时检查已终止，接收服务正在退出..."}, 200)

@app.route("/ping", methods=["GET", "POST"])
def handle_ping():
    """接收 /ping 请求，根据 HANDLEPUSH 返回状态"""
    return format_response({"handlepush": HANDLEPUSH}, 200)

# ==================== Web 帮助与运行路由 ====================

@app.route("/help", methods=["GET"])
def get_help():
    """返回 WebHome.html 页面"""
    html_dir = os.path.dirname(os.path.abspath(__file__))
    html_filename = "WebHome.html"
    
    if not os.path.exists(os.path.join(html_dir, html_filename)):
        return f"HTML文件未找到: {html_filename}", 404
        
    return send_from_directory(html_dir, html_filename)

@app.route("/run", methods=["GET", "POST"])
def handle_run():
    """接收 /run 请求，同步执行 handlerun，并将 handlerun 的返回值直接返回"""
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

    # 直接同步调用 handlerun 并获取其返回值
    run_result = handlerun(req_data)

    # 直接将 handlerun 的结果作为 HTTP 响应返回
    return format_response(run_result, 200)

def main():
    """独立的服务启动主入口"""
    # 0. 启动时优先检查并请求管理员权限（最多重试5次）
    request_admin_privileges(max_retries=5)

    # 1. 检查并结束占用 25566 端口的原进程
    kill_port_process(LISTEN_PORT)

    # 2. 启动每半小时运行一次 alas_mumu_check 的后台定时线程
    start_alas_mumu_check_timer()

    # 3. 打印提示与发送启动成功通知
    print(f"OnePush接收服务已启动（已获取管理员权限），监听端口：{LISTEN_PORT}")
    PerseusNotifyMsg(
        "OnePush 服务启动成功", 
        f"服务已成功绑定端口 {LISTEN_PORT} 并开始监听请求。"
    )
    print(f"访问地址示例：http://127.0.0.1:{LISTEN_PORT}/push")
    print(f"帮助页面地址：http://127.0.0.1:{LISTEN_PORT}/help")
    print(f"运行接口地址：http://127.0.0.1:{LISTEN_PORT}/run")

    # 4. 运行 Flask 实例
    app.run(host="0.0.0.0", port=LISTEN_PORT, debug=False)

if __name__ == "__main__":
    multiprocessing.freeze_support()  # 兼容 Windows 打包/多进程机制
    main()
