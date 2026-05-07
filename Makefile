.PHONY: help build-desktop build-mac build-win

help:
	@echo "make build-desktop — PyInstaller 데스크톱 번들 (.venv 있으면 requirements.txt 선행 설치, BUG-5)"
	@echo "make build-mac / build-win — build-desktop 과 동일 (플랫폼 가정만 문서용)"

build-desktop:
	@chmod +x scripts/build_desktop.sh 2>/dev/null || true
	@if [ -x .venv/bin/pip ]; then .venv/bin/pip install -q -r requirements.txt; fi
	@./scripts/build_desktop.sh

build-mac: build-desktop

build-win: build-desktop
