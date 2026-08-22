import os
from pathlib import Path
from typing import Any, Optional
from ruamel.yaml import YAML

# 初始化 YAML 处理器
yaml = YAML()
yaml.preserve_quotes = True  # 保留引号格式
yaml.indent(mapping=2, sequence=4, offset=2)  # 设置良好的排版缩进

DEFAULT_CONFIG_PATH = Path("config.yaml")

def _load_yaml(config_path: Path = DEFAULT_CONFIG_PATH):
    """读取 YAML 文件并返回配置对象"""
    target_path = config_path
    
    # 如果当前路径不存在，尝试到上一级目录寻找（最多向前查找一次）
    if not target_path.exists():
        parent_path = config_path.parent.resolve().parent / config_path.name
        if parent_path.exists():
            target_path = parent_path
        else:
            raise FileNotFoundError(f"未找到配置文件: {config_path.resolve()}")
    
    with open(target_path, "r", encoding="utf-8") as f:
        return yaml.load(f)

def _save_yaml(data: Any, config_path: Path = DEFAULT_CONFIG_PATH) -> None:
    """将配置对象写回文件"""
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f)

def get_config(key_path: Optional[str] = None, default: Any = None, config_path: Path = DEFAULT_CONFIG_PATH) -> Any:
    """
    读取配置项。
    
    :param key_path: 配置项路径，支持层级路径（如 'server.port'）。若为 None 则返回完整配置字典。
    :param default: 查找失败时的默认返回值
    :param config_path: 配置文件路径
    :return: 配置项的值
    """
    data = _load_yaml(config_path)
    
    if key_path is None:
        return data

    keys = key_path.split(".")
    curr = data
    for k in keys:
        if isinstance(curr, dict) and k in curr:
            curr = curr[k]
        else:
            return default
    return curr

def set_config(key_path: str, value: Any, config_path: Path = DEFAULT_CONFIG_PATH) -> None:
    """
    修改或设置配置项，自动写回文件并保留原有的注释与排版。
    
    :param key_path: 配置项路径，支持层级路径（如 'server.port'）
    :param value: 要设置的新值
    :param config_path: 配置文件路径
    """
    data = _load_yaml(config_path)
    
    keys = key_path.split(".")
    curr = data
    
    # 逐层遍历/建树，保证嵌套结构存在
    for k in keys[:-1]:
        if k not in curr or not isinstance(curr[k], dict):
            curr[k] = {}
        curr = curr[k]
    
    # 修改目标 key
    curr[keys[-1]] = value
    
    # 保存修改，保留注释
    _save_yaml(data, config_path)

if __name__ == "__main__":
    ALAS_PATH = get_config("app.alas_path")
    TARGET_PROCESS = get_config("app.target_process")
    TARGET_TITLE = get_config("app.target_title")
    print(TARGET_PROCESS)