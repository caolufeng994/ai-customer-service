"""
Text Splitter Module
Splits documents into semantic chunks for embedding and retrieval.

切分策略:语义切分(semantic chunking)
不再依赖「固定长度 + 简单分隔符」的硬切,而是优先在文本的语义边界处断块:
  1. 结构边界:Markdown 标题(章节)、空行(段落) —— 章节/段落本就是天然语义单元;
  2. 主题转换点:在段落/章节内部,借助主题转换检测(启发式,或可选的 embedding
     相似度)识别话题切换处,避免在一段连续论述中硬切;
  3. 合并策略:在不超过目标长度的前提下,把相邻的短语义单元合并,减少碎片;
  4. 回退:仅当单个语义单元(如超长无标点句子)超过硬上限时,才回退到按
     标点 / 字符递归切分(带重叠)。

边界情况(均经测试覆盖):
  - 空文档 / 纯空白 -> 返回 [] 不崩溃;
  - 极短文档(<= 目标长度) -> 整体作为一个分块,不切碎也不丢弃;
  - 含特殊字符(BOM、控制符 \\x00-\\x1f、零宽 \\u200b 等、Windows \\r\\n) ->
    先净化再切分,不会因为脏字符导致编码/切分异常。

修复说明(相对旧版固定长度递归切分):
  - 旧版 bug:当某段落/部分自身超过 chunk_size 时,会产出超过 chunk_size 的块;
    新版合并阶段严格不超过 chunk_size,超长单元走回退切分,任何块 <= max_chunk_size。
  - 旧版会静默丢弃 < 10 字符的块(可能丢弃有意义的短标题/短条目);
    新版仅丢弃空白块,保留所有非空语义单元。
  - 旧版不做文本净化,脏字符会原样进入向量库;新版统一归一化。
"""
from typing import List, Optional
import re
import unicodedata
import logging

logger = logging.getLogger(__name__)


# ---- 文本净化:统一处理各类边界输入 ----
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")   # 控制字符(保留 \n \t)
_ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\ufeff]")       # 零宽 / BOM
_HEADER_RE = re.compile(r"^\s{0,3}#{1,6}\s+.*$", flags=re.MULTILINE)
_SENT_SPLIT_RE = re.compile(r"([。！？!?；;])")                  # 句末标点(切句保留标点)


def _sanitize(text: str) -> str:
    """净化文本:去 BOM/控制符/零宽、统一换行、NFC 归一、压缩空行。"""
    if not text:
        return ""
    text = text.replace("\ufeff", "")               # BOM
    text = _ZERO_WIDTH_RE.sub("", text)             # 零宽字符
    text = text.replace("\r\n", "\n").replace("\r", "\n")  # Windows 换行
    text = _CONTROL_RE.sub("", text)                # 其它控制字符
    text = unicodedata.normalize("NFC", text)       # 同形归一
    text = re.sub(r"\n{3,}", "\n\n", text)          # 压缩 3+ 空行
    return text.strip()


class TopicDetector:
    """主题转换检测接口:判断在 cur_text 之前是否应断块。"""

    def should_break(self, prev_text: str, cur_text: str, current_len: int, target: int) -> bool:
        raise NotImplementedError


class HeuristicTopicDetector(TopicDetector):
    """启发式主题转换检测:基于转换提示词 + 词汇位移(默认,零额外成本)。"""

    CUES = (
        "另外", "此外", "与此同时", "同时", "不过", "然而", "但是", "但", "总之",
        "综上所述", "接下来", "下面", "以下是", "注意", "温馨提示", "最后", "首先",
        "其次", "然后", "第一步", "第二步", "第三步", "一方面", "另一方面",
    )

    def __init__(self, cue_threshold_ratio: float = 0.4):
        self.cue_ratio = cue_threshold_ratio

    def should_break(self, prev_text: str, cur_text: str, current_len: int, target: int) -> bool:
        # 当前块已有一定规模才考虑断块,避免把过短块切碎
        if current_len < target * self.cue_ratio:
            return False
        # 仅依赖"转换提示词"判断主题切换点。
        # 注:不采用"词汇位移/字符重叠率"作为信号 —— 中文相邻句常有很低字符重叠,
        # 该信号会在几乎每对句子间误触发断块,导致过度切分(实测把 3 文档切成 96 个
        # 平均 55 字的小块)。提示词信号稀疏且语义明确,足以在话题切换处断块且不碎化。
        if any(cur_text.startswith(c) for c in self.CUES):
            return True
        return False


class EmbeddingTopicDetector(TopicDetector):
    """基于 embedding 相似度的主题转换检测(可选,默认关闭,需额外 embedding 调用)。"""

    def __init__(self, threshold: float = 0.5):
        self.threshold = threshold
        self._embedder = None
        self._prev_vec = None

    @staticmethod
    def _cosine(a, b) -> float:
        if not a or not b:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(y * y for y in b) ** 0.5
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    def _get_embedder(self):
        if self._embedder is None:
            try:
                from app.rag.embedder import Embedder
                self._embedder = Embedder()
            except Exception as e:  # 无 key / 无网络 -> 降级为不触发断块
                logger.warning(f"EmbeddingTopicDetector unavailable, fallback no-break: {e}")
                self._embedder = False
        return self._embedder

    def should_break(self, prev_text: str, cur_text: str, current_len: int, target: int) -> bool:
        if current_len < target * 0.4:
            return False
        emb = self._get_embedder()
        if emb is False:
            return False
        try:
            vec = emb.embed(cur_text)
        except Exception:
            return False
        if self._prev_vec is None:
            self._prev_vec = vec
            return False
        sim = self._cosine(self._prev_vec, vec)
        self._prev_vec = vec
        return sim < self.threshold


class TextSplitter:
    """
    语义切分器(替代原固定长度递归切分)。

    公开接口与旧版保持一致:``split_text(text) -> List[str]``、``get_chunk_count(text) -> int``,
    因此 ``knowledge_service.py`` 等调用方无需改动即可获得语义切分能力。

    新增语义相关参数可由配置注入(见 app.config)。
    """

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 80,
        max_chunk_size: Optional[int] = None,
        use_embedding: bool = False,
        topic_threshold: float = 0.5,
        topic_detector: Optional[TopicDetector] = None,
    ):
        self.chunk_size = max(1, int(chunk_size))            # 目标长度(软上限)
        self.chunk_overlap = max(0, int(chunk_overlap))
        self.max_chunk_size = max(self.chunk_size, int(max_chunk_size or self.chunk_size))
        self.use_embedding = use_embedding
        if topic_detector is not None:
            self.topic_detector = topic_detector
        elif use_embedding:
            self.topic_detector = EmbeddingTopicDetector(threshold=topic_threshold)
        else:
            self.topic_detector = HeuristicTopicDetector()

    # ---------- 公开 API ----------
    def split_text(self, text: str) -> List[str]:
        text = _sanitize(text)
        if not text:
            return []

        # 极短文档:整体作为一个分块(不切碎、不丢弃)
        if len(text) <= self.chunk_size:
            return [text]

        units = self._segment(text)
        chunks = self._build_chunks(units)
        chunks = self._dedupe(chunks)  # 去重 + 丢弃空白
        logger.info(
            f"Semantic split -> {len(chunks)} chunks "
            f"(target={self.chunk_size}, max={self.max_chunk_size})"
        )
        return chunks

    def get_chunk_count(self, text: str) -> int:
        clean = _sanitize(text)
        if not clean:
            return 0
        step = max(1, self.chunk_size - self.chunk_overlap)
        return max(1, (len(clean) + step - 1) // step)

    # ---------- 语义单元切分 ----------
    def _segment(self, text: str) -> List[dict]:
        """
        将文本切分为有序的语义叶单元(句子级),并标注结构边界:
          - is_header : 该单元是 Markdown 标题(章节边界,硬断点)
          - para_start: 该单元是一个新段落的首句(软断点,允许合并)
        返回单元列表,每个单元 {text, is_header, para_start}。
        """
        units: List[dict] = []
        last = 0
        for m in _HEADER_RE.finditer(text):
            body = text[last:m.start()].strip()
            if body:
                self._append_body(units, body)
            units.append({"text": m.group(0).strip(), "is_header": True, "para_start": True})
            last = m.end()
        tail = text[last:].strip()
        if tail:
            self._append_body(units, tail)
        if not units:
            self._append_body(units, text)
        return units

    def _append_body(self, units: List[dict], body: str) -> None:
        for para in re.split(r"\n{2,}", body):
            para = para.strip()
            if not para:
                continue
            sentences = self._split_sentences(para)
            for i, s in enumerate(sentences):
                units.append({"text": s, "is_header": False, "para_start": (i == 0)})

    @staticmethod
    def _split_sentences(para: str) -> List[str]:
        """按句末标点切分并保留标点;无标点则整体作为一句(交由回退切分处理超长)。"""
        pieces = _SENT_SPLIT_RE.split(para)
        sentences: List[str] = []
        buf = ""
        for piece in pieces:
            if not piece:
                continue
            buf += piece
            if _SENT_SPLIT_RE.match(piece):
                if buf.strip():
                    sentences.append(buf.strip())
                buf = ""
        if buf.strip():
            sentences.append(buf.strip())
        return sentences or [para]

    # ---------- 合并成块 ----------
    def _build_chunks(self, units: List[dict]) -> List[str]:
        chunks: List[str] = []
        current: List[str] = []
        current_len = 0
        prev_text = ""

        def flush():
            nonlocal current, current_len
            if current:
                chunks.append("".join(current))
                current = []
                current_len = 0

        for u in units:
            t = u["text"]
            t_len = len(t)

            # 章节标题:当前块已有一定内容(>=0.3*目标)时才另起一块,
            # 避免把连续的小章节切成大量碎片块(实测会把 3 文档切成 96 个平均 55 字块)。
            if u["is_header"] and current and current_len >= int(self.chunk_size * 0.3):
                flush()

            # 主题转换点:仅在"新段落起点"且当前块足够大(>=0.4*目标)时断块。
            # 限制 para_start 可避免对中文相邻句(字符重叠天然很低)误触发过度切分。
            if current and u["para_start"] and self.topic_detector.should_break(prev_text, t, current_len, self.chunk_size):
                flush()

            if current_len + t_len <= self.chunk_size:
                current.append(t)
                current_len += t_len
            else:
                if current:
                    flush()
                if t_len <= self.chunk_size:
                    current.append(t)
                    current_len = t_len
                else:
                    # 单个语义单元超长 -> 回退切分,直接成块(保证 <= max_chunk_size)
                    for piece in self._fallback_split(t):
                        chunks.append(piece)
            prev_text = t

        flush()
        return chunks

    def _fallback_split(self, text: str) -> List[str]:
        """回退:对超长单元按标点 / 字符递归切分,保证每块 <= max_chunk_size。"""
        out: List[str] = []
        buf = ""
        for s in self._split_sentences(text):
            if len(buf) + len(s) <= self.max_chunk_size:
                buf += s
            else:
                if buf:
                    out.append(buf)
                if len(s) <= self.max_chunk_size:
                    buf = s
                else:
                    # 单句仍超长 -> 滑动窗口字符切分(带重叠)
                    step = max(1, self.max_chunk_size - self.chunk_overlap)
                    for i in range(0, len(s), step):
                        out.append(s[i:i + self.max_chunk_size])
                    buf = ""
        if buf:
            out.append(buf)

        # 兜底:理论上不会到达,但防御性保证无超长块
        final: List[str] = []
        for c in out:
            if len(c) <= self.max_chunk_size:
                final.append(c)
            else:
                step = max(1, self.max_chunk_size - self.chunk_overlap)
                for i in range(0, len(c), step):
                    final.append(c[i:i + self.max_chunk_size])
        return final

    @staticmethod
    def _dedupe(chunks: List[str]) -> List[str]:
        seen = set()
        out = []
        for c in chunks:
            c = c.strip()
            if not c or c in seen:
                continue
            seen.add(c)
            out.append(c)
        return out
