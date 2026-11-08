#!/bin/bash
# Install from the Pi's canetebros login, without sudo.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
exec python3 ./smartmirror-kiosk.py install
