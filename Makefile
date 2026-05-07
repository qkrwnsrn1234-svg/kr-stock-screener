.PHONY: help build-desktop build-mac build-win install

help:
	@echo "make build-desktop — requirements 동기화 후 PyInstaller 데스크톱 번들 (BUG-5)"
	@echo "make install — build-desktop 후 /Applications/KRStockScreener.app 복사 (macOS)"
	@echo "make build-mac / build-win — build-desktop 과 동일 (플랫폼 가정만 문서용)"

build-desktop:
	@chmod +x scripts/build_desktop.sh 2>/dev/null || true
	@python3 -m pip install -q -r requirements.txt
	@./scripts/build_desktop.sh

build-mac: build-desktop

build-win: build-desktop

install: build-desktop
	@test -d dist/KRStockScreener.app || (echo "오류: dist/KRStockScreener.app 없음 — macOS에서 빌드하세요." && exit 1)
	cp -r dist/KRStockScreener.app /Applications/
	@echo "✅ 설치 완료: /Applications/KRStockScreener.app"
