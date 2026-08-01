# 本代码只负责转发Musicdl的web
# 其他控制项直接写死在了zOnepush.py

import socket
import threading

# 目标地址（本地绑定的应用）
TARGET_HOST = '127.0.0.1'
TARGET_PORT = 37777

# 对局域网开放的监听地址和端口
LISTEN_HOST = '0.0.0.0'
LISTEN_PORT = 37777

def handle_client(client_socket):
    try:
        # 创建连接到本地 127.0.0.1:37777 的 socket
        target_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        target_socket.connect((TARGET_HOST, TARGET_PORT))
    except Exception as e:
        print(f"[-] 无法连接到本地 127.0.0.1:{TARGET_PORT}: {e}")
        client_socket.close()
        return

    # 客户端 -> 本地 127.0.0.1
    def forward_in():
        try:
            while True:
                data = client_socket.recv(4096)
                if not data:
                    break
                target_socket.sendall(data)
        except Exception:
            pass
        finally:
            client_socket.close()
            target_socket.close()

    # 本地 127.0.0.1 -> 客户端
    def forward_out():
        try:
            while True:
                data = target_socket.recv(4096)
                if not data:
                    break
                client_socket.sendall(data)
        except Exception:
            pass
        finally:
            client_socket.close()
            target_socket.close()

    t1 = threading.Thread(target=forward_in, daemon=True)
    t2 = threading.Thread(target=forward_out, daemon=True)
    t1.start()
    t2.start()

def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # 关键设置：允许端口重用，避免因为 127.0.0.1 占用了 37777 而报错
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server.bind((LISTEN_HOST, LISTEN_PORT))
    except Exception as e:
        print(f"[-] 绑定端口失败: {e}")
        print("💡 提示：请确认是否已经允许端口重用，或者本地应用是否绑定了 0.0.0.0。")
        return

    server.listen(5)
    print(f"[*] 成功监听 0.0.0.0:{LISTEN_PORT}！")
    print(f"[*] 现在你可以通过 http://192.168.10.3:{LISTEN_PORT} 进行访问了。")

    while True:
        client_socket, addr = server.accept()
        # 排除来自本机的内部转发循环
        if addr[0] == '127.0.0.1':
            continue
        threading.Thread(target=handle_client, args=(client_socket,), daemon=True).start()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n[*] 已退出")
