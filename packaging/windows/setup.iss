#define AppName "ClipFlow"
#ifndef AppVersion
  #error AppVersion must be supplied by scripts/build.py
#endif

[Setup]
AppId={{7624D3E9-7848-4DB1-A1F9-071096576222}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\ClipFlow
UsePreviousAppDir=no
DefaultGroupName={#AppName}
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableDirPage=no
DisableProgramGroupPage=yes
OutputDir=..\..\outputs
OutputBaseFilename=ClipFlow-Setup-{#AppVersion}
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\..\assets\icons\clipflow.ico
UninstallDisplayIcon={app}\ClipFlow.exe
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
ShowLanguageDialog=yes
UsePreviousLanguage=no
LanguageDetectionMethod=none

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Ярлыки:"

[Files]
Source: "..\..\outputs\ClipFlow\*"; DestDir: "{app}"; Excludes: "unins*,*.py,*.pyc,*.pyo,__pycache__\*,*.spec,*.log"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal\customtkinter"
Type: filesandordirs; Name: "{app}\_internal\yt_dlp"
Type: filesandordirs; Name: "{app}\_internal\yt_dlp_ejs"
Type: files; Name: "{app}\downloader.py"
Type: files; Name: "{app}\embedded_auth.py"
Type: files; Name: "{app}\youtube_session.py"
Type: files; Name: "{app}\__pycache__\downloader.*.pyc"
Type: files; Name: "{app}\__pycache__\embedded_auth.*.pyc"
Type: files; Name: "{app}\__pycache__\youtube_session.*.pyc"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\ClipFlow.exe"; WorkingDir: "{app}"; IconFilename: "{app}\ClipFlow.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\ClipFlow.exe"; WorkingDir: "{app}"; IconFilename: "{app}\ClipFlow.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ClipFlow.exe"; Description: "Запустить ClipFlow"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var Lang: String;
begin
  if CurStep = ssPostInstall then
  begin
    Lang := 'ru';
    if ExpandConstant('{language}') = 'english' then Lang := 'en';
    SaveStringToFile(ExpandConstant('{app}\language.txt'), '{#AppVersion}:' + Lang, False);
  end;
end;
