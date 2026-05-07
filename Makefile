.PHONY: help build-desktop build-mac build-win build-win-installer install install-only

help:
	@echo "make build-desktop      — requirements 동기화 후 PyInstaller 데스크톱 번들 (현재 OS 기준)"
	@echo "make install            — build-desktop 후 /Applications/KRStockScreener.app 복사 (macOS)"
	@echo "make install-only       — 이미 빌드된 dist/KRStockScreener.app 만 /Applications 로 복사"
	@echo "make build-mac          — macOS 데스크톱 번들 (= build-desktop)"
	@echo "make build-win          — Windows 빌드 안내 (PyInstaller 크로스컴파일 불가)"
	@echo "make build-win-installer— Windows 인스톨러 빌드 안내 (GitHub Actions 또는 PowerShell)"

build-desktop:
	@chmod +x scripts/build_desktop.sh 2>/dev/null || true
	@python3 -m pip install -q -r requirements.txt
	@./scripts/build_desktop.sh

build-mac: build-desktop

# Windows 빌드는 반드시 Windows 머신에서 수행해야 함 (PyInstaller 크로스컴파일 미지원)
build-win:
	@echo "⚠️  PyInstaller 는 macOS/Linux 에서 Windows .exe 를 만들 수 없습니다."
	@echo ""
	@echo "선택지:"
	@echo "  1) GitHub Actions 자동 빌드 (권장)"
	@echo "     - 태그 푸시:  git tag v0.1.0 && git push origin v0.1.0"
	@echo "     - 수동 실행:  gh workflow run release-windows.yml -f version=0.1.0"
	@echo ""
	@echo "  2) Windows PC 에서 PowerShell 실행"
	@echo "     PS> .\\scripts\\build_windows_installer.ps1 -Version \"0.1.0\""
	@echo ""
	@echo "자세한 내용: installer/windows/README.md"

build-win-installer: build-win

install: build-desktop
	@test -d dist/KRStockScreener.app || (echo "오류: dist/KRStockScreener.app 없음 — macOS에서 빌드하세요." && exit 1)
	cp -r dist/KRStockScreener.app /Applications/
	@echo "✅ 설치 완료: /Applications/KRStockScreener.app"

install-only:
	@test -d dist/KRStockScreener.app || (echo "오류: dist/KRStockScreener.app 없음 — 먼저 make build-desktop 하세요." && exit 1)
	cp -r dist/KRStockScreener.app /Applications/
	@echo "✅ 설치 완료 (빌드 생략): /Applications/KRStockScreener.app"
