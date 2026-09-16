#define AppName "Slitlamp Studio"
#define AppVersion "0.1.0"
[Setup]
AppId={{36585BC4-501E-432D-B773-285C114983CB}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Slitlamp Studio
AppPublisherURL=https://github.com/bgcronin/Slitlampcamerasystem
DefaultDirName={localappdata}\Programs\SlitlampStudio
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\installer
OutputBaseFilename=SlitlampStudio-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\SlitlampStudio.exe
CloseApplications=yes

[Files]
Source: "..\dist\SlitlampStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\SlitlampStudio.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\SlitlampStudio.exe"
Name: "{group}\{#AppName} Demo"; Filename: "{app}\SlitlampStudio.exe"; Parameters: "--demo"
Name: "{group}\Choose Slitlamp archive"; Filename: "{app}\SlitlampStudio.exe"; Parameters: "--choose-archive"

[Run]
Filename: "{app}\SlitlampStudio.exe"; Description: "Open Slitlamp Studio"; Flags: nowait postinstall skipifsilent

; Patient data is stored outside {app}. There is intentionally no uninstall-delete entry for it.
