[Setup]
AppId={{A4E3A1A5-7A5D-47B9-A60B-57530AAEA673}
AppName=MomoBot
AppVersion=0.10.0
AppPublisher=BL62
AppPublisherURL=https://github.com/Sususu-slac/MomoBot
DefaultDirName={localappdata}\Programs\MomoBot
DefaultGroupName=MomoBot
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
OutputDir=release
OutputBaseFilename=MomoBot_Setup_0.10.0
SetupIconFile=assets\momobot-orange-kitten.ico
UninstallDisplayIcon={app}\assets\momobot-orange-kitten.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: checkedonce
[Files]
Source: "release_source\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{autoprograms}\MomoBot"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\run_momobot.vbs"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\momobot-orange-kitten.ico"
Name: "{autodesktop}\MomoBot"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\run_momobot.vbs"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\momobot-orange-kitten.ico"; Tasks: desktopicon
