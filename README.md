# SpeedTaier · 泰尔测速一键脚本

针对电信/联通/移动测速节点的**全运营商一键测速**工具：交互选择省市后，自动测速该市所有运营商节点，输出**NextTrace 路由追踪、小包/大包延迟与丢包率、下载/上传**。



## 快速开始（一键脚本）

```

# 带参数（指定省市 / 单线程）
bash <(curl -sL https://raw.githubusercontent.com/transflo/speedtaier/main/onekey.sh) --province 江苏 --city 南京
bash <(curl -sL https://raw.githubusercontent.com/transflo/speedtaier/main/onekey.sh) --province 江苏 --city 南京 --threads 1
```

## Core 模式（轻量，不加载沙箱）

不需要沙箱/反代时，用 `--core` 直接在**本机**执行核心测速/延迟/丢包（需本地脚本）。大小包延迟/丢包采用 **NetQuality 风格 mtr TCP 探测**（`-s 64` / `-s 1400`，单次 `-c N` 采样），**非 root 也可测**；未安装 mtr 时显示 `-` 并提示安装：

```bash
bash run_sandbox.sh --core --node 218.2.122.246:65499          # 直接测指定节点
bash run_sandbox.sh --core --serverlist-url ./nodes.json --list --province 江苏 --city 南京
python3 globalspeed_test.py --core --node 218.2.122.246:65499  # 或直接 python 调用
```
## 沙箱机制

`run_sandbox.sh`（bash 方式）：**先查 IP 属地**（Cloudflare trace / ip-api）——中国大陆 IP 才测速选最快 GitHub 反代（cdn/axisnow/gh-proxy/v4/v6，各下载 1MB 比速；查询失败按大陆处理），**海外 IP 跳过反代直连** → 下载 BenchOS 与脚本（断点续传+校验+重试）→ 挂载 proc/sys/dev → chroot → **沙箱内自动装依赖**（python3/curl/ca-certificates/**mtr**，大小包探测在沙箱内直接用 mtr）→ **测速前自动安装 nexttrace**（`curl -sL https://nxtrace.org/nt | bash`，已安装则跳过）→ 测速 → **自动卸载并删除沙箱**。

需 root（非 root 自动 sudo）；首次运行下载约 300MB BenchOS rootfs 并**缓存到 `~/.cache/speedtaier`**（可用环境变量 `SPEEDTAIER_CACHE` 覆盖），测速结束删除沙箱但**保留安装包**，下次运行直接复用、无需重复下载。

## 参数

| 参数 | 说明 | 默认 |
|---|---|---|
| `--province` / `--city` | 省份/城市，如 江苏/南京 | 交互选择 |
| `--operator` | 只测指定运营商（电信/联通/移动…） | 全部 |
| `--node` | 直接测指定节点 `IP:端口` | - |
| `--threads` | 并发连接数（`--threads 1` 为单线程） | **8** |
| `--timeout` | 单节点总超时（秒），卡住自动跳过切换下一节点 | 45 |
| `--seconds` | 每项测速时长（秒） | 4 |
| `--bandwidth` | 上报带宽（Mbps） | 200 |
| `--list` | 只列出匹配节点 | - |
| `--no-progress` | 关闭进度显示 | - |
| `--imei` | 固定 IMEI（调试用）；不指定则自动生成虚假 IMEI | 自动 |
| `--serverlist-url` | 节点表来源：GitHub URL 或**本地 JSON 路径/`file://`**（本地文件不走反代，自动复制进沙箱） | 见下 |
| `--core` | Core 模式：不加载沙箱、不做反代判断，仅本机执行核心测速/延迟/丢包 | - |
| `--local` | 本地优先：本地存在的资源自动采用，不拉网络——脚本(`globalspeed_test.py`)、节点表(`serverlist_decrypted.json`/`serverlist.json`/`nodes.json`,自动发现脚本同目录)、BenchOS 安装包(`BenchOs.tar.gz` 同目录)；缺少的仍走缓存/下载 | - |

## 节点表

从 GitHub 获取，由 GitHub Actions 每天 10:00 自动更新：
`https://raw.githubusercontent.com/transflo/speedtaier/main/serverlist_decrypted.json`

## 节点路由追踪（NextTrace）

测速（速度 + 大小包延迟/丢包）完成后，对**每个成功的节点 IP** 自动运行 [NextTrace](https://github.com/nxtrace/NTrace-core) 路由追踪并输出完整结果。沙箱（root）模式下直接 ICMP 追踪；非 root 的 `--core` 模式自动回退 TCP 模式，若仍因权限失败请执行：

```bash
sudo setcap cap_net_raw,cap_net_admin+eip $(command -v nexttrace)
```

nexttrace 缺失时自动安装：`curl -sL https://nxtrace.org/nt | bash`

## 常见问题

- **`dovalid: -1-`**：节点拒绝入队（限流/忙），自动尝试同运营商下一节点。
- **nexttrace 无法运行**：非 root 且未授予 `cap_net_raw` 时提示权限不足，执行 `sudo setcap cap_net_raw,cap_net_admin+eip $(command -v nexttrace)` 后重试；沙箱（root）模式无需处理。
- **反代全挂**：自动回退直连 github.com；海外 IP 默认直连不走反代。
- **大小包显示 `-`**：沙箱内 mtr 安装失败或 core 模式未装 mtr 时，大小包延迟/丢包显示 `-`（提示 `apt install mtr`）；不影响下载/上传测速。
- **大陆 apt 慢/卡**：沙箱内检测到中国大陆环境自动切换清华镜像（`mirrors.tuna.tsinghua.edu.cn`），apt 命令均带超时防卡死。
- **大陆节点表下载**：开始阶段测好最快的 GitHub 反代后，通过 `SPEEDTAIER_PROXY` 环境变量传入沙箱，沙箱内拉取节点表自动复用该反代，无需二次测速。
