[Setup]
AppName=CanvasMind
AppVersion=v0.2.3
DefaultDirName={autopf}\CanvasMind
DefaultGroupName=CanvasMind
OutputBaseFilename=CanvasMind_installer
Compression=lzma2
SolidCompression=yes
SetupIconFile=logoico.ico
UninstallDisplayIcon={app}\CanvasMind.exe

[Files]
Source: "CanvasMind\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\CanvasMind"; Filename: "{app}\main.exe"
Name: "{autodesktop}\CanvasMind"; Filename: "{app}\main.exe"; Tasks: desktopicon

[Tasks]
Name: desktopicon; Description: "Create a desktop icon"; GroupDescription: "Additional icons:"