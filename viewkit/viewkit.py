#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
viewkit — 二级视图构建器

这是原构想里的那件事，不是别的东西：
    原文 → 沉积层（无损保留）
         → 二级视图（模型真正读的那一小段）
         → 答案 + 出处

它只做"造视图"，**不做计算、不替模型回答**。

**默认模式是 turns**：

    turns    ：语料是对话回合格式（用户一句 + AI 一段）
                → 视图 = 相关**整回合**，按原文顺序拼接，绝不拆句
                → 目标已在尾部高注意力区时 **不产出视图**（view=None）

非回合模式（lookup / gather / search）面向文档 / 针型语料，**非回合语料才用**：

    lookup   ：问题指向一个具体实体 → 视图 = 含该实体的最小窗口（实测 78 字符）
    gather   ：问题在问聚合 → 视图 = **所有同类型实例**（不是 top-k）（实测 1,662 字符）
    search   ：两者都不是 → 句级 BM25/CE 检索

`--mode auto` 会按语料格式判断：有回合标记 → turns；没有 → 退回非回合路由。
**不传 --mode 就是 turns**，非回合语料要显式传 `--mode auto`。

用法
    python viewkit.py --corpus conv_turns.txt --ask "..."            # 默认 turns
    python viewkit.py --corpus conv_turns.txt                        # 不给 ask：Q 取末条用户输入
    python viewkit.py --corpus doc.txt --ask "..." --mode auto       # 按语料格式判断
    python viewkit.py --corpus doc.txt --ask "..." --json            # 机读
    python viewkit.py --self-test                                    # 回归
"""
import argparse
import json
import re
import sys

NUM = re.compile(r"(?<!\d)(\d{3,7})(?!\d)")
ENTITY = re.compile(r"\b([A-Z]{1,3})-(\d{3,6})\b")
# 只在**没有具体实体**时才算聚合意图；'entry count' 这类词不算
AGG_HINT = re.compile(r"\b(total|sum|all the|how many|largest|smallest|maximum|minimum|average|every)\b", re.I)


def normalize(t):
    t = re.sub(r"[\u2010-\u2015\u2212]", "-", t)
    t = re.sub(r"\b([A-Z]{2,3})\s+(\d{3,6})\b", r"\1-\2", t)   # 只认大写前缀，避免 'to 9216' → 'to-9216' 
    return t


def sentences(text):
    """按行切（句级，保留行号供回溯）"""
    out = []
    for i, line in enumerate(text.split("\n")):
        s = line.strip()
        if len(s) >= 12:
            out.append({"line": i, "text": s})
    return out


def est_tokens(s):
    """粗估 token：中文约 1.5 字/token，英文约 4 字/token（用于预算，不用于计费）"""
    cjk = sum(1 for ch in s if "\u4e00" <= ch <= "\u9fff")
    other = len(s) - cjk
    return cjk / 1.5 + other / 4.0


def latest_user_turn(text):
    """取出**最新一条用户输入信息块**作为 Q（设计口径：Q 就是当前这一回合的用户那一句/块）。
    同时认 `user:` / `assistant:` 与 `用户：` / `助手：` 两套标记；取不到标记时退回整个末回合。"""
    units = parse_turns(text)
    TURN = r"(?:===== TURN \d+\s*=====\s*)?"
    U = re.compile(r"(?:^|\n)\s*" + TURN + r"(?:user|human|用户)\s*[:：]\s*", re.I)
    A = re.compile(r"(?:^|\n)\s*" + TURN + r"(?:assistant|助手|ai)\s*[:：]\s*", re.I)
    for k in range(len(units) - 1, -1, -1):
        u = units[k]
        m = U.search(u)
        if not m:
            continue
        start = m.end()
        a = A.search(u, start)
        end = a.start() if a else len(u)
        return u[start:end].strip(), k
    return (units[-1] if units else ""), len(units) - 1


# 续说类短回复：直接跳过整个 viewkit（no-op）。
# 理由：这是**注意力管理工程**，不是检索。
# 「继续」要接的内容本来就在对话尾部的天然高注意力区，系统再做任何事都是多余的。
CONTINUE_WORDS = {
    "继续", "接着说", "接着", "往下", "然后呢", "还有呢", "继续吧", "说下去",
    "嗯", "嗯嗯", "好", "好的", "行", "可以", "再来", "多说点",
    "continue", "go on", "more", "keep going", "next",
}


def is_continuation(q):
    """极短且只由续说词构成 → 视为续说，整个 viewkit 跳过"""
    s = re.sub(r"[\s，,。.!！?？~、；;：:]+", "", (q or "").lower())
    if not s or len(s) > 8:
        return False
    # 英文多词（go on）去空格后比对
    return any(s == w.replace(" ", "") or s.startswith(w.replace(" ", "")) for w in CONTINUE_WORDS)


def looks_truncated(turn_text):
    """助手回复是否疑似被截断：末尾没有终止标点"""
    body = turn_text.split("助手：")[-1].rstrip()
    return bool(body) and body[-1] not in "。！？.!?」』）”\"'"


def parse_turns(text):
    """按**对话回合**切块：一回合 = 用户一句 + AI 一条回复。
    识别 '===== TURN n =====' 或 'user:'/'assistant:' 交替；都没有则退化为按空行分段。"""
    if "===== TURN" in text:
        parts = re.split(r"(?=^===== TURN)", text, flags=re.M)
    elif re.search(r"^(user|human)\s*:", text, re.M | re.I):
        parts = re.split(r"(?=^(?:user|human)\s*:)", text, flags=re.M | re.I)
    else:
        parts = re.split(r"\n\s*\n", text)
    return [p.strip() for p in parts if p.strip()]


def blocks(text, max_chars=4000):
    """按块切：优先用 '===== FILE: xxx =====' 分节，否则按空行分段。
    块是检索的**默认单位**——句级单位太多（5,400 vs 195），CE 扛不住。"""
    if "===== FILE:" in text:
        parts = re.split(r"(?=^===== FILE:)", text, flags=re.M)
    else:
        parts = re.split(r"\n\s*\n", text)
    out, buf = [], []
    acc = 0
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if acc + len(p) > max_chars and buf:
            out.append("\n".join(buf)); buf, acc = [], 0
        buf.append(p); acc += len(p) + 1
    if buf:
        out.append("\n".join(buf))
    return out


def has_turn_marks(text):
    """语料是不是**对话回合**格式？认 '===== TURN' 与 'user:/用户：'+'assistant:/助手：' 两套标记。"""
    if "===== TURN" in text:
        return True
    head = text[:200000]
    u = re.search(r"^\s*(?:user|human|用户)\s*[:：]", head, re.M | re.I)
    a = re.search(r"^\s*(?:assistant|助手|ai)\s*[:：]", head, re.M | re.I)
    return bool(u and a)


def pick_mode(question, forced=None):
    if forced:
        return forced
    has_ent = bool(ENTITY.search(question))
    if has_ent and not AGG_HINT.search(question):
        return "lookup"          # 指向具体实体 → 最小窗口
    if AGG_HINT.search(question):
        return "gather"          # 问整体 → 全量实例
    return "search"              # 两者都不是 → 语义检索（打分器）


# 视图预算的**默认口径**：200K token（200K 仍在注意力舒适区）。
# 不传 budget 就按这个走；想不限得显式传一个更大的数。
DEFAULT_BUDGET_TOKENS = 200_000


def build_view(text, question, mode="auto", budget=None, use_ce=False,
               model_dir=None, topk=1):
    """返回 {mode, view, spans, note}
    spans 指回沉积层（行号），这是"下钻"的接口——今天只做到接口，没做交互"""
    text = normalize(text)
    sents = sentences(text)
    # auto 的**默认出口是 turns**——语料是回合格式就直接走主线；
    # 只有非回合语料（针型语料、k8s 配置等）才退回 lookup/gather/search。
    if mode == "auto":
        mode = "turns" if has_turn_marks(text) else pick_mode(question)
    else:
        mode = pick_mode(question, mode)

    # ---- lookup：定位实体，扩到最小窗口
    if mode == "lookup":
        m = ENTITY.search(question)
        if not m:
            return {"mode": "lookup", "view": "", "spans": [], "note": "问句里没有可定位的实体 → 请改用 gather 或转上层"}
        ent = f"{m.group(1)}-{m.group(2)}"
        hit = [s for s in sents if ent in s["text"]]
        if not hit:
            if use_ce:
                # 字面没命中 → 交给打分器（原构想的检索层）
                from retriever import retrieve
                docs = [x["text"] for x in sents]
                r = retrieve(docs, question, topk=topk, model_dir=model_dir)
                picked = [sents[i] for i, sc, st in r]
                return {"mode": "lookup", "view": "\n".join(x["text"] for x in picked),
                        "spans": [x["line"] for x in picked], "chars": sum(len(x["text"]) for x in picked),
                        "retriever": r[0][2] if r else None,
                        "scores": [round(sc, 3) for _, sc, _ in r if sc is not None],
                        "note": f"字面未命中 {ent}；由 BM25+CE 举证（得分见 scores），仍不确定则由上层判"}
            return {"mode": "lookup", "view": "", "spans": [], "not_found": True,
                    "note": f"沉积层中不存在 {ent} —— 视图为空，交由上层拒答（不要替它编）"}
        s0 = hit[0]
        return {"mode": "lookup", "view": s0["text"], "spans": [s0["line"]],
                "chars": len(s0["text"]), "note": "最小窗口 = 证据行本身（实测 10/10 的下界）"}

    # ---- search：语义检索（原构想的"打分器"位置）
    if mode == "search":
        docs = [x["text"] for x in sents]
        if not docs:
            return {"mode": "search", "view": "", "spans": [], "not_found": True, "note": "语料为空"}
        from retriever import retrieve
        r = retrieve(docs, question, topk=max(1, topk),
                     model_dir=model_dir if use_ce else None, use_ce=use_ce)
        picked = [sents[i] for i, _, _ in r]
        return {"mode": "search", "view": "\n".join(x["text"] for x in picked),
                "spans": [x["line"] for x in picked], "chars": sum(len(x["text"]) for x in picked),
                "retriever": r[0][2] if r else None,
                "scores": [round(sc, 3) for _, sc, _ in r if sc is not None],
                "note": "BM25 粗筛 + CE 精排选出的句子；分数低则由上层判不确定"}

    # ---- gather_turns：回合级整块入选（相关就整回合搬，绝不拆句）
    if mode == "turns":
        from retriever import BM25
        units = parse_turns(text)
        if not units:
            return {"mode": "turns", "view": "", "spans": [], "not_found": True}
        # 续说旁路：整个 viewkit 跳过（no-op），不产出视图。
        # 尾部本就是高注意力区，系统不做任何事；宿主照原样把对话发过去即可。
        if is_continuation(question):
            return {"mode": "turns", "view": None, "spans": [], "n_blocks": 0,
                    "chars": 0, "total_blocks": len(units), "view_tokens_est": 0,
                    "bypass": "passthrough", "truncated_last": looks_truncated(units[-1]),
                    "note": "续说类回复：目标内容在尾部高注意力区，viewkit 不产出视图（no-op）"}
        # Q = 最新用户输入（未显式给问句时自动取）
        q_auto = not question
        if q_auto:
            question, _ = latest_user_turn(text)
        if use_ce and model_dir:
            # 二级筛选：BM25 粗筛 → CE 逐回合精排（长回合分块取最大分）
            from retriever import rerank_turns
            ranked = rerank_turns(units, question, prefilter=20, model_dir=model_dir)
            scored = [(s if s is not None else 0.0, i) for i, s, _ in ranked]
            stage = "bm25+ce"
        else:
            bm = BM25(units)
            scored = bm.score(question)                 # [(score, idx)] 降序
            stage = "bm25"
        # 语言无关：同回合内出现「实体 id + 3~7 位数字」即视为事实回合
        FACT = re.compile(r"[A-Z]{2,3}-\d{3,6}[^\n]{0,80}?\d{3,7}")
        fact_turns = {i for i, u in enumerate(units) if FACT.search(u)}
        # 预算制（**token 口径**）：按相关度依次装入整回合，装不下整块跳过，绝不拆
        budget = DEFAULT_BUDGET_TOKENS if budget is None else budget
        if AGG_HINT.search(question):
            cand = [i for i in sorted(fact_turns, key=lambda i: -dict((j, s) for s, j in scored).get(i, 0))]
        else:
            cand = [i for sc, i in scored]
        keep, used, skipped = set(), 0.0, []
        for i in cand:
            L = est_tokens(units[i])
            if used + L > budget:
                skipped.append(i); continue
            keep.add(i); used += L
        keep = sorted(keep)                            # **输出按原文顺序**
        # 聚合题若漏掉了事实回合，必须**显式标残缺**，不能悄悄少算
        is_agg = bool(AGG_HINT.search(question))
        incomplete = is_agg and bool(set(skipped) & fact_turns)
        missing = sorted(set(skipped) & fact_turns) if is_agg else []
        if not keep:
            return {"mode": "turns", "view": "", "spans": [], "not_found": True,
                    "total_blocks": len(units),
                    "note": "无可用回合 —— 空视图，交由上层拒答（不猜）"}
        view = "\n\n".join(units[i] for i in keep)
        return {"mode": "turns", "view": view, "spans": keep, "n_blocks": len(keep),
                "chars": len(view), "total_blocks": len(units),
                "view_tokens_est": round(est_tokens(view)),
                "skipped": len(skipped), "budget_tokens": budget,
                "incomplete": incomplete, "missing_fact_turns": missing, "q": question[:120],
                "retriever": stage,
                "note": ("聚合所需的事实回合有 %d 个装不下 → 视图残缺，上层应拒答或加预算"
                         % len(missing)) if incomplete else
                        "整回合入选、按原文顺序拼接；预算装不下的整块跳过（不拆）"}

    # ---- gather：把所有同类型实例装进来（这是聚合能成立的前提）
    # 严格抽取：实体 + 数值必须有**量词或动词**挂钩，否则不算一条事实
    STRICT = re.compile(
        r"(?P<ent>[A-Z]{1,3}-\d{3,6}).{0,80}?"
        r"(?:\b(?:holds|retains|lists|reports|contains|runs|keeps|scales to|has)\s+(?P<v1>\d{3,7})"
        r"|(?P<v2>\d{3,7})\s+(?:entr\w*|replica\w*|shard\w*|record\w*|row\w*))", re.I)
    facts = []
    for s in sents:
        m = STRICT.search(s["text"])
        if not m:
            continue
        if not re.fullmatch(r"[A-Z]{2,3}-\d{3,6}", m.group("ent")):
            continue                      # 小写假实体（to-9216 之类）直接丢
        val = m.group("v1") or m.group("v2")
        facts.append({"ent": m.group("ent").upper(), "val": val,
                      "line": s["line"], "text": s["text"]})
    if not facts:
        return {"mode": "gather", "view": "", "spans": [], "not_found": True,
                "note": "没有抽到任何 (实体, 数值) —— 视图为空"}
    # 预算统一走 **token 口径**（与 turns 一致）；不传 budget 时用 DEFAULT_BUDGET_TOKENS
    if budget is None:
        budget = DEFAULT_BUDGET_TOKENS
    if budget:
        keep, total = [], 0.0
        for f in facts:
            L = est_tokens(f["text"])
            if total + L > budget and keep:
                break
            keep.append(f); total += L
        truncated = len(keep) < len(facts)
        facts = keep
    else:
        truncated = False
    view = "\n".join(f["text"] for f in facts)
    return {"mode": "gather", "view": view, "spans": [f["line"] for f in facts],
            "chars": len(view), "n_facts": len(facts), "truncated": truncated,
            "note": "全量实例视图（不是 top-k）；截断会发生则显式标注"}


CASES = [
    # (语料, 问题, 期望 mode, 期望 n_facts / 是否命中实体)
    ("corpus/calib/probe_hard/calib_128_hard.txt", "What is the entry count reported for archive NX-7001?", "lookup", 1),
    ("corpus/calib/probe_hard/calib_128_hard.txt", "What is the entry count reported for archive NX-9901?", "lookup", 0),
    ("corpus/calib/probe_hard/calib_128_hard.txt", "What is the total of all entry counts?", "gather", 20),
    ("corpus/calib/probe_hard5/calib_128_hard5.txt", "How many archives are described?", "gather", 5),
]


def self_test(root="."):
    ok = 0
    for corpus, q, want_mode, want_n in CASES:
        try:
            text = open(f"{root}/{corpus}", encoding="utf-8").read()
        except FileNotFoundError:
            print("  SKIP", corpus); continue
        r = build_view(text, q)
        n = r.get("n_facts", 1 if r.get("spans") else 0)
        good = (r["mode"] == want_mode) and (n == want_n)
        ok += good
        print(f"  {'✓' if good else '✗'} {q[:56]:<56} {r['mode']:<7} n={n}/{want_n} chars={r.get('chars', 0)}")
    print(f"\n自检 {ok}/{len(CASES)}")


def main():
    ap = argparse.ArgumentParser(description="二级视图构建器")
    ap.add_argument("--corpus")
    ap.add_argument("--ask")
    ap.add_argument("--mode", choices=["auto", "lookup", "gather", "search", "turns"],
                    default="turns",
                    help="默认 turns（对话回合主线）；传 auto 则由语料格式判断，非回合语料退回基础模式")
    ap.add_argument("--budget", type=int, default=DEFAULT_BUDGET_TOKENS,
                    help=f"turns 模式的 **token** 预算；装不下整块跳过（默认 {DEFAULT_BUDGET_TOKENS}）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--ce", action="store_true", help="开启 BM25+CE 检索层（需 FlagEmbedding + 本地模型）")
    ap.add_argument("--model", default="models/bge-reranker-v2-m3")
    a = ap.parse_args()

    if a.self_test:
        self_test(); return
    if not a.corpus:
        ap.error("需要 --corpus")
    # 不给 --ask 时：**Q = 最新一条用户输入信息块**（turns 的设计口径）
    if not a.ask and a.mode in ("auto", "turns"):
        a.mode = "turns"
    r = build_view(open(a.corpus, encoding="utf-8").read(), a.ask, a.mode, a.budget,
                   use_ce=a.ce, model_dir=a.model)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return
    bypass = r.get("bypass")
    head = f"模式: {r['mode']} | 视图 {r.get('chars', 0)} 字符 | 片段 {len(r['spans'])}"
    if bypass:
        head += f" | bypass={bypass}"
    print(head)
    print(f"说明: {r['note']}")
    print("-" * 60)
    view = r.get("view")
    if view is None:
        print("(no-op：目标已在高注意力区，不产出视图 —— 宿主照原样发对话)")
    else:
        print(view[:1200] or "(空)")


if __name__ == "__main__":
    main()
