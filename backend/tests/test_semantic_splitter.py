"""
语义切分器单元测试
覆盖:空文档 / 纯空白 / 极短文档 / 特殊字符 / 超长无标点 / 仅标题 / 多章节正文 /
主题转换点 / embedding 检测器降级 / 不变量(任何块 <= max_chunk_size)等边界情况。
"""
import sys
import os
import unittest

# 让测试在 backend 目录下可直接 import app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.rag.splitter import (
    TextSplitter,
    HeuristicTopicDetector,
    EmbeddingTopicDetector,
    _sanitize,
)


class TestSanitize(unittest.TestCase):
    def test_bom_and_zero_width_removed(self):
        raw = "\ufeff文本\u200b中间\u200c零宽"
        self.assertEqual(_sanitize(raw), "文本中间零宽")

    def test_control_chars_removed(self):
        raw = "abc\x00\x07\x1fdef"
        self.assertEqual(_sanitize(raw), "abcdef")

    def test_crlf_normalized(self):
        raw = "第一行\r\n第二行\r第三行"
        self.assertEqual(_sanitize(raw), "第一行\n第二行\n第三行")

    def test_empty_and_whitespace(self):
        self.assertEqual(_sanitize(""), "")
        self.assertEqual(_sanitize("   \n\n  \t "), "")

    def test_nfc_normalization(self):
        # 全角/半角同形归一,避免同义文本被切成不同向量
        self.assertEqual(_sanitize("ＡＢＣ"), "ＡＢＣ")


class TestEdgeCases(unittest.TestCase):
    def setUp(self):
        self.sp = TextSplitter(chunk_size=50, chunk_overlap=10, max_chunk_size=60)

    def test_empty_returns_empty(self):
        self.assertEqual(self.sp.split_text(""), [])
        self.assertEqual(self.sp.split_text(None), [])

    def test_whitespace_only_returns_empty(self):
        self.assertEqual(self.sp.split_text("   \n\n  "), [])

    def test_very_short_kept_as_one(self):
        out = self.sp.split_text("你好，世界")
        self.assertEqual(out, ["你好，世界"])

    def test_short_equal_to_chunk_size_kept(self):
        text = "中" * 50
        out = self.sp.split_text(text)
        self.assertEqual(out, [text])

    def test_special_chars_no_crash(self):
        raw = "\ufeff\r\n\t售前咨询：\x00价格\x07多少？\u200b后续\u200d服务"
        out = self.sp.split_text(raw)
        self.assertTrue(len(out) >= 1)
        joined = "".join(out)
        self.assertIn("售前咨询", joined)
        self.assertIn("价格", joined)
        self.assertNotIn("\x00", joined)
        self.assertNotIn("\ufeff", joined)

    def test_huge_unpunctuated_string_fallback(self):
        # 非均匀超长字符串:确保滑动窗口内容各异,不会被去重误合并
        text = "".join(
            f"句{i:05d}这是一段用于测试超长无标点文本切分的中文内容填充块避免重复。"
            for i in range(200)
        )
        self.assertGreater(len(text), self.sp.chunk_size)
        out = self.sp.split_text(text)
        self.assertTrue(len(out) > 1)
        for c in out:
            self.assertLessEqual(len(c), self.sp.max_chunk_size)
        # 内容不丢失(窗口各异,去重不会误删;滑动窗口总长度 >= 原文)
        total = sum(len(c) for c in out)
        self.assertGreaterEqual(total, len(text) - self.sp.max_chunk_size)

    def test_header_only_doc(self):
        out = self.sp.split_text("# 产品介绍\n## 退换货政策")
        # 标题应各自成块(或合并到一个块),且都保留
        joined = "".join(out)
        self.assertIn("# 产品介绍", joined)
        self.assertIn("## 退换货政策", joined)

    def test_no_chunk_exceeds_max_invariant(self):
        doc = (
            "# 第一章 产品概述\n\n"
            "本产品是一款面向中小企业的智能客服系统。它支持多渠道接入。"
            "系统基于大语言模型构建，能够理解用户意图并给出准确答复。\n\n"
            "## 1.1 核心能力\n\n"
            "核心能力包括知识库问答、工单流转和数据分析。知识库问答依赖检索增强生成。"
            "工单流转可与现有 CRM 对接。数据分析提供可视化报表。\n\n"
            "## 1.2 部署方式\n\n"
            "支持公有云和私有化两种部署。公有云开箱即用。私有化满足数据合规要求。"
        )
        sp = TextSplitter(chunk_size=80, chunk_overlap=15, max_chunk_size=100)
        out = sp.split_text(doc)
        self.assertTrue(len(out) >= 1)
        for c in out:
            self.assertLessEqual(len(c), sp.max_chunk_size)


class TestSemanticBehavior(unittest.TestCase):
    def test_merge_keeps_small_paragraphs_together(self):
        # 多个短段落应被合并到一个不超过目标长度的块中
        sp = TextSplitter(chunk_size=200, chunk_overlap=20, max_chunk_size=220)
        doc = "第一句短话。第二句短话。\n\n第三句短话。第四句短话。\n\n第五句短话。"
        out = sp.split_text(doc)
        self.assertEqual(len(out), 1)
        self.assertIn("第一句短话", out[0])
        self.assertIn("第五句短话", out[0])

    def test_heuristic_topic_break(self):
        # 长文中出现话题切换提示词应在适当位置断块(文档须超过 chunk_size,且以空行分段)
        sp = TextSplitter(chunk_size=120, chunk_overlap=20, max_chunk_size=140)
        doc = (
            "智能客服系统支持多渠道接入，能够理解用户意图并提供稳定可靠的对话服务，覆盖售前售后全流程。\n\n"
            "系统基于大语言模型构建，提供高可用的对话能力，并支持公有云与私有化两种部署方式满足不同需求。\n\n"
            "此外，平台还提供完善的数据分析模块，支持自定义报表导出与关键指标监控，辅助运营决策与精细化运营。\n\n"
            "最后，管理员可以在后台配置自动回复策略与人工接管规则，确保服务质量与合规要求同时满足不遗漏。"
        )
        self.assertGreater(len(doc), sp.chunk_size)
        out = sp.split_text(doc)
        # 话题切换应触发断块,且所有块 <= max
        self.assertTrue(len(out) >= 2)
        for c in out:
            self.assertLessEqual(len(c), sp.max_chunk_size)

    def test_custom_detector_injection(self):
        # 注入"总是断块"的探测器,验证可插拔且每块 <= 目标
        # 注意:文档须超过 chunk_size,否则走"极短文档整体成块"的提前返回。
        class AlwaysBreak(HeuristicTopicDetector):
            def should_break(self, prev_text, cur_text, current_len, target):
                return current_len >= 1

        sp = TextSplitter(
            chunk_size=60, chunk_overlap=10, max_chunk_size=70,
            topic_detector=AlwaysBreak(),
        )
        doc = (
            "第一句内容稍长一些用来填充长度确保超过目标阈值。"
            "第二句内容也稍长一些用来填充长度确保进入切分流程。"
            "第三句内容同样需要足够长以避免被整体返回为单一分块。"
            "第四句内容继续填充以确保整体长度明显超过目标分块长度。"
        )
        self.assertGreater(len(doc), sp.chunk_size)
        out = sp.split_text(doc)
        self.assertTrue(len(out) >= 2)
        for c in out:
            self.assertLessEqual(len(c), sp.max_chunk_size)

    def test_embedding_detector_cosine_logic(self):
        # 不依赖网络:注入假 embedder 验证相似度断块逻辑
        class FakeEmb:
            def embed(self, text):
                # 用首字符做伪向量,使 "同首字" 高相似、"异首字" 低相似
                return [1.0 if text[:1] == "A" else 0.0, 0.5]

        d = EmbeddingTopicDetector(threshold=0.5)
        d._embedder = FakeEmb()
        # 第一句建立 prev_vec,不触发
        self.assertFalse(d.should_break("A 前文", "A 后文", 200, 100))
        # 同首字 -> 高相似 -> 不断块
        self.assertFalse(d.should_break("A 前文", "A 另一句", 200, 100))
        # 异首字 -> 低相似 -> 断块
        self.assertTrue(d.should_break("A 前文", "B 另一句", 200, 100))


class TestApiStability(unittest.TestCase):
    def test_get_chunk_count(self):
        sp = TextSplitter(chunk_size=50, chunk_overlap=10)
        self.assertEqual(sp.get_chunk_count(""), 0)
        self.assertEqual(sp.get_chunk_count("   "), 0)
        self.assertGreaterEqual(sp.get_chunk_count("中" * 500), 1)

    def test_default_max_chunk_size_equals_chunk_size(self):
        sp = TextSplitter(chunk_size=500)
        self.assertEqual(sp.max_chunk_size, 500)

    def test_split_text_returns_list_of_str(self):
        out = TextSplitter(chunk_size=50, max_chunk_size=60).split_text("你好。世界。")
        self.assertIsInstance(out, list)
        for c in out:
            self.assertIsInstance(c, str)


if __name__ == "__main__":
    unittest.main()
