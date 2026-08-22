import os
import re
import time
import json
import asyncio
import threading
import subprocess
import urllib.request
from typing import List, Optional

from zConfig import get_config

# Cpolar 安装路径与主程序路径
CPOLAR_DIR = get_config("cpolar.dir")
CPOLAR_EXE = os.path.join(CPOLAR_DIR, "cpolar.exe") if CPOLAR_DIR else ""

# Cpolar Authtoken
AUTHTOKEN = get_config("cpolar.authtoken", default="")

_cpolar_process: Optional[subprocess.Popen] = None
_output_logs: List[str] = []


def _clean_ansi(text: str) -> str:
    ansi_regex = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_regex.sub('', text)


def _reader_thread(pipe):
    global _output_logs
    try:
        while True:
            chunk = pipe.read(512)
            if not chunk:
                break
            cleaned = _clean_ansi(chunk)
            _output_logs.append(cleaned)
    except Exception:
        pass


def _get_urls_from_api() -> List[str]:
    api_url = "http://127.0.0.1:4040/api/tunnels"
    try:
        req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=1) as response:
            data = json.loads(response.read().decode('utf-8'))
            urls = []
            for tunnel in data.get("tunnels", []):
                public_url = tunnel.get("public_url")
                if public_url:
                    urls.append(public_url)
            return list(set(urls))
    except Exception:
        return []


def bind_authtoken_if_needed(token: str):
    """防止未认证导致隧道启动失败"""
    if not token:
        return
    try:
        cmd = [CPOLAR_EXE, "authtoken", token]
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        subprocess.run(cmd, cwd=CPOLAR_DIR, creationflags=creationflags, timeout=5)
        print("[cpolar] Authtoken 配置完成。")
    except Exception as e:
        print(f"[Warning] 配置 Authtoken 失败: {e}")


def start_cpolar_tunnel(port: int = 25568, timeout: int = 15) -> List[str]:
    global _cpolar_process, _output_logs
    _output_logs.clear()

    stop_cpolar_tunnel()

    if not os.path.exists(CPOLAR_EXE):
        print(f"[Error] 找不到 cpolar.exe: {CPOLAR_EXE}")
        return []

    # 如果配置了 token 则自动绑定
    bind_authtoken_if_needed(AUTHTOKEN)

    # 带上 --log=stdout 强制让 cpolar 把日志写到标准输出流中，便于正则抓取
    cmd = [CPOLAR_EXE, "http", str(port), "--log=stdout"]
    print(f"[cpolar] 正在后台静默启动隧道: {' '.join(cmd)}")

    try:
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

        _cpolar_process = subprocess.Popen(
            cmd,
            cwd=CPOLAR_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            bufsize=0,
            encoding="utf-8",
            errors="ignore",
            creationflags=creationflags
        )
        print(f"[DEBUG Process] cpolar 已后台启动，PID: {_cpolar_process.pid}")
    except Exception as e:
        print(f"[Error] 启动进程失败: {e}")
        return []

    t = threading.Thread(target=_reader_thread, args=(_cpolar_process.stdout,), daemon=True)
    t.start()

    urls = []
    start_time = time.time()
    url_pattern = re.compile(r"https?://[a-zA-Z0-9.-]+\.cpolar\.[a-zA-Z0-9]+")

    print("[cpolar] 等待隧道建立并抓取地址...")

    while time.time() - start_time < timeout:
        if _cpolar_process.poll() is not None:
            print(f"[DEBUG Process Exit] cpolar 进程提前退出，退出码: {_cpolar_process.poll()}")
            break

        # 1. 查询 4040 API
        api_urls = _get_urls_from_api()
        if api_urls:
            print(f"[cpolar] [成功] 通过 API 获取到公网地址: {api_urls}")
            return api_urls

        # 2. 从控制台日志抓取
        full_log = "".join(_output_logs)
        matches = url_pattern.findall(full_log)
        for u in matches:
            if u not in urls:
                urls.append(u)

        if urls:
            print(f"[cpolar] [成功] 从控制台日志捕获到公网地址: {urls}")
            return urls

        time.sleep(0.5)

    if not urls:
        print("[Warning] 未能捕获到公网地址。")
        if _output_logs:
            print(f"[DEBUG 内部日志捕获]:\n{''.join(_output_logs)}")

    return urls


def stop_cpolar_tunnel() -> bool:
    global _cpolar_process

    if _cpolar_process is not None:
        try:
            _cpolar_process.terminate()
            _cpolar_process.wait(timeout=2)
        except Exception:
            pass
        _cpolar_process = None

    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", "cpolar.exe"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=True
        )
        print("[cpolar] 已清理 cpolar 进程。")
        return True
    except Exception as e:
        print(f"[Error] 清理进程失败: {e}")
        return False


async def main():
    urls = start_cpolar_tunnel(port=25568, timeout=15)
    print("\n最终获得公网地址:", urls)
    await asyncio.sleep(2)
    stop_cpolar_tunnel()

if __name__ == "__main__":
    asyncio.run(main())