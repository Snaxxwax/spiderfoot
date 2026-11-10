#!/bin/sh
# Install Maigret and GHunt for sfp_tool_maigret / sfp_tool_ghunt. Run as root at build time.
#
# Each tool gets its own uv-managed venv on Python 3.12, never /opt/venv: their pinned
# dependency trees (numpy/scipy for ghunt, an old socid-extractor for maigret) must not
# resolve against SpiderFoot's own, and the constraint pins were resolved for 3.12.
set -eu
here=$(dirname "$0")
export UV_TOOL_DIR=/opt/sf-tools UV_TOOL_BIN_DIR=/usr/local/bin UV_PYTHON_INSTALL_DIR=/opt/sf-tools/python
python -m pip install --no-cache-dir --target /tmp/uv uv==0.12.11
uv=/tmp/uv/bin/uv
$uv tool install --no-cache --python 3.12 --constraints "$here/maigret-constraints.txt" maigret==0.6.6
$uv tool install --no-cache --python 3.12 --constraints "$here/ghunt-constraints.txt" ghunt==2.3.4

# ghunt 2.3.4 crashes on every `ghunt email --json`; both fixes are on upstream master but
# unreleased. Grep-guarded so a changed upstream fails the build instead of the scan.
# (1) parsers/people.py KeyError 'container' on any account with a cover photo.
P=$(find /opt/sf-tools -path "*/ghunt/parsers/people.py" | head -1)
grep -q 'self.coverPhotos\[cover_photo_data\["metadata"\]\["container"\]\]' "$P" \
    || { echo "ghunt coverPhoto patch no longer applies"; exit 1; }
sed -i 's#self\.coverPhotos\[cover_photo_data\["metadata"\]\["container"\]\]#self.coverPhotos[(cover_photo_data.get("metadata") or {}).get("container") or (cover_photo_data.get("metadata") or {}).get("containerType") or "unknown"]#' "$P"
# (2) modules/email.py NameError: `photos`/`reviews` are never assigned.
E=$(find /opt/sf-tools -path "*/ghunt/modules/email.py" | head -1)
grep -q '"photos": photos,' "$E" || { echo "ghunt maps-json patch no longer applies"; exit 1; }
sed -i 's#"photos": photos,#"photos": None,#; s#"reviews": reviews,#"reviews": None,#' "$E"
if grep -q '"photos": photos,\|"reviews": reviews,' "$E"; then echo "ghunt maps-json patch did not apply"; exit 1; fi

rm -rf /tmp/uv
chmod -R a+rX /opt/sf-tools
maigret --version >/dev/null
test -x /usr/local/bin/ghunt
