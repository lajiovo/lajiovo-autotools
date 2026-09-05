# 🌌 Perseus (lajiovo-autotools) 🐾

<div align="center">
  <img src="QBot/suoha.png" alt="Project Icon" width="150" />
  <h3>集自动化运维、远程控制、轻量工具箱与辅助自动化脚本于一体的 Python 综合工具库</h3>
  <p>由开发者与 AI 协作完成，旨在构建一个全能、高效且自动化的“数字管家”。</p>
</div>

---

## ⚙️ 核心功能详解

### 1. 🎮 游戏运维大本营 (AzurPilot & MuMu)
针对《碧蓝航线》自动化工具 AzurPilot (Alas) 与 MuMu 模拟器深度定制的监控系统：
*   🙈 **后台静默控制**：利用 Win32 API 强制隐藏模拟器与 Alas 窗口，通过 `zAlas.py` 和 `zMumu.py` 实现完全后台化运行。
*   🔄 **闭环自愈流程**：`zMainHandler.py` 实现了 `check -> start -> wait -> check -> update` 的完整检查链。若检测到 `0026`（运行错误）、`0016/0017`（页面超时），会自动执行软重启或清理进程硬重启。
* 🌐 **网页自动化**：基于 Playwright 实现 AzurPilot 的自动化启动与更新。
*   📲 **智能消息解析**：
    *   **红尖尖委托**：自动解析“顶级奖励”消息，统计并通知获得的钻石数量。
    *   **行动力监控**：实时更新 AP 变化，并在低于最低保留值时发送预警。
    *   **经验报告**：汇总舰队舰船等级进度，预测经验满额剩余时间。
    *   **异常拦截**：捕捉 `EmulatorNotRunningError` 等关键错误并自动触发修复。
    *   **多端推送**：同步推送到手机 Bark App 及 QQ 群。
* 🧹 **广告弹窗清理（可选）**：提供可选的弹窗清理逻辑，按需自动拦截并清理 MuMu 模拟器的广告弹窗。

### 2. 🤖 QBot 智能管家 (QQ Bot)
基于 `botpy` 实现的深度交互机器人，集成在 [`QBot/`](QBot/) 目录下：
* 💬 **多场景交互与昵称支持**：支持群聊与私聊模式，允许用户昵称自定义。
*   📜 **OP 级远程控制**：
    *   系统监控：实时查看 CPU、内存、磁盘占用（`#op sys`）。
    *   进程管理：远程启动/终止云崽 (Yunzai-bot) 及其关联插件。
    *   服务操控：控制后端 25566 端口的开启与关闭，管理 Cpolar 穿透隧道。
*   🖼️ **日志/截图可视化**：
    *   支持远程查看本地四路预设日志，具备上翻、下翻、刷新及页码跳转功能。
    *   **报错溯源**：当 Alas 报错时，可远程调取错误时刻的屏幕截图（`#op log goto 0`）。
* 🔌 **云崽 Bot 协议接入与扩展**：支持基于 `WebSocket` 与 `OneBot v11` 协议链接云崽 Bot（Yunzai-bot），可通过虚构 ID 转发消息，并支持 `phi-plugin` 等插件扩展（*提示：此板块目前存在一定 问题*）。
*   🎮 **港区养成小游戏**：内置打捞（单抽/十连）、钓鱼、拆弹专家、21 点、算术 24 点、战力排行榜等丰富的养成与互动玩法。
* 🖥️ **WebUI 后台管理**：提供带密码验证的 WebUI 管理后台，支持群聊和私信，支持加载昵称。

### 3. 📚 LK 电子书神器 (LightNovel Crawler)
基于 Playwright 开发的轻之国度 (LK) 自动化抓取工具：
*   🕵️ **全仿真抓取**：模拟移动端 Safari 行为，绕过检测，支持 `book_id` 在线抓取。
*   💾 **智能持久化**：
    *   支持断点续传，缓存精确到卷/章级别（JSON 格式）。
    *   **插图处理**：自动建立图片 Hash 映射，支持补齐/重载图片，并在生成的 EPUB 中自动嵌入。
    *   **繁简转换**：内置 OpenCC/zhconv 转换，生成符合阅读习惯的简体 EPUB。
*   💻 **双端入口**：既支持 Web API 触发后台异步任务，也提供独立的 Tkinter GUI 桌面程序进行可视化管理。

### 4. 🛠️ 百宝箱工具集 (More)
*   🌐 **网络穿透 (Cpolar)**：集成 `zCpolar.py`，支持一键启动 HTTP 隧道，30 分钟自动关停保护，自动提取并分发公网地址。
*   🎵 **音乐分享 (MusicDL)**：
    *   利用 `zMusicDL.py` 实现端口重用与双向流量透传。
    *   自动将本地 MusicDL 服务广播至局域网，并具备 Webview 窗口自动隐藏逻辑。
*   🎬 **多媒体处理 (FFmpeg)**：通过 `zFfmpeg.py` 监控目录，自动将 MP3 转换为 64k 低比特率版本，支持抹除冗余元数据标签。
*   🍎 **自动化签到**：`zPGRJZ.py` 实现了针对特定软件站的 Playwright 模拟登录与每日签到任务，具备二次验证逻辑。
*   🌐 **代理浏览器**：`zBrowser.py` 提供了一个预设好缩放比例、地理位置伪装及剪切板穿透的自动化浏览器环境。
* 🛡️ **安全权限与防重复运行**：严格校验管理员权限，并构建防重复启动屏障，防止多进程冲突。
* 🛟 **进程守护与开机自启**：具备完善的异常捕获机制，即便遭遇报错也会守护进程挂机运行；支持配置系统开机自动启动（需手动在系统中完成配置）。
* 🌐 **可视化导航与控制面板**：自带导航网页与控制面板网页，方便集中管理各服务状态与快捷跳转。

---

## 📁 项目目录结构

```text
Perseus/
├── QBot/                     # QBot 机器人独立服务目录
│   ├── assets/               # 静态资源文件
│   │    ├── index.html       # 主页面
│   │    ├── login.html
│   │    └── chat.html
│   ├── temp_images/          # 云崽图片消息缓存
│   ├── botdata/              # 机器人数据
│   │    ├── c2chistory/      # 私聊聊天记录
│   │    ├── grouphistory/    # 群聊聊天记录
│   │    ├── groupinfo/       # 群聊信息
│   │    ├── userdata/        # 用户的游戏数据
│   │    ├── userinfo/        # 用户信息
│   │    ├── extra.json       # 其他信息
│   │    ├── opsetting.json   # 管理员设置
│   │    └── pushhistory.json # 已废弃
│   ├── log/                  # 机器人板块日志
│   ├── config.py             # QBot 配置脚本
│   ├── game.py               # 简易互动小游戏逻辑
│   ├── gameconfig.json       # 游戏配置文件
│   ├── key.example.json      # Web 密钥示例文件
│   ├── main.py               # QBot 启动入口
│   ├── opcmd.py              # OP 指令集与富媒体卡片处理
│   ├── server.py             # WebUI 及服务控制端
│   ├── suoha.png             # 示例图片
│   ├── botpy.log             # botpy的日志文件
│   └── yz.py                 # 云崽 Bot接入
├── cache/                    # zBrowser的文件
├── servercache/              # 大本营的缓存文件
├── browser_downloads/        # zBrowser的下载文件
├── lkcache/                  # LK板块的缓存文件
│   └── <book-name>/          # 单书籍缓存
│        ├── .../             # 分卷和分章节的文本与插图
│        ├── images_mapped    # 封面
│        └── metadata.json    # 书籍信息
├── logs/                     # 大本营的日志文件
├── temp_images/              # 乱飞的云崽图片消息缓存
├── quick_tools/              # 轻量化快捷小工具目录
├── webassets/                # Web 后台/控制面板前端静态资源
│   ├── index.html            # 导航页
│   └── dash.html             # 仪表盘 控制页
├── begin.vbs                 # 一级启动入口
├── Begin.example.bat         # 二级启动入口 示例
├── begin.pyw                 # 三级启动入口
├── zOnepush.py               # 主控大本营中心调度与状态监控
├── CodeList.txt              # 错误码清单
├── LICENSE                   # 项目开源许可证
├── README.md                 # 项目说明文档
├── WebHome.html              # 废弃Help页
├── auth.example.json         # AzurpilotWebui 认证信息配置示例
├── config.example.yaml       # 主配置文件示例
├── zAlas.py                  # AzurPilot 自动化控制与更新逻辑
├── zBanMumu.py               # MuMu 模拟器广告弹窗处理
├── zBark.py                  # Bark 消息推送核心模块
├── zBarkCustom.py            # 自定义消息推送接口
├── zBrowser.py               # 代理浏览器一键启动
├── zConfig.py                # 全局配置读取与解析模块
├── zCpolar.py                # Cpolar 内网穿透隧道管理
├── zEditProxy.py             # 程序与系统 Git 代理一键修改
├── zFfmpeg.py                # FFmpeg 音频压缩
├── zLK.py                    # 轻之国度电子书抓取、解析与 EPUB 打包
├── zMainHandler.py           # 消息转发和指令处理
├── zMumu.py                  # MuMu 模拟器进程相关
├── zMusicDL.py               # MusicDL 音乐服务启动与局域网广播
├── zPGRJZ.py                 # 苹果软件站签到等扩展自动化任务
├── zPerseusLogger.py         # 全局日志轮转与格式化处理
├── zPgrjzLogin.py            # 苹果软件站网页登录入口
├── zPlaywright.py            # AzurpilotWebui 控制相关
├── pgrjzauth.json            # 苹果软件站登入信息
└── last_checkin.txt          # 签到日期记录

```

---

## 🚀 启动流程(没写完)

### 1. 前置准备
*   **Python 环境**：Python 3.10+
*   **核心依赖**：
    ```bash
    pip install -r requirements.txt
    playwright install chromium
    ```
*   **配置配置**：
    *   将 `config.example.yaml` 复制为 `config.yaml`，填入路径、Bark Key、Cpolar Token 等。
    *   将 `auth.example.json` 复制为 `auth.json` 放入根目录以供自动化登录。

### 2. 多级启动 (Windows)
*   **`begin.vbs`**：推荐入口。无窗口运行，自动检测 25566 端口，若未启动则自动请求管理员权限唤起 `Begin.bat`。
*   **`Begin.bat`**：带路径的脚本，调用 `pythonw` 拉起后端核心。
*   **`begin.pyw`**：Python 后端静默启动入口，直接挂载 `zOnepush.main()`。

---

## 📖 使用说明（没写完）

### 1. 控制台访问
*   **主控大本营**：`http://localhost:25566/main/` (可视化开关服务)
*   **机器人 WebUI**：`http://localhost:25567/bot` (需配置 `key.json` 密码，可查看聊天记录与配置)

### 2. 核心 API 路由
*   `/push`：接收外部 Push 消息并分发处理。
*   `/cp/start`：开启 Cpolar 隧道。
*   `/lk/<book_id>`：提交异步 LK 爬取任务。
*   `/bot/start`：重启机器人进程。
*   ...

---

## 📜 证书 (License)

本项目采用 [GNU GENERAL PUBLIC LICENSE Version 3](LICENSE) 协议授权。

---
<div align="right">
  <i>Update Time: 2026-09-05</i>
</div>
