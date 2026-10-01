#!/bin/bash
# SpeedTaier 一键脚本，两种使用方式：
#   --sandbox  沙箱模式（默认）：加载 BenchOS 沙箱运行，需 root，测速结束自动删除沙箱
#   --script   纯脚本模式：本机直接用 python3 运行，无需 root、不加载沙箱
# 其余参数原样透传给 globalspeed_test.py（如 --province 江苏 --city 南京）
#
# 下载组件前会先查询 IP 属地：中国大陆（或查询失败）时测速选用最快的 GitHub 反代，
# 海外 IP 直连。可用环境变量 SPEEDTAIER_PROXY 手动指定反代，跳过自动探测。

DEFAULT_BASE_URL="https://raw.githubusercontent.com/transflo/speedtaier/main"
BASE_URL="${SPEEDTAIER_BASE_URL:-$DEFAULT_BASE_URL}"

GITHUB_PROXIES=(
    "https://cdn.gh-proxy.org"
    "https://axisnow.gh-proxy.org"
    "https://gh-proxy.org"
    "https://v4.gh-proxy.org"
    "https://v6.gh-proxy.org"
)

MODE="sandbox"
ARGS=()
for arg in "$@"; do
    case "$arg" in
        --sandbox) MODE="sandbox" ;;
        --script)  MODE="script" ;;
        --core)
            echo "[!] --core 模式已移除，请改用 --script（纯脚本）或 --sandbox（沙箱）"
            exit 1
            ;;
        *) ARGS+=("$arg") ;;
    esac
done

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
    local url="$1" best="" best_speed=0
    local proxy out bytes speed probe="$tmp_dir/.probe"
    for proxy in "${GITHUB_PROXIES[@]}"; do
        rm -f "$probe"
        out="$(curl -fsL --connect-timeout 4 -m 8 -r 0-1048575 -o "$probe" \
                -w '%{size_download} %{speed_download}' "$proxy/$url" 2>/dev/null)" || out=""
        bytes="${out%% *}"
        speed="${out##* }"
        bytes="${bytes:-0}"
        speed="${speed:-0}"
        # 返回的不是脚本（如 200 的错误页）视为不可用
        [[ "$(head -c 2 "$probe" 2>/dev/null)" == "#!" ]] || bytes=0
        if [[ "$bytes" -gt 0 ]] && awk -v s="$speed" -v b="$best_speed" 'BEGIN{ exit !(s>b) }'; then
            best="$proxy"
            best_speed="$speed"
        fi
        echo "  代理 $proxy -> ${bytes}B / ${speed%.*}B/s" >&2
    done
    if [[ -n "$best" ]]; then
        echo "  选用: $best" >&2
    else
        echo "  所有反代均不可用，回退直连 github.com" >&2
    fi
    echo "$best"
}

# 设置 PROXY（空表示直连）。仅在使用默认 GitHub 下载源时才探测，自定义下载源不加反代前缀。
setup_proxy() {
    PROXY=""
    [[ "$BASE_URL" == "$DEFAULT_BASE_URL" ]] || return 0
    if [[ -n "${SPEEDTAIER_PROXY:-}" ]]; then
        PROXY="${SPEEDTAIER_PROXY%/}"
        echo "[*] 使用环境变量 SPEEDTAIER_PROXY 指定的反代: $PROXY"
        return 0
    fi
    local cc
    cc="$(get_country_code)"
    if [[ -n "$cc" && "$cc" != "CN" ]]; then
        echo "[*] IP 属地：$cc（中国大陆以外），直连 github.com"
        return 0
    fi
    if [[ -z "$cc" ]]; then
        echo "[*] IP 属地查询失败，按中国大陆处理，测速选择最快的 GitHub 反代..."
    else
        echo "[*] IP 属地：中国大陆，测速选择最快的 GitHub 反代..."
    fi
    PROXY="$(pick_fastest_proxy "$BASE_URL/globalspeed_test.py")"
}

download() {
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL --connect-timeout 10 -m 60 -o "$2" "$1" 2>/dev/null
    else
        wget -qO "$2" -T 20 "$1" 2>/dev/null
    fi
}

# 下载成功且内容是脚本（以 #! 开头）才算成功，避免把反代返回的错误页当成脚本
fetch() {
    local name="$1" out="$tmp_dir/$1"
    if [[ -n "$PROXY" ]]; then
        if download "$PROXY/$BASE_URL/$name" "$out" && [[ "$(head -c 2 "$out")" == "#!" ]]; then
            return 0
        fi
        echo "  反代下载 $name 失败，改为直连" >&2
    fi
    download "$BASE_URL/$name" "$out" && [[ "$(head -c 2 "$out")" == "#!" ]]
}

run_sandbox_mode() {
    cd "$tmp_dir" || return 1
    bash run_sandbox.sh --local "${ARGS[@]}"
}

run_script_mode() {
    if ! command -v python3 >/dev/null 2>&1; then
        echo "[!] 未检测到 python3，请先安装后重试（例如: apt install python3）"
        return 1
    fi
    echo "[*] 纯脚本模式：在本机直接运行（不加载沙箱）"
    python3 "$tmp_dir/globalspeed_test.py" "${ARGS[@]}"
}

setup_proxy
if [[ -n "$PROXY" ]]; then
    export SPEEDTAIER_PROXY="$PROXY"
fi

echo "[*] 下载 SpeedTaier 组件..."
components=(globalspeed_test.py)
[[ "$MODE" == "sandbox" ]] && components+=(run_sandbox.sh)
for c in "${components[@]}"; do
    if ! fetch "$c"; then
        echo "[!] 组件下载失败（$c），请检查网络后重试"
        exit 1
    fi
done

if [[ "$MODE" == "sandbox" ]]; then
    run_sandbox_mode
else
    run_script_mode
fi
exit $?
