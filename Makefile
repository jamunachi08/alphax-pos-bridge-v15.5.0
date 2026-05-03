# AlphaX POS Bridge — local installer build automation.
#
# Most contributors won't need this — the GitHub Actions workflow at
# .github/workflows/build-installers.yml builds all three OS installers
# automatically on every release tag.
#
# But if you want to build locally for testing, this Makefile is the
# entry point:
#
#   make windows      # build .exe (run on Windows)
#   make mac          # build .pkg (run on macOS)
#   make linux        # build .deb + .AppImage (run on Linux)
#   make pyinstaller  # just the PyInstaller step (any OS)
#   make clean        # nuke dist/ and build/

PYTHON ?= python3
VERSION := 15.5.0

.PHONY: help
help:
	@echo "AlphaX POS Bridge — installer build targets"
	@echo ""
	@echo "  make pyinstaller    Build the PyInstaller bundle (any OS)"
	@echo "  make windows        Build .exe installer (run on Windows)"
	@echo "  make mac            Build .pkg installer  (run on macOS)"
	@echo "  make linux          Build .deb + AppImage (run on Linux)"
	@echo "  make test           Run unit tests"
	@echo "  make clean          Remove dist/ and build/"
	@echo ""

.PHONY: deps
deps:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install pyinstaller pystray Pillow pyyaml pyserial pyusb
	$(PYTHON) -m pip install -e .[tray]

.PHONY: test
test:
	$(PYTHON) -m unittest tests.test_bridge

.PHONY: pyinstaller
pyinstaller: deps
	$(PYTHON) -m PyInstaller packaging/pyinstaller/alphax-bridge.spec --clean --noconfirm
	@echo "✓ PyInstaller bundle in dist/alphax-bridge/"

.PHONY: windows
windows: pyinstaller
	@echo "→ Building Windows installer with Inno Setup"
	@command -v iscc >/dev/null 2>&1 || { echo "❌ iscc not found. Install Inno Setup 6 first."; exit 1; }
	iscc packaging/windows/alphax-bridge.iss
	@echo "✓ Installer in dist/installers/"

.PHONY: mac
mac: pyinstaller
	@echo "→ Building macOS .pkg"
	bash packaging/macos/build-pkg.sh

.PHONY: linux
linux: pyinstaller deb appimage
	@echo "✓ Linux installers built"

.PHONY: deb
deb: pyinstaller
	@echo "→ Building .deb"
	bash packaging/linux/build-deb.sh

.PHONY: appimage
appimage: pyinstaller
	@echo "→ Building AppImage"
	bash packaging/linux/build-appimage.sh

.PHONY: clean
clean:
	rm -rf build/ dist/ *.spec.bak
	find . -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name '*.pyc' -delete 2>/dev/null || true
	@echo "✓ Cleaned build artifacts"
