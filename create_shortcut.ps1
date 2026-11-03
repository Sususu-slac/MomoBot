$ErrorActionPreference='Stop'
$shell=New-Object -ComObject WScript.Shell
$link=$shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'MomoBot.lnk'))
$link.TargetPath=Join-Path $env:WINDIR 'System32\wscript.exe'
$link.Arguments='"'+(Join-Path $PSScriptRoot 'run_momobot.vbs')+'"'
$link.WorkingDirectory=$PSScriptRoot
$link.IconLocation=Join-Path $PSScriptRoot 'assets\momobot-orange-kitten.ico'
$link.Description='MomoBot local reconstruction, segmentation and fine-tuning assistant'
$link.Save()
