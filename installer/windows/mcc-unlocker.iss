; MCC Unlocker — installateur Windows (Inno Setup 6).
; Construit après PyInstaller sur Windows ; ne pas compiler depuis macOS.

#define MyAppName "MCC Unlocker"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "MCC-Unlocker contributors"
#define MyAppExeName "MCC-Unlocker.exe"

[Setup]
AppId={{7B8A0F3D-6F64-4E2B-9A2C-2D8E2D9B3C11}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\MCC Unlocker
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\..\dist
OutputBaseFilename=MCC-Unlocker-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
; Code signing is configured in CI when a certificate is available.
; SignedUninstaller / SignTool are intentionally not hard-coded here.

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Files]
Source: "..\..\dist\MCC-Unlocker\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le Bureau"; GroupDescription: "Raccourcis :"; Flags: unchecked

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Lancer {#MyAppName}"; Flags: nowait postinstall skipifsilent
