#!/bin/bash
# Compatibility wrapper — use create-demodb.sh
exec "$(cd "$(dirname "$0")" && pwd)/create-demodb.sh" "$@"
