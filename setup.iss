#define MyAppVersion "1.0.1"

[Setup]
AppVersion={#MyAppVersion}
AppName=FamilBudget
AppVersion=1.0.0
AppPublisher=Shawn
DefaultDirName={autopf}\FamilBudget
DefaultGroupName=FamilBudget
OutputDir=installer
OutputBaseFilename=FamilBudgetSetup
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "danish"; MessagesFile: "compiler:Languages\Danish.isl"

[Files]
Source: "dist\budget.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\budget.db"; DestDir: "{app}"; Flags: ignoreversion
Source: "version.json"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Budget Manager"; Filename: "{app}\budget.exe"
Name: "{commondesktop}\Budget Manager"; Filename: "{app}\budget.exe"

[Run]
Filename: "{app}\budget.exe"; Description: "Start Budget Manager"; Flags: nowait postinstall skipifsilent