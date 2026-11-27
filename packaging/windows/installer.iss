; Inno Setup script for CompTIA Linux+ (XK0-006 / V8) Study Trainer
#define MyAppName "CompTIA Linux+ Study Trainer"
#define MyAppShortName "LinuxPlusTrainer"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Linux+ Trainer Contributors"
#define MyAppExeName "LinuxPlusTrainer.exe"

[Setup]
AppId={{8D4F62E1-3B9A-4D7E-9A55-7B1F2E4D90C1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppShortName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=..\..\dist\installer
OutputBaseFilename=LinuxPlusTrainer-Setup-Windows
SetupIconFile=..\assets\linux-plus-trainer.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\..\dist\LinuxPlusTrainer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{#MyAppName} (Terminal Mode)"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--terminal"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
