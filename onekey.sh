#!/bin/bash

BASE_URL="https://raw.githubusercontent.com/transflo/speedtaier/main"
tmp_dir="$(mktemp -d)"
cleanup() {
    local d
    for d in "$tmp_dir"/.speedtaier_sandbox*; do
        [[ -e "$d" ]] || continue
        umount -R "$d/BenchOs/dev/" 2>/dev/null
        umount "$d/BenchOs/proc/" 2>/dev/null
        umount "$d/BenchOs/sys/" 2>/dev/null
    done
    rm -rf "$tmp_dir" 2>/dev/null
}
trap cleanup EXIT

echo "[*] 下载 SpeedTaier 组件..."
if command -v curl >/dev/null 2>&1; then
    curl -sL -o "$tmp_dir/run_sandbox.sh"      "$BASE_URL/run_sandbox.sh"
    curl -sL -o "$tmp_dir/globalspeed_test.py" "$BASE_URL/globalspeed_test.py"
else
    wget -qO "$tmp_dir/run_sandbox.sh"      "$BASE_URL/run_sandbox.sh"
    wget -qO "$tmp_dir/globalspeed_test.py" "$BASE_URL/globalspeed_test.py"
fi

if [[ ! -s "$tmp_dir/run_sandbox.sh" || ! -s "$tmp_dir/globalspeed_test.py" ]]; then
    echo "[!] 组件下载失败，请检查网络后重试"
    exit 1
fi
chmod +x "$tmp_dir/run_sandbox.sh"

cd "$tmp_dir" || exit 1
bash run_sandbox.sh --local "$@"
exit $?
