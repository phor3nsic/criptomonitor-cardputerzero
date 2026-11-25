#!/bin/sh
# Monta o .deb a partir do código-fonte. Requer dpkg-deb e python3.
# Uso: packaging/build_deb.sh [diretório-de-saída]
set -eu
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=${1:-$ROOT/dist}
VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$ROOT/criptomonitor/__init__.py")
STAGE=$(mktemp -d)
chmod 755 "$STAGE"
trap 'rm -rf "$STAGE"' EXIT

install -d "$STAGE/DEBIAN" "$STAGE/usr/lib/criptomonitor/criptomonitor" \
  "$STAGE/usr/share/APPLaunch/bin" "$STAGE/usr/share/APPLaunch/applications" \
  "$STAGE/usr/share/APPLaunch/share/images" "$STAGE/usr/share/doc/criptomonitor"
install -m 644 "$ROOT"/criptomonitor/*.py "$STAGE/usr/lib/criptomonitor/criptomonitor/"
install -m 755 "$ROOT/packaging/CriptoMonitor" "$STAGE/usr/share/APPLaunch/bin/CriptoMonitor"
install -m 644 "$ROOT/packaging/criptomonitor.desktop" "$STAGE/usr/share/APPLaunch/applications/"
install -m 644 "$ROOT/packaging/criptomonitor.png" "$STAGE/usr/share/APPLaunch/share/images/"
install -m 644 "$ROOT/LICENSE" "$ROOT/THIRD_PARTY_NOTICES.md" "$STAGE/usr/share/doc/criptomonitor/"
sed "s/@VERSION@/$VERSION/" "$ROOT/packaging/control.in" > "$STAGE/DEBIAN/control"

# Smoke test do código montado antes de empacotar.
PYTHONPATH="$STAGE/usr/lib/criptomonitor" python3 -s -m criptomonitor --version >/dev/null

mkdir -p "$OUT"
DEB="$OUT/criptomonitor_${VERSION}_all.deb"
dpkg-deb --root-owner-group -Zxz --build "$STAGE" "$DEB" >/dev/null
echo "$DEB"
