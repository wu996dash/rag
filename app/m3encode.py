"""BGE-M3 双通道编码器：稠密(CLS+L2) + 学习式稀疏(sparse_linear)。
不依赖 FlagEmbedding：直接加载本地权重的 sparse_linear.pt，词项权重 = ReLU(线性层输出)，
子词合并到整词后按 crc32 生成稳定词项 id（Milvus SPARSE_FLOAT_VECTOR 接受 {int: float}）。"""
import zlib
from functools import lru_cache
from . import config
import threading
_GPU_LOCK = threading.Lock()
SPECIAL = {"[CLS]", "[SEP]", "</s>", "<pad>", "[PAD]", "[MASK]", "[UNK]"}
@lru_cache(maxsize=1)
def _load():
    import torch
    from transformers import AutoModel, AutoTokenizer
    dev = getattr(config, "EMBED_DEVICE", "cpu")
    tok = AutoTokenizer.from_pretrained(config.EMBED_MODEL_PATH)
    model = AutoModel.from_pretrained(config.EMBED_MODEL_PATH)
    sl = torch.nn.Linear(model.config.hidden_size, 1)
    sl.load_state_dict(torch.load(f"{config.EMBED_MODEL_PATH}/sparse_linear.pt", map_location="cpu"))
    model.to(dev); sl.to(dev)
    model.eval(); sl.eval()
    return tok, model, sl, dev, torch
def _merge_weights(ids, toks, scores):
    """子词并入父词；父词取最大权重。"""
    words = {}
    parent = None
    for i, (t, s) in enumerate(zip(toks, scores)):
        if t in SPECIAL or t == "[UNK]":
            parent = None; continue
        if t.startswith("##"):
            w = parent
        else:
            w = t
            parent = t
        if w is None:
            continue
        words[w] = max(words.get(w, 0.0), float(s))
    return {(zlib.crc32(w.encode("utf-8")) & 0x7FFFFFFF): v for w, v in words.items() if v > 0}
def _encode_once(texts):
    tok, model, sl, dev, torch = _load()
    dense_all, sparse_all = [], []
    with _GPU_LOCK, torch.no_grad():
        for t in texts:
            enc = tok([t], truncation=True, max_length=1024, return_tensors="pt").to(dev)
            hs = model(**enc).last_hidden_state
            d = torch.nn.functional.normalize(hs[:, 0], dim=1)
            sc = torch.relu(sl(hs).squeeze(-1))[0]
            ids = enc["input_ids"][0].tolist()
            toks = tok.convert_ids_to_tokens(ids)
            sp = _merge_weights(ids, toks, sc.tolist())
            dense_all.append(d[0].tolist())
            sparse_all.append(sp)
    return dense_all, sparse_all

_CACHE = {}
_CACHE_MAX = 4096

def encode(texts):
    """带缓存：nav 与 hybrid 对同一查询文本只前向一次；文档嵌入在进程内亦复用。"""
    d_out, s_out = [None] * len(texts), [None] * len(texts)
    miss = []
    for i, t in enumerate(texts):
        hit = _CACHE.get(t)
        if hit is not None:
            d_out[i], s_out[i] = hit
        else:
            miss.append(i)
    if miss:
        d, sp = _encode_once([texts[i] for i in miss])
        for j, i in enumerate(miss):
            d_out[i], s_out[i] = d[j], sp[j]
            if len(_CACHE) < _CACHE_MAX:
                _CACHE[texts[i]] = (d[j], sp[j])
    return d_out, s_out
