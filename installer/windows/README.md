# Windows 인스톨러 빌드 가이드

KR Stock Screener의 Windows `.exe` 인스톨러를 만드는 방법입니다.

## 두 가지 빌드 경로

### A. GitHub Actions (권장 — 자동화)
저장소에 태그를 푸시하면 자동으로 인스톨러가 만들어지고 Release에 업로드됩니다.

```bash
git tag v0.1.0
git push origin v0.1.0
```

워크플로 정의: [`.github/workflows/release-windows.yml`](../../.github/workflows/release-windows.yml)
또는 GitHub Actions 페이지에서 수동 실행(`workflow_dispatch`)도 가능합니다.

### B. 로컬 Windows PC에서 빌드
저장소 루트에서 PowerShell:
```powershell
.\scripts\build_windows_installer.ps1 -Version "0.1.0"
```
산출물: `dist\KRStockScreener-Setup-0.1.0.exe`

## 사전 준비물 (로컬 빌드 시)

| 도구 | 다운로드 | 비고 |
|---|---|---|
| Python 3.12 | https://www.python.org/downloads/windows/ | "Add Python to PATH" 체크 |
| Node.js 20 LTS | https://nodejs.org | `npm` 함께 설치됨 |
| Inno Setup 6 | https://jrsoftware.org/isinfo.php | 기본 경로 권장 |
| Git | https://git-scm.com | 저장소 클론용 |

## 산출물 구조

```
dist/
├── KRStockScreener/                  ← PyInstaller 산출 폴더
│   ├── KRStockScreener.exe
│   └── (런타임 DLL·데이터)
└── KRStockScreener-Setup-0.1.0.exe   ← Inno Setup 인스톨러 (사용자 배포용)
```

## 사용자 설치 흐름

1. `KRStockScreener-Setup-X.Y.Z.exe` 다운로드
2. 더블클릭 → 설치 마법사 진행 ("다음 → 다음 → 설치")
3. 시작 메뉴 또는 바탕화면 아이콘으로 실행

## WebView2 런타임 안내

Windows 11과 최신 Windows 10은 Microsoft Edge WebView2 런타임이 사전 설치되어 있어
별도 설치가 필요 없습니다. 구형 Windows 10에서 창이 뜨지 않으면
[Microsoft 공식 페이지](https://developer.microsoft.com/microsoft-edge/webview2/)
에서 "Evergreen Bootstrapper"를 받아 설치하세요.

## 아이콘 교체

기본 아이콘은 `assets/icon.ico` (멀티해상도 16/32/48/64/128/256)입니다.
원하는 디자인으로 바꾸려면 같은 경로에 ICO 파일로 덮어쓴 뒤 다시 빌드하면 됩니다.

## 자주 묻는 질문

**Q. macOS·Linux에서 Windows 인스톨러를 만들 수 있나요?**
A. PyInstaller는 크로스 컴파일이 불가합니다. 반드시 Windows 환경에서 빌드해야 하며,
가장 쉬운 방법은 **GitHub Actions** 사용입니다.

**Q. 코드 사인 인증서가 필요한가요?**
A. 필수는 아닙니다. 다만 인증서가 없으면 사용자 PC의 SmartScreen이
"확인되지 않은 게시자" 경고를 띄울 수 있습니다. 사용자는 "추가 정보 → 실행" 으로
우회 가능합니다.
