' SJTU Assistant - launch without a console window.
' Content is ASCII-only on purpose: WSH reads .vbs as ANSI unless a BOM is
' present, so non-ASCII source text would be garbled on a GBK locale.
Option Explicit
Dim shell, fso, here, exe, py
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

here = fso.GetParentFolderName(WScript.ScriptFullName)

exe = "C:\Users\Administrator\AppData\Local\Programs\Python\Python312\pythonw.exe"
If Not fso.FileExists(exe) Then exe = "pythonw.exe"

If Not fso.FileExists(here & "\app.py") Then
  MsgBox "app.py not found next to this launcher:" & vbCrLf & here, 16, "SJTU Assistant"
  WScript.Quit 1
End If

shell.CurrentDirectory = here
' Window style must be 1 (normal). Style 0 (hidden) also hides the GUI window
' pywebview creates, leaving a live process with no visible window.
' pythonw.exe is a GUI-subsystem binary, so no console flashes either way.
WScript.Quit shell.Run("""" & exe & """ """ & here & "\app.py""", 1, False)
