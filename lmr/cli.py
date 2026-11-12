"""命令行接口（cli/spec.md 的落地）。

六个主命令：record / recall / show / invalidate / rebuild / list。
另有初始化与审批类辅助命令，宿主无需知道文件路径，只用定位标识交互。
错误信息只写标准错误，且不含凭据或记忆正文。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import config, distill, index, proposal, queue, store
from . import llm as llm_module
from . import judgment
from . import host as host_module
from . import backup as backup_module
from .errors import EXIT_INTERNAL, EXIT_OK, EXIT_VALIDATION, MemError, NotFoundError, ValidationError

CANDIDATE_FIELDS = (
    "name", "abstract", "type", "conclusion", "reason", "author", "key",
    "weight", "valid_from", "created", "invalid_at", "superseded_by",
    "source_category", "original_date", "batch",
)


def _common():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--data-dir", default=None, help="记忆数据目录（默认在代码仓库外）")
    return parser


def _build_parser():
    common = _common()
    root = argparse.ArgumentParser(
        prog="mem", description="通用长期记忆仓库：文件是真相源，索引是可重建缓存"
    )
    sub = root.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", parents=[common], help="初始化代码仓库外的私有数据目录")
    init.add_argument("--no-sample", dest="sample", action="store_false", default=True,
                      help="不写入虚构示例记忆")

    record = sub.add_parser("record", parents=[common], help="写入一条候选记忆（过第一审）")
    record.add_argument("--candidate", help="候选记忆的 JSON 文件路径")
    record.add_argument("--name", help="身份名（同类型内唯一）")
    record.add_argument("--abstract", help="一句话摘要")
    record.add_argument("--type", help="9 类类型之一")
    record.add_argument("--conclusion", help="结论正文")
    record.add_argument("--reason", help="理由正文（必填）")
    record.add_argument("--author", help="写入者标识")
    record.add_argument("--key", help="按类型分组键自动推导身份名")
    record.add_argument("--weight", help="权重，范围 [0, 10]")
    record.add_argument("--valid-from", dest="valid_from", help="生效日期 ISO 8601")
    record.add_argument("--created", help="创建时间（一般留空由系统生成）")
    record.add_argument("--invalid-at", dest="invalid_at", help="失效日期")
    record.add_argument("--superseded-by", dest="superseded_by", help="取代者标识")
    record.add_argument("--links", help="关联标识，逗号分隔")
    record.add_argument("--source-category", dest="source_category", help="导入来源类别")
    record.add_argument("--original-date", dest="original_date", help="导入条目的原始生效日期")
    record.add_argument("--batch", help="导入批次标识")

    recall = sub.add_parser("recall", parents=[common], help="关键词+语义检索（本地向量，可选依赖）")
    recall.add_argument("query", help="查询词，支持中文两字及以上")
    recall.add_argument("--as-of", dest="as_of", help="查询该日期成立的真相")
    recall.add_argument("--type", dest="type_filter", help="按类型筛选")
    recall.add_argument("--limit", type=int, help="返回条数上限")

    show = sub.add_parser("show", parents=[common], help="按定位标识读回完整正文")
    show.add_argument("entry_id")

    invalidate = sub.add_parser("invalidate", parents=[common], help="标记失效，不物理删除")
    invalidate.add_argument("entry_id")
    invalidate.add_argument("--by", dest="superseded_by", help="取代它的新条目标识")
    invalidate.add_argument("--invalid-at", dest="invalid_at", help="失效日期")

    sub.add_parser("rebuild", parents=[common], help="删除索引后从真相源重建")

    sub.add_parser("list", parents=[common], help="输出一句话摘要目录")

    inject = sub.add_parser("inject", parents=[common], help="输出注入用目录（按字节预算截断）")
    inject.add_argument("--budget", type=int, help="字节预算上限")
    inject.add_argument("--query", help="按查询词召回相关条目（两段式第一段），省略则全量")
    inject.add_argument("--limit", type=int, help="召回条数上限（配合 --query）")

    embed_cmd = sub.add_parser("embed", parents=[common], help="全量向量化（补建语义索引）")

    sub.add_parser("serve", parents=[common],
                   help="常驻召回服务：模型只加载一次，检索毫秒级（挂 SessionStart）")
    sub.add_parser("serve-shutdown", parents=[common],
                   help="通知常驻召回服务退出（挂 SessionEnd）")

    distill_cmd = sub.add_parser("distill", parents=[common], help="批量写入候选（原子预校验）")
    distill_cmd.add_argument("--candidates", required=True, help="候选数组的 JSON 文件")
    distill_cmd.add_argument("--source-category", dest="source_category")
    distill_cmd.add_argument("--original-date", dest="original_date")
    distill_cmd.add_argument("--batch")

    judge_cmd = sub.add_parser("judge", parents=[common], help="对候选记忆做软判断并定级 L0/L1/L2")
    judge_cmd.add_argument("--candidates", required=True, help="候选数组的 JSON 文件")

    consolidate_cmd = sub.add_parser(
        "consolidate", parents=[common],
        help="自动去重合并落库：NOOP 丢、ADD 入、UPDATE 自动更、SUPERSEDE 停下待批")
    consolidate_cmd.add_argument("--candidates", required=True, help="候选数组的 JSON 文件")
    consolidate_cmd.add_argument("--batch", default="", help="导入批次标识（可选）")
    consolidate_cmd.add_argument("--dry-run", dest="dry_run", action="store_true",
                                 help="只判 action 不落库，输出分流统计报告（预览用）")
    consolidate_cmd.add_argument("--limit", type=int, default=0,
                                 help="只处理前 N 条候选（0=全部），用于分批")

    batch_cmd = sub.add_parser("batch-distill", parents=[common], help="用 LLM 批量蒸馏旧记忆文本")
    batch_cmd.add_argument("--file", required=True, help="待蒸馏的文本文件")
    batch_cmd.add_argument("--dry-run", dest="dry_run", action="store_true", help="只产出候选 JSON，不落库")

    propose = sub.add_parser("propose", parents=[common], help="生成内容变更类审批提案")
    propose.add_argument("op", nargs="?", help="merge/split/supersede/delete/purge/update_abstract")
    propose.add_argument("target", nargs="?", help="目标条目定位标识")
    propose.add_argument("--payload", help="附加参数的 JSON 字符串")
    propose.add_argument("--batch-file", dest="batch_file", help="批量提案的 JSON 数组文件")

    apply_cmd = sub.add_parser("apply", parents=[common], help="确认并应用一份提案")
    apply_cmd.add_argument("proposal_id")

    sub.add_parser("proposals", parents=[common], help="列出全部提案")
    sub.add_parser("undo", parents=[common], help="撤销最近一次写入")

    undo_batch = sub.add_parser("undo-batch", parents=[common], help="整批撤销一个导入批次")
    undo_batch.add_argument("batch")

    archive = sub.add_parser("archive", parents=[common], help="把失效条目移入归档目录")
    archive.add_argument("entry_id")

    purge = sub.add_parser("purge", parents=[common], help="真正删除一条错误/无效记忆（需审批，不可逆）")
    purge.add_argument("entry_id")
    purge.add_argument("--reason", default="", help="删除原因（写入审计）")

    queue_cmd = sub.add_parser("queue", parents=[common], help="查看/处理待审队列（L1/L2 蒸馏候选）")
    queue_cmd.add_argument("action", nargs="?", default="list",
                           help="list（查看待审）/ approve <id>（批准入库）/ reject <id>（驳回）/ expire（超时降级）")
    queue_cmd.add_argument("entry_id", nargs="?", default="", help="approve/reject 时的候选 id")
    queue_cmd.add_argument("--days", type=int, default=None, help="expire 的超时天数（默认 7）")

    setup_cmd = sub.add_parser("setup", parents=[common], help="把记忆能力接入宿主（无感集成）")
    setup_cmd.add_argument("--host", required=True, help="宿主名（可用: workbuddy）")

    backup_cmd = sub.add_parser("backup", parents=[common], help="加密数据目录并产出密文备份")
    backup_cmd.add_argument("--target", help="备份产物目录（默认数据目录下 backup/）")

    restore_cmd = sub.add_parser("restore", parents=[common], help="用本地密钥解密备份并恢复")
    restore_cmd.add_argument("backup_file", help="备份密文文件路径")

    return root


def _paths(args, allow_missing=False):
    paths = config.Paths(config.resolve_data_dir(args.data_dir))
    if not allow_missing and not paths.root.is_dir():
        raise NotFoundError("数据目录未初始化，请先运行 init")
    return paths, config.settings_for(paths.root)


def _json_file(path, expect):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValidationError("候选文件无法读取或不是合法 JSON") from exc
    if not isinstance(data, expect):
        raise ValidationError("候选文件的顶层结构不符合要求")
    return data


def cmd_init(args):
    paths = store.init_data_dir(config.resolve_data_dir(args.data_dir), sample=args.sample)
    return {
        "data_dir": str(paths.root),
        "store": str(paths.store),
        "sample": args.sample,
        "entries": store.entry_count(paths),
    }


def cmd_record(args):
    paths, settings = _paths(args)
    raw = _json_file(args.candidate, dict) if args.candidate else {}
    for field in CANDIDATE_FIELDS:
        value = getattr(args, field, None)
        if value is not None:
            raw[field] = value
    if args.links:
        raw["links"] = [part.strip() for part in args.links.split(",") if part.strip()]
    importing = [raw.get(k) for k in ("source_category", "original_date", "batch")]
    if any(importing) and not all(importing):
        raise ValidationError("导入条目必须同时提供来源类别、原始日期与批次标识")
    return store.record(paths, settings, raw)


def cmd_recall(args):
    paths, settings = _paths(args)
    return index.Index(paths, settings).recall(
        args.query, as_of=args.as_of, type_filter=args.type_filter, limit=args.limit
    )


def cmd_show(args):
    paths, _ = _paths(args)
    return store.show(paths, args.entry_id)


def cmd_invalidate(args):
    paths, settings = _paths(args)
    return store.invalidate(paths, settings, args.entry_id,
                            superseded_by=args.superseded_by, invalid_at=args.invalid_at)


def cmd_rebuild(args):
    paths, settings = _paths(args)
    stats = index.Index(paths, settings).rebuild()
    info = index.Index(paths, settings).build_memory_md()
    return {"rebuilt": stats, "memory_index": info}


def cmd_list(args):
    paths, _ = _paths(args)
    return store.list_entries(paths)


def cmd_inject(args):
    paths, settings = _paths(args)
    budget = args.budget or int(settings["injection_budget_bytes"])
    # 有 query 时按相关度召回（两段式第一段），并写回 memory_md 供注入
    if getattr(args, "query", None):
        info = index.Index(paths, settings).build_memory_md(
            budget=budget, query=args.query, limit=getattr(args, "limit", None))
        if not paths.memory_md.is_file():
            return ""
        return paths.memory_md.read_text(encoding="utf-8")
    if not paths.memory_md.is_file():
        return ""
    data = paths.memory_md.read_bytes()
    if len(data) <= budget:
        return data.decode("utf-8")
    # 按行截断，保证不切坏一行
    text = data.decode("utf-8", errors="ignore")
    used, lines = 0, []
    for line in text.splitlines(keepends=True):
        size = len(line.encode("utf-8"))
        if used + size > budget:
            break
        lines.append(line)
        used += size
    return "".join(lines)


def cmd_embed(args):
    """全量向量化：把记忆库里所有条目补上语义向量。"""
    paths, settings = _paths(args)
    return index.Index(paths, settings).embed_all()


def cmd_distill(args):
    paths, settings = _paths(args)
    candidates = _json_file(args.candidates, list)
    fields = {"source_category": args.source_category,
              "original_date": args.original_date, "batch": args.batch}
    if all(fields.values()):
        for item in candidates:
            for key, value in fields.items():
                item.setdefault(key, value)
    return distill.run_candidates(candidates, paths, settings)


def cmd_judge(args):
    """对候选做软判断（第二审），产出体检报告 + 分级裁决。

    冲突检测增强（#10）：先用本地索引检索库中相似结论（零网络），
    喂给 LLM 与候选比对，显式判定 ADD/UPDATE/SUPERSEDE/NOOP。
    """
    paths, settings = _paths(args)
    candidates = _json_file(args.candidates, list)
    # 读数据目录私有配置（含 llm_key 等），不写公开仓库。
    data_config = config._data_config(paths.root)
    # 检索索引复用 Index，读路径零网络；未初始化时降级为空比对。
    try:
        idx = index.Index(paths, settings)
    except Exception:
        idx = None
    results = []
    for cand in candidates:
        # 检索库中相似结论（本地零网络），失败或索引未建则空列表。
        existing = judgment.find_related(idx, cand) if idx is not None else []
        try:
            client = llm_module.make_client(settings, data_config)
            report = judgment.judge(client, cand, existing)
        except llm_module.LLMUnavailable:
            # 降级路径：LLM 不可用时用规则产出报告。
            report = judgment.rule_report(cand, existing)
        results.append({
            "name": cand.get("name"),
            "report": report,
            "level": judgment.classify(report),
            "degraded": isinstance(report.get("confidence"), str) and report.get("confidence") == "low" and not any(
                [report.get(k) for k in ("conflict", "high_impact", "ambiguous", "novel_type", "compliance", "uncertain")]),
        })
    return {"count": len(results), "items": results}


def cmd_consolidate(args):
    """自动去重合并落库（v1.1 #12 的落库策略）。

    对每条候选：检索相似结论 → LLM 判 ADD/UPDATE/SUPERSEDE/NOOP →
    按用户拍板的策略分流：
      - NOOP       等价重复，自动丢弃；
      - ADD        全新结论，自动入库；
      - UPDATE     修正已有，自动入库（新条目成为最新真相，旧条目靠时间轴收敛）；
      - SUPERSEDE  取代过时结论（真冲突），**停下待人批**，不落库。

    返回报告：自动处理数 + 待审批的真冲突清单。真冲突是唯一需要
    用户人工拍板的，其余全自动，避免几百条候选逐个手审。
    """
    paths, settings = _paths(args)
    candidates = _json_file(args.candidates, list)
    if getattr(args, "limit", 0) > 0:
        candidates = candidates[: args.limit]
    dry_run = getattr(args, "dry_run", False)
    data_config = config._data_config(paths.root)
    try:
        idx = index.Index(paths, settings)
    except Exception:
        idx = None

    auto_applied = []      # 已自动处理（ADD/UPDATE）
    noop_dropped = []      # 等价重复，丢弃
    needs_review = []      # 真冲突（SUPERSEDE），待人批
    degraded = 0           # 降级次数（LLM 不可用）

    for cand in candidates:
        existing = judgment.find_related(idx, cand) if idx is not None else []
        related_entries = judgment.find_related_entries(idx, cand) if idx is not None else []
        try:
            client = llm_module.make_client(settings, data_config)
            report = judgment.judge(client, cand, existing)
        except llm_module.LLMUnavailable:
            report = judgment.rule_report(cand, existing)
            degraded += 1

        action = judgment.decide_action(report)
        name = cand.get("name", "")

        # 时间维度守卫：SUPERSEDE 若方向反了（新候选比被取代结论更旧），
        # 禁止作废更精确的新结论，降级为 NOOP 丢弃（更旧的重复/过时结论不入库）。
        if action == "SUPERSEDE":
            allow, guard_note = judgment.supersede_time_guard(cand, related_entries)
            if not allow:
                noop_dropped.append({
                    "name": name,
                    "abstract": cand.get("abstract", ""),
                    "guard_note": guard_note,
                })
                action = "NOOP"  # 降级，走下面的 NOOP 分支

        if action == "NOOP":
            noop_dropped.append({"name": name, "abstract": cand.get("abstract", "")})
        elif action == "SUPERSEDE":
            # 真冲突（新结论推翻旧结论）：停下交人批。附上被取代旧条目的摘要，
            # 供用户拍板「是否作废这些旧条目」。不作废、不自动入库。
            conflict = report.get("conflict") or {}
            supersede_ids = conflict.get("ids", [])
            supersede_entries = []
            for sid in supersede_ids:
                try:
                    text = store.show(paths, sid)
                    import re as _re
                    m = _re.search(r"^abstract:\s*(.+)$", text, _re.MULTILINE)
                    supersede_entries.append({
                        "id": sid,
                        "abstract": m.group(1).strip() if m else "",
                    })
                except Exception:
                    supersede_entries.append({"id": sid, "abstract": ""})
            needs_review.append({
                "name": name,
                "abstract": cand.get("abstract", ""),
                "conclusion": cand.get("conclusion", ""),
                "reason": cand.get("reason", ""),
                "type": cand.get("type", ""),
                "supersede_entries": supersede_entries,
                "candidate": cand,
            })
        else:
            # ADD 或 UPDATE：自动入库（dry-run 时只记录不落库）。
            if not dry_run:
                outcome = store.record(paths, settings, cand)
                entry_id = outcome.get("id", "")
            else:
                entry_id = ""
            auto_applied.append({
                "name": name,
                "action": action,
                "id": entry_id,
            })

    result = {
        "auto_applied": len(auto_applied),
        "applied_items": auto_applied,
        "noop_dropped": len(noop_dropped),
        "noop_items": noop_dropped,
        "needs_review": len(needs_review),
        "review_items": needs_review,
        "degraded": degraded,
        "dry_run": dry_run,
    }
    return result


def cmd_batch_distill(args):
    """用 LLM 把一段旧文本蒸馏成候选，可选落库。"""
    paths, settings = _paths(args)
    data_config = config._data_config(paths.root)
    text = Path(args.file).read_text(encoding="utf-8")
    client = llm_module.make_client(settings, data_config)
    distiller = distill.LLMDistiller(client)
    candidates = distiller.distill(text)
    if args.dry_run:
        return {"count": len(candidates), "candidates": candidates}
    return distill.run_candidates(candidates, paths, settings)


def cmd_propose(args):
    paths, _ = _paths(args)
    if args.batch_file:
        items = _json_file(args.batch_file, list)
        return proposal.create_batch(paths, items)
    if not args.op or not args.target:
        raise ValidationError("生成单条提案需要操作名与目标标识")
    payload = {}
    if args.payload:
        try:
            payload = json.loads(args.payload)
        except ValueError as exc:
            raise ValidationError("payload 不是合法 JSON") from exc
    return proposal.create(paths, args.op, args.target, payload)


def cmd_apply(args):
    paths, settings = _paths(args)
    return proposal.apply(paths, settings, args.proposal_id)


def cmd_proposals(args):
    paths, _ = _paths(args)
    return proposal.list_proposals(paths)


def cmd_undo(args):
    paths, settings = _paths(args)
    return store.undo(paths, settings)


def cmd_undo_batch(args):
    paths, settings = _paths(args)
    return store.undo_batch(paths, settings, args.batch)


def cmd_archive(args):
    paths, settings = _paths(args)
    return store.archive(paths, settings, args.entry_id)


def cmd_purge(args):
    paths, settings = _paths(args)
    return store.purge(paths, settings, args.entry_id, reason=args.reason)


def cmd_queue(args):
    """待审队列：list / approve / reject / expire 四个子操作。

    候选分级后 L0 静默入库（不经这里），L1/L2 进队列待人批。
    approve 走 store.record 完整写入链，不绕过脚本红线与分级裁决。
    """
    paths, settings = _paths(args)
    action = args.action
    if action == "list":
        return {"count": len(queue.list_pending(paths)), "items": queue.list_pending(paths)}
    if action == "approve":
        if not args.entry_id:
            raise ValidationError("approve 需要候选 id")
        return queue.approve(paths, settings, args.entry_id)
    if action == "reject":
        if not args.entry_id:
            raise ValidationError("reject 需要候选 id")
        return queue.reject(paths, args.entry_id)
    if action == "expire":
        days = args.days or queue.DEFAULT_TIMEOUT_DAYS
        return queue.expire(paths, timeout_days=days)
    raise ValidationError("未知的 queue 子操作: %s" % action)


def cmd_setup(args):
    """把记忆能力接入宿主：生成适配器 hook 脚本并注册到宿主配置。"""
    paths, _ = _paths(args, allow_missing=True)
    adapter = host_module.get_host(args.host)
    return adapter.install(paths)


def cmd_backup(args):
    """加密数据目录并产出密文备份。加密库未装时优雅降级为未配置提示。"""
    paths, settings = _paths(args)
    return backup_module.backup(paths, settings, target_dir=args.target)


def cmd_restore(args):
    """用本地密钥解密备份并恢复数据目录。密钥缺失时明确报错。"""
    paths, settings = _paths(args)
    return backup_module.restore(paths, settings, args.backup_file)


def cmd_serve(args):
    """常驻召回服务：离线加载模型后阻塞监听，空闲超时自退。"""
    from . import serve
    # 服务进程必须离线加载模型（禁联网），否则联网验证会把启动拖到 100 秒。
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    return serve.serve_forever()


def cmd_serve_shutdown(args):
    """通知常驻召回服务退出；服务未运行则静默成功。"""
    from . import serve
    serve.client_shutdown()
    return {"shutdown": "requested"}


HANDLERS = {
    "init": cmd_init,
    "record": cmd_record,
    "recall": cmd_recall,
    "show": cmd_show,
    "invalidate": cmd_invalidate,
    "rebuild": cmd_rebuild,
    "list": cmd_list,
    "inject": cmd_inject,
    "embed": cmd_embed,
    "distill": cmd_distill,
    "judge": cmd_judge,
    "consolidate": cmd_consolidate,
    "batch-distill": cmd_batch_distill,
    "propose": cmd_propose,
    "apply": cmd_apply,
    "proposals": cmd_proposals,
    "undo": cmd_undo,
    "undo-batch": cmd_undo_batch,
    "archive": cmd_archive,
    "purge": cmd_purge,
    "queue": cmd_queue,
    "setup": cmd_setup,
    "backup": cmd_backup,
    "restore": cmd_restore,
    "serve": cmd_serve,
    "serve-shutdown": cmd_serve_shutdown,
}


def main(argv=None):
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
        result = HANDLERS[args.command](args)
        if isinstance(result, str):
            print(result, end="" if result.endswith("\n") else "\n")
        elif result is not None:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return EXIT_OK
    except MemError as exc:
        print("错误: %s" % exc.message, file=sys.stderr)
        return exc.exit_code
    except (OSError, ValueError) as exc:
        # 不打印异常内容：可能夹带记忆正文或凭据形状的原值。
        print("错误: 输入或文件读取失败（%s）" % type(exc).__name__, file=sys.stderr)
        return EXIT_VALIDATION
    except Exception as exc:
        print("内部错误: %s" % type(exc).__name__, file=sys.stderr)
        return EXIT_INTERNAL
