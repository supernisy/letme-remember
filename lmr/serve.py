"""常驻召回服务（mem.py serve）：模型只加载一次，检索毫秒级。

解决的问题：hook 每次提交消息都是全新进程，若走语义向量会冷启动加载
120MB 模型 + 联网验证，轻松超 100 秒，被宿主超时掐死。本服务把模型
常驻内存，客户端（hook）只需发一行 JSON 请求，毫秒级拿回召回结果。

设计约束：
- 零新依赖：只用标准库 socket / json / threading / time。
- 离线加载：HF_HUB_OFFLINE=1 / TRANSFORMERS_OFFLINE=1，避免联网验证
  拖慢启动（纯本地加载约 11 秒）。
- 故障隔离：服务挂掉或没起来，客户端降级为本地关键词，绝不拖累会话。
- 空闲自退：超过 IDLE_TIMEOUT 秒无请求自动退出，避免残留僵尸进程
  （即使 SessionEnd 没触发也能自愈）。
- 单实例：用端口锁 + PID 文件，重复拉起时静默跳过。

协议（TCP，127.0.0.1:7867，每行一个 JSON，换行分隔）：
  请求  {"op":"recall","query":"...","limit":N}
  响应  {"ok":true,"results":[...]}  或  {"ok":false,"error":"..."}
  关闭  {"op":"shutdown"}
"""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time

HOST = "127.0.0.1"
PORT = 7867
# 无请求多少秒后自动退出（默认 30 分钟）。
IDLE_TIMEOUT = float(os.environ.get("LMR_SERVE_IDLE_TIMEOUT", "1800"))


def _offline_env():
    """返回禁联网的环境变量副本，避免加载模型时联网验证拖慢启动。"""
    env = dict(os.environ)
    env["HF_HUB_OFFLINE"] = "1"
    env["TRANSFORMERS_OFFLINE"] = "1"
    return env


def _load_engine():
    """加载引擎与模型（离线）。返回 (index.Index, paths, settings)。"""
    # 最关键的一步：在 import 任何会加载模型的模块之前，先把联网关掉。
    # 否则 sentence-transformers 会联网验证模型版本，SSL 重试把启动拖到 100 秒。
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"

    from . import config
    from . import index as index_module

    data_dir = config.resolve_data_dir()
    settings = config.settings_for(data_dir)
    paths = config.Paths(data_dir)
    eng = index_module.Index(paths, settings)
    # 预热：确保语义模型加载到位（离线，约 11 秒），后续 recall 秒回。
    from . import embedding as _emb
    _emb._load()
    return eng, paths, settings


def _recall_json(eng, paths, settings, query, limit):
    """执行召回，返回可 JSON 序列化的结果列表。"""
    limit = int(limit or 10)
    hits = eng.recall(query, limit=limit)
    out = []
    for h in hits:
        out.append({
            "id": h["id"],
            "abstract": h["abstract"],
            "type": h["type"],
            "score": h["score"],
            "semantic": h["semantic"],
        })
    return out


def _handle(conn, eng, paths, settings):
    """处理单个连接的一行请求。"""
    try:
        conn.settimeout(30)
        raw = b""
        while b"\n" not in raw:
            chunk = conn.recv(4096)
            if not chunk:
                return
            raw += chunk
        line = raw.split(b"\n", 1)[0].decode("utf-8", "ignore").strip()
        req = json.loads(line)
        op = req.get("op", "")
        if op == "shutdown":
            _send(conn, {"ok": True, "shutdown": True})
            return "shutdown"
        if op == "recall":
            query = req.get("query", "")
            limit = req.get("limit", 10)
            results = _recall_json(eng, paths, settings, query, limit)
            _send(conn, {"ok": True, "results": results})
            return
        if op == "ping":
            _send(conn, {"ok": True, "pong": True})
            return
        _send(conn, {"ok": False, "error": "unknown op: %s" % op})
    except Exception as e:  # noqa: BLE001
        try:
            _send(conn, {"ok": False, "error": str(e)})
        except Exception:  # noqa: BLE001
            pass


def _send(conn, obj):
    conn.sendall((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))


def serve_forever():
    """主循环：监听端口，串行处理请求，空闲超时自退。"""
    # 端口锁：已有实例在跑则静默退出（重复拉起不报错、不冲突）。
    if _already_running():
        print("[serve] 已有实例在运行，跳过", file=sys.stderr)
        return 0

    print("[serve] 离线加载向量模型（约 11 秒）...", file=sys.stderr)
    t0 = time.time()
    eng, paths, settings = _load_engine()
    print("[serve] 模型就绪，耗时 %.1f 秒，监听 %s:%d" % (time.time() - t0, HOST, PORT),
          file=sys.stderr)

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(5)
    srv.settimeout(2.0)

    last_active = time.time()
    shutdown = False
    try:
        while not shutdown:
            try:
                conn, _addr = srv.accept()
            except socket.timeout:
                # 空闲自退：长时间无请求则退出，避免残留僵尸进程。
                if time.time() - last_active > IDLE_TIMEOUT:
                    print("[serve] 空闲超时，自动退出", file=sys.stderr)
                    break
                continue
            last_active = time.time()
            try:
                result = _handle(conn, eng, paths, settings)
                if result == "shutdown":
                    shutdown = True
            finally:
                conn.close()
    finally:
        srv.close()
        print("[serve] 服务已退出", file=sys.stderr)
    return 0


def _already_running():
    """检测端口是否已被占用（说明已有实例在跑）。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        return s.connect_ex((HOST, PORT)) == 0
    finally:
        s.close()


def client_recall(query, limit=10, timeout=2.0):
    """客户端：向常驻服务发召回请求；服务不可用/超时抛异常（调用方降级）。

    供 hook 与 CLI 复用：优先走常驻服务（毫秒级、带语义），
    失败则由调用方降级为本地纯关键词召回。
    """
    if not query:
        return None
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((HOST, PORT))
        s.sendall((json.dumps({"op": "recall", "query": query, "limit": limit})
                   + "\n").encode("utf-8"))
        raw = b""
        while b"\n" not in raw:
            chunk = s.recv(4096)
            if not chunk:
                break
            raw += chunk
        resp = json.loads(raw.decode("utf-8", "ignore"))
        return resp
    except Exception:  # noqa: BLE001
        return None
    finally:
        s.close()


def client_shutdown(timeout=1.0):
    """客户端：请求常驻服务退出（SessionEnd 时调用）。失败静默。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((HOST, PORT))
        s.sendall(b'{"op":"shutdown"}\n')
        s.close()
    except Exception:  # noqa: BLE001
        pass
