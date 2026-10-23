# -*- coding: utf-8 -*-
"""retriever — BM25 粗筛 + CE 精排（可选层，内核仍零依赖）

为什么需要它：
    纯正则只认 'NX-7001' 这种字面。问 'the deployment that serves tensorflow'
    正则完全无解——而这正是原构想里"打分器"该干的活。

为什么不是"CE 全量"：
    实测 CE ≈ 50ms/对；5400 句全量 ≈ 270s。
    必须 BM25 粗筛到 20 条，再 CE 精排（20 对 ≈ 1.3s）。
"""
import math
import os
import re
from collections import Counter

TOK = re.compile(r"[a-z0-9_\-\.]+")
STOP = set("the a an of in on for to and or is are was were be with by as at from that this it its".split())


CJK = re.compile(r"[\u4e00-\u9fff]+")


def _toks(s):
    """中文走**二元切分**（BM25 在中文上的通行做法），英文/数字按词。
    早期只抓 ASCII：中文句子只剩数字能进词表，相关度全零，排序退化成"从第一回装"。"""
    # '×8' 这类记法此前被切成单字 '8'，等于把抓手销毁 → 先把 × 归成 x
    low = s.lower().replace("×", "x").replace("＊", "x")
    out = [t for t in TOK.findall(low) if t not in STOP and (len(t) > 1 or t.isdigit())]
    for run in CJK.findall(low):
        if len(run) == 1:
            out.append(run)
        else:
            out.extend(run[i:i + 2] for i in range(len(run) - 1))
    return out


class BM25:
    def __init__(self, docs):
        self.docs = docs
        self.tf = [Counter(_toks(d)) for d in docs]
        self.len = [len(t) for t in self.tf]
        self.avg = sum(self.len) / max(len(self.len), 1)
        df = Counter()
        for t in self.tf:
            df.update(set(t))
        self.df = df
        self.N = len(docs)

    def score(self, q):
        qt = _toks(q)
        out = []
        for i, tf in enumerate(self.tf):
            s = 0.0
            for t in qt:
                if t not in self.df:
                    continue
                d = self.df[t]
                idf = math.log(1 + (self.N - d + 0.5) / (d + 0.5))
                f = tf.get(t, 0)
                s += idf * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * self.len[i] / self.avg))
            out.append((s, i))
        # 平局取**较早**的回合（原来 reverse=True 会让平局偏向最后一条，属任意偏向）
        return sorted(out, key=lambda x: (-x[0], x[1]))


_RR = None


def _reranker(model_dir):
    global _RR
    if _RR is None:
        from FlagEmbedding import FlagReranker
        _RR = FlagReranker(model_dir, use_fp16=False)
    return _RR


def retrieve(docs, query, topk=3, prefilter=20, model_dir=None, use_ce=True):
    """返回 [(index, score, stage)]，stage ∈ {'bm25','ce'}"""
    bm = BM25(docs)
    cand = [i for s, i in bm.score(query)[:prefilter]]
    if not use_ce or model_dir is None:
        return [(i, None, "bm25") for i in cand[:topk]]
    rr = _reranker(model_dir)
    pairs = [[query, docs[i]] for i in cand]
    sc = rr.compute_score(pairs, normalize=True)
    if isinstance(sc, float):
        sc = [sc]
    ranked = sorted(zip(sc, cand), reverse=True)[:topk]
    return [(i, float(s), "ce") for s, i in ranked]


def retrieve_hier(text_units, sent_units, query, blocks_topk=3, sent_topk=1,
                  model_dir=None, use_ce=True):
    """分层检索：块级 BM25 粗筛 → 块内句级精排
    text_units: [(start,end)] 块的行号区间；sent_units: [{'line','text'}]
    """
    bm = BM25([t for t, _ in text_units]) if text_units and isinstance(text_units[0], str) else None
    return bm


def _chunks(text, max_chars=1800):
    """按 ~512 token（≈1800 英文字符 / ~750 汉字）切块，供长回合做 CE 分块打分"""
    if len(text) <= max_chars:
        return [text]
    out, buf, n = [], [], 0
    for line in text.split("\n"):
        if n + len(line) > max_chars and buf:
            out.append("\n".join(buf)); buf, n = [], 0
        buf.append(line); n += len(line) + 1
    if buf:
        out.append("\n".join(buf))
    return out


def rerank_turns(units, query, prefilter=20, topk=None, model_dir=None, use_ce=True):
    """BM25 粗筛 → CE 精排（**长回合分块取最大分**，规避 CE 的 512 token 截断）
    返回 [(idx, score, stage)]，按分降序；stage ∈ {'ce','bm25'}"""
    bm = BM25(units)
    cand = [i for _, i in bm.score(query)[:prefilter]]
    if not use_ce or model_dir is None:
        return [(i, None, "bm25") for i in cand]
    rr = _reranker(model_dir)
    # 展开成 (turn_idx, chunk_text)
    pairs, owner = [], []
    for i in cand:
        for c in _chunks(units[i]):
            pairs.append([query, c]); owner.append(i)
    sc = rr.compute_score(pairs, normalize=True)
    if isinstance(sc, float):
        sc = [sc]
    best = {}
    for s, i in zip(sc, owner):
        if i not in best or s > best[i]:
            best[i] = float(s)                       # max-pooling
    ranked = sorted(best.items(), key=lambda kv: (-kv[1], kv[0]))
    return [(i, s, "ce") for i, s in (ranked[:topk] if topk else ranked)]
