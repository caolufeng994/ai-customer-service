"""
Embedder 单元测试
重点回归: DashScope text-embedding-v3 单批上限 10 条, 超出会 400 InvalidParameter。
embed_batch 必须把任何传入的 batch_size 收敛到 <= 10, 否则 FAQ 这类文档会整篇上传失败。
"""
from unittest.mock import MagicMock, patch


def _make_fake_client():
    """返回一个 embeddings.create 按输入条数回吐向量的假 client。"""
    client = MagicMock()

    def fake_create(model, input, dimensions):
        Embedding = type("Embedding", (), {"embedding": [0.1] * 1024})
        Response = type("Response", (), {"data": [Embedding() for _ in input]})
        return Response()

    client.embeddings.create.side_effect = fake_create
    return client


def test_embed_batch_clamps_to_dashscope_limit():
    from app.rag.embedder import Embedder

    fake_client = _make_fake_client()

    # 绕过 __init__ 的真实 DashScope 连接, 直接注入假 client
    with patch.object(Embedder, "__init__", lambda self: None):
        emb = Embedder()
        emb.provider = "dashscope"
        emb.model = "text-embedding-v3"
        emb.client = fake_client

        texts = [f"t{i}" for i in range(25)]
        out = emb.embed_batch(texts, batch_size=16)  # 故意传 16, 超过限额

    assert len(out) == 25, "返回向量数应与输入文本数一致"

    # 验证每次真实 API 调用的批大小都不超过 10
    for call in fake_client.embeddings.create.call_args_list:
        batch = call.kwargs["input"]
        assert len(batch) <= 10, f"单批 {len(batch)} 条超过 DashScope 上限 10"
