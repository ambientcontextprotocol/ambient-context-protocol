#!/bin/sh
# Tells Chrome where the helper is and which extension may start it, by
# writing one file into Chrome's NativeMessagingHosts folder. Run it once
# after building the helper; run it with --remove to take the file away.
#
#   providers/chrome/register.sh [--remove] [extension id]
#
# For another Chromium browser, set HOSTS to its NativeMessagingHosts
# folder. The extension id defaults to the one the manifest's key gives.
set -eu

NAME="io.github.ambientcontextprotocol.chrome"
HOSTS="${HOSTS:-$HOME/Library/Application Support/Google/Chrome/NativeMessagingHosts}"
HERE="$(cd "$(dirname "$0")" && pwd)"
HELPER="$HERE/helper/.build/release/ambient-context-chrome"
FILE="$HOSTS/$NAME.json"

if [ "${1:-}" = "--remove" ]; then
    rm -f "$FILE"
    echo "removed $FILE"
    exit 0
fi

ID="${1:-ablpecmggklfelddalonopnjdkcfhdpe}"
if [ ! -x "$HELPER" ]; then
    echo "no helper at $HELPER; build it first: swift build -c release --package-path $HERE/helper" >&2
    exit 1
fi

mkdir -p "$HOSTS"
cat > "$FILE" <<JSON
{
  "name": "$NAME",
  "description": "Ambient Context for Chrome",
  "path": "$HELPER",
  "type": "stdio",
  "allowed_origins": ["chrome-extension://$ID/"]
}
JSON
echo "wrote $FILE"
