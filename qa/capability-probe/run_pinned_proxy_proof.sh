#!/bin/sh
# Public runtime artifacts must already exist; never downloads or installs.
set -eu
proof_runtime=${1:?Pass directory containing copied opencode.exe and proxy-runtime}
proof_python=${2:?Pass existing Python executable with project dependencies}
proof_repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$proof_repo"
exec unshare --user --map-root-user --net sh -c '
  set -eu
  ip link set lo up
  ip -brief address
  ip route
  exec env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
    PYTHONPATH="$1/proxy-runtime" OMNI_PINNED_PROXY_PROOF=1 \
    PROOF_BINARY="$1/opencode.exe" PROOF_PROXY_RUNTIME="$1/proxy-runtime" \
    "$2" -m pytest -q tests/backend/test_pinned_chat_proxy.py
' proof "$proof_runtime" "$proof_python"
