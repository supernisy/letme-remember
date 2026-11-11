"""可重建的 SQLite 索引与中文检索（design D6 / D10）。

真相源是 Markdown 文件；这里的库只是缓存，删掉整个 .index/ 也不丢知识。
读路径只用标准库与本地分词词典：零大模型调用、零网络依赖。
"""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
from datetime import date, datetime
from pathlib import Path

from . import frontmatter, schema, tokenizer
from .errors import InternalError

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS meta (
  k TEXT PRIMARY KEY,
  v TEXT
);
CREATE TABLE IF NOT EXISTS memories (
  id TEXT PRIMARY KEY,
  path TEXT NOT NULL,
  hash TEXT NOT NULL,
  name TEXT, abstract TEXT, type TEXT, weight REAL,
  created TEXT, updated TEXT, valid_from TEXT, invalid_at TEXT,
  superseded_by TEXT, author TEXT, provenance TEXT,
  body TEXT, seg TEXT, archived INTEGER DEFAULT 0
);
CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(
  id UNINDEXED, seg, abstract, body, tokenize='unicode61'
);
"""


def _hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _as_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        return None


class Index:
    def __init__(self, paths, settings):
        self.paths = paths
        self.settings = settings

    def _connect(self):
        self.paths.index.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.paths.db))
        conn.row_factory = sqlite3.Row
        conn.executescript(SCHEMA_SQL)
        return conn

    def _meta(self, conn, key):
        row = conn.execute("SELECT v FROM meta WHERE k=?", (key,)).fetchone()
        return row["v"] if row else None

    def _set_meta(self, conn, key, value):
        conn.execute("INSERT OR REPLACE INTO meta(k, v) VALUES (?, ?)", (key, str(value)))

    def _fts_replace(self, conn, rowid, entry_id, seg, abstract, body):
        conn.execute("DELETE FROM fts WHERE rowid=?", (rowid,))
        conn.execute(
            "INSERT INTO fts(rowid, id, seg, abstract, body) VALUES (?, ?, ?, ?, ?)",
            (rowid, entry_id, seg, abstract, body),
        )

    def sync(self, force=False):
        """按内容哈希增量同步；分词器版本变化时自动全量重建。"""
        version = tokenizer.tokenizer_version()
        conn = self._connect()
        stats = {"added": 0, "updated": 0, "skipped": 0, "removed": 0}
        try:
            if force or self._meta(conn, "tokenizer_version") != version:
                conn.execute("DELETE FROM fts")
                conn.execute("DELETE FROM memories")
                force = True
            seen = set()
            for path in self.paths.memory_files():
                content = path.read_text(encoding="utf-8")
                digest = _hash(content)
                entry_id = schema.entry_id(path.name)
                seen.add(entry_id)
                existing = conn.execute(
                    "SELECT rowid, hash FROM memories WHERE id=?", (entry_id,)
                ).fetchone()
                if not force and existing and existing["hash"] == digest:
                    stats["skipped"] += 1
                    continue
                meta, body = frontmatter.parse(content)
                seg = tokenizer.segment(" ".join([meta["name"], meta["abstract"], body]))
                values = (
                    entry_id, str(path), digest, meta["name"], meta["abstract"], meta["type"],
                    float(meta["weight"] or 1.0), meta["created"], meta["updated"],
                    meta["valid_from"], meta["invalid_at"], meta["superseded_by"],
                    meta["author"], "|".join(meta["provenance"]), body, seg,
                    1 if path.parent == self.paths.archive else 0,
                )
                if existing:
                    rowid = existing["rowid"]
                    conn.execute(
                        "UPDATE memories SET path=?, hash=?, name=?, abstract=?, type=?, weight=?, "
                        "created=?, updated=?, valid_from=?, invalid_at=?, superseded_by=?, "
                        "author=?, provenance=?, body=?, seg=?, archived=? WHERE rowid=?",
                        values[1:] + (rowid,),
                    )
                    stats["updated"] += 1
                else:
                    cursor = conn.execute(
                        "INSERT INTO memories(id, path, hash, name, abstract, type, weight, "
                        "created, updated, valid_from, invalid_at, superseded_by, author, "
                        "provenance, body, seg, archived) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        values,
                    )
                    rowid = cursor.lastrowid
                    stats["added"] += 1
                self._fts_replace(conn, rowid, entry_id, seg, meta["abstract"], body)
            stale = [row for row in conn.execute("SELECT rowid, id FROM memories").fetchall()
                     if row["id"] not in seen]
            for row in stale:
                conn.execute("DELETE FROM fts WHERE rowid=?", (row["rowid"],))
                conn.execute("DELETE FROM memories WHERE rowid=?", (row["rowid"],))
                stats["removed"] += 1
            self._set_meta(conn, "tokenizer_version", version)
            conn.commit()
        finally:
            conn.close()
        return stats

    def rebuild(self):
        if self.paths.index.exists():
            shutil.rmtree(self.paths.index)
        return self.sync(force=True)

    def _recency(self, valid_from, as_of):
        base = float(self.settings.get("recency_decay_base", 0.5))
        half_life = float(self.settings.get("recency_half_life_days", 90.0))
        floor = float(self.settings.get("recency_floor", 0.1))
        start = _as_date(valid_from) or as_of
        age = max(0, (as_of - start).days)
        return max(floor, base ** (age / half_life)) if half_life > 0 else 1.0

    def recall(self, query, as_of=None, type_filter=None, limit=None):
        """返回按 相关度 × 权重 × 新鲜度 排序的摘要列表。"""
        self.sync()
        as_of_date = _as_date(as_of) if as_of else date.today()
        if as_of_date is None:
            raise InternalError("as-of 日期非法")
        historical = as_of is not None
        limit = int(limit or self.settings.get("max_results", 20))
        conn = self._connect()
        try:
            relevance = {}
            terms = tokenizer.query_terms(query)
            if terms:
                expression = " OR ".join('"%s"' % term.replace('"', '""') for term in terms)
                for row in conn.execute(
                    "SELECT rowid, bm25(fts) AS rank FROM fts WHERE fts MATCH ?", (expression,)
                ):
                    relevance[row["rowid"]] = 1.0 + max(0.0, -float(row["rank"]))
            # 两字短词子串兜底：即使分词口径漂移也不零命中。
            for term in tokenizer.short_terms(query):
                pattern = "%" + term + "%"
                for row in conn.execute(
                    "SELECT rowid FROM memories WHERE body LIKE ? OR abstract LIKE ? OR seg LIKE ?",
                    (pattern, pattern, pattern),
                ):
                    relevance.setdefault(row["rowid"], 0.5)

            results = []
            for rowid, rel in relevance.items():
                row = conn.execute("SELECT * FROM memories WHERE rowid=?", (rowid,)).fetchone()
                if row is None:
                    continue
                if type_filter and row["type"] != type_filter:
                    continue
                valid_from = _as_date(row["valid_from"])
                invalid_at = _as_date(row["invalid_at"])
                if valid_from and valid_from > as_of_date:
                    continue
                if historical:
                    if invalid_at and invalid_at <= as_of_date:
                        continue
                else:
                    if row["invalid_at"] or row["archived"]:
                        continue
                score = rel * float(row["weight"]) * self._recency(row["valid_from"], as_of_date)
                results.append({
                    "id": row["id"], "abstract": row["abstract"], "type": row["type"],
                    "score": round(score, 6), "path": row["path"],
                    "valid_from": row["valid_from"], "invalid_at": row["invalid_at"],
                })
            results.sort(key=lambda item: (-item["score"], item["id"]))
            return results[:limit]
        finally:
            conn.close()

    def build_memory_md(self, budget=None):
        """生成注入用的一句话目录，超出字节预算即截断。"""
        self.sync()
        budget = int(budget or self.settings.get("injection_budget_bytes", 8192))
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT id, abstract FROM memories WHERE invalid_at='' AND archived=0 ORDER BY name"
            ).fetchall()
        finally:
            conn.close()
        lines = []
        used = 0
        for row in rows:
            line = "- %s [%s]\n" % (row["abstract"], row["id"])
            size = len(line.encode("utf-8"))
            if used + size > budget:
                break
            lines.append(line)
            used += size
        self.paths.memory_md.write_text("".join(lines), encoding="utf-8")
        return {"lines": len(lines), "bytes": used, "budget": budget}
