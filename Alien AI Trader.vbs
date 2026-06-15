' Alien AI Trader - silent launcher.
' Starts the local app server with NO visible window, then opens the dashboard
' in your default browser once it is ready. One double-click, nothing to read.
Option Explicit
Dim sh, fso, appDir
Set sh  = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
appDir = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = appDir

' 0 = hidden window, False = do not wait. The server keeps running in this
' hidden console for as long as the app is open.
sh.Run "cmd /c """ & appDir & "\_server.bat""", 0, False

' A separate hidden helper waits until the server is ready, then opens the
' dashboard in the default browser. Keeps the two jobs from blocking each other.
sh.Run "cmd /c """ & appDir & "\_open_browser.bat""", 0, False
