; Bulkrr 2.0 Windows installer preview.
; This is a test installer only. Publishing requires explicit approval.
#define AppName "Bulkrr"
#define AppVersion "2.0.0-beta"
#define AppExe "Bulkrr-2.0-preview.exe"

[Setup]
AppId={{CF0D631A-95B8-4FA5-A1C2-2E7F1A61D0C1}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=DOM
DefaultDirName={autopf}\Bulkrr
DefaultGroupName=Bulkrr
DisableProgramGroupPage=yes
OutputDir=installer-dist
OutputBaseFilename=Bulkrr-2.0-Windows-setup-preview
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#AppExe}

[Files]
Source: "dist\Bulkrr-2.0-preview\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Bulkrr"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\Bulkrr"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch Bulkrr"; Flags: nowait postinstall skipifsilent
