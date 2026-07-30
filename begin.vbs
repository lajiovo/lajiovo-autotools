Option Explicit

Dim http, pingUrl, startUrl, responseText, handlepushVal
Dim Shell, FSO, scriptDir, batPath

pingUrl = "http://127.0.0.1:25566/ping"
startUrl = "http://127.0.0.1:25566/start"

On Error Resume Next

' 1. 创建 HTTP 请求对象
Set http = CreateObject("MSXML2.ServerXMLHTTP.6.0")
If http Is Nothing Then
    Set http = CreateObject("MSXML2.ServerXMLHTTP")
End If

' 设置超时时间 (单位：毫秒) -> 域名, 连接, 发送, 接收
http.setTimeouts 1500, 1500, 1500, 1500

' 2. 尝试访问 /ping 接口
http.open "GET", pingUrl, False
http.send

' 判断网络连接情况
If Err.Number <> 0 Or http.status <> 200 Then
    ' ==================== 情况 3：无法访问服务 ====================
    Err.Clear
    Set http = Nothing
    
    Set Shell = CreateObject("Shell.Application")
    Set FSO = CreateObject("Scripting.FileSystemObject")

    scriptDir = FSO.GetParentFolderName(WScript.ScriptFullName)
    batPath = scriptDir & "\begin.bat"

    ' 判断 bat 文件是否存在
    If FSO.FileExists(batPath) Then
        Dim attempts, success
        attempts = 0
        success = False

        ' 管理员权限拒绝重试循环，最多尝试 3 次
        Do While attempts < 3 And Not success
            attempts = attempts + 1
            Err.Clear
            
            ' 以管理员权限 (runas) 和隐藏窗口 (0) 尝试运行 BAT
            Shell.ShellExecute batPath, "", scriptDir, "runas", 0
            
            ' 如果 ShellExecute 被拒绝 (如点击了 UAC 否)，Err.Number 会捕获到异常
            If Err.Number = 0 Then
                success = True
            Else
                ' 如果被拒绝，稍等 0.5 秒后再发起下一次提权请求
                WScript.Sleep 500
            End If
        Loop
    End If

    Set Shell = Nothing
    Set FSO = Nothing
    WScript.Quit
End If

' 3. 解析 /ping 返回的 JSON 结果
responseText = http.responseText
Set http = Nothing

handlepushVal = ParseHandlepush(responseText)

If handlepushVal = "true" Then
    ' ==================== 情况 1：返回 True ====================
    ' 任务直接结束
    WScript.Quit

ElseIf handlepushVal = "false" Then
    ' ==================== 情况 2：返回 False ====================
    ' 访问 /start 接口：改用同步模式(False)，确保请求顺利发出后再退出
    Set http = CreateObject("MSXML2.ServerXMLHTTP.6.0")
    If http Is Nothing Then Set http = CreateObject("MSXML2.ServerXMLHTTP")
    
    ' 设置较短的超时，发出去即算完成
    http.setTimeouts 1000, 1000, 1000, 1000
    http.open "GET", startUrl, False
    http.send
    
    Set http = Nothing
    WScript.Quit
Else
    ' 解析非预期结果时兜底处理：也可以默认触发 /start 或者启动
    WScript.Quit
End If


' ============================================================
' 辅助函数：更加稳健的 JSON / 字符串匹配解析
' ============================================================
Function ParseHandlepush(jsonStr)
    Dim lowerStr
    ' 统一转为小写
    lowerStr = LCase(jsonStr)
    
    ' 优先判断是否存在 handlepush 字段
    If InStr(lowerStr, "handlepush") > 0 Then
        ' 检测 handlepush 后面跟着的是 false 还是 true
        ' 兼容 {"handlepush": false} 或 {"handlepush": "false"} 等格式
        If InStr(lowerStr, "false") > 0 Then
            ParseHandlepush = "false"
        ElseIf InStr(lowerStr, "true") > 0 Then
            ParseHandlepush = "true"
        Else
            ParseHandlepush = "unknown"
        End If
    Else
        ParseHandlepush = "not_found"
    End If
End Function
