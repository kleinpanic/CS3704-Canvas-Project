#!/usr/bin/env bash
hits=$(grep -rn "XXX\|FIXME\|HACK" --include="*.py" src/ scripts/ tools/ 2>/dev/null | grep -v "build/")
if [ -n "$hits" ]; then
    printf "WARN: code smell markers:\n%s\n" "$hits"
fi
exit 0
