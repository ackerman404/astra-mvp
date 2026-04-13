; Inno Setup Script for Astra Interview Copilot
; Packages PyInstaller --onedir output into a single installer .exe
; Build with: iscc installer\astra_setup.iss

[Setup]
AppName=Astra Interview Copilot
AppVersion=3.0
AppPublisher=Astra
AppSupportURL=https://astra.ai
DefaultDirName={localappdata}\Astra
DefaultGroupName=Astra
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=AstraSetup
Compression=lzma2/ultra64
SolidCompression=yes
SetupIconFile=..\assets\astra.ico
UninstallDisplayIcon={app}\Astra.exe
WizardStyle=modern
DisableProgramGroupPage=auto
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
; Copy the entire PyInstaller --onedir output into the install directory
Source: "..\dist\Astra\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Bundle user guide and icon in the install directory
Source: "..\USER_GUIDE.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\assets\astra.ico"; DestDir: "{app}"; Flags: ignoreversion

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Icons]
; Desktop shortcut (optional, user chooses during install)
Name: "{userdesktop}\Astra Interview Copilot"; Filename: "{app}\Astra.exe"; IconFilename: "{app}\astra.ico"; Tasks: desktopicon
; Start Menu entries
Name: "{group}\Astra Interview Copilot"; Filename: "{app}\Astra.exe"; IconFilename: "{app}\astra.ico"
Name: "{group}\User Guide"; Filename: "{app}\USER_GUIDE.txt"
Name: "{group}\Uninstall Astra"; Filename: "{uninstallexe}"

[UninstallDelete]
; Only clean up the install directory — user data is preserved.
; User data lives in {localappdata}\astra\ (ChromaDB, config, prompts)
; managed by platformdirs. We do NOT touch that directory.
; Inno Setup automatically removes {app} contents and the uninstaller.

[Code]
// Check if Astra is running before install or uninstall.
function IsAppRunning(): Boolean;
var
  ResultCode: Integer;
begin
  Result := False;
  if Exec('cmd.exe', '/c tasklist /FI "IMAGENAME eq Astra.exe" /NH | find /i "Astra.exe" >nul 2>&1',
           '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    Result := (ResultCode = 0);
  end;
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
  if IsAppRunning() then
  begin
    MsgBox('Astra Interview Copilot is currently running.' + #13#10 +
           'Please close Astra before continuing the installation.',
           mbError, MB_OK);
    Result := False;
  end;
end;

function InitializeUninstall(): Boolean;
begin
  Result := True;
  if IsAppRunning() then
  begin
    MsgBox('Astra Interview Copilot is currently running.' + #13#10 +
           'Please close Astra before continuing the uninstallation.',
           mbError, MB_OK);
    Result := False;
  end;
end;
