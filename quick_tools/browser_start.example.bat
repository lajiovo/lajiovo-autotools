@echo off
:: 切换到目标目录（/d 确保能跨盘符切换）
cd /d "D:\???r\Perseus"

:: 使用指定的 pythonw.exe 后台运行 zBrowser.py
start "" "C:\Users\???\AppData\Local\Programs\Python\Python314\pythonw.exe" "zBrowser.py"

exit