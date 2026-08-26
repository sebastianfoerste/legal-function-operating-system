#!/bin/sh
set -eu

branch="release/legal-ops-agent"
prefix="supervised-agent"

dirty=$(git status --porcelain | grep -v '^?? .gstack/' || true)
if [ -n "$dirty" ]; then
  echo "working tree must be clean before preparing an export" >&2
  exit 1
fi

git branch -D "$branch" 2>/dev/null || true
git subtree split --prefix="$prefix" -b "$branch"
echo "prepared local branch $branch"
echo "review it before pushing to the supervised-agent release surface"
