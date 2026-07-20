from flask import Flask, request
import json

app = Flask(__name__)
LISTEN_PORT = 25566

# 推送接收接口，同时支持 GET / POST
@app.route("/push", methods=["GET", "POST"])
def receive_push():
    # 合并三种传参方式：GET参数、POST表单、POST JSON
    msg_dict = {}
    # GET url 参数
    msg_dict.update(request.args.to_dict())
    # POST 表单 x-www-form-urlencoded
    msg_dict.update(request.form.to_dict())
    # POST json 请求体
    if request.is_json:
        msg_dict.update(request.get_json())

    # 终端格式化打印完整消息字典
    print("\n========================================")
    print(f"【新OnePush推送】时间：{str(request.args)}")
    print("消息完整字典：")
    print(json.dumps(msg_dict, ensure_ascii=False, indent=4))
    print("========================================\n")

    # 返回成功响应给推送客户端
    resp = {
        "status": "ok",
        "code": 200,
        "message": "消息接收完成",
        "data": msg_dict
    }
    return json.dumps(resp, ensure_ascii=False), 200, {"Content-Type": "application/json"}

if __name__ == "__main__":
    # host=0.0.0.0 允许局域网、外网设备访问本机25566端口
    print(f"OnePush接收服务已启动，监听端口：{LISTEN_PORT}")
    print(f"访问地址示例：http://127.0.0.1:{LISTEN_PORT}/push")
    app.run(host="0.0.0.0", port=LISTEN_PORT, debug=False)
