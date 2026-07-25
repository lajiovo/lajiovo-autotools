Set Shell = CreateObject("Shell.Application")
Set FSO = CreateObject("Scripting.FileSystemObject")

' 获取当前 VBS 脚本所在目录及 BAT 文件完整路径
scriptDir = FSO.GetParentFolderName(WScript.ScriptFullName)
batPath = scriptDir & "\begin.bat"

' 以管理员权限 (runas)、完全隐藏窗口 (0) 的方式直接运行 BAT
Shell.ShellExecute batPath, "", scriptDir, "runas", 0
