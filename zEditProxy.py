import os
import subprocess
import tkinter as tk
from tkinter import messagebox
from ruamel.yaml import YAML


def update_proxy():
    num = entry.get().strip()
    if not num.isdigit():
        messagebox.showerror("错误", "请输入有效的数字！")
        return

    ip = f"192.168.10.{num}"
    http_proxy = f"http://{ip}:1082"
    socks_proxy = f"socks5://{ip}:1082"

    # 1. 使用 ruamel.yaml 读取并更新，保留原本的注释和格式
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")

    yaml = YAML()
    yaml.preserve_quotes = True  # 保留原有引号格式
    yaml.indent(mapping=2, sequence=4, offset=2)  # 保持良好的缩进

    try:
        data = {}
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.load(f) or {}

        # 确保 proxy 节点存在
        if "proxy" not in data or data["proxy"] is None:
            data["proxy"] = {}

        data["proxy"]["http"] = http_proxy
        data["proxy"]["socks"] = socks_proxy

        # 写入文件（原有的注释将被完整保留）
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        # 2. 修改 Git 代理设置
        subprocess.run(
            ["git", "config", "--global", "http.proxy", http_proxy], check=True
        )
        subprocess.run(
            ["git", "config", "--global", "https.proxy", http_proxy], check=True
        )

        messagebox.showinfo(
            "成功",
            f"已成功更新配置文件及 Git 代理！\nHTTP: {http_proxy}\nSOCKS: {socks_proxy}",
        )
        root.destroy()

    except Exception as e:
        messagebox.showerror("错误", f"操作失败：{e}")


# 搭建 GUI 界面
root = tk.Tk()
root.title("代理设置")
root.geometry("260x130")
root.resizable(False, False)

# 居中显示窗口
root.eval("tk::PlaceWindow . center")

label = tk.Label(root, text="请输入 IP 最后一位数字 (例如 13):")
label.pack(pady=10)

entry = tk.Entry(root, width=15, justify="center")
entry.pack(pady=5)
entry.focus_set()

# 绑定回车键快捷提交
entry.bind("<Return>", lambda event: update_proxy())

btn = tk.Button(root, text="确认更新", command=update_proxy)
btn.pack(pady=10)

root.mainloop()