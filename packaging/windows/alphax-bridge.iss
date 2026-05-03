; AlphaX POS Bridge — Windows installer
; Build with Inno Setup 6 (https://jrsoftware.org/isinfo.php):
;   iscc packaging\windows\alphax-bridge.iss
;
; Prereq: PyInstaller has produced dist\alphax-bridge\ from the .spec file.

#define AppName       "AlphaX POS Bridge"
#define AppVersion    "15.5.0"
#define AppPublisher  "AlphaX"
#define AppURL        "https://github.com/alphax/alphax-pos-suite"
#define AppExeName    "alphax-bridge.exe"

[Setup]
AppId={{6F4A1AB2-7DC1-4F1E-B7E8-21C0A3F90A4E}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
DefaultDirName={autopf}\AlphaX POS Bridge
DefaultGroupName=AlphaX POS Bridge
AllowNoIcons=yes
LicenseFile=..\..\license.txt
OutputDir=..\..\dist\installers
OutputBaseFilename=AlphaX-POS-Bridge-Setup-{#AppVersion}
SetupIconFile=..\assets\alphax-bridge.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64
UninstallDisplayIcon={app}\{#AppExeName}

; Don't require admin: we install per-user by default (so it works on
; Frappe Cloud-style locked-down corporate machines without UAC).
; If user has admin, they can choose machine-wide install on the
; privileges dialog.

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon";   Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"
Name: "autostart";     Description: "Start AlphaX POS Bridge automatically when I sign in"; GroupDescription: "Startup:"; Flags: checkedonce
Name: "openconsole";   Description: "Open the cashier UI in my browser after install"; GroupDescription: "Post-install:"; Flags: checkedonce

[Files]
; PyInstaller output — the entire dist\alphax-bridge\ folder.
Source: "..\..\dist\alphax-bridge\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}";              Filename: "{app}\{#AppExeName}"
Name: "{group}\Edit configuration";       Filename: "{app}\{#AppExeName}"; Parameters: "--edit-config"
Name: "{group}\View logs";                Filename: "{app}\{#AppExeName}"; Parameters: "--view-logs"
Name: "{group}\Uninstall {#AppName}";     Filename: "{uninstallexe}"
Name: "{userdesktop}\{#AppName}";         Filename: "{app}\{#AppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}";         Filename: "{app}\{#AppExeName}"; Tasks: autostart

[Run]
; First-run setup wizard
Filename: "{app}\{#AppExeName}"; Parameters: "--wizard"; Description: "Run setup wizard now"; Flags: postinstall nowait skipifsilent
; Optional: open cashier UI
Filename: "https://www.google.com/"; Description: "Open cashier UI in browser"; Flags: shellexec postinstall skipifsilent runasoriginaluser; Tasks: openconsole

[UninstallDelete]
; Don't delete the user's config — they may reinstall and want to keep it.
; Logs go away because they live under %USERPROFILE% and can be cleared by the user.
Type: filesandordirs; Name: "{app}\__pycache__"

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
  // Reserved for future preflight checks (Python version, free disk, etc).
end;
