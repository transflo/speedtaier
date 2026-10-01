# SpeedTaier · 泰爾測速一鍵腳本

針對中國電信／中國聯通／中國移動測速節點的**全電信業者一鍵測速**工具：互動選擇省市後，自動測試該市所有電信業者的節點，輸出**NextTrace 路由追蹤、小封包／大封包延遲與封包遺失率、下載／上傳速度**。



## 使用方式（兩種）

| | 沙箱模式（預設） | 純腳本模式 |
|---|---|---|
| 一鍵參數 | `--sandbox`（可省略） | `--script` |
| 執行位置 | 隔離的 BenchOS chroot 沙箱，測完自動刪除 | 本機直接以 `python3` 執行 |
| root 權限 | 需要（非 root 時自動使用 sudo） | 不需要 |
| GitHub 反向代理 | 依 IP 屬地自動判斷並選用最快的 | 經一鍵腳本啟動時依 IP 屬地自動判斷（用於下載腳本與節點清單）；直接執行 `python3 globalspeed_test.py` 則直連，可自行設定環境變數 `SPEEDTAIER_PROXY` |
| 相依套件 | 沙箱內自動安裝 | 本機需有 `python3`；建議安裝 `mtr`，`nexttrace` 會自動安裝 |

## 快速開始（一鍵腳本）

### 沙箱模式（預設）

```bash
# 互動選擇省市
bash <(curl -sL https://raw.githubusercontent.com/transflo/speedtaier/main/onekey.sh)

# 指定參數（省市／單執行緒）
bash <(curl -sL https://raw.githubusercontent.com/transflo/speedtaier/main/onekey.sh) --province 江苏 --city 南京
bash <(curl -sL https://raw.githubusercontent.com/transflo/speedtaier/main/onekey.sh) --province 江苏 --city 南京 --threads 1
```

### 純腳本模式

不需要沙箱時，加上 `--script`，直接在**本機**執行測速、延遲與封包遺失率測試。小封包與大封包的延遲及封包遺失率採用 **NetQuality 風格的 mtr TCP 探測**（`-s 64`／`-s 1400`，單次以 `-c N` 取樣），**不需 root 權限也能測試**；未安裝 mtr 時會顯示 `-` 並提示安裝：

```bash
bash <(curl -sL https://raw.githubusercontent.com/transflo/speedtaier/main/onekey.sh) --script
bash <(curl -sL https://raw.githubusercontent.com/transflo/speedtaier/main/onekey.sh) --script --province 江苏 --city 南京
```

已下載本倉庫時，也可以不經一鍵腳本，直接使用：

```bash
bash run_sandbox.sh --province 江苏 --city 南京                  # 沙箱模式
python3 globalspeed_test.py --node 218.2.122.246:65499           # 純腳本模式：直接測試指定節點
python3 globalspeed_test.py --serverlist-url ./nodes.json --list --province 江苏 --city 南京
```

> 舊的 `--core` 參數已移除，請改用 `--script`（純腳本）或 `--sandbox`（沙箱）。直接執行 `python3 globalspeed_test.py` 現在一律在本機執行，不再自動載入沙箱。

### 中國大陸網路

一鍵腳本啟動後，會先查詢 IP 屬地：中國大陸（或查詢失敗）時，自動測速並選用最快的 GitHub 反向代理來下載組件（純腳本模式下也用於下載節點清單）；海外 IP 直連。反向代理失敗或回傳的不是腳本時，會自動改為直連重試。

但最外層這條命令本身是在腳本啟動**之前**由 curl 直接下載的，無法自動代理。大陸網路下請在 URL 前加上反向代理前綴（任一可用，例如 `cdn.gh-proxy.org`）：

```bash
bash <(curl -sL https://cdn.gh-proxy.org/https://raw.githubusercontent.com/transflo/speedtaier/main/onekey.sh)
bash <(curl -sL https://cdn.gh-proxy.org/https://raw.githubusercontent.com/transflo/speedtaier/main/onekey.sh) --script --province 江苏 --city 南京
```

也可以用環境變數 `SPEEDTAIER_PROXY` 手動指定反向代理（如 `SPEEDTAIER_PROXY=https://gh-proxy.org`）：一鍵腳本會跳過自動探測，直接使用它下載組件；純腳本模式的節點清單也會使用它。沙箱模式下，`run_sandbox.sh` 仍會自行判斷屬地並選擇下載 BenchOS 的反向代理。

## 沙箱運作方式

`run_sandbox.sh`（bash 方式）：**先查詢 IP 地理位置**（Cloudflare trace／ip-api）——只有中國大陸 IP 才會測試並選用速度最快的 GitHub 反向代理（cdn／axisnow／gh-proxy／v4／v6，各下載 1 MB 比較速度；查詢失敗時按中國大陸處理），**海外 IP 會略過反向代理，直接連線** → 下載 BenchOS 與腳本（支援續傳、校驗及重試）→ 掛載 proc／sys／dev → chroot → **在沙箱內自動安裝相依套件**（python3／curl／ca-certificates／**mtr**；沙箱內直接使用 mtr 探測大小封包）→ **測速前自動安裝 nexttrace**（`curl -sL https://nxtrace.org/nt | bash`；若已安裝則略過）→ 開始測速 → **自動卸載並刪除沙箱**。

需要 root 權限（非 root 時會自動使用 sudo）；首次執行會下載約 300 MB 的 BenchOS rootfs，並**快取至 `~/.cache/speedtaier`**（可用環境變數 `SPEEDTAIER_CACHE` 覆寫）。測速結束後會刪除沙箱，但**保留安裝包**；下次執行會直接重用，不必重新下載。

## 參數

| 參數 | 說明 | 預設值 |
|---|---|---|
| `--province` / `--city` | 省份／城市，例如 `江苏/南京` | 互動選擇 |
| `--operator` | 僅測指定電信業者（`电信`／`联通`／`移动`…） | 全部 |
| `--node` | 直接測試指定節點 `IP:通訊埠` | - |
| `--threads` | 並行連線數（`--threads 1` 為單執行緒） | **8** |
| `--timeout` | 單一節點的總逾時時間（秒）；逾時時會自動略過並切換至下一節點 | 45 |
| `--seconds` | 每項測速的時間（秒） | 4 |
| `--bandwidth` | 回報頻寬（Mbps） | 200 |
| `--list` | 僅列出符合條件的節點 | - |
| `--no-progress` | 關閉進度顯示 | - |
| `--imei` | 固定 IMEI（供除錯使用）；未指定時會自動產生虛假的 IMEI | 自動 |
| `--serverlist-url` | 節點清單來源：GitHub URL 或**本機 JSON 路徑／`file://`**（本機檔案不經反向代理，會自動複製到沙箱） | 見下方說明 |
| `--sandbox` / `--script` | 僅 `onekey.sh` 使用：選擇沙箱模式或純腳本模式，其餘參數會原樣傳給測速腳本 | `--sandbox` |
| `--local` | 優先使用本機資源，不從網路下載：腳本（`globalspeed_test.py`）、節點清單（`serverlist_decrypted.json`／`serverlist.json`／`nodes.json`，自動搜尋腳本所在目錄）、BenchOS 安裝包（同目錄中的 `BenchOs.tar.gz`，僅沙箱模式）；缺少的資源仍會使用快取或下載 | - |

## 節點清單

從 GitHub 取得，由 GitHub Actions 每天 10:00 自動更新：
`https://raw.githubusercontent.com/transflo/speedtaier/main/serverlist_decrypted.json`

## 節點路由追蹤（NextTrace）

測速（速度、小封包／大封包延遲與封包遺失率）完成後，會對**每個測速成功的節點 IP**自動執行 [NextTrace](https://github.com/nxtrace/NTrace-core) 路由追蹤，並輸出完整結果。沙箱（root）模式會直接進行 ICMP 追蹤；非 root 的純腳本模式會自動改用 TCP 模式。若仍因權限不足而失敗，請執行：

```bash
sudo setcap cap_net_raw,cap_net_admin+eip $(command -v nexttrace)
```

若缺少 nexttrace，會自動安裝：`curl -sL https://nxtrace.org/nt | bash`
## 常見問題

- **`dovalid: -1-`**：節點拒絕排入佇列（限流或忙碌），程式會自動嘗試同一電信業者的下一個節點。
- **nexttrace 無法執行**：非 root 且未授予 `cap_net_raw` 時會提示權限不足；執行 `sudo setcap cap_net_raw,cap_net_admin+eip $(command -v nexttrace)` 後重試。沙箱（root）模式不需處理。
- **所有反向代理都無法使用**：會自動改為直接連線 github.com；海外 IP 預設直接連線，不使用反向代理。
- **大小封包顯示 `-`**：若沙箱內 mtr 安裝失敗，或純腳本模式的本機尚未安裝 mtr，大小封包的延遲與封包遺失率會顯示為 `-`（並提示執行 `apt install mtr`）；不影響下載／上傳測速。
- **中國大陸 apt 速度慢或卡住**：沙箱偵測到位於中國大陸時，會自動切換至清華鏡像（`mirrors.tuna.tsinghua.edu.cn`）；所有 apt 命令皆設有逾時，避免卡住。
- **在中國大陸下載節點清單**：開始時測出最快的 GitHub 反向代理後，會透過 `SPEEDTAIER_PROXY` 環境變數傳入沙箱；沙箱內下載節點清單時會重用該代理，無需再次測速。
