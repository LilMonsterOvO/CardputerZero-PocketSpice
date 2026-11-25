#!/usr/bin/env bash
set -euo pipefail

# Build CardputerZero arm64 .deb package for PocketSpice (cp0-ngspice).
# Run on a Debian/Ubuntu host or directly on CardputerZero.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="0.2.0"
REV="1"
ARCH="arm64"
PKG_NAME="cp0-ngspice"
STAGE="${ROOT_DIR}/dist/${PKG_NAME}_${VERSION}-${REV}_${ARCH}"

rm -rf "${STAGE}"
mkdir -p \
  "${STAGE}/DEBIAN" \
  "${STAGE}/usr/bin" \
  "${STAGE}/usr/share/${PKG_NAME}" \
  "${STAGE}/usr/share/APPLaunch/applications" \
  "${STAGE}/usr/share/APPLaunch/share/images" \
  "${STAGE}/usr/share/doc/${PKG_NAME}"

cp -r "${ROOT_DIR}/cp0_ngspice" "${STAGE}/usr/share/${PKG_NAME}/"
cp -r "${ROOT_DIR}/circuits" "${STAGE}/usr/share/${PKG_NAME}/"
cp -r "${ROOT_DIR}/lib" "${STAGE}/usr/share/${PKG_NAME}/"
cp -r "${ROOT_DIR}/docs" "${STAGE}/usr/share/${PKG_NAME}/"
cp -r "${ROOT_DIR}/assets" "${STAGE}/usr/share/${PKG_NAME}/"
find "${STAGE}/usr/share/${PKG_NAME}" -name "__pycache__" -prune -exec rm -rf {} +

cp "${ROOT_DIR}/assets/icon_100.png" "${STAGE}/usr/share/APPLaunch/share/images/${PKG_NAME}_100.png"

cp "${ROOT_DIR}/docs/"*.md "${STAGE}/usr/share/doc/${PKG_NAME}/"
cp "${ROOT_DIR}/docs/recipes.json" "${STAGE}/usr/share/doc/${PKG_NAME}/"

cat > "${STAGE}/usr/bin/${PKG_NAME}" << 'EOF'
#!/usr/bin/env bash
export PYTHONPATH="/usr/share/cp0-ngspice:${PYTHONPATH:-}"
if [ $# -gt 0 ]; then
  exec python3 -m cp0_ngspice.cli "$@"
fi
exec python3 -m cp0_ngspice.ui.app
EOF
chmod 0755 "${STAGE}/usr/bin/${PKG_NAME}"

cat > "${STAGE}/usr/share/APPLaunch/applications/${PKG_NAME}.desktop" << 'EOF'
[Desktop Entry]
Type=Application
Name=PocketSpice
Comment=NGSPICE Simulator for CardputerZero
Exec=/usr/bin/cp0-ngspice
Icon=share/images/cp0-ngspice_100.png
Categories=Development;Education;
Terminal=false
EOF

cat > "${STAGE}/DEBIAN/control" << EOF
Package: ${PKG_NAME}
Version: ${VERSION}-${REV}
Section: electronics
Priority: optional
Architecture: ${ARCH}
Depends: python3 (>= 3.10), libngspice0, python3-pygame, python3-numpy, python3-psutil
Maintainer: PocketSpice Project
Description: Pocket NGSPICE simulator with 320x170 scope, raw netlist editor, and local AI CLI
EOF

find "${STAGE}" -type d -exec chmod 0755 {} +
find "${STAGE}/usr/share" -type f -exec chmod 0644 {} +
chmod 0755 "${STAGE}/usr/bin/${PKG_NAME}"

mkdir -p "${ROOT_DIR}/dist"
dpkg-deb --root-owner-group --build "${STAGE}" "${ROOT_DIR}/dist/${PKG_NAME}_${VERSION}-${REV}_${ARCH}.deb"
echo "Built: ${ROOT_DIR}/dist/${PKG_NAME}_${VERSION}-${REV}_${ARCH}.deb"
