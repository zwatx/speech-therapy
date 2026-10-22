#!/bin/sh
set -eu
# Build the Foundation-only production catalog directly; no regex parser or scientific data.
repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
build_dir="$repo_root/work/assessment-milestone-20261002/materials"
output_dir=${1:-"$repo_root/docs/consumer-assessment"}
mkdir -p "$build_dir"
swiftc "$repo_root/apps/ios-learner/Sources/DirectPractice/PracticeLibrary.swift" \
  "$repo_root/apps/ios-learner/Sources/DirectPractice/PracticeVocabulary.swift" \
  "$repo_root/docs/consumer-assessment/catalog-audit.swift" \
  -o "$build_dir/catalog-audit"
"$build_dir/catalog-audit" "$repo_root" "$output_dir"
