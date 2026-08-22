@echo off
:: 设置UTF-8编码，解决中文乱码
chcp 65001 >nul
setlocal enabledelayedexpansion

:: ====================== 配置区（只改这里即可）======================
:: 脚本存放根目录
set SCRIPT_DIR=D:\???\Perseus
:: 带控制台窗口 Python 完整路径
set PYTHON_EXE=C:\Users\???\AppData\Local\Programs\Python\Python314\python.exe
:: 无窗口后台运行 pythonw 路径
set PYTHONW_EXE=C:\Users\???\AppData\Local\Programs\Python\Python314\pythonw.exe
:: =================================================================

:: 切换到脚本目录
cd /d "%SCRIPT_DIR%" || (
    echo 【错误】无法进入目录：%SCRIPT_DIR%
    pause
    goto END
)

:: 检查 pythonw 是否存在
if not exist "%PYTHONW_EXE%" (
    echo 【错误】找不到 pythonw.exe 路径：%PYTHONW_EXE%
    pause
    goto END
)

:: 启动 begin.pyw
if exist "begin.pyw" (
    echo 正在后台启动 begin.pyw ...
    powershell -Command "$p = New-Object System.Diagnostics.ProcessStartInfo; $p.FileName = '%PYTHONW_EXE%'; $p.Arguments = 'begin.pyw'; $p.WorkingDirectory = '%SCRIPT_DIR%'; $p.UseShellExecute = $true; [System.Diagnostics.Process]::Start($p) | Out-Null"
    if !errorlevel! equ 0 (
        echo 启动命令执行成功（pythonw无控制台，程序异常需要查看脚本自身日志）
    ) else (
        echo 【警告】powershell启动调用返回异常
        pause
    )
) else (
    echo 【错误】目录内未找到 begin.pyw
    pause
)

:END
endlocal
echo.
echo 脚本执行完毕，3秒后自动关闭，按任意键立即关闭...
timeout /t 3 >nul
pause >nul
exit /b
