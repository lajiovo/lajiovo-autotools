import os
import shutil
import subprocess

from zConfig import get_config

# 1. 配置需要处理的文件夹目标
FOLDER_TARGETS = get_config("banmumu.folder_targets")

# 2. 配置需要处理的文件目标
FILE_TARGETS = get_config("banmumu.file_targets")

# 3. 需要停止并禁用的系统服务
SERVICE_NAME = get_config("banmumu.service_name")


def stop_and_disable_service(service_name: str):
    """停止并禁用指定的 Windows 系统服务"""
    print(f"[服务操作] 尝试停止服务: {service_name}")
    # 停止服务
    subprocess.run(["sc", "stop", service_name], capture_output=True, text=True)

    print(f"[服务操作] 尝试禁用服务: {service_name}")
    # 设置服务启动类型为禁用 (disabled)
    result = subprocess.run(["sc", "config", service_name, "start=", "disabled"], capture_output=True, text=True)
    
    if result.returncode == 0:
        print(f"[完成] 已成功禁用服务: {service_name}")
    else:
        print(f"[提示] 服务设置完毕（若服务不存在或无管理员权限可能提示失败）")


def kill_process(process_name: str):
    """尝试强行结束指定的进程"""
    try:
        result = subprocess.run(
            ["taskkill", "/F", "/IM", process_name],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print(f"[进程结束] 成功终止后台进程: {process_name}")
    except Exception as e:
        print(f"[警告] 尝试终止进程 {process_name} 时发生异常: {e}")


def process_folder_to_empty_file(base_dir: str, item_name: str):
    """处理文件夹：删除非空文件夹并重新创建同名空文件"""
    item_path = os.path.join(base_dir, item_name)

    if os.path.isdir(item_path):
        if not os.listdir(item_path):
            print(f"[跳过] 已经是空文件夹: {item_path}")
            return
        
        try:
            shutil.rmtree(item_path)
            open(item_path, "w").close()
            print(f"[完成] 已删除文件夹并替换为同名空文件: {item_path}")
        except Exception as e:
            print(f"[失败] 处理文件夹 {item_path} 报错: {e}")

    elif os.path.isfile(item_path):
        print(f"[跳过] 已经是文件: {item_path}")
    else:
        print(f"[跳过] 不存在: {item_path}")


def process_file_to_empty(base_dir: str, item_name: str):
    """处理文件：清空文件内容使其变为0字节"""
    item_path = os.path.join(base_dir, item_name)

    if os.path.isdir(item_path):
        try:
            shutil.rmtree(item_path)
            open(item_path, "w").close()
            print(f"[完成] 已删除同名文件夹并替换为同名空文件: {item_path}")
        except Exception as e:
            print(f"[失败] 处理 {item_path} 报错: {e}")

    elif os.path.isfile(item_path):
        if os.path.getsize(item_path) == 0:
            print(f"[跳过] 已经是空文件: {item_path}")
        else:
            try:
                with open(item_path, "w") as f:
                    pass
                print(f"[完成] 已清空文件内容: {item_path}")
            except Exception as e:
                print(f"[失败] 清空文件 {item_path} 报错: {e}")
    else:
        print(f"[跳过] 不存在: {item_path}")


if __name__ == "__main__":
    print("=== 开始停止并禁用系统服务 ===")
    stop_and_disable_service(SERVICE_NAME)

    print("\n=== 开始处理文件夹目标 ===")
    for folder_name in FOLDER_TARGETS["items"]:
        process_folder_to_empty_file(FOLDER_TARGETS["dir"], folder_name)

    print("\n=== 开始终止目标进程 ===")
    for file_name in FILE_TARGETS["items"]:
        kill_process(file_name)

    print("\n=== 开始处理文件目标 ===")
    for file_name in FILE_TARGETS["items"]:
        process_file_to_empty(FILE_TARGETS["dir"], file_name)
        
    print("\n所有任务处理完毕。")
