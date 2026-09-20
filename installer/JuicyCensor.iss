#ifndef PayloadDir
  #error PayloadDir must point to the staged application folder
#endif
#ifndef ReleaseDir
  #define ReleaseDir "..\release"
#endif
[Setup]
AppId={{87EB6B6A-613E-4D53-8E9F-CAB413902000}
AppName=JuicyCensor
AppVersion=2.0.2
AppPublisher=JuicyCensor
AppPublisherURL=https://github.com/seagullslayer7/JuicyCensor
AppSupportURL=https://github.com/seagullslayer7/JuicyCensor/issues
AppUpdatesURL=https://github.com/seagullslayer7/JuicyCensor/releases
DefaultDirName={localappdata}\Programs\JuicyCensor 2.0
DefaultGroupName=JuicyCensor
DisableDirPage=no
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir={#ReleaseDir}
OutputBaseFilename=JuicyCensor-2.0.2-Windows-x64-Setup
SetupIconFile=..\assets\orange.ico
UninstallDisplayIcon={app}\JuicyCensor.exe
LicenseFile=..\LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
Uninstallable=not PortableMode
CreateUninstallRegKey=not PortableMode

[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: unchecked; Check: not PortableMode

[Files]
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "config.json,banned_words.txt,banned_phrases.txt"
Source: "{#PayloadDir}\config.json"; DestDir: "{app}"; Flags: onlyifdoesntexist uninsneveruninstall
Source: "{#PayloadDir}\banned_words.txt"; DestDir: "{app}"; Flags: onlyifdoesntexist uninsneveruninstall
Source: "{#PayloadDir}\banned_phrases.txt"; DestDir: "{app}"; Flags: onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{group}\JuicyCensor"; Filename: "{app}\JuicyCensor.exe"; WorkingDir: "{app}"; Check: not PortableMode
Name: "{autodesktop}\JuicyCensor"; Filename: "{app}\JuicyCensor.exe"; WorkingDir: "{app}"; Tasks: desktopicon; Check: not PortableMode

[Run]
Filename: "{app}\JuicyCensor.exe"; Description: "Launch JuicyCensor and set up its processing runtime"; Flags: nowait postinstall skipifsilent

[Code]
function PortableMode: Boolean;
begin
  Result := ExpandConstant('{param:PORTABLE|0}') = '1';
end;
