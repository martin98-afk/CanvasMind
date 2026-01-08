[Setup]
AppName=CanvasMind
AppVersion=v0.2.6
DefaultDirName={autopf}\CanvasMind
DefaultGroupName=CanvasMind
OutputBaseFilename=CanvasMind_installer
Compression=lzma2
SolidCompression=yes
SetupIconFile=logoico.ico
UninstallDisplayIcon={app}\CanvasMind.exe
AppMutex=CanvasMind_Mutex_String
CloseApplications=yes

[Files]
Source: "CanvasMind\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\CanvasMind"; Filename: "{app}\main.exe"
Name: "{autodesktop}\CanvasMind"; Filename: "{app}\main.exe"; Tasks: desktopicon

[Tasks]
Name: desktopicon; Description: "Create a desktop icon"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\main.exe"; Description: "{cm:LaunchProgram,CanvasMind}"; Flags: nowait postinstall skipifsilent