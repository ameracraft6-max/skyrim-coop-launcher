; Inno Setup Script for Skyrim Together Reborn Co-op Pack
#define MyAppName "Skyrim Together Reborn"
#define MyAppVersion "1.8.0"
#define MyAppPublisher "Skyrim Together Team"
#define MyAppExeName "Data\SkyrimTogetherReborn\SkyrimTogether.exe"
#define MyServerExeName "Data\SkyrimTogetherReborn\SkyrimTogetherServer.exe"
#define MyLauncherExeName "SkyrimCoopLauncher.exe"

[Setup]
AppId={{C575BB9D-4433-4974-A7C3-194FDA039CA9}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={code:GetDefaultSkyrimPath}
DefaultGroupName={#MyAppName}
OutputDir=E:\NEW WORLD\SkyrimCoopLauncher\setup\output
OutputBaseFilename=SkyrimTogether_Setup
SetupIconFile=E:\NEW WORLD\SkyrimCoopLauncher\assets\app_icon.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
DisableDirPage=no
AppendDefaultDirName=no
PrivilegesRequired=lowest
UninstallFilesDir={app}\Data\SkyrimTogetherReborn\uninstall

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Messages]
russian.SelectDirBrowseLabel=Выберите корневую папку с установленной игрой Skyrim Special Edition (где лежит файл SkyrimSE.exe):

[Files]
Source: "E:\NEW WORLD\SkyrimCoopLauncher\setup\files\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Skyrim Together (Играть)"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}\Data\SkyrimTogetherReborn"
Name: "{group}\Сервер Skyrim Together"; Filename: "{app}\{#MyServerExeName}"; WorkingDir: "{app}\Data\SkyrimTogetherReborn"
Name: "{group}\Лаунчер и Сервер Hub"; Filename: "{app}\{#MyLauncherExeName}"; WorkingDir: "{app}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"

Name: "{autodesktop}\Skyrim Together (Играть)"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}\Data\SkyrimTogetherReborn"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Сервер Skyrim Together"; Filename: "{app}\{#MyServerExeName}"; WorkingDir: "{app}\Data\SkyrimTogetherReborn"
Name: "{autodesktop}\Skyrim Co-op Hub"; Filename: "{app}\{#MyLauncherExeName}"; WorkingDir: "{app}"

[Run]
Filename: "{app}\{#MyLauncherExeName}"; Description: "Открыть лаунчер Skyrim Co-op Hub (рекомендуется)"; Flags: postinstall nowait skipifsilent
Filename: "{app}\{#MyAppExeName}"; Description: "Сразу запустить игру Skyrim Together"; Flags: postinstall nowait skipifsilent unchecked

[Code]
function GetDefaultSkyrimPath(Param: String): String;
var
  InstalledPath: String;
begin
  // 1. Try Bethesda registry 64-bit
  if RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Bethesda Softworks\Skyrim Special Edition', 'installed path', InstalledPath) then
  begin
    if DirExists(InstalledPath) then
    begin
      Result := InstalledPath;
      Exit;
    end;
  end;

  // 2. Try Bethesda registry 32-bit
  if RegQueryStringValue(HKLM, 'SOFTWARE\Bethesda Softworks\Skyrim Special Edition', 'installed path', InstalledPath) then
  begin
    if DirExists(InstalledPath) then
    begin
      Result := InstalledPath;
      Exit;
    end;
  end;

  // 3. Known active drive on host
  if FileExists('E:\SteamLibrary\steamapps\common\Skyrim Special Edition\SkyrimSE.exe') then
  begin
    Result := 'E:\SteamLibrary\steamapps\common\Skyrim Special Edition';
    Exit;
  end;

  // 4. Default Steam path
  if FileExists('C:\Program Files (x86)\Steam\steamapps\common\Skyrim Special Edition\SkyrimSE.exe') then
  begin
    Result := 'C:\Program Files (x86)\Steam\steamapps\common\Skyrim Special Edition';
    Exit;
  end;

  // Fallback
  Result := 'C:\Program Files (x86)\Steam\steamapps\common\Skyrim Special Edition';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  SelectedDir: String;
  ExeFile: String;
begin
  Result := True;
  if CurPageID = wpSelectDir then
  begin
    SelectedDir := WizardDirValue();
    ExeFile := AddBackslash(SelectedDir) + 'SkyrimSE.exe';
    
    if not FileExists(ExeFile) then
    begin
      MsgBox('Внимание! В указанной папке не найден файл SkyrimSE.exe:' + #13#10#13#10 +
             SelectedDir + #13#10#13#10 +
             'Пожалуйста, укажите верную корневую папку с установленной игрой Skyrim Special Edition.', mbCriticalError, MB_OK);
      Result := False;
    end;
  end;
end;
