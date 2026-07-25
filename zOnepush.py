import zPerseusLogger
import os
import sys
import json
import time
import subprocess
import threading
from flask import Flask, request, send_from_directory
from zPushhandler import Handlepush
from zBarkCustom import PerseusNotifyMsg, PerseusErrorMsg
from zRunHandler import handlerun

app = Flask(__name__)
LISTEN_PORT = 25566
HANDLEPUSH = True

def kill_port_process(port):
    """启动时结束指定端口的原有占用进程"""
    try:
        if sys.platform.startswith("win"):
            # Windows 平台处理
            cmd = f"netstat -ano | findstr :{port}"
            output = subprocess.check_output(cmd, shell=True).decode('gbk', errors='ignore')
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
                # 说明没有找到占用端口的 PID，无需处理
                pass
    except Exception as e:
        print(f"⚠️ 尝试清理端口 {port} 占用进程时遇到问题: {e}")

def shutdown_server():
    """延迟 0.5 秒关闭整个 Python 进程，确保响应能先返回给请求方"""
    print("❌ Handlepush 处理失败，准备停止服务...")
    # 补充失败异常通知
    PerseusErrorMsg(
        "OnePush 服务终止", 
        "Handlepush 处理推送消息失败，服务已被强制停止，请检查日志！"
    )
    time.sleep(0.5)
    os._exit(1)  # 强制退出当前 Python 进程

# 推送接收接口，同时支持 GET / POST
@app.route("/push", methods=["GET", "POST"])
def receive_push():
    # 合并三种传参方式：GET参数、POST表单、POST JSON
    msg_dict = {}
    msg_dict.update(request.args.to_dict())
    msg_dict.update(request.form.to_dict())
    if request.is_json:
        msg_dict.update(request.get_json())

    # 终端格式化打印完整消息字典
    print("\n========================================")
    print(f"【新OnePush推送】时间：{str(request.args)}")
    print("消息完整字典：")
    print(json.dumps(msg_dict, ensure_ascii=False, indent=4))
    print("========================================\n")

    if HANDLEPUSH:
        if not Handlepush(msg_dict):
            # 1. 启动异步线程准备关闭服务
            threading.Thread(target=shutdown_server, daemon=True).start()
            
            # 2. 返回处理失败的响应给客户端
            fail_resp = {
                "status": "error",
                "code": 500,
                "message": "推送处理失败，服务即将停止运行",
                "data": msg_dict
            }
            return json.dumps(fail_resp, ensure_ascii=False), 500, {"Content-Type": "application/json"}

    # 返回成功响应给推送客户端
    resp = {
        "status": "ok",
        "code": 200,
        "message": "消息接收完成",
        "data": msg_dict
    }
    
    return json.dumps(resp, ensure_ascii=False), 200, {"Content-Type": "application/json"}


# ==================== 新增路由: /help 网页请求 ====================
@app.route("/help", methods=["GET"])
def get_help():
    """返回 WebHome.html 页面"""
    # 默认寻找当前脚本运行目录下的 WebHome.html
    # 如果文件在 templates 子目录下，可以使用 render_template('WebHome.html')
    html_dir = os.path.dirname(os.path.abspath(__file__))
    html_filename = "WebHome.html"
    
    if not os.path.exists(os.path.join(html_dir, html_filename)):
        return f"HTML文件未找到: {html_filename}", 404
        
    return send_from_directory(html_dir, html_filename)


# ==================== 新增路由: /run 预处理请求 ====================
@app.route("/run", methods=["GET", "POST"])
def handle_run():
    """接收 /run 请求，对 onpush 消息进行预处理"""
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

    # 1. 调用预留的预处理函数
    process_result = handlerun(req_data)

    # 2. 返回结果响应
    resp = {
        "status": "ok" if process_result[0] else "error",
        "code": 200 if process_result[0] else 500,
        "message": f"{process_result[1]}",
        "data": req_data
    }
    return json.dumps(resp, ensure_ascii=False), resp["code"], {"Content-Type": "application/json"}


def main():
    """独立的服务启动主入口"""
    # 1. 检查并结束占用 25566 端口的原进程
    kill_port_process(LISTEN_PORT)

    # 2. 打印提示与发送启动成功通知
    print(f"OnePush接收服务已启动，监听端口：{LISTEN_PORT}")
    PerseusNotifyMsg(
        "OnePush 服务启动成功", 
        f"服务已成功绑定端口 {LISTEN_PORT} 并开始监听请求。"
    )
    print(f"访问地址示例：http://127.0.0.1:{LISTEN_PORT}/push")
    print(f"帮助页面地址：http://127.0.0.1:{LISTEN_PORT}/help")
    print(f"运行接口地址：http://127.0.0.1:{LISTEN_PORT}/run")

    # 3. 运行 Flask 实例
    app.run(host="0.0.0.0", port=LISTEN_PORT, debug=False)

if __name__ == "__main__":
    main()
