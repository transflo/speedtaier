#!/usr/bin/env python3

import argparse
import hashlib
import json
import os
import random
import re
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

PKG = "com.cnspeedtest.globalspeed"
APP = "globalspeed"
RAND_CONST = "12345555"
UA_DOWN = ("Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/100.0.4896.60 Safari/537.36")
UA_UP = "Dalvik/1.6.0 (Linux; U; Android 4.2.2; GT-I9505 Build/JDQ39)"
BOUNDARY = "00content0boundary00"
DEFAULT_SERVERLIST_URL = "https://raw.githubusercontent.com/transflo/speedtaier/main/serverlist_decrypted.json"

_USE_COLOR = False
try:
    _USE_COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
except Exception:
    _USE_COLOR = False

_CYAN, _GREEN, _YELLOW, _RED, _BOLD, _DIM = (
    "\033[36m", "\033[32m", "\033[33m", "\033[31m", "\033[1m", "\033[2m")
_RESET = "\033[0m"

def _c(s, code):
    return (code + s + _RESET) if _USE_COLOR else s

def _info(msg):
    print(_c("[*] " + msg, _CYAN + _BOLD))

def _ok(msg):
    print(_c("[+] " + msg, _GREEN))

def _warn(msg):
    print(_c("[!] " + msg, _RED + _BOLD))

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_TABLE_WIDTH = 80

def _strip_ansi(s):
    return _ANSI_RE.sub("", s)

def _disp_width(s):
    w = 0
    for ch in _strip_ansi(s):
        o = ord(ch)
        if o < 32 or 0x7F <= o < 0xA0:
            continue
        if (0x1100 <= o <= 0x115F or 0x2E80 <= o <= 0x303E or 0x3041 <= o <= 0x33FF
                or 0x3400 <= o <= 0x4DBF or 0x4E00 <= o <= 0x9FFF or 0xA000 <= o <= 0xA4CF
                or 0xAC00 <= o <= 0xD7A3 or 0xF900 <= o <= 0xFAFF or 0xFE30 <= o <= 0xFE4F
                or 0xFF00 <= o <= 0xFF60 or 0xFFE0 <= o <= 0xFFE6 or o >= 0x20000):
            w += 2
        else:
            w += 1
    return w

def _pad(s, width, align="left"):
    is_left = align[0] == "l"
    is_center = align[0] == "c"
    vis = _strip_ansi(s)
    vw = _disp_width(vis)
    if vw > width:
        cut = vis[:width - 1] if is_left or is_center else vis[-(width - 1):]
        return cut + "…"
    pad = width - vw
    if is_center:
        return " " * (pad // 2) + s + " " * (pad - pad // 2)
    return (s + " " * pad) if is_left else (" " * pad + s)

def _divider(msg):
    w = _disp_width(msg)
    total = _TABLE_WIDTH
    if w >= total - 2:
        print(msg)
        return
    n = total - w - 2
    print(_c("─" * (n // 2) + " " + msg + " " + "─" * (n - n // 2), _DIM))

def _ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

def http_get(url, timeout=10, no_proxy=False):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({})) if no_proxy else None
    try:
        if opener:
            with opener.open(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx()) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read()[:200].decode("utf-8", "replace").strip()
        except Exception:
            pass
        msg = "HTTP %d %s" % (e.code, e.reason)
        if body:
            msg += " (%s)" % body
        raise RuntimeError(msg)
    except urllib.error.URLError as e:
        if isinstance(e.reason, socket.timeout):
            raise RuntimeError("连接超时 (>%ds)" % timeout)
        if isinstance(e.reason, ConnectionRefusedError):
            raise RuntimeError("连接被拒绝")
        raise RuntimeError("网络请求失败: %s" % e.reason)
    except socket.timeout:
        raise RuntimeError("连接超时 (>%ds)" % timeout)
    except Exception as e:
        raise RuntimeError("%s: %s" % (type(e).__name__, e))

def http_post(url, body=b"", timeout=10):
    req = urllib.request.Request(url, data=body, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx()) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        msg = "HTTP %d %s" % (e.code, e.reason)
        raise RuntimeError(msg)
    except urllib.error.URLError as e:
        raise RuntimeError("POST失败: %s" % e.reason)
    except Exception as e:
        raise RuntimeError("%s: %s" % (type(e).__name__, e))

IMEI_TACS = (
    "86309606", "86107500", "86135803", "86330801", "86293103",
    "86824303", "86436303", "86970103", "86114003", "86663003",
)

def luhn_check_digit(digits):
    total = 0
    for i, ch in enumerate(reversed(str(digits))):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return (10 - total % 10) % 10

def generate_imei(tac=None):
    if tac is None:
        tac = random.choice(IMEI_TACS)
    serial = "%06d" % random.randint(0, 999999)
    return tac + serial + str(luhn_check_digit(tac + serial))

def make_token(imei, t, bandwidth):
    h1 = hashlib.md5(("model=Android&imei=" + imei).encode()).hexdigest()
    h2 = hashlib.md5(("stime=" + t + "&band=" + str(bandwidth) + "&rand=" + RAND_CONST).encode()).hexdigest()
    return hashlib.md5((h1 + h2).encode()).hexdigest()

def check_tcp_connectivity(ip, port, timeout=1.2):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except Exception:
            pass
        s.connect((ip, int(port)))
        s.close()
        return True, None
    except ConnectionRefusedError:
        return False, "连接被拒绝 (端口未开放/服务未启动)"
    except socket.timeout:
        return False, "连接超时 (>%.1fs)" % timeout
    except OSError as e:
        if getattr(e, "errno", None) in (111, 61):
            return False, "连接被拒绝"
        if getattr(e, "errno", None) in (113, 65):
            return False, "主机不可达 (No route to host)"
        if getattr(e, "errno", None) in (101, 51):
            return False, "网络不可达 (Network unreachable)"
        return False, "网络异常: %s" % e
    except Exception as e:
        return False, "连接异常: %s" % e

def tcp_reachable(ip, port, timeout=1.5):
    ok, _ = check_tcp_connectivity(ip, port, timeout)
    return ok

def fetch_nodes_from_github(url):
    if url.startswith(("http://", "https://")):
        proxy = os.environ.get("SPEEDTAIER_PROXY") or ""
        if proxy:
            url = proxy.rstrip("/") + "/" + url
        data = http_get(url, timeout=30)
    else:
        path = url[7:] if url.startswith("file://") else url
        with open(path, "r", encoding="utf-8") as f:
            data = f.read()
    nodes = json.loads(data)
    if not isinstance(nodes, list) or not nodes:
        raise RuntimeError("节点表为空或格式错误")
    return nodes

def pick_nodes(nodes, province=None, city=None, operator=None):
    out = []
    for n in nodes:
        if province and n.get("p") != province:
            continue
        if city and n.get("c") != city:
            continue
        if operator and n.get("o") != operator:
            continue
        out.append(n)
    return out

def list_provinces(nodes):
    seen = []
    for n in nodes:
        p = n.get("p") or "其他"
        if p not in seen:
            seen.append(p)
    return seen

def list_cities(nodes, province):
    seen = []
    for n in nodes:
        if n.get("p") != province:
            continue
        c = n.get("c") or "未知"
        if c not in seen:
            seen.append(c)
    return seen

def group_by_operator(nodes):
    groups = {}
    order = []
    for n in nodes:
        o = n.get("o") or "其他"
        if o not in groups:
            groups[o] = []
            order.append(o)
        groups[o].append(n)
    return order, groups

_MTR_OK = None
_MTR_BIN = None
_MTR_SMALL_SIZE = 64
_MTR_LARGE_SIZE = 1400
_MTR_PACKETS = 8
_MTR_TIMEOUT = 15

def _mtr_available():
    global _MTR_OK, _MTR_BIN
    if _MTR_OK is None:
        for name in ("mtr-tiny", "mtr"):
            try:
                r = subprocess.run([name, "--version"], capture_output=True, timeout=5)
            except Exception:
                continue
            if r.returncode == 0:
                _MTR_BIN = name
                _MTR_OK = True
                break
        if not _MTR_OK:
            _MTR_BIN = "mtr"
            _warn("未检测到 mtr/mtr-tiny，大小包延迟/丢包将显示 -（安装: apt install mtr-tiny）")
    return _MTR_OK

def _mtr_parse(out, host, packets):
    lines = out.splitlines()
    header = next((l for l in lines if l.startswith("Mtr_Version")), None)
    if header is None:
        return None
    hdr = header.rstrip(",").split(",")

    def col(name):
        return hdr.index(name) if name in hdr else None

    i_ip, i_loss, i_snt, i_avg = col("Ip"), col("Loss%"), col("Snt"), col("Avg")
    i_best, i_wrst, i_std = col("Best"), col("Wrst"), col("StDev")
    if None in (i_ip, i_loss, i_snt, i_avg):
        return None
    for line in reversed(lines):
        parts = line.split(",")
        if len(parts) <= i_ip or parts[i_ip].strip() != host:
            continue
        try:
            loss = float(parts[i_loss])
            sent = int(parts[i_snt]) if parts[i_snt] else packets
            avg = float(parts[i_avg])
        except (ValueError, IndexError):
            return None

        def num(idx):
            try:
                return float(parts[idx]) if idx is not None and parts[idx] else None
            except (ValueError, IndexError):
                return None

        return avg, loss, sent, num(i_best), num(i_wrst), num(i_std)
    return None, 100.0, packets, None, None, None

def _mtr_run(host, port, packets, large=False):
    if not _mtr_available() or ":" in host:
        return None
    size = _MTR_LARGE_SIZE if large else _MTR_SMALL_SIZE
    cmd = [_MTR_BIN, "-4", "--tcp", "-P", str(port), "-c", str(packets),
           "-f", "1", "-C", "-i", "1", "-G", "1", "-s", str(size), "--no-dns", host]
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=_MTR_TIMEOUT).stdout
    except Exception:
        return None

def _mtr_loss_probe(host, port, packets=8, large=False):
    out = _mtr_run(host, port, packets, large)
    if out is None:
        return None
    return _mtr_parse(out, host, packets)

def _mtr_unavailable():
    return {"latency_ms": None, "jitter_ms": None, "min_ms": None, "max_ms": None,
            "loss_pct": None, "samples": 0, "lost": 0}

def _mtr_to_summary(res):
    avg, loss, sent, best, wrst, std = res
    return {"latency_ms": avg, "jitter_ms": std, "min_ms": best, "max_ms": wrst,
            "loss_pct": loss, "samples": sent,
            "lost": int(round(sent * loss / 100.0)) if loss else 0}

def small_packet_probe(node, samples=8):
    host = node["ip"]
    port = int(node.get("port") or "65499")
    res = _mtr_loss_probe(host, port, packets=_MTR_PACKETS, large=False)
    if res is None:
        return _mtr_unavailable()
    return _mtr_to_summary(res)

def large_packet_probe(node, samples=5):
    host = node["ip"]
    port = int(node.get("port") or "65499")
    res = _mtr_loss_probe(host, port, packets=_MTR_PACKETS, large=True)
    if res is None:
        return _mtr_unavailable()
    return _mtr_to_summary(res)

def _ensure_nexttrace():
    if shutil.which("nexttrace"):
        return True
    if not shutil.which("curl"):
        _warn("未检测到 curl，无法安装 nexttrace，跳过路由追踪")
        return False
    _info("未检测到 nexttrace，正在安装 (curl -sL https://nxtrace.org/nt | bash) ...")
    try:
        r = subprocess.run("curl -sL https://nxtrace.org/nt | bash",
                           shell=True, capture_output=True, text=True, timeout=180)
    except Exception as e:
        _warn("nexttrace 安装失败: %s" % e)
        return False
    if r.returncode != 0 or not shutil.which("nexttrace"):
        _warn("nexttrace 安装失败: %s" % ((r.stderr or r.stdout or "").strip()[-200:]))
        return False
    _ok("nexttrace 安装完成")
    return True

def run_nexttrace(ip):
    for mode in (None, "-T"):
        cmd = ["nexttrace"] + ([mode] if mode else []) + [ip]
        try:
            r = subprocess.run(cmd, stderr=subprocess.PIPE, timeout=120)
        except Exception as e:
            return False, str(e)
        if r.returncode == 0:
            return True, ""
        err = (r.stderr or b"").decode("utf-8", "replace").strip()
        if "permission" not in err and "permitted" not in err:
            return False, (err or "exit %d" % r.returncode)[:200]
    return False, "权限不足（非 root 且未设置 cap_net_raw），可执行 sudo setcap cap_net_raw,cap_net_admin+eip $(command -v nexttrace) 后重试"

def dovalid(node, imei, bandwidth, token=None, uuid=None, timeout=3.5):
    host = node["ip"]
    port = node.get("port") or "65499"
    ts = str(int(time.time()))
    if uuid is None:
        tok = token if token is not None else make_token(imei, ts, bandwidth)
        url = ("http://%s:%s/speed/dovalid?key=&flag=true&bandwidth=%d&model=Android"
               "&imei=%s&time=%s&app=%s&token=%s&pkg=%s" % (
                   host, port, bandwidth, imei, ts, APP, tok, PKG))
        try:
            r = http_get(url, timeout=timeout, no_proxy=True)
        except Exception as e:
            return None, "dovalid 连接失败: %s" % e
        r = r.strip()
        if r.startswith("-1"):
            return None, "节点繁忙/排队超限 (dovalid: -1)"
        if r.startswith("0"):
            return None, "鉴权失败/Token无效 (dovalid: 0)"
        if r.startswith("2"):
            return None, "参数非法/版本不符 (dovalid: 2)"
        if not r.startswith("1"):
            return None, "dovalid 返回异常: %s" % r[:120]
        return r[2:], None
    else:
        url = "http://%s:%s/speed/dovalid?key=%s" % (host, port, uuid)
        try:
            http_post(url, b"", timeout=3.0)
        except Exception:
            pass
        return uuid, None

def _resolve_addr(host, port):
    try:
        infos = socket.getaddrinfo(host, int(port), socket.AF_INET, socket.SOCK_STREAM)
        return infos[0][4]
    except Exception as e:
        raise OSError("地址解析失败 (%s:%s): %s" % (host, port, e))

def _connect(host, port, timeout=3.0, addr=None):
    if addr is None:
        addr = _resolve_addr(host, port)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except Exception:
        pass
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 524288)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 524288)
    except Exception:
        pass
    s.settimeout(timeout)
    s.connect(addr)
    s.settimeout(None)
    return s

def _download_conn(host, port, req, stop, counter, lock, errors=None, fail=None, addr=None):
    try:
        s = _connect(host, port, timeout=3.0, addr=addr)
        s.sendall(req.encode())
        s.settimeout(4.0)
        buf = b""
        while b"\r\n\r\n" not in buf:
            c = s.recv(4096)
            if not c:
                break
            buf += c
        if not buf.startswith(b"HTTP/1.1 200") and not buf.startswith(b"HTTP/1.0 200"):
            if errors is not None:
                with lock:
                    status = buf.split(b"\r\n", 1)[0].decode("utf-8", "replace") if buf else "空响应"
                    errors.append("下载HTTP响应异常: %s" % status)
            if fail is not None:
                with lock:
                    fail[0] += 1
            s.close()
            return
        while not stop.is_set():
            c = s.recv(65536)
            if not c:
                break
            with lock:
                counter[0] += len(c)
        s.close()
    except Exception as e:
        if errors is not None:
            with lock:
                err_str = "连接超时" if isinstance(e, socket.timeout) else ("%s: %s" % (type(e).__name__, e))
                errors.append("下载连接失败: %s" % err_str)
        if fail is not None:
            with lock:
                fail[0] += 1

_UPLOAD_CHUNK_SIZE = 131072
_UPLOAD_CHUNK = os.urandom(_UPLOAD_CHUNK_SIZE)

def _upload_conn(host, port, uuid, stop, counter, lock, content_length=900000000, errors=None, fail=None, addr=None):
    fname = "SPEED_" + time.strftime("%Y%m%d_%H%M%S_") + str(int(time.time() * 1000) % 1000)
    header = ("POST /speed/doAnalsLoad.do HTTP/1.1\r\n"
              "Connection: close\r\nCache-Control: no-cache\r\nCharset: UTF-8\r\n"
              "Key: %s\r\n"
              "Content-Type: multipart/form-data;boundary=%s\r\n"
              "User-Agent: %s\r\nHost: %s:%s\r\nAccept-Encoding: gzip\r\n"
              "Content-Length: %d\r\n\r\n--%s\r\n"
              'Content-Disposition: form-data; name="upload";filename="%s"\r\n\r\n'
              % (uuid, BOUNDARY, UA_UP, host, port, content_length, BOUNDARY, fname)).encode()
    chunk = _UPLOAD_CHUNK
    try:
        s = _connect(host, port, timeout=3.0, addr=addr)
        s.sendall(header)
        while not stop.is_set():
            s.sendall(chunk)
            with lock:
                counter[0] += len(chunk)
        try:
            s.sendall(("\r\n--%s--\r\n" % BOUNDARY).encode())
        except Exception:
            pass
        s.close()
    except Exception as e:
        if errors is not None:
            with lock:
                err_str = "连接超时" if isinstance(e, socket.timeout) else ("%s: %s" % (type(e).__name__, e))
                errors.append("上传连接失败: %s" % err_str)
        if fail is not None:
            with lock:
                fail[0] += 1

def _progress_monitor(label, total_seconds, counter, stop, lock, start_time, enabled, tty):
    while not stop.is_set():
        time.sleep(0.5)
        with lock:
            cur = counter[0]
        now = time.time()
        elapsed = now - start_time
        avg_rate = (cur * 8.0 / elapsed / 1e6) if elapsed > 0 else 0.0
        pct = min(100.0, elapsed / total_seconds * 100.0)
        if not enabled:
            continue
        bar_width = 20
        filled = int(pct / 100.0 * bar_width)
        bar = "\u2588" * filled + "\u2591" * (bar_width - filled)
        body = "%s %s %7.1f Mbps" % (_c(label, _CYAN + _BOLD), bar, avg_rate)
        if tty:
            sys.stdout.write("\r" + body + "\x1b[K")
            sys.stdout.flush()
        else:
            if pct >= 100:
                continue
            step = int(pct // 20)
            if step != int((now - start_time - 0.5) / total_seconds * 100 // 20):
                sys.stdout.write(body + "\n")
                sys.stdout.flush()

def _run_with_progress(label, seconds, fn, enabled=True, tty=False):
    if not enabled or not tty:
        return fn()
    stop = threading.Event()
    t0 = time.time()

    def mon():
        while not stop.is_set():
            time.sleep(0.2)
            pct = min(100.0, (time.time() - t0) / max(1, seconds) * 100.0)
            bar_width = 20
            filled = int(pct / 100.0 * bar_width)
            bar = "\u2588" * filled + "\u2591" * (bar_width - filled)
            sys.stdout.write("\r%s %s %3.0f%%\x1b[K" % (_c(label, _CYAN + _BOLD), bar, pct))
            sys.stdout.flush()

    th = threading.Thread(target=mon)
    th.start()
    try:
        return fn()
    finally:
        stop.set()
        th.join(timeout=1)
        sys.stdout.write("\r\x1b[K")
        sys.stdout.flush()

def measure_download(node, uuid, seconds=5, threads=4, progress_label=None, progress_enabled=True, tty=False):
    host = node["ip"]
    port = node.get("port") or "65499"
    ts = str(int(time.time()))
    path = "/speed/File(1G).dl?r=%s&key=%s" % (ts, uuid)
    req = ("GET %s HTTP/1.1\r\nAccept: */*\r\nConnection: close\r\n"
           "User-Agent: %s\r\nHost:%s:%s\r\n\r\n" % (path, UA_DOWN, host, port))
    stop = threading.Event()
    counter = [0]
    lock = threading.Lock()
    errors = []
    fail = [0]
    try:
        addr = _resolve_addr(host, port)
    except Exception as e:
        return 0.0, ["地址解析失败: %s" % e]

    t0 = time.time()
    workers = []
    n_threads = max(1, threads)
    for _ in range(n_threads):
        th = threading.Thread(target=_download_conn, args=(host, port, req, stop, counter, lock, errors, fail, addr))
        th.start()
        workers.append(th)
    monitor = None
    if progress_label:
        monitor = threading.Thread(target=_progress_monitor, args=(
            progress_label, seconds, counter, stop, lock, t0, progress_enabled, tty))
        monitor.start()
    wait_end = t0 + seconds
    while time.time() < wait_end:
        with lock:
            if fail[0] >= n_threads:
                break
        time.sleep(0.1)
    t_stop = time.time()
    stop.set()
    for th in workers:
        th.join(timeout=2.5)
    if monitor:
        monitor.join(timeout=1.5)
    dt = t_stop - t0
    total = counter[0]
    rate = (total * 8 / dt / 1e6) if dt > 0 else 0.0
    if progress_label and progress_enabled:
        body = "%s: 100%%  %7.1f Mbps" % (progress_label, rate)
        if tty:
            sys.stdout.write("\r" + body + "\x1b[K\n")
        else:
            sys.stdout.write(body + "\n")
        sys.stdout.flush()
    return rate, errors

def measure_upload(node, uuid, seconds=5, threads=4, progress_label=None, progress_enabled=True, tty=False):
    host = node["ip"]
    port = node.get("port") or "65499"
    content_length = 900000000
    stop = threading.Event()
    counter = [0]
    lock = threading.Lock()
    errors = []
    fail = [0]
    try:
        addr = _resolve_addr(host, port)
    except Exception as e:
        return 0.0, ["地址解析失败: %s" % e]

    t0 = time.time()
    workers = []
    n_threads = max(1, threads)
    for _ in range(n_threads):
        th = threading.Thread(target=_upload_conn,
                              args=(host, port, uuid, stop, counter, lock, content_length, errors, fail, addr))
        th.start()
        workers.append(th)
    monitor = None
    if progress_label:
        monitor = threading.Thread(target=_progress_monitor, args=(
            progress_label, seconds, counter, stop, lock, t0, progress_enabled, tty))
        monitor.start()
    wait_end = t0 + seconds
    while time.time() < wait_end:
        with lock:
            if fail[0] >= n_threads:
                break
        time.sleep(0.1)
    t_stop = time.time()
    stop.set()
    for th in workers:
        th.join(timeout=2.5)
    if monitor:
        monitor.join(timeout=1.5)
    dt = t_stop - t0
    total = counter[0]
    rate = (total * 8 / dt / 1e6) if dt > 0 else 0.0
    if progress_label and progress_enabled:
        body = "%s: 100%%  %7.1f Mbps" % (progress_label, rate)
        if tty:
            sys.stdout.write("\r" + body + "\x1b[K\n")
        else:
            sys.stdout.write(body + "\n")
        sys.stdout.flush()
    return rate, errors

def run_operator_test(node, imei, bandwidth, seconds, threads, progress_enabled, tty, timeout=45):
    if imei is None:
        imei = generate_imei()
    host = node["ip"]
    port = node.get("port") or "65499"
    result = {"node": node, "ok": False}
    deadline = time.time() + max(5, int(timeout))

    def expired(phase=""):
        if time.time() > deadline:
            result["error"] = "超时 (%s耗时过长)" % phase if phase else "超时"
            return True
        return False

    is_reach, reach_err = check_tcp_connectivity(host, port, timeout=1.2)
    if not is_reach:
        result["error"] = reach_err or "端口不可达"
        return result
    if expired("连通性探测"):
        return result

    ts_now = str(int(time.time()))
    token = make_token(imei, ts_now, bandwidth)
    uuid, err = dovalid(node, imei, bandwidth, token=token, timeout=3.5)
    if uuid is None and ("dovalid" in str(err) or "超时" in str(err)):
        uuid, err = dovalid(node, imei, bandwidth, token="", timeout=2.5)

    if uuid is None:
        result.update({"error": str(err), "server_log": str(err)})
        return result

    if expired("dovalid鉴权"):
        dovalid(node, imei, bandwidth, uuid=uuid)
        return result

    down, down_log = measure_download(node, uuid, seconds, threads,
                                      progress_label="下载" if progress_enabled else None,
                                      progress_enabled=progress_enabled, tty=tty)
    if expired("下载测速"):
        dovalid(node, imei, bandwidth, uuid=uuid)
        return result

    up, up_log = measure_upload(node, uuid, seconds, threads,
                                progress_label="上传" if progress_enabled else None,
                                progress_enabled=progress_enabled, tty=tty)
    if expired("上传测速"):
        dovalid(node, imei, bandwidth, uuid=uuid)
        return result

    small = _run_with_progress("小包延迟/丢包", _MTR_PACKETS + 2,
                               lambda: small_packet_probe(node), progress_enabled, tty)
    if expired("小包探测"):
        dovalid(node, imei, bandwidth, uuid=uuid)
        return result

    large = _run_with_progress("大包延迟/丢包", _MTR_PACKETS + 2,
                               lambda: large_packet_probe(node), progress_enabled, tty)
    if expired("大包探测"):
        dovalid(node, imei, bandwidth, uuid=uuid)
        return result

    dovalid(node, imei, bandwidth, uuid=uuid)

    server_log = down_log + up_log
    if (down == 0.0 or up == 0.0) and server_log:
        err_detail = " | ".join(sorted(set(server_log)))[:300]
        result.update({"ok": False, "error": "测速失败: %s" % err_detail,
                       "server_log": err_detail})
        return result
    elif down == 0.0 and up == 0.0:
        result.update({"ok": False, "error": "测速无数据返回 (上下行速率均为0)"})
        return result

    result.update({
        "ok": True, "uuid": uuid, "imei": imei,
        "small_latency_ms": small.get("latency_ms"),
        "small_jitter_ms": small.get("jitter_ms"),
        "small_loss_pct": small.get("loss_pct"),
        "large_latency_ms": large.get("latency_ms"),
        "large_loss_pct": large.get("loss_pct"),
        "download_mbps": round(down, 2),
        "upload_mbps": round(up, 2),
    })
    return result

def choose_index(prompt, count):
    while True:
        try:
            v = input(prompt).strip()
        except EOFError:
            return None
        if v == "":
            return None
        if v.isdigit() and 1 <= int(v) <= count:
            return int(v) - 1
        print("输入无效，请输入 1-%d 之间的编号。" % count)

def print_summary(province, city, results):
    widths = (6, 19, 10, 10)
    n_cols = len(widths)
    top = _c("┌" + "┬".join("─" * (w + 2) for w in widths) + "┐", _DIM)
    mid = _c("├" + "┼".join("─" * (w + 2) for w in widths) + "┤", _DIM)
    bot = _c("└" + "┴".join("─" * (w + 2) for w in widths) + "┘", _DIM)

    def trow(cells):
        parts = []
        for (txt, align), w in zip(cells, widths):
            parts.append(_pad(txt, w, align))
        return "│ " + " │ ".join(parts) + " │"

    def probe_line(label, lat_txt, loss_txt):
        cell = "%s %s/%s" % (_c(label, _DIM), lat_txt, loss_txt)
        return trow([("", "c"), (cell, "c"), ("", "c"), ("", "c")])

    title = _c("%s - %s 全运营商测速汇总" % (province, city), _CYAN + _BOLD)
    inner = _TABLE_WIDTH - 2
    tw = _disp_width(title)
    pad_l = max(0, (inner - tw) // 2)
    print("")
    print(_c("┌" + "─" * inner + "┐", _DIM))
    print("│ " + " " * pad_l + title + " " * (inner - tw - pad_l) + " │")
    print(_c("└" + "─" * inner + "┘", _DIM))

    print(top)
    head = trow([("运营商", "c"), ("节点", "c"), ("下载", "c"), ("上传", "c")])
    print(_c(head, _BOLD))
    print(mid)

    for i, r in enumerate(results):
        if i > 0:
            print(mid)
        op = r["node"].get("o", "?")
        name = r["node"].get("name", "")
        if not r["ok"]:
            span = widths[2] + 3 + widths[3]
            err = _pad(str(r.get("error", "失败")), span)
            print("│ " + _pad(_c(op, _CYAN), widths[0], "c") + " │ " + _pad(name, widths[1], "c")
                  + " │ " + _c(err, _RED) + " │")
            continue
        d_txt = ("%.1fMbps" % r["download_mbps"]) if r.get("download_mbps") else _c("-", _DIM)
        u_txt = ("%.1fMbps" % r["upload_mbps"]) if r.get("upload_mbps") else _c("-", _DIM)
        print(trow([(_c(op, _CYAN), "c"), (name, "c"),
                    (_c(d_txt, _GREEN), "c"), (_c(u_txt, _GREEN), "c")]))
        sm = r.get("small_latency_ms")
        sl = r.get("small_loss_pct")
        lg = r.get("large_latency_ms")
        ll = r.get("large_loss_pct")
        sm_txt = ("%.1fms" % sm) if sm is not None else _c("-", _DIM)
        sl_txt = ("%.1f%%" % sl) if sl is not None else _c("-", _DIM)
        lg_txt = ("%.1fms" % lg) if lg is not None else _c("-", _DIM)
        ll_txt = ("%.1f%%" % ll) if ll is not None else _c("-", _DIM)
        print(probe_line("小包", sm_txt, sl_txt))
        print(probe_line("大包", lg_txt, ll_txt))
    print(bot)

SANDBOX_MARK = "/etc/speedtaier-sandbox"

def _re_exec_in_sandbox():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    runner = os.path.join(script_dir, "run_sandbox.sh")
    if not os.path.exists(runner):
        try:
            tmp = tempfile.mkdtemp(prefix="speedtaier_")
            runner = os.path.join(tmp, "run_sandbox.sh")
            data = http_get("https://raw.githubusercontent.com/transflo/speedtaier/main/run_sandbox.sh",
                            timeout=20)
            with open(runner, "w", encoding="utf-8") as f:
                f.write(data)
            os.chmod(runner, 0o755)
        except Exception:
            print("[!] 未找到 run_sandbox.sh，且从 GitHub 拉取失败，无法自动加载沙箱。")
            print("[!] 请确保 run_sandbox.sh 与 globalspeed_test.py 位于同一目录后重试。")
            sys.exit(1)
    if os.path.exists(os.path.join(script_dir, "run_sandbox.sh")) and "--local" not in sys.argv:
        cmd = ["bash", runner, "--local"] + sys.argv[1:]
    else:
        cmd = ["bash", runner] + sys.argv[1:]
    print("[*] 不在沙箱内，自动加载 BenchOS 沙箱运行（测速结束自动删除沙箱）...")
    try:
        ret = subprocess.call(cmd)
    except KeyboardInterrupt:
        ret = 130
    sys.exit(ret)

def require_sandbox():
    if os.path.exists(SANDBOX_MARK):
        return
    try:
        if os.stat("/proc/1/root").st_ino != os.stat("/").st_ino:
            return
    except Exception:
        pass
    _re_exec_in_sandbox()

def main():
    ap = argparse.ArgumentParser(description="全球网测：交互选择省市，一键测速该市所有运营商（节点表来自 GitHub）")
    ap.add_argument("--core", action="store_true",
                    help="Core 模式：不加载沙箱、不做 GitHub 反代判断，仅本机执行核心测速/延迟/丢包")
    ap.add_argument("--province", default=None, help="省份（不指定则交互选择）")
    ap.add_argument("--city", default=None, help="城市（不指定则交互选择）")
    ap.add_argument("--operator", default=None, help="只测指定运营商")
    ap.add_argument("--imei", default=None, help="固定IMEI（15位）；不指定则每次测速自动生成虚假IMEI")
    ap.add_argument("--bandwidth", type=int, default=200, help="带宽参数 Mbps（默认200）")
    ap.add_argument("--seconds", type=int, default=4, help="每项测速时长秒（默认4）")
    ap.add_argument("--threads", type=int, default=8,
                    help="下载/上传并发连接数（默认8；--threads 1 为单线程测速）")
    ap.add_argument("--timeout", type=int, default=45,
                    help="单节点总超时秒数，卡住自动跳过切换下一节点（默认45）")
    ap.add_argument("--node", default=None, help="直接指定节点 IP:端口（如 218.2.122.246:65499）")
    ap.add_argument("--list", action="store_true", help="只列出匹配节点")
    ap.add_argument("--no-progress", action="store_true", help="关闭测速进度显示")
    ap.add_argument("--serverlist-url", default=None,
                    help="GitHub raw 节点表地址（也可用环境变量 SERVERLIST_URL）")
    ap.add_argument("--local", action="store_true",
                    help="本地优先：脚本同目录存在节点表（serverlist_decrypted.json 等）时自动采用本地文件，不拉 GitHub")
    args = ap.parse_args()

    if args.core:
        os.environ.pop("SPEEDTAIER_PROXY", None)
    else:
        require_sandbox()
    _ensure_nexttrace()

    progress_enabled = not args.no_progress
    try:
        tty = sys.stdout.isatty()
    except Exception:
        tty = False

    if args.node:
        parts = args.node.split(":")
        node = {"ip": parts[0], "port": parts[1] if len(parts) > 1 else "65499",
                "name": args.node, "p": "", "c": "", "o": "指定"}
        r = run_operator_test(node, args.imei, args.bandwidth, args.seconds, args.threads,
                              progress_enabled, tty, args.timeout)
        if r["ok"]:
            _divider("NextTrace 路由追踪: %s" % (r["node"].get("name") or r["node"]["ip"]))
            ok, err = run_nexttrace(r["node"]["ip"])
            if not ok:
                _warn("nexttrace 追踪失败: %s" % err)
        print_summary("指定", "节点", [r])
        return

    gh_url = args.serverlist_url
    if gh_url is None and args.local:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        for f in ("serverlist_decrypted.json", "serverlist.json", "nodes.json"):
            p = os.path.join(script_dir, f)
            if os.path.isfile(p):
                gh_url = p
                _info("--local 本地优先: 自动采用本地节点表 %s" % p)
                break
    gh_url = gh_url or os.environ.get("SERVERLIST_URL") or DEFAULT_SERVERLIST_URL
    try:
        nodes = fetch_nodes_from_github(gh_url)
    except Exception as e:
        print("[!] 节点表拉取失败: %s" % e)
        print("[!] 请检查 --serverlist-url / 环境变量 SERVERLIST_URL 是否正确。")
        sys.exit(1)
    _info("节点表来源: %s (%d 个节点)" % (gh_url, len(nodes)))

    province = args.province
    city = args.city
    if province is None:
        provinces = list_provinces(nodes)
        print("")
        print(_c("===== 选择省份 =====", _CYAN + _BOLD))
        for i, p in enumerate(provinces, 1):
            print("%3d) %s" % (i, p))
        idx = choose_index("请输入省份编号（回车退出）: ", len(provinces))
        if idx is None:
            return
        province = provinces[idx]

    if city is None:
        cities = list_cities(nodes, province)
        if not cities:
            print("[!] 该省份没有节点")
            return
        print("")
        print(_c("===== %s - 选择城市 =====" % province, _CYAN + _BOLD))
        for i, c in enumerate(cities, 1):
            print("%3d) %s" % (i, c))
        idx = choose_index("请输入城市编号（回车退出）: ", len(cities))
        if idx is None:
            return
        city = cities[idx]

    cand = pick_nodes(nodes, province, city, args.operator)
    if not cand:
        print("[!] 节点表中没有匹配 %s/%s%s 的节点" % (
            province, city, ("/" + args.operator) if args.operator else ""))
        return

    if args.list:
        for n in cand:
            print("%s:%s  %s  %s/%s/%s" % (n["ip"], n.get("port"), n.get("name", ""),
                                           n.get("p", ""), n.get("c", ""), n.get("o", "")))
        return

    order, groups = group_by_operator(cand)
    results = []
    print("")
    _info("%s/%s 共 %d 个节点，覆盖 %d 家运营商" % (province, city, len(cand), len(order)))
    for op in order:
        node = groups[op][0]
        print("")
        _divider("正在测试: %s %s (%s:%s)" % (op, node.get("name", ""), node["ip"], node.get("port")))
        r = run_operator_test(node, args.imei, args.bandwidth, args.seconds, args.threads,
                              progress_enabled, tty, args.timeout)
        results.append(r)
        if not r["ok"]:
            _warn("%s (%s) 失败/超时: %s，切换下一节点" % (op, node.get("name", ""), r.get("error", "未知")))
            if r.get("server_log"):
                _warn("  服务器返回日志: %s" % r["server_log"])
        if not r["ok"] and len(groups[op]) > 1:
            for alt in groups[op][1:]:
                print("")
                _divider("切换: %s %s (%s:%s)" % (op, alt.get("name", ""), alt["ip"], alt.get("port")))
                r2 = run_operator_test(alt, args.imei, args.bandwidth, args.seconds,
                                       args.threads, progress_enabled, tty, args.timeout)
                if r2["ok"]:
                    results[-1] = r2
                    break

    for r in results:
        if r["ok"]:
            _divider("NextTrace 路由追踪: %s" % (r["node"].get("name") or r["node"]["ip"]))
            ok, err = run_nexttrace(r["node"]["ip"])
            if not ok:
                _warn("nexttrace 追踪失败: %s" % err)

    print_summary(province, city, results)

if __name__ == "__main__":
    main()
