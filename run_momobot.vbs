Option Explicit
Dim shell, fs, folder, env, envs, python, state, item, hasLegacy
Set shell = CreateObject("WScript.Shell")
Set fs = CreateObject("Scripting.FileSystemObject")
Set env = shell.Environment("PROCESS")
folder = fs.GetParentFolderName(WScript.ScriptFullName)
envs = env("BL62_CONDA_ENVS")
If envs = "" Then envs = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\miniforge3\envs"
python = envs & "\BL62_Studio\pythonw.exe"
If Not fs.FileExists(python) Then
  MsgBox "Python environment BL62_Studio was not found. See README.md for setup.", 48, "MomoBot setup"
  WScript.Quit 1
End If
If env("MOMOBOT_STATE_ROOT") = "" Then
  hasLegacy = False
  If fs.FolderExists(folder & "\conversations") Then
    For Each item In fs.GetFolder(folder & "\conversations").Files
      If LCase(fs.GetExtensionName(item.Name)) = "json" Then hasLegacy = True
    Next
  End If
  If hasLegacy Then
    env("MOMOBOT_STATE_ROOT") = folder
  Else
    env("MOMOBOT_STATE_ROOT") = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\BL62_UserData\MomoBot"
  End If
End If
If env("MOMOBOT_RUNTIME_ROOT") = "" And Not fs.FolderExists(folder & "\runtime\llama-b11988") Then
  If fs.FolderExists("D:\BL62_Assistant_Chat\runtime\llama-b11988") Then env("MOMOBOT_RUNTIME_ROOT") = "D:\BL62_Assistant_Chat\runtime\llama-b11988"
End If
env("PYTHONNOUSERSITE") = "1"
env("PYTHONUTF8") = "1"
shell.CurrentDirectory = folder
shell.Run Chr(34) & python & Chr(34) & " " & Chr(34) & folder & "\app.py" & Chr(34), 1, False
