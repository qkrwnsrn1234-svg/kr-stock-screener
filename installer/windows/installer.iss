; ============================================================
; KR Stock Screener — Windows Installer (Inno Setup 6)
; ------------------------------------------------------------
; 사전 조건:
;   1) PyInstaller 빌드 완료 → dist\KRStockScreener\KRStockScreener.exe
;   2) Inno Setup 6 설치 (https://jrsoftware.org/isinfo.php)
;   3) 본 스크립트는 저장소 루트 기준으로 작성됨
;
; 컴파일:
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\windows\installer.iss
;   또는 GUI: 본 파일 더블클릭 → Compile (F9)
;
; 산출물: dist\KRStockScreener-Setup-{#MyAppVersion}.exe
;
; 버전은 환경변수 KR_APP_VERSION 으로 주입 가능 (CI 권장):
;   set KR_APP_VERSION=0.1.0 && ISCC installer.iss
; ============================================================

#ifndef MyAppVersion
  #define MyAppVersion GetEnv("KR_APP_VERSION")
#endif
#if MyAppVersion == ""
  #define MyAppVersion "0.0.0-dev"
#endif

#define MyAppName        "KR Stock Screener"
#define MyAppShortName   "KRStockScreener"
#define MyAppPublisher   "KR Stock Screener"
#define MyAppURL         "https://github.com/"
#define MyAppExeName     "KRStockScreener.exe"
; Inno Setup 스크립트 위치(installer\windows) 기준 → 저장소 루트는 ..\..
#define RepoRoot         "..\\.."
#define BuildDir         RepoRoot + "\\dist\\KRStockScreener"
#define IconFile         RepoRoot + "\\assets\\icon.ico"
#define OutputDir        RepoRoot + "\\dist"

[Setup]
; AppId 는 한 번 정하면 절대 바꾸지 말 것 — 업그레이드 식별자
AppId={{A2D5FB0E-5B43-4B6E-9F8B-4F2B0E8C7E11}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppShortName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir={#OutputDir}
OutputBaseFilename={#MyAppShortName}-Setup-{#MyAppVersion}
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; 일반 사용자 권한으로도 설치 가능하도록 — Program Files 가 아닌 경우는 자동 다운그레이드
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
  GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; PyInstaller 산출 폴더 전체를 그대로 동봉
Source: "{#BuildDir}\\*"; DestDir: "{app}"; \
  Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; 시작 메뉴
Name: "{autoprograms}\\{#MyAppName}"; Filename: "{app}\\{#MyAppExeName}"; \
  IconFilename: "{app}\\{#MyAppExeName}"
Name: "{autoprograms}\\{#MyAppName} 제거"; Filename: "{uninstallexe}"
; 바탕화면 (옵션)
Name: "{autodesktop}\\{#MyAppName}"; Filename: "{app}\\{#MyAppExeName}"; \
  Tasks: desktopicon; IconFilename: "{app}\\{#MyAppExeName}"

[Run]
; 설치 마지막 페이지 "지금 실행" 체크박스
Filename: "{app}\\{#MyAppExeName}"; \
  Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; \
  Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 사용자 데이터(%LOCALAPPDATA%\KRStockScreener)는 보존 — 일부러 삭제하지 않음
; 필요 시 사용자가 직접 정리
