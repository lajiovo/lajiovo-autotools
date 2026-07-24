# 🛡️ lajiovo-autotools

**lajiovo-autotools** 是由**la_jiovo** 个人开发并维护的自动化脚本**合集**。

本项目核心功能是在**无人值守**的情况下，自动调度 **Alas (AzurPilot)** 和**Mumu模拟器**，并最小化隐藏窗口以**无感运行**。

> ⚠️ **免责声明与注意事项**
> - **个人项目**：本项目为作者课余所作，能力有限，请见谅。
> - **AI 辅助**：本项目许多代码都是 AI辅助完成。
> - **风险自担**：本工具仅供技术交流与个人自动化测试使用。作者不对使用本脚本过程中可能产生的任何潜在风险、账号异常、系统问题或财产损失承担任何责任。

---

## ✨ 已实现的功能

* 🤖 **Alas (AzurPilot) 管理**：
  * **提权启动**：支持检测 Alas 运行状态，通过 UAC 管理员权限拉起运行。
  * **自动最小化**：基于 Win32 GDI 内存快照与多维颜色（`#3B82F6` 蓝色 / `#FEBC2E` 黄色）矩阵匹配，自动扫描窗口标题栏，点击最小化按钮。
  * **网页交互**：集成 Playwright 无头浏览器，自动登录 Alas 网页后台，处理版本更新，以及启动中断的调度器。
  * **故障检测**：本地监听智慧港区的 Onepush 推送，收到错误提醒时，自动尝试解决问题。
  * **进程清理**：可强行释放被占用的通信端口（`22267` / `22268`）。

* 🎮 **MuMu 模拟器管理**：
  * **运行补齐**：同时检测 `mumunxmain` 与 `mumunxdevice` 进程状态，缺一即自动补齐拉起。
  * **窗口隐藏**：使用 Win32 API 精准抓取真实渲染界面，自动模拟预设老板键（`Ctrl` + `Alt` + `→`）确保窗口隐藏。
  * **自动重启**：当检测到 `EmulatorNotRunningError` 或未知卡死时，自动重启并重新隐藏模拟器。

* 🔔 **Bark 消息推送**：
  * **分级推送**：提供 `Warning`、`Error`和 `Notify`（非`TimeSensitive`）三个函数。
  * **主题图标** 默认用碧蓝航线♡英仙座♡(`Perseus`)的JUUs作为图标。

* 📑 **日志轮转**：
  * 无缝重定向 `sys.stdout`，将所有控制台输出同步存盘至 `logs/` 目录。
  * 支持日志自动分卷轮转（单个文件上限 5MB，最多保留 20 个备份）。

* 🌐 **OnePush网关**：
  * 基于 Flask 构建轻量级 Web 接收服务端（默认端口 `25566`），支持 GET/POST/JSON 参数解析。
  * 接收来自智慧港区的错误提醒，并尝试解决。

---

## ⚙️ 核心配置与前置设置

> 💡 **特别说明**：本项目**暂时没有单独设立统一的配置文件**（如 `.env` 或 `config.ini`）。大部分运行参数（如端口号、程序路径、超时时间、Bark Key 等）需要**直接在对应 Python 代码文件开头的“配置区”中手动修改**。

### 1. 代码文件参数修改 🛠️
在启动各脚本前，请根据你的实际环境修改代码顶部的变量定义：
* **`zBarkCustom.py`**：修改你的 Bark 服务器地址与推送 Key。
* **`zMumu.py`**：修改 MuMu 模拟器的安装路径与运行参数。
* **`zAlas.py`**：修改 Alas / AzurPilot 路径及通信端口（默认 `22267`）。
* **`zPushServer.py`**：修改监听端口（默认 `25566`）。
* 等等

### 2. MuMu 模拟器老板键设置 ⚠️【重要】
为了使脚本能够顺利自动隐藏 MuMu 模拟器窗口，请务必在 **MuMu 模拟器设置** 中将老板键修改为：
> **老板键快捷键**：`Ctrl` + `Alt` + `→` (方向键右)

### 3. WebUI 身份凭证配置 (`auth.json`)
在项目根目录下，`auth.json` 用于保存 Playwright 自动控制 Alas WebUI 时的身份凭证。

如果你的 Alas 设置了 WebUI 访问密码，请将 `password` 字段的 `value` 替换为你的真实密码（未设置可留空或保留默认值）：

```
json
{
  "cookies": [],
  "origins": [
    {
      "origin": "http://127.0.0.1:22267",
      "localStorage": [
        {
          "name": "password",
          "value": "你的WebUI密码"
        },
        {
          "name": "aside",
          "value": "alas"
        }
      ]
    }
  ]
}
```

### 4.AzurPilot推送设置
请去azurpilot面板`智慧港区设置`把`错误推送设置`改为如下所示
```
provider: bark
key: http://127.0.0.1:25566/push
```

---

## 📁项目架构与模块说明

lajiovo-autotools/

├── begin.bat           # 启动脚本（建议去系统的“任务计划程序” taskschd.msc 里加开机自动运行）

├── zAlas.py            # Alas 运维管理（UAC 提权启动/黑名单进程全清/通信端口强退）

├── zHideAlas.py            # Alas 窗口最小化（基于 Win32 GDI 内存快照与多维颜色矩阵匹配）

├── zMumu.py            # MuMu 模拟器控制（进程检测/管理员拉起/真实窗口识别与 Ctrl+Alt+→ 隐藏）

├── zPlaywright.py      # Playwright 网页自动化（关闭公告/处理更新/重启调度器/错误诊断）

├── zOnepush.py      # Flask Webhook 推送网关（监听 25566 端口，自动清理占用）

├── zPushhandler.py     # 消息路由中心（解析推送、触发 Playwright 修复与钻石喜报）

├── zPerseusLogger.py   # 全局日志接管重定向 (5MB * 20 备份轮转) + Bark 专属日志组件

├── zBark.py            # 自制 Bark API 底层封装 (单发/群发/iOS高级推送属性)

├── zBarkCustom.py      # Perseus 专属分级日志组件 (Warning / Error / Notice)

├── auth.json           # Playwright 自动登录凭证与密码配置文件

├── LICENSE             # GPL v3 开源许可证文件

├── log/                # 日志文件夹

└── README.md           # 项目说明文档

---

## 📦 环境依赖与安装（未更新）

> 确保你的 Python 环境在 Windows 平台运行（部分模块涉及 Windows API 与 PowerShell）：

### 安装基础依赖
```
pip install requests flask psutil pyautogui pywin32 playwright
```

### 初始化 Playwright 浏览器内核 (Chromium)
```
playwright install chromium
```

---

## 🚀 快速使用指南（未更新）
### 1. 启动全自动 Webhook 守护服务
直接运行 zPushServer.py 启动接收服务
```
python zPushServer.py
```

### 2. 手动执行 Playwright 修复诊断
如需测试 UI 自动化控制逻辑，可直接运行：
```
from zPlaywright import main as mainplaywright
mainplaywright(headless=True, mummu_hide=True)
```

### 3. 单独控制模拟器隐藏
确保已在 MuMu 设置中把老板键设为 Ctrl + Alt + 右，运行以下代码测试自动唤醒与隐藏：
```
from zMumu import hidemumu
hidemumu()
```

### 4. 发送 Bark 测试通知
```
from zBarkCustom import PerseusNotifyMsg, PerseusErrorMsg
PerseusNotifyMsg("测试通知", "这是一个 Perseus 静默通知")
PerseusErrorMsg("异常测试", "这是一个突破勿扰模式的强提醒")
```

---

## 📄 开源许可证 / License

本项目采用 **GNU General Public License v3.0 (GPL-3.0)** 开源许可证。  
This project is licensed under the **GNU General Public License v3.0 (GPL-3.0)**.

### 📌 GPL v3 核心条款摘要 / Terms Summary

- **自由使用与修改 / Free Use & Modification**：  
  任何人均可免费商业使用、修改及分发本项目代码。  
  *Anyone can freely modify, distribute, and use this project for commercial or non-commercial purposes.*

- **强开源传染性（关键）/ Copyleft Protection**：  
  如果您修改了本项目代码，或在您的项目中引用/合并了本项目的任何部分，**您的衍生项目也必须无条件以 GPL v3 许可证完整开源**。  
  *If you modify this codebase or incorporate any part of it into your own project, **your derived work must also be fully open-sourced under the GPL v3 license**.*

- **保留版权声明 / Copyright Notice**：  
  在分发源码或衍生作品时，必须完整保留原作者的版权声明及 GPL v3 许可证文本。  
  *Distributions of source code or derived works must retain the original copyright notice and GPL v3 text.*

- **禁止附加限制 / No Additional Restrictions**：  
  不得将本项目代码用于闭源商业软件的分发，亦不得增加超越 GPL v3 范围的附加限制条款。  
  *You may not restrict others from exercising the rights granted by GPL v3 or distribute this code within closed-source proprietary software.*

- **免责声明 / Disclaimer**：  
  本项目按“原样”提供，不提供任何形式的明示或暗示担保，作者不对使用本软件造成的任何直接或间接损失承担责任。  
  *This project is provided "AS IS" without warranty of any kind. The author assumes no liability for any damages arising from its use.*

👉 完整的许可证文本请参阅项目根目录下的 [LICENSE](LICENSE) 文件，或访问 [GNU GPL v3 官方页面](https://www.gnu.org/licenses/gpl-3.0.html)。  
*For the full license text, please refer to the [LICENSE](LICENSE) file or visit [GNU GPL v3 Official Page](https://www.gnu.org/licenses/gpl-3.0.html).*
