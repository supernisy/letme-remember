"""letme-remember 只读 GUI 后端（零新依赖，标准库 http.server）。

设计约束（对齐 serve.py 的既有哲学）：
- 当前阶段只读：所有 API 只查询，绝不写 store / index / audit。写/编辑操作是后续明确要做的，路由与口子已预留（见下方「写操作预留」注释），不是永久只读。
- 零新依赖：只用标准库 http.server / json / sqlite3 / urllib。
- 复用 lmr：config.Paths 定位数据、frontmatter 解析、index.Index 读索引。
- 可重建：全部数据来自 SQLite 索引与 store 文件，服务本身无状态。

启动：python mem.py gui [--port 8787] [--host 127.0.0.1]
前端：gui/dist/（Vite + Vue3 构建产物，先 `cd gui && pnpm build`）；无 dist 时回退 gui-demo/ 旧单文件。

API：
  GET /api/overview      总览统计（类型分布、健康四维、来源分布、数据状态）
  GET /api/memories?q=&type=&sup=&limit=&offset=   记忆列表（搜索/过滤/分页）
  GET /api/memory/{id}   单条记忆详情（完整 frontmatter + 正文）
  GET /api/status        服务状态（向量库/embedding/serve/开关占位）
  GET /api/audit         审计日志（最近 N 条）
  GET /api/health        问题记忆诊断（逐条健康指标）
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse, unquote

from . import config, frontmatter, schema

HOST = "127.0.0.1"
PORT = 8787


# ---------------------------------------------------------------------------
# 数据读取（全部只读）
# ---------------------------------------------------------------------------

def _data_dir():
    return config.resolve_data_dir()


def _paths():
    return config.Paths(_data_dir())


def _connect(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _index_exists(paths):
    return paths.db.is_file()


def _read_memories():
    """读索引里全部记忆（不含已归档），返回 dict 列表。"""
    paths = _paths()
    if not _index_exists(paths):
        return []
    conn = _connect(paths.db)
    try:
        rows = conn.execute(
            "SELECT id, name, abstract, type, boost, created, updated, "
            "valid_from, invalid_at, superseded_by, author, provenance "
            "FROM memories WHERE archived=0"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _count_by(field):
    memories = _read_memories()
    out = {}
    for m in memories:
        key = m.get(field) or "(空)"
        out[key] = out.get(key, 0) + 1
    return out


def _vec_stats(paths):
    """向量库状态：是否启用、模型名、已向量化条数。"""
    if not _index_exists(paths):
        return {"enabled": False, "note": "索引不存在"}
    conn = _connect(paths.db)
    try:
        vec_count = conn.execute("SELECT COUNT(*) AS c FROM vec").fetchone()["c"]
        dim = conn.execute("SELECT MAX(dim) AS d FROM vec").fetchone()["d"]
    finally:
        conn.close()
    return {"indexed": vec_count, "dim": dim}


def _embedding_status():
    """语义检索是否可用（依赖 + 模型 + 开关），尽量不真加载模型以免慢。"""
    from . import embedding as _emb
    enabled = os.environ.get(config.ENV_DISABLE_EMBEDDING) != "1"
    settings = config.settings_for(_data_dir())
    if not settings.get("embedding_enabled", True):
        enabled = False
    model = settings.get("embedding_model", "")
    return {"enabled": enabled, "model": model}


def _access_stats():
    """读访问日志（access 表），供健康页「检索效用」维度。"""
    from . import index as index_module
    paths = _paths()
    if not _index_exists(paths):
        return []
    idx = index_module.Index(paths, config.settings_for(_data_dir()))
    try:
        return idx.access_stats()
    except Exception:
        return []


def _serve_status():
    """常驻召回服务三态：running / idle（空闲自退，正常）/ error（异常）。"""
    import socket
    from . import serve as serve_module
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        running = s.connect_ex(("127.0.0.1", 7867)) == 0
    finally:
        s.close()
    if running:
        return "running"
    # 端口连不上：看状态文件区分「空闲自退/正常关闭」vs「异常（从未启动或崩溃）」
    state = serve_module.serve_state()
    if state in ("idle-exit", "shutdown"):
        return "idle"
    return "error"


def _audit_recent(paths, n=50):
    """最近 n 条审计日志（只读，倒序）。"""
    if not paths.audit.is_file():
        return []
    lines = paths.audit.read_text(encoding="utf-8", errors="ignore").strip().split("\n")
    lines = [ln for ln in lines if ln.strip()]
    out = []
    for ln in reversed(lines[-n:]):
        parts = ln.split("\t")
        if len(parts) >= 4:
            out.append({"ts": parts[0], "action": parts[1], "id": parts[2], "rules": parts[3]})
    return out


# ---------------------------------------------------------------------------
# 聚合接口
# ---------------------------------------------------------------------------

def _overview():
    memories = _read_memories()
    total = len(memories)
    type_count = {"semantic": 0, "episodic": 0, "procedural": 0}
    superseded = 0
    has_links = 0
    has_boost = 0
    authors = {}
    for m in memories:
        t = m.get("type")
        if t in type_count:
            type_count[t] += 1
        if m.get("superseded_by"):
            superseded += 1
        if m.get("provenance"):
            has_links += 1
        if m.get("boost"):
            has_boost += 1
        a = m.get("author") or "(空)"
        authors[a] = authors.get(a, 0) + 1
    author_list = sorted(authors.items(), key=lambda kv: -kv[1])
    # 健康四维（能真算的算真值；访问热度来自 access 表）
    paths = _paths()
    vec = _vec_stats(paths)
    embed = _embedding_status()
    serve = _serve_status()
    access = _access_stats()
    health = _health_dimensions(memories, vec, access)
    return {
        "total": total,
        "type_count": type_count,
        "superseded": superseded,
        "has_provenance": has_links,
        "has_boost": has_boost,
        "files": _count_files(paths),
        "authors": [{"name": k, "n": v} for k, v in author_list],
        "vector": vec,
        "embedding": embed,
        "serve_state": serve,
        "health": health,
    }


def _count_files(paths):
    store = len(list(paths.store.glob("*.md"))) if paths.store.is_dir() else 0
    archive = len(list(paths.archive.glob("*.md"))) if paths.archive.is_dir() else 0
    return {"store": store, "archive": archive}


def _health_dimensions(memories, vec, access):
    """健康四维（能真算的算真值，缺数据源的标注）。

    - freshness：valid_from 距今超过新鲜期（recency_half_life_days）的比例
    - uniqueness：无（去重未落地），返回占位
    - consistency：有 superseded 的条数（隐性矛盾检测未做）
    - utility：被召回过的记忆占比（access 表有记录的）
    """
    settings = config.settings_for(_data_dir())
    half_life = float(settings.get("recency_half_life_days", 90.0))
    today = date.today()
    stale = 0
    total = len(memories) or 1
    for m in memories:
        vf = m.get("valid_from")
        if vf:
            try:
                d = datetime.fromisoformat(str(vf).replace("Z", "+00:00")).date()
                if (today - d).days > half_life:
                    stale += 1
            except ValueError:
                pass
    stale_pct = round(stale / total * 100)
    freshness = 100 - stale_pct
    superseded = sum(1 for m in memories if m.get("superseded_by"))
    consistency = 100 if total == 1 else round(100 - superseded / total * 100)
    # utility：被召回过的记忆占比。access 表为空时说明「还没被召回过」，
    # 不是「无法计算」——是诚实的 0（或 None 表示还没埋点数据）。
    accessed = len(access)
    if accessed == 0 and not any(m for m in memories):
        utility = None
        util_note = "无记忆"
    else:
        # 访问记录是按召回命中的条目累计的；这里给出「有访问记录的记忆数」。
        utility = round(accessed / total * 100) if total > 1 else None
        util_note = "被召回过的记忆 %d / %d 条" % (accessed, len(memories))
    return {
        "freshness": {"score": freshness, "stale": stale, "total": len(memories)},
        "uniqueness": {"score": None, "note": "去重/合并未落地，无法计算"},
        "consistency": {"score": consistency, "superseded": superseded},
        "utility": {"score": utility, "note": util_note, "accessed": accessed},
    }


def _health_issues():
    """问题记忆诊断：找出新鲜度过期、被取代、来源缺失的条目。

    每条附三根真实诊断指标：
    - access：访问次数 + 最近召回时间（access 表）
    - stale：valid_from 距今天数（是否过新鲜期）
    - provenance：来源链是否完整
    """
    memories = _read_memories()
    settings = config.settings_for(_data_dir())
    half_life = float(settings.get("recency_half_life_days", 90.0))
    today = date.today()
    # 读 access 表，建 id -> {count, last_at} 映射
    from . import index as index_module
    paths = _paths()
    access_map = {}
    try:
        if _index_exists(paths):
            idx = index_module.Index(paths, settings)
            for a in idx.access_stats():
                access_map[a.get("id")] = a
    except Exception:
        pass
    issues = []
    for m in memories:
        flags = []
        if m.get("superseded_by"):
            flags.append("conflict")
        stale_days = None
        if m.get("valid_from"):
            try:
                d = datetime.fromisoformat(str(m["valid_from"]).replace("Z", "+00:00")).date()
                stale_days = (today - d).days
                if stale_days > half_life:
                    flags.append("stale")
            except ValueError:
                pass
        if not m.get("provenance"):
            flags.append("nosrc")
        if flags:
            acc = access_map.get(m["id"], {"count": 0, "last_at": ""})
            issues.append({
                "id": m["id"], "name": m.get("name") or m["id"],
                "type": m.get("type"), "abstract": m.get("abstract"),
                "flags": flags,
                "access_count": acc.get("count", 0),
                "last_accessed": acc.get("last_at", ""),
                "stale_days": stale_days,
                "has_provenance": bool(m.get("provenance")),
            })
    order = {"conflict": 0, "stale": 1, "nosrc": 2}
    issues.sort(key=lambda x: min(order.get(f, 9) for f in x["flags"]))
    return issues


def _memories(params):
    memories = _read_memories()
    q = (params.get("q", [""])[0] or "").strip().lower()
    type_filter = (params.get("type", [""])[0] or "").strip()
    sup = (params.get("sup", ["0"])[0] or "0") == "1"
    if type_filter:
        memories = [m for m in memories if m.get("type") == type_filter]
    if sup:
        memories = [m for m in memories if m.get("superseded_by")]
    if q:
        memories = [m for m in memories
                    if q in (m.get("name") or "").lower()
                    or q in (m.get("abstract") or "").lower()]
    memories.sort(key=lambda m: (m.get("updated") or ""), reverse=True)
    limit = int(params.get("limit", ["50"])[0] or 50)
    offset = int(params.get("offset", ["0"])[0] or 0)
    page = memories[offset:offset + limit]
    return {"total": len(memories), "items": page}


def _memory_detail(entry_id):
    paths = _paths()
    for directory in (paths.store, paths.archive):
        path = directory / (entry_id + ".md")
        if path.is_file():
            meta, body = frontmatter.read_file(path)
            sections = frontmatter.body_sections(body)
            # 附带访问统计（access 表）
            from . import index as index_module
            access = {"count": 0, "last_at": ""}
            try:
                idx = index_module.Index(paths, config.settings_for(_data_dir()))
                access = idx.access_stats(entry_id)
            except Exception:
                pass
            return {"id": entry_id, "meta": meta,
                    "conclusion": sections.get("结论", ""),
                    "reason": sections.get("理由", ""),
                    "access": access,
                    "path": str(path)}
    return None


# ---------------------------------------------------------------------------
# HTTP 处理
# ---------------------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):
    server_version = "lmr-gui/0.1"

    def _send(self, obj, status=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            params = parse_qs(parsed.query)
            if path == "/api/overview":
                self._send(_overview())
            elif path == "/api/memories":
                self._send(_memories(params))
            elif path == "/api/health":
                self._send({"issues": _health_issues()})
            elif path == "/api/status":
                paths = _paths()
                self._send({
                    "serve_state": _serve_status(),
                    "embedding": _embedding_status(),
                    "vector": _vec_stats(paths),
                    "data_dir": str(_data_dir()),
                    "files": _count_files(paths),
                })
            elif path == "/api/audit":
                n = int(params.get("n", ["50"])[0] or 50)
                self._send({"items": _audit_recent(_paths(), n)})
            elif path.startswith("/api/memory/"):
                entry_id = path[len("/api/memory/"):]
                detail = _memory_detail(entry_id)
                if detail is None:
                    self._send({"error": "not found"}, 404)
                else:
                    self._send(detail)
            elif path in ("/", "/index.html"):
                self._serve_html()
            elif path.startswith("/assets/"):
                self._serve_static(path)
            else:
                self._send({"error": "unknown path"}, 404)
        except Exception as e:  # noqa: BLE001
            self._send({"error": str(e)}, 500)

    # 前端静态文件：优先 dist/（Vite 构建产物），无 dist 时回退 gui-demo/（旧单文件）。
    def _frontend_root(self):
        root = Path(__file__).resolve().parent.parent / "gui"
        dist = root / "dist"
        if dist.is_dir():
            return dist
        return root.parent / "gui-demo"

    def _serve_html(self):
        html_path = self._frontend_root() / "index.html"
        if not html_path.is_file():
            self._send({"error": "前端 index.html 未找到（请先在 gui/ 执行 pnpm build）"}, 404)
            return
        data = html_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_static(self, path):
        # 只允许 /assets/ 下的静态资源，防目录穿越。
        rel = path.lstrip("/")
        if ".." in rel:
            self._send({"error": "bad path"}, 400)
            return
        asset_path = self._frontend_root() / rel
        if not asset_path.is_file():
            self._send({"error": "asset not found"}, 404)
            return
        data = asset_path.read_bytes()
        ctype = "text/css" if asset_path.suffix == ".css" else "application/javascript"
        if asset_path.suffix == ".svg":
            ctype = "image/svg+xml"
        self.send_response(200)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        pass


def serve_gui(host=HOST, port=PORT):
    print("[gui] 只读服务启动，数据目录: %s" % _data_dir(), file=sys.stderr)
    print("[gui] 打开 http://%s:%d" % (host, port), file=sys.stderr)
    server = HTTPServer((host, port), _Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
