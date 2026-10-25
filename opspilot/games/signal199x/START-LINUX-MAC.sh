#!/bin/sh
set -eu
cd "$(dirname "$0")"
echo 'Signal 199X starts at http://localhost:3000'
exec node server.mjs
