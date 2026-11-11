#!/bin/sh
# Run Cargo from the harness checkout and remove build artifacts on exit.
set -u

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd) || exit 1
cd "$repo_root" || exit 1

# Match Cargo's target-directory override, including arguments before `--`.
target_dir=${CARGO_TARGET_DIR:-"$repo_root/target"}
expect_target_dir=false
for arg do
    if "$expect_target_dir"; then
        target_dir=$arg
        expect_target_dir=false
        continue
    fi
    case "$arg" in
        --) break ;;
        --target-dir) expect_target_dir=true ;;
        --target-dir=*) target_dir=${arg#--target-dir=} ;;
    esac
done
export CARGO_TARGET_DIR="$target_dir"

cleanup() {
    result=$?
    trap - 0
    cargo clean --target-dir "$target_dir"
    clean_result=$?
    if [ "$result" -ne 0 ]; then
        exit "$result"
    fi
    exit "$clean_result"
}
trap cleanup 0
trap 'exit 130' INT
trap 'exit 143' TERM

cargo "$@"
