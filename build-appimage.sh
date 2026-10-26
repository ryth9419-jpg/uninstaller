#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 -m venv .build-venv
source .build-venv/bin/activate
python -m pip install --upgrade pip
python -m pip install PySide6 pyinstaller
pyinstaller --noconfirm --clean --windowed --onefile --name BazziteRPMUninstaller src/main.py

mkdir -p AppDir/usr/bin AppDir/usr/share/applications AppDir/usr/share/icons/hicolor/256x256/apps
cp -f dist/BazziteRPMUninstaller AppDir/usr/bin/bazzite-rpm-uninstaller
cp bazzite-rpm-uninstaller.png AppDir/usr/share/icons/hicolor/256x256/apps/bazzite-rpm-uninstaller.png
cp bazzite-rpm-uninstaller.png AppDir/.DirIcon

cat > AppDir/bazzite-rpm-uninstaller.desktop <<'EOF'
[Desktop Entry]
Type=Application
Name=Bazzite RPM Uninstaller
Comment=List and uninstall rpm-ostree layered packages
Exec=bazzite-rpm-uninstaller
Icon=bazzite-rpm-uninstaller
Categories=System;Settings;
Terminal=false
EOF
cp AppDir/bazzite-rpm-uninstaller.desktop AppDir/usr/share/applications/

cat > AppDir/AppRun <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/bazzite-rpm-uninstaller" "$@"
EOF
chmod +x AppDir/AppRun

command -v appimagetool >/dev/null || { echo "Install appimagetool and ensure it is on PATH." >&2; exit 2; }
ARCH=x86_64 appimagetool AppDir BazziteRPMUninstaller-x86_64.AppImage
chmod +x BazziteRPMUninstaller-x86_64.AppImage
echo "Built BazziteRPMUninstaller-x86_64.AppImage"
