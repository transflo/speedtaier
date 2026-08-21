#!/bin/bash

current_time="$(date +%Y_%m_%d_%H_%M_%S)"
work_dir=".speedtaier_sandbox$current_time"
bench_os_url="https://github.com/LloydAsp/NodeQuality/releases/download/v0.0.2/BenchOs.tar.gz"
if uname -m | grep -Eq 'arm|aarch64'; then
    bench_os_url="https://github.com/LloydAsp/NodeQuality/releases/download/v0.0.2/BenchOs-arm.tar.gz"
fi
script_url="https://raw.githubusercontent.com/transflo/speedtaier/main/globalspeed_test.py"

CACHE_DIR="${SPEEDTAIER_CACHE:-${HOME}/.cache/speedtaier}"
CACHE_FILE="$CACHE_DIR/$(basename "$bench_os_url")"

USE_LOCAL=0
SCRIPT_ARGS=()
for arg in "$@"; do
    case "$arg" in
        --local) USE_LOCAL=1 ;;
        *) SCRIPT_ARGS+=("$arg") ;;
    esac
done

if [ -t 1 ] && [ -z "$NO_COLOR" ]; then
    _red()    { echo -e "\033[0;31m$1\033[0m"; }
    _green()  { echo -e "\033[0;32m$1\033[0m"; }
    _yellow() { echo -e "\033[0;33m$1\033[0m"; }
else
    _red()    { echo "$1"; }
    _green()  { echo "$1"; }
    _yellow() { echo "$1"; }
fi

GITHUB_PROXIES=(
    "https://cdn.gh-proxy.org"
    "https://axisnow.gh-proxy.org"
    "https://gh-proxy.org"
    "https://v4.gh-proxy.org"
    "https://v6.gh-proxy.org"
)

get_country_code() {
    local cc
    cc=$(curl -sL -m 8 "https://www.cloudflare.com/cdn-cgi/trace" 2>/dev/null \
         | awk -F= '$1=="loc"{print $2; exit}')
    if [[ -z "$cc" ]]; then
        cc=$(curl -sL -m 8 "https://ip-api.com/json/?fields=status,countryCode" 2>/dev/null \
             | sed -n 's/.*"countryCode":"\([^"]*\)".*/\1/p')
    fi
    echo "$cc"
}

pick_fastest_proxy() {
    local url="$1"
    local best=""
    local best_speed=0
    local bytes speed dt t0 t1
    _green "[0/3] 测速选择最快的 GitHub 反代..." >&2
    for proxy in "${GITHUB_PROXIES[@]}"; do
        t0="$(date +%s.%N)"
        bytes="$(curl -sL -m 8 -r 0-1048575 -o /dev/null -w '%{size_download}' "$proxy/$url" 2>/dev/null || echo 0)"
        t1="$(date +%s.%N)"
        dt="$(awk -v a="$t0" -v b="$t1" 'BEGIN{printf "%.4f", b-a}')"
        speed="$(awk -v b="$bytes" -v d="$dt" 'BEGIN{ if (d>0) printf "%.0f", b/d; else print 0 }')"
        if [[ "$bytes" -gt 0 ]] && awk -v s="$speed" -v bs="$best_speed" 'BEGIN{ exit !(s>bs) }'; then
            best="$proxy"
            best_speed="$speed"
        fi
        _yellow "  代理 $proxy -> ${bytes}B / ${speed}B/s" >&2
    done
    if [[ -n "$best" ]]; then
        _green "  选用: $best (${best_speed}B/s)" >&2
    else
        _yellow "  所有反代均不可用，回退直连 github.com" >&2
    fi
    echo "$best"
}

download_with_retry() {
    local url="$1" out="$2"
    local tries=0
    while [[ $tries -lt 5 ]]; do
        tries=$((tries + 1))
        curl -sL -C - --retry 3 --retry-delay 1 -o "$out" "$url" 2>/dev/null || true
        if gzip -t "$out" 2>/dev/null; then
            return 0
        fi
        _yellow "  下载不完整($(stat -c%s "$out" 2>/dev/null || echo 0)B)，重试 $tries/5 ..." >&2
    done
    return 1
}

clear_mount() {
    umount -R "$work_dir/BenchOs/dev/" 2>/dev/null
    umount "$work_dir/BenchOs/proc/" 2>/dev/null
    umount "$work_dir/BenchOs/sys/" 2>/dev/null
}

pre_cleanup() {
    local d
    for d in .speedtaier_sandbox*; do
        [[ -e "$d" ]] || continue
        _yellow "清理残留沙箱目录: $d"
        umount -R "$d/BenchOs/dev/" 2>/dev/null
        umount "$d/BenchOs/proc/" 2>/dev/null
        umount "$d/BenchOs/sys/" 2>/dev/null
        if mount | grep -q "$d"; then
            _red "警告: $d 仍有挂载未清理，请重启后手动删除"
        else
            rm -rf "$d"
        fi
    done
}

load_bench_os() {
    local start_dir="$1"
    mkdir -p "$work_dir"
    cd "$work_dir" || exit 1
    work_dir="$(pwd)"
    _green "[1/3] 加载 BenchOS rootfs"
    mkdir -p "$CACHE_DIR"
    local_os="$start_dir/$(basename "$bench_os_url")"
    if [[ $USE_LOCAL -eq 1 ]] && [[ -f "$local_os" ]] && gzip -t "$local_os" 2>/dev/null; then
        _green "  使用本地安装包（--local 本地优先）: $local_os"
        cp "$local_os" BenchOs.tar.gz
    elif [[ -f "$CACHE_FILE" ]] && gzip -t "$CACHE_FILE" 2>/dev/null; then
        _green "  使用缓存安装包: $CACHE_FILE"
        cp "$CACHE_FILE" BenchOs.tar.gz
    else
        _green "  下载 BenchOS rootfs ($bench_os_url)"
        if command -v curl >/dev/null 2>&1; then
            if ! download_with_retry "$bench_os_url" "BenchOs.tar.gz"; then
                _red "错误: BenchOS rootfs 下载失败（5 次重试后仍不完整）"
                cd "$start_dir" || true
                post_cleanup
                exit 1
            fi
        else
            wget -qO BenchOs.tar.gz "$bench_os_url"
        fi
        if gzip -t BenchOs.tar.gz 2>/dev/null; then
            cp BenchOs.tar.gz "$CACHE_FILE"
            _green "  安装包已缓存: $CACHE_FILE"
        fi
    fi
    tar --no-same-owner -xzf BenchOs.tar.gz
    if [[ ! -d "$work_dir/BenchOs" ]]; then
        _red "错误: BenchOS rootfs 解压失败"
        cd "$start_dir" || true
        post_cleanup
        exit 1
    fi
    cd "$work_dir/BenchOs" || exit 1

    _green "[2/3] 挂载 proc/sys/dev 并写入沙箱标记"
    mount -t proc /proc proc/
    mount --bind /sys sys/
    mount --rbind /dev dev/
    mount --make-rslave dev
    rm -f etc/resolv.conf
    cp /etc/resolv.conf etc/resolv.conf
    touch etc/speedtaier-sandbox
    mkdir -p opt

    cat > opt/install_deps.sh <<'INNER'
_LOC=$(curl -sL -m 5 "https://www.cloudflare.com/cdn-cgi/trace" 2>/dev/null | awk -F= '$1=="loc"{print $2; exit}')
if [ "$_LOC" = "CN" ]; then
    echo "检测到中国大陆环境，切换 apt 源到清华镜像..."
    sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g; s|security.debian.org|mirrors.tuna.tsinghua.edu.cn|g' \
        /etc/apt/sources.list /etc/apt/sources.list.d/*.sources 2>/dev/null || true
fi

deps=""
for c in python3 curl ca-certificates; do
    dpkg -s "$c" >/dev/null 2>&1 || deps="$deps $c"
done
command -v mtr >/dev/null 2>&1 || command -v mtr-tiny >/dev/null 2>&1 || deps="$deps mtr-tiny"
if [ -n "$deps" ]; then
    echo "沙箱内安装依赖:$deps ..."
    timeout 300 apt-get update -y -qq && timeout 300 apt-get install -y -qq --no-install-recommends $deps || exit 1
else
    echo "沙箱内依赖已就绪: python3/curl/ca-certificates/mtr"
fi
if ! command -v mtr >/dev/null 2>&1 && ! command -v mtr-tiny >/dev/null 2>&1; then
    echo "警告: 沙箱内未安装 mtr/mtr-tiny，大小包延迟/丢包将显示 -"
fi
INNER
    chmod +x opt/install_deps.sh

    if [[ $USE_LOCAL -eq 1 ]]; then
        if [[ ! -f "$start_dir/globalspeed_test.py" ]]; then
            _red "错误: --local 模式下找不到 $start_dir/globalspeed_test.py"
            exit 1
        fi
        cp "$start_dir/globalspeed_test.py" opt/globalspeed_test.py
        _yellow "使用本地脚本: $start_dir/globalspeed_test.py"
    else
        curl -sL --retry 3 -o opt/globalspeed_test.py "$script_url"
        if [[ ! -s opt/globalspeed_test.py ]] || ! head -1 opt/globalspeed_test.py | grep -q "^#!/usr/bin/env python3"; then
            _red "错误: globalspeed_test.py 下载失败"
            cd "$start_dir" || true
            post_cleanup
            exit 1
        fi
    fi
    chmod +x opt/globalspeed_test.py

    if [[ -n "$LOCAL_SERVERLIST" ]]; then
        cp "$LOCAL_SERVERLIST" opt/serverlist.json
        chmod 644 opt/serverlist.json
    fi

    _green "[2/3] 检查并安装沙箱内依赖"
    if ! chroot_run "bash /opt/install_deps.sh"; then
        _red "错误: 沙箱内依赖安装失败"
        cd "$start_dir" || true
        post_cleanup
        exit 1
    fi
    cd "$start_dir" || exit 1
}

chroot_run() {
    chroot "$work_dir/BenchOs" /bin/bash -c "$*"
}

post_cleanup() {
    _green "[3/3] 卸载挂载并清除沙箱"
    cd / 2>/dev/null || true
    clear_mount
    umount -l -R "$work_dir/BenchOs/dev/" 2>/dev/null
    umount -l "$work_dir/BenchOs/proc/" 2>/dev/null
    umount -l "$work_dir/BenchOs/sys/" 2>/dev/null
    if mount | grep -q "$work_dir"; then
        _yellow "  存在挂载残留，尝试强制删除..." >&2
    fi
    if rm -rf "$work_dir" 2>/dev/null && [[ ! -e "$work_dir" ]]; then
        _green "沙箱已清除，无痕完成"
        return 0
    fi
    _red "警告: $work_dir 清理失败，请手动检查后删除"
    return 1
}

sig_cleanup() {
    trap '' INT TERM HUP EXIT
    echo
    _yellow "收到中断信号，正在清理沙箱..."
    post_cleanup
    exit 1
}

main() {
    start_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

    CORE_MODE=0
    for a in "${SCRIPT_ARGS[@]}"; do
        [[ "$a" == "--core" ]] && CORE_MODE=1
    done
    if [[ $CORE_MODE -eq 1 ]]; then
        _green "Core 模式：跳过沙箱与反代判断，直接本机执行"
        if [[ ! -f "$start_dir/globalspeed_test.py" ]]; then
            _red "错误: 当前目录缺少 globalspeed_test.py（Core 模式需本地脚本）"
            exit 1
        fi
        local core_args=("${SCRIPT_ARGS[@]}")
        [[ $USE_LOCAL -eq 1 ]] && core_args+=(--local)
        exec python3 "$start_dir/globalspeed_test.py" "${core_args[@]}"
    fi

    if [[ $EUID -ne 0 ]]; then
        _yellow "需要 root 权限（mount/chroot），自动使用 sudo 重新执行..."
        local reexec_args=("${SCRIPT_ARGS[@]}")
        [[ $USE_LOCAL -eq 1 ]] && reexec_args+=(--local)
        exec sudo bash "$0" "${reexec_args[@]}"
    fi
    trap 'sig_cleanup' INT TERM HUP EXIT

    pre_cleanup

    cc="$(get_country_code)"
    fast_proxy=""
    if [[ -z "$cc" || "$cc" == "CN" ]]; then
        if [[ -z "$cc" ]]; then
            _yellow "IP 属地查询失败，按中国大陆处理" >&2
        else
            _green "IP 属地：中国大陆" >&2
        fi
        fast_proxy="$(pick_fastest_proxy "$bench_os_url")"
    else
        _yellow "IP 属地：$cc（中国大陆以外），跳过反代，直连 github.com" >&2
    fi
    if [[ -n "$fast_proxy" ]]; then
        bench_os_url="$fast_proxy/$bench_os_url"
        script_url="$fast_proxy/$script_url"
        export SPEEDTAIER_PROXY="$fast_proxy"
    fi

    LOCAL_SERVERLIST=""
    for i in "${!SCRIPT_ARGS[@]}"; do
        if [[ "${SCRIPT_ARGS[$i]}" == "--serverlist-url" ]] && [[ $((i + 1)) -lt ${#SCRIPT_ARGS[@]} ]]; then
            v="${SCRIPT_ARGS[$((i + 1))]}"
            [[ "$v" == file://* ]] && v="${v#file://}"
            if [[ -f "$v" ]]; then
                LOCAL_SERVERLIST="$(readlink -f "$v" 2>/dev/null || echo "$v")"
                SCRIPT_ARGS[$((i + 1))]="/opt/serverlist.json"
                _yellow "本地节点表: $LOCAL_SERVERLIST -> 沙箱 /opt/serverlist.json（不走反代）" >&2
            fi
        fi
    done
    if [[ $USE_LOCAL -eq 1 ]] && [[ -z "$LOCAL_SERVERLIST" ]]; then
        for f in "$start_dir/serverlist_decrypted.json" "$start_dir/serverlist.json" "$start_dir/nodes.json"; do
            if [[ -f "$f" ]]; then
                LOCAL_SERVERLIST="$(readlink -f "$f" 2>/dev/null || echo "$f")"
                SCRIPT_ARGS+=("--serverlist-url" "/opt/serverlist.json")
                _yellow "自动采用本地节点表（--local 本地优先）: $LOCAL_SERVERLIST" >&2
                break
            fi
        done
    fi

    load_bench_os "$start_dir"

    local cmd="python3 /opt/globalspeed_test.py"
    local a
    for a in "${SCRIPT_ARGS[@]}"; do
        cmd+=" $(printf '%q' "$a")"
    done
    _green "在 BenchOS 沙箱内执行: $cmd"
    echo "------------------------------------------------------------"
    chroot_run "$cmd"
    local ret=$?
    echo "------------------------------------------------------------"
    post_cleanup
    trap - INT TERM HUP EXIT
    exit $ret
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
