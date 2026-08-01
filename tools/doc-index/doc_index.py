#!/usr/bin/env python3
"""面向 AI Agent 的文档索引系统（machine-readable 版）。

让 agent 在执行任务时，根据「任务描述 / 关键词」从索引中精准筛选出
*需要读取*的文件，而不是盲目地把整个代码库塞进上下文。

设计要点
--------
1. 索引（JSON）为仓库中每个文件登记：
     - path        文件相对/绝对路径
     - category    分类（rag / api / model / service ...）
     - description 一句话功能概述
     - use_cases   适用场景列表（自然语言短语）
     - keywords    关键词列表（便于精确匹配）
2. 给定任务 query，对每条文件计算相关性得分（0~1）：
     score = 0.40*关键词命中 + 0.30*场景命中 + 0.20*概述命中 + 0.10*路径命中
   命中率 = 查询词与文件词表的交集 / 查询词总数。
3. 仅返回 score >= threshold 的文件，按得分降序排列，并给出命中理由。

工程约束（对齐《代码规范》）
-------------------------
- 纯标准库，无第三方依赖，运行快、结果确定可复现。
- 中英混排友好的分词器（ASCII 词 + 中文二元文法 + 整句短语）。
- 统一使用 ``logging.getLogger(__name__)`` 输出，禁止 ``print()`` 调试。
- 所有公开类/方法带 docstring，函数签名带类型注解。
- 索引与引擎解耦：换一个 index JSON 即可服务任意项目。

用法（CLI）
----------
  python doc_index.py query "实现 RAG 检索与多轮问答" --topk 5
  python doc_index.py query "修复登录密码校验" --threshold 0.15 --json
  python doc_index.py paths "聊天流式输出 SSE"        # 仅打印待读文件路径
  python doc_index.py stats                            # 索引统计

用法（库）
----------
  from doc_index import DocIndex
  idx = DocIndex.load("doc_index.json")
  for hit in idx.query("实现 RAG 检索", top_k=5):
      print(hit.path, hit.score, hit.reason)
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# 各维度权重（合计 = 1.0）
W_KEYWORD: float = 0.40
W_USECASE: float = 0.30
W_DESC: float = 0.20
W_PATH: float = 0.10

_ASCII_RE = re.compile(r"[a-zA-Z0-9_]+")
_CJK_RE = re.compile(r"[一-鿿]+")


class DocIndexError(Exception):
    """索引加载或查询过程中的业务异常。

    用于替代裸 ``Exception``，提供清晰的可读错误信息（文件缺失、JSON 损坏等），
    便于 CLI 层优雅退出与自动化测试断言。
    """


def tokenize(text: str) -> set[str]:
    """把文本切成一组 term。

    - ASCII 连续串（长度 >= 2）转小写作为整词。
    - 中文连续串：整句作为一个 term + 相邻二元文法（bigram）。
    这样既能做整词/整句精确匹配，又能做局部子串模糊匹配。
    """
    if not text:
        return set()
    terms: set[str] = set()
    for match in _ASCII_RE.findall(text):
        if len(match) >= 2:
            terms.add(match.lower())
    for run in _CJK_RE.findall(text):
        if len(run) == 1:
            terms.add(run)  # 单字也保留
        else:
            terms.add(run)  # 整句短语
            for i in range(len(run) - 1):
                terms.add(run[i:i + 2])  # 二元文法
    return terms


@dataclass
class IndexEntry:
    """索引中的单个文件条目。

    字段与 JSON 一一对应；``_kw_terms`` 等带下划线前缀的字段为运行时预计算的
    词表，不写入 JSON。
    """

    path: str
    category: str = ""
    description: str = ""
    use_cases: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)

    # 运行时预计算的词表（不写入 JSON）
    _kw_terms: set[str] = field(default_factory=set, repr=False)
    _uc_terms: set[str] = field(default_factory=set, repr=False)
    _desc_terms: set[str] = field(default_factory=set, repr=False)
    _path_terms: set[str] = field(default_factory=set, repr=False)

    def build_terms(self) -> None:
        """根据文本字段预计算各维度 term 集合，供查询时快速求交集。"""
        self._kw_terms = tokenize(" ".join(self.keywords))
        self._uc_terms = tokenize(" ".join(self.use_cases))
        self._desc_terms = tokenize(self.description)
        self._path_terms = tokenize(Path(self.path).name)


@dataclass
class Hit:
    """一次查询命中的文件及其相关性信息。"""

    path: str
    category: str
    score: float
    matched_keywords: list[str]
    reason: str
    description: str = ""

    def to_dict(self) -> dict:
        """序列化为可 JSON 化的字典，供 ``--json`` 输出与下游消费。"""
        return asdict(self)


class DocIndex:
    """文档索引引擎：加载索引、按任务查询相关文件。"""

    def __init__(
        self,
        project: str = "",
        description: str = "",
        files: list[IndexEntry] | None = None,
    ) -> None:
        self.project = project
        self.description = description
        self.entries: list[IndexEntry] = files or []
        for entry in self.entries:
            entry.build_terms()

    # ------------------------- 加载 / 保存 ------------------------- #
    @classmethod
    def load(
        cls,
        path: str | Path,
        base_dir: str | Path | None = None,
    ) -> DocIndex:
        """从 JSON 文件加载索引。

        :param path: 索引 JSON 路径。
        :param base_dir: 索引中相对路径的基准目录；默认取 JSON 文件所在位置的**仓库根**
                         （``tools/doc-index/doc_index.json`` 向上 3 级即仓库根），使输出的
                         路径为绝对路径，便于 agent 直接读取。若索引被移动到其他位置，
                         需显式传入 ``--base-dir`` 指定仓库根。
        :raises DocIndexError: 文件不存在或 JSON 解析失败时抛出。
        """
        p = Path(path)
        if not p.exists():
            raise DocIndexError(f"索引文件不存在: {p}")
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DocIndexError(f"索引 JSON 解析失败 ({p}): {exc}") from exc

        try:
            files = [IndexEntry(**f) for f in raw.get("files", [])]
        except TypeError as exc:
            raise DocIndexError(f"索引条目字段缺失或类型错误: {exc}") from exc

        if base_dir is None:
            # 规范位置 tools/doc-index/doc_index.json -> 向上 3 级为仓库根
            base_dir = p.resolve().parent.parent.parent
        index = cls(
            project=raw.get("project", ""),
            description=raw.get("description", ""),
            files=files,
        )
        index._resolve_paths(Path(base_dir))
        return index

    def _resolve_paths(self, base_dir: Path) -> None:
        """将索引中的相对路径解析为基于 ``base_dir`` 的绝对路径，并重建路径词表。"""
        for entry in self.entries:
            src = Path(entry.path)
            if not src.is_absolute():
                entry.path = str((base_dir / entry.path).resolve())
            entry.build_terms()

    def to_dict(self) -> dict:
        """导出为与加载格式一致的字典。"""
        return {
            "project": self.project,
            "description": self.description,
            "files": [
                {
                    "path": e.path,
                    "category": e.category,
                    "description": e.description,
                    "use_cases": e.use_cases,
                    "keywords": e.keywords,
                }
                for e in self.entries
            ],
        }

    # ------------------------- 查询 ------------------------- #
    def query(
        self,
        task: str,
        top_k: int = 5,
        threshold: float = 0.15,
    ) -> list[Hit]:
        """按任务描述查询相关文件。

        :param task: 任务描述或关键词。
        :param top_k: 返回的最大文件数。
        :param threshold: 最低相关性得分阈值（0~1）。
        :return: 按得分降序的命中列表（已截断到 top_k）。
        """
        q_terms = tokenize(task)
        if not q_terms:
            return []

        hits: list[Hit] = []
        for entry in self.entries:
            kw_hit = q_terms & entry._kw_terms
            uc_hit = q_terms & entry._uc_terms
            desc_hit = q_terms & entry._desc_terms
            path_hit = q_terms & entry._path_terms

            # 命中率：命中的查询词数 / 查询词总数
            kw_r = len(kw_hit) / len(q_terms)
            uc_r = len(uc_hit) / len(q_terms)
            desc_r = len(desc_hit) / len(q_terms)
            path_r = len(path_hit) / len(q_terms)

            score = (
                W_KEYWORD * kw_r
                + W_USECASE * uc_r
                + W_DESC * desc_r
                + W_PATH * path_r
            )
            if score < threshold:
                continue

            matched = sorted({*kw_hit, *uc_hit})
            reason_parts: list[str] = []
            if kw_hit:
                reason_parts.append(f"关键词命中[{','.join(sorted(kw_hit))}]")
            if uc_hit:
                reason_parts.append(f"场景命中[{','.join(sorted(uc_hit))}]")
            if desc_hit and not kw_hit and not uc_hit:
                reason_parts.append(f"概述相关[{','.join(sorted(desc_hit)[:3])}]")
            hits.append(
                Hit(
                    path=entry.path,
                    category=entry.category,
                    score=round(score, 3),
                    matched_keywords=matched,
                    reason="; ".join(reason_parts) or "路径相关",
                    description=entry.description,
                )
            )

        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:top_k]

    # ------------------------- 辅助 ------------------------- #
    def stats(self) -> dict:
        """返回索引统计：文件总数与分类分布。"""
        cats: dict[str, int] = {}
        for entry in self.entries:
            key = entry.category or "uncategorized"
            cats[key] = cats.get(key, 0) + 1
        return {"total": len(self.entries), "by_category": cats}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _configure_cli_logging() -> None:
    """为 CLI 配置 stdout 日志输出（仅当尚无 handler 时），统一走 logging。"""
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)


def _print_hits(hits: list[Hit], task: str) -> None:
    logger.info("\n任务: %s", task)
    logger.info("匹配到 %d 个文件（按相关性降序）：\n", len(hits))
    if not hits:
        logger.info("  （无文件达到阈值，建议放宽 --threshold 或补充索引描述）")
        return
    for i, hit in enumerate(hits, 1):
        logger.info("%d. [%.2f] %s", i, hit.score, hit.path)
        logger.info("     分类: %s  |  理由: %s", hit.category, hit.reason)
        if hit.description:
            logger.info("     概述: %s", hit.description)


def main(argv: list[str] | None = None) -> int:
    """CLI 入口：query / paths / stats 三个子命令。

    :param argv: 参数列表；为 ``None`` 时取 ``sys.argv[1:]``。
    :return: 进程退出码（0 成功，2 参数错误）。
    """
    _configure_cli_logging()
    parser = argparse.ArgumentParser(description="AI Agent 文档索引系统")
    default_index = str(Path(__file__).resolve().parent / "doc_index.json")
    parser.add_argument("--index", "-i", default=default_index, help="索引 JSON 路径")
    parser.add_argument(
        "--base-dir",
        default=None,
        help="索引中相对路径的基准目录（默认取仓库根：索引文件向上 3 级）",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    pq = sub.add_parser("query", help="按任务查询需读取的文件")
    pq.add_argument("task", help="任务描述 / 关键词")
    pq.add_argument("--topk", "-k", type=int, default=5)
    pq.add_argument("--threshold", "-t", type=float, default=0.15)
    pq.add_argument("--json", action="store_true", help="以 JSON 输出")

    pp = sub.add_parser("paths", help="仅输出待读文件路径（便于管道）")
    pp.add_argument("task", help="任务描述 / 关键词")
    pp.add_argument("--topk", "-k", type=int, default=5)
    pp.add_argument("--threshold", "-t", type=float, default=0.15)

    sub.add_parser("stats", help="打印索引统计")

    args = parser.parse_args(argv)
    try:
        idx = DocIndex.load(args.index, base_dir=args.base_dir)
    except DocIndexError as exc:
        logger.error("加载索引失败: %s", exc)
        return 2

    if args.cmd == "stats":
        stat = idx.stats()
        logger.info("项目: %s", idx.project)
        logger.info("文件总数: %d", stat["total"])
        logger.info("分类分布: %s", stat["by_category"])
        return 0

    if args.cmd == "query":
        hits = idx.query(args.task, top_k=args.topk, threshold=args.threshold)
        if args.json:
            logger.info(
                json.dumps(
                    {"task": args.task, "hits": [h.to_dict() for h in hits]},
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            _print_hits(hits, args.task)
        return 0

    if args.cmd == "paths":
        hits = idx.query(args.task, top_k=args.topk, threshold=args.threshold)
        for hit in hits:
            logger.info("%s", hit.path)
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
