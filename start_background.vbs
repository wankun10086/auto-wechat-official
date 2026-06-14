' 无窗口后台启动 Auto WeChat（不弹出任何 CMD 控制台，日志只在网页里看）
' 双击本文件即可启动；停止请运行 stop_server.bat
Set fso = CreateObject("Scripting.FileSystemObject")
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.Run "cmd /c set AUTOWECHAT_BACKGROUND=1&&pythonw.exe -m web.server 8000", 0, False
