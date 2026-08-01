# 这里是音乐文件暴力压缩还有降低响度（耳机炸了）
# 使用了ffmpeg，没有要自己下

import os
import subprocess
from pathlib import Path

# 定义源目录与目标目录
SRC_DIR = Path(r"\musicdl\data\downloads")
DST_DIR = Path(r"")

# 音频处理参数
AUDIO_FILTER = "loudnorm=I=-50:LRA=11:TP=-1.5, dynaudnorm"
BITRATE = "64k"


def process_audio():
    # 确保目标目录存在
    DST_DIR.mkdir(parents=True, exist_ok=True)

    # 获取所有 .mp3 文件
    mp3_files = list(SRC_DIR.glob("*.mp3"))

    if not mp3_files:
        print("未找到需要处理的 MP3 文件。")
        return

    print(f"找到 {len(mp3_files)} 个 MP3 文件，准备开始处理...\n")

    for idx, src_file in enumerate(mp3_files, 1):
        # 排除已经是 _64k 结尾的文件，防止二次转换
        if src_file.stem.endswith("_64k"):
            continue

        # 构建输出文件路径
        out_filename = f"{src_file.stem}_64k.mp3"
        dst_file = DST_DIR / out_filename

        # 检查是否已存在，自动避免重复处理
        if dst_file.exists():
            print(f"[{idx}/{len(mp3_files)}] 跳过（已存在）: {out_filename}")
            continue

        print(f"[{idx}/{len(mp3_files)}] 处理中: {src_file.name} -> {out_filename}")

        # 构建 ffmpeg 命令
        cmd = [
            "ffmpeg",
            "-y",  # 覆盖模式
            "-i",
            str(src_file),
            "-vn",  # 关键点 1：禁用视频流（去除内嵌专辑封面/图片）
            "-map_metadata",
            "-1",  # 关键点 2：剥离文件元数据（如图片标签、歌词等）
            "-af",
            AUDIO_FILTER,
            "-c:a",
            "libmp3lame",
            "-b:a",
            BITRATE,
            str(dst_file),
        ]

        try:
            # 执行 ffmpeg 命令，隐藏冗余的标准输出
            subprocess.run(
                cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
            )
            print(f"  └─ 完成!")
        except subprocess.CalledProcessError as e:
            print(f"  └─ 处理失败: {e.stderr.decode('utf-8', errors='ignore')}")
        except FileNotFoundError:
            print(
                "错误：未找到 ffmpeg 程序，请确保已将 ffmpeg 添加到系统环境变量 Path 中。"
            )
            break


if __name__ == "__main__":
    process_audio()
