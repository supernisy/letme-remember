"""命令行接口（cli/spec.md 的落地）。

六个主命令：record / recall / show / invalidate / rebuild / list。
另有初始化与审批类辅助命令，宿主无需知道文件路径，只用定位标识交互。
错误信息只写标准错误，且不含凭据或记忆正文。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import config, distill, index, proposal, store
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

    recall = sub.add_parser("recall", parents=[common], help="关键词检索（零模型、零网络）")
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

    distill_cmd = sub.add_parser("distill", parents=[common], help="批量写入候选（原子预校验）")
    distill_cmd.add_argument("--candidates", required=True, help="候选数组的 JSON 文件")
    distill_cmd.add_argument("--source-category", dest="source_category")
    distill_cmd.add_argument("--original-date", dest="original_date")
    distill_cmd.add_argument("--batch")

    propose = sub.add_parser("propose", parents=[common], help="生成内容变更类审批提案")
    propose.add_argument("op", nargs="?", help="merge/split/supersede/delete/update_abstract")
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


HANDLERS = {
    "init": cmd_init,
    "record": cmd_record,
    "recall": cmd_recall,
    "show": cmd_show,
    "invalidate": cmd_invalidate,
    "rebuild": cmd_rebuild,
    "list": cmd_list,
    "inject": cmd_inject,
    "distill": cmd_distill,
    "propose": cmd_propose,
    "apply": cmd_apply,
    "proposals": cmd_proposals,
    "undo": cmd_undo,
    "undo-batch": cmd_undo_batch,
    "archive": cmd_archive,
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
