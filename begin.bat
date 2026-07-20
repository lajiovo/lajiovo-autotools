@echo off
:: 设置UTF-8编码，解决中文乱码
chcp 65001 >nul
:: 关闭命令回显
setlocal enabledelayedexpansion

:: ====================== 配置区（只改这里即可）======================
:: 脚本存放根目录
set SCRIPT_DIR=
:: 虚拟环境Python完整路径
set PYTHON_EXE=\Python\Python314\python.exe
:: =================================================================

echo 正在准备运行脚本...
echo 脚本目录：%SCRIPT_DIR%
echo Python解释器路径：%PYTHON_EXE%
echo --------------------------------------------------

:: 切换到脚本目录，后续文件判断、执行都基于此目录
cd /d "%SCRIPT_DIR%"

:: 校验Python解释器是否存在
if not exist "%PYTHON_EXE%" (
    echo [致命错误] 找不到指定Python解释器，请检查路径：%PYTHON_EXE%
    pause >nul
    exit /b 1
)

:: 第一个脚本 zMumu.py
if exist "zMumu.py" (
    echo [1/2] 正在运行 zMumu.py...
    "%PYTHON_EXE%" "zMumu.py"
    :: 捕获上一步运行返回码，判断是否报错
    if !errorlevel! neq 0 (
        echo [警告] zMumu.py 运行过程出现异常，错误码：!errorlevel!
    )
) else (
    echo [错误] 未找到 zMumu.py，目录：%SCRIPT_DIR%
)

echo --------------------------------------------------

:: 第二个脚本 zAlas.py
if exist "zAlas.py" (
    echo [2/2] 正在运行 zAlas.py...
    "%PYTHON_EXE%" "zAlas.py"
    if !errorlevel! neq 0 (
        echo [警告] zAlas.py 运行过程出现异常，错误码：!errorlevel!
    )
) else (
    echo [错误] 未找到 zAlas.py，目录：%SCRIPT_DIR%
)

:: 第三个脚本 zPlaywright.py
if exist "zPlaywright.py" (
    echo [2/2] 正在运行 zPlaywright.py...
    "%PYTHON_EXE%" "zPlaywright.py"
    if !errorlevel! neq 0 (
        echo [警告] zPlaywright.py 运行过程出现异常，错误码：!errorlevel!
    )
) else (
    echo [错误] 未找到 zPlaywright.py，目录：%SCRIPT_DIR%
)

echo --------------------------------------------------
echo 全部脚本执行流程结束，按任意键关闭窗口
::pause >nul
endlocal