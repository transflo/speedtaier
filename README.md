# SpeedTaier · 泰爾測速一鍵腳本

針對中國電信／中國聯通／中國移動測速節點的**全電信業者一鍵測速**工具：互動選擇省市後，自動測試該市所有電信業者的節點，輸出**NextTrace 路由追蹤、小封包／大封包延遲與封包遺失率、下載／上傳速度**。



## 快速開始（一鍵腳本）

```

# 指定參數（省市／單執行緒）
bash <(curl -sL https://raw.githubusercontent.com/transflo/speedtaier/main/onekey.sh) --province 江苏 --city 南京
bash <(curl -sL https://raw.githubusercontent.com/transflo/speedtaier/main/onekey.sh) --province 江苏 --city 南京 --threads 1
```
## Core 模式（輕量，不載入沙箱）

不需要沙箱／反向代理時，可使用 `--core` 直接在**本機**執行核心測速、延遲與封包遺失率測試（需要本機腳本）。小封包與大封包的延遲及封包遺失率採用 **NetQuality 風格的 mtr TCP 探測**（`-s 64`／`-s 1400`，單次以 `-c N` 取樣），**不需 root 權限也能測試**；未安裝 mtr 時會顯示 `-` 並提示安裝：

```bash
bash run_sandbox.sh --core --node 218.2.122.246:65499          # 直接測試指定節點
bash run_sandbox.sh --core --serverlist-url ./nodes.json --list --province 江苏 --city 南京
python3 globalspeed_test.py --core --node 218.2.122.246:65499  # 或直接使用 Python 呼叫
```
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
| `--core` | Core 模式：不載入沙箱、不判斷反向代理，僅在本機執行核心測速、延遲與封包遺失率測試 | - |
| `--local` | 優先使用本機資源，不從網路下載：腳本（`globalspeed_test.py`）、節點清單（`serverlist_decrypted.json`／`serverlist.json`／`nodes.json`，自動搜尋腳本所在目錄）、BenchOS 安裝包（同目錄中的 `BenchOs.tar.gz`）；缺少的資源仍會使用快取或下載 | - |

## 節點清單

從 GitHub 取得，由 GitHub Actions 每天 10:00 自動更新：
`https://raw.githubusercontent.com/transflo/speedtaier/main/serverlist_decrypted.json`

## 節點路由追蹤（NextTrace）

測速（速度、小封包／大封包延遲與封包遺失率）完成後，會對**每個測速成功的節點 IP**自動執行 [NextTrace](https://github.com/nxtrace/NTrace-core) 路由追蹤，並輸出完整結果。沙箱（root）模式會直接進行 ICMP 追蹤；非 root 的 `--core` 模式會自動改用 TCP 模式。若仍因權限不足而失敗，請執行：

```bash
sudo setcap cap_net_raw,cap_net_admin+eip $(command -v nexttrace)
```

若缺少 nexttrace，會自動安裝：`curl -sL https://nxtrace.org/nt | bash`
## 常見問題

- **`dovalid: -1-`**：節點拒絕排入佇列（限流或忙碌），程式會自動嘗試同一電信業者的下一個節點。
- **nexttrace 無法執行**：非 root 且未授予 `cap_net_raw` 時會提示權限不足；執行 `sudo setcap cap_net_raw,cap_net_admin+eip $(command -v nexttrace)` 後重試。沙箱（root）模式不需處理。
- **所有反向代理都無法使用**：會自動改為直接連線 github.com；海外 IP 預設直接連線，不使用反向代理。
- **大小封包顯示 `-`**：若沙箱內 mtr 安裝失敗，或 Core 模式尚未安裝 mtr，大小封包的延遲與封包遺失率會顯示為 `-`（並提示執行 `apt install mtr`）；不影響下載／上傳測速。
- **中國大陸 apt 速度慢或卡住**：沙箱偵測到位於中國大陸時，會自動切換至清華鏡像（`mirrors.tuna.tsinghua.edu.cn`）；所有 apt 命令皆設有逾時，避免卡住。
- **在中國大陸下載節點清單**：開始時測出最快的 GitHub 反向代理後，會透過 `SPEEDTAIER_PROXY` 環境變數傳入沙箱；沙箱內下載節點清單時會重用該代理，無需再次測速。
