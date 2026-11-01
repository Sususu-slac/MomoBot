$taskRoot = 'D:\BL62_Assistant_Chat'
$taskPython = Join-Path $env:LOCALAPPDATA 'miniforge3\envs\BL62_Studio\pythonw.exe'
$taskShell = New-Object -ComObject WScript.Shell
$taskDesktop = [Environment]::GetFolderPath('Desktop')
$taskOldLink = Join-Path $taskDesktop 'BL62 Assistant Chat.lnk'
$taskNewLink = Join-Path $taskDesktop 'MomoBot.lnk'
if ((Test-Path $taskOldLink) -and -not (Test-Path $taskNewLink)) {
    Rename-Item -LiteralPath $taskOldLink -NewName 'MomoBot.lnk'
}
$taskLink = $taskShell.CreateShortcut($taskNewLink)
$taskLink.TargetPath = $taskPython
$taskLink.Arguments = '"D:\BL62_Assistant_Chat\app.py"'
$taskLink.WorkingDirectory = $taskRoot
$taskLink.IconLocation = Join-Path $taskRoot 'assets\momobot-orange-kitten.ico'
$taskLink.Description = 'MomoBot - local reconstruction, segmentation and fine-tuning assistant'
$taskLink.Save()
Write-Output $taskLink.FullName
