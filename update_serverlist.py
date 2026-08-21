#!/usr/bin/env python3
import json
import os
import ssl
import sys
import urllib.parse
import urllib.request

CONFIG_URL = "https://dlcv2.cnspeedtest.cn:8443"
CONFIG_PHP = CONFIG_URL + "/TaierAndroid/Config/ConfigMD5.php"
APP = "globalspeed"

_IP = [58,50,42,34,26,18,10,2,60,52,44,36,28,20,12,4,62,54,46,38,30,22,14,6,64,56,48,40,32,24,16,8,
       57,49,41,33,25,17,9,1,59,51,43,35,27,19,11,3,61,53,45,37,29,21,13,5,63,55,47,39,31,23,15,7]
_FP = [40,8,48,16,56,24,64,32,39,7,47,15,55,23,63,31,38,6,46,14,54,22,62,30,37,5,45,13,53,21,61,29,
       36,4,44,12,52,20,60,28,35,3,43,11,51,19,59,27,34,2,42,10,50,18,58,26,33,1,41,9,49,17,57,25]
_E = [32,1,2,3,4,5,4,5,6,7,8,9,8,9,10,11,12,13,12,13,14,15,16,17,16,17,18,19,20,21,20,21,
      22,23,24,25,24,25,26,27,28,29,28,29,30,31,32,1]
_P = [16,7,20,21,29,12,28,17,1,15,23,26,5,18,31,10,2,8,24,14,32,27,3,9,19,13,30,6,22,11,4,25]
_S = [
 [14,4,13,1,2,15,11,8,3,10,6,12,5,9,0,7,0,15,7,4,14,2,13,1,10,6,12,11,9,5,3,8,
  4,1,14,8,13,6,2,11,15,12,9,7,3,10,5,0,15,12,8,2,4,9,1,7,5,11,3,14,10,0,6,13],
 [15,1,8,14,6,11,3,4,9,7,2,13,12,0,5,10,3,13,4,7,15,2,8,14,12,0,1,10,6,9,11,5,
  0,14,7,11,10,4,13,1,5,8,12,6,9,3,2,15,13,8,10,1,3,15,4,2,11,6,7,12,0,5,14,9],
 [10,0,9,14,6,3,15,5,1,13,12,7,11,4,2,8,13,7,0,9,3,4,6,10,2,8,5,14,12,11,15,1,
  13,6,4,9,8,15,3,0,11,1,2,12,5,10,14,7,1,10,13,0,6,9,8,7,4,15,14,3,11,5,2,12],
 [7,13,14,3,0,6,9,10,1,2,8,5,11,12,4,15,13,8,11,5,6,15,0,3,4,7,2,12,1,10,14,9,
  10,6,9,0,12,11,7,13,15,1,3,14,5,2,8,4,3,15,0,6,10,1,13,8,9,4,5,11,12,7,2,14],
 [2,12,4,1,7,10,11,6,8,5,3,15,13,0,14,9,14,11,2,12,4,7,13,1,5,0,15,10,3,9,8,6,
  4,2,1,11,10,13,7,8,15,9,12,5,6,3,0,14,11,8,12,7,1,14,2,13,6,15,0,9,10,4,5,3],
 [12,1,10,15,9,2,6,8,0,13,3,4,14,7,5,11,10,15,4,2,7,12,9,5,6,1,13,14,0,11,3,8,
  9,14,15,5,2,8,12,3,7,0,4,10,1,13,11,6,4,3,2,12,9,5,15,10,11,14,1,7,6,0,8,13],
 [4,11,2,14,15,0,8,13,3,12,9,7,5,10,6,1,13,0,11,7,4,9,1,10,14,3,5,12,2,15,8,6,
  1,4,11,13,12,3,7,14,10,15,6,8,0,5,9,2,6,11,13,8,1,4,10,7,9,5,0,15,14,2,3,12],
 [13,2,8,4,6,15,11,1,10,9,3,14,5,0,12,7,1,15,13,8,10,3,7,4,12,5,6,11,0,14,9,2,
  7,11,4,1,9,12,14,2,0,6,10,13,15,3,5,8,2,1,14,7,4,10,8,13,15,12,9,0,3,5,6,11],
]
_PC1 = [57,49,41,33,25,17,9,1,58,50,42,34,26,18,10,2,59,51,43,35,27,19,11,3,60,52,44,36,
        63,55,47,39,31,23,15,7,62,54,46,38,30,22,14,6,61,53,45,37,29,21,13,5,28,20,12,4]
_PC2 = [14,17,11,24,1,5,3,28,15,6,21,10,23,19,12,4,26,8,16,7,27,20,13,2,
        41,52,31,37,47,55,30,40,51,45,33,48,44,49,39,56,34,53,46,42,50,36,29,32]
_SHIFTS = [1,1,2,2,2,2,2,2,1,2,2,2,2,2,2,1]

def _permute(bits, table):
    return [bits[i - 1] for i in table]

def _str_to_bits(s):
    return [(s[i // 8] >> (7 - i % 8)) & 1 for i in range(len(s) * 8)]

def _bits_to_int(bits):
    v = 0
    for b in bits:
        v = (v << 1) | b
    return v

def _key_schedule(keybytes):
    k = _permute(_str_to_bits(keybytes)[:64], _PC1)
    c, d = k[:28], k[28:]
    subkeys = []
    for shift in _SHIFTS:
        c = c[shift:] + c[:shift]
        d = d[shift:] + d[:shift]
        subkeys.append(_permute(c + d, _PC2))
    return subkeys

def _feistel(r32, subkey):
    x = [a ^ b for a, b in zip(_permute(r32, _E), subkey)]
    out = []
    for i in range(8):
        block = x[i * 6:(i + 1) * 6]
        row = (block[0] << 1) | block[5]
        col = _bits_to_int(block[1:5])
        val = _S[i][row * 16 + col]
        out.extend([(val >> 3) & 1, (val >> 2) & 1, (val >> 1) & 1, val & 1])
    return _permute(out, _P)

def _des_block_decrypt(block64, subkeys):
    ip = _permute(_str_to_bits(block64), _IP)
    l, r = ip[:32], ip[32:]
    for k in reversed(subkeys):
        new_r = [a ^ b for a, b in zip(l, _feistel(r, k))]
        l, r = r, new_r
    fp = _permute(r + l, _FP)
    out = bytearray(8)
    for i in range(64):
        if fp[i]:
            out[i // 8] |= 1 << (7 - i % 8)
    return bytes(out)

def des_ecb_decrypt(data, key):
    subkeys = _key_schedule(key)
    out = bytearray()
    for i in range(0, len(data) - 7, 8):
        out += _des_block_decrypt(data[i:i + 8], subkeys)
    return bytes(out)

def unpad_pkcs5(data):
    if not data:
        return data
    pad = data[-1]
    if 1 <= pad <= 8:
        return data[:-pad]
    return data

def _ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

def http_get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx()) as r:
        return r.read().decode("utf-8", "replace")

def fetch_fresh_nodes(des_key):
    q = urllib.parse.urlencode({"province": "北京", "city": "北京", "imei": "863096060000001",
                                "appname": APP, "vercode": "40408", "type": "globalspeed", "ipv6": "0"})
    cfg = json.loads(http_get(CONFIG_PHP + "?" + q))
    url = None
    for e in cfg:
        if e.get("name") == "serverlist_encrypt_url":
            url = e.get("filename")
    if not url:
        raise RuntimeError("ConfigMD5 响应中没有 serverlist_encrypt_url")
    enc = http_get(url).strip()
    pt = unpad_pkcs5(des_ecb_decrypt(bytes.fromhex(enc), des_key.encode())).decode("utf-8")
    nodes = json.loads(pt)
    out = []
    for n in nodes:
        out.append({
            "ip": n.get("hostip"), "port": n.get("port", "65499"), "name": n.get("hostname", ""),
            "p": n.get("pname", ""), "c": n.get("location", ""), "o": n.get("oper", ""),
        })
    return out

def main():
    des_key = os.environ.get("SERVERLIST_DES_KEY", "").strip()
    if not des_key:
        print("错误: 未设置环境变量 SERVERLIST_DES_KEY（DES 解密密钥）", file=sys.stderr)
        print("请在 GitHub 仓库 Settings -> Secrets and variables -> Actions 添加该 Secret，", file=sys.stderr)
        print("或在本地执行: SERVERLIST_DES_KEY='...' python3 update_serverlist.py", file=sys.stderr)
        sys.exit(1)
    nodes = fetch_fresh_nodes(des_key)
    with open("serverlist_decrypted.json", "w", encoding="utf-8") as f:
        json.dump(nodes, f, ensure_ascii=False, separators=(",", ":"))
    print("saved %d nodes -> serverlist_decrypted.json" % len(nodes))

if __name__ == "__main__":
    main()
