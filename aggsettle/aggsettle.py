#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
aggsettle — 确定性结算器：把"从长文里数数"这件事从模型手里拿回来

为什么会有这个东西
    2026-10-21 的实测：模型在单事实上 20/20，在聚合（计数/求和/极值）上 0/6。
    失败不是算错，是**枚举不全**——它只看到 5 条里的 1 条，或 20 条里的 1 条。
    结论：聚合不该交给模型，该交给能穷举的代码。

它做什么
    1) 把语料切句 → 抽「实体 + 数值 + 单位」三元组（正则，可配）
    2) 按问题类型路由：lookup / count / sum / max / min / ratio
    3) **在代码里做聚合**，输出答案 + 每一个被用到的证据行
    4) 找不到实体 → 明确拒答（NOT_FOUND），绝不编一个值

用法
    python aggsettle.py --corpus corpus/calib/probe_hard/calib_128_hard.txt --ask "How many archives hold more than 7000 entries?"
    python aggsettle.py --corpus <path> --ask "What is the total of all entry counts?"
    python aggsettle.py --corpus <path> --ask "What is the entry count for NX-7001?"
    python aggsettle.py --self-test          # 用本仓实验语料跑回归

设计约束
    - 只用标准库（无依赖、可拷走）
    - 每个答案必须带证据行；给不出证据就拒答
    - 不调用任何模型
"""
import argparse
import json
import re
import sys

# ---------------------------------------------------------------- 摄取层规范化
_DASH = re.compile(r"[\u2010-\u2015\u2212]")          # 各种长短横线统一
_SPACED_ID = re.compile(r"\b([A-Za-z]{1,3})\s+(\d{3,6})\b")   # 'NX 7001' → 'NX-7001'
_OCR = str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1", "|": "1"})


def normalize_text(t):
    """摄取层：把 PDF/OCR/录入 的常见破坏先归一再抽取。
    只做**形态**归一，不改语义；归一失败的行原样保留。"""
    t = _DASH.sub("-", t)
    t = _SPACED_ID.sub(r"\1-\2", t)
    # OCR：仅当整个 token 长得像 ID 时，才把字母数字混写里的 O/I/l 换成 0/1
    def _fix(m):
        tok = m.group(0)
        return tok.translate(_OCR)
    t = re.sub(r"\b[A-Za-z]{1,3}-[0-9OoIl|]{3,6}\b", _fix, t)
    return t


def parse_entity(raw):
    """'NX-70O1' → 'NX-7001'；无法解析返回 None"""
    m = re.match(r"([A-Za-z]{1,3})-(\d{3,6})$", raw)
    if not m:
        return None
    return f"{m.group(1).upper()}-{m.group(2)}"


# ---------------------------------------------------------------- 事实抽取
# 三元组：(实体, 数值, 单位, 原文行)
PATTERNS = [
    re.compile(r"(?P<ent>[A-Z]{1,3}-\d{3,6})\b[^.\n]{0,80}?\b(?P<val>\d{3,7})\s*(?P<unit>entr\w*|replica\w*|shard\w*|record\w*|row\w*)", re.I),
    re.compile(r"(?P<ent>[A-Z]{1,3}-\d{3,6})\b[^.\n]{0,40}?\b(?:holds|retains|lists|reports|contains|runs|keeps|scales to|has)\s+(?P<val>\d{3,7})", re.I),
]
NUM = re.compile(r"(?<!\d)(\d{3,7})(?!\d)")


def extract_facts(text, normalize=True):
    """返回 [{'ent','val','unit','line'}]，同一 (ent,val) 去重"""
    if normalize:
        text = normalize_text(text)
    facts, seen = [], set()
    for line in text.split("\n"):
        s = line.strip()
        if not s or len(s) < 12:
            continue
        got = None
        for p in PATTERNS:
            m = p.search(s)
            if m:
                got = (m.group("ent").upper(), int(m.group("val")), (m.groupdict().get("unit") or "").lower())
                break
        if not got:
            continue
        ent, val, unit = got
        ent = parse_entity(ent) or ent.upper()
        if (ent, val) in seen:
            continue
        seen.add((ent, val))
        facts.append({"ent": ent, "val": val, "unit": unit, "line": s[:160]})
    return facts


# ---------------------------------------------------------------- 问题路由
def _num_after(q, words=("more than", "greater than", "over", "above", "fewer than", "less than", "below", "under")):
    for w in words:
        m = re.search(w + r"\s+(\d{2,7})", q, re.I)
        if m:
            return w, int(m.group(1))
    return None, None


def route(q):
    ql = q.lower()
    if re.search(r"\bbetween\s+\d+\s+and\s+\d+\b", ql) and "how many" in ql:
        return "range"
    if re.search(r"how many|number of .*\b(?:archives|items|entries|records|files)\b", ql) and (_num_after(q)[0] or "described" in ql):
        return "count"
    if re.search(r"\btotal\b|\bsum\b|in total|altogether", ql):
        return "sum"
    if re.search(r"\blargest\b|\bmaximum\b|\bmax\b|\bhighest\b", ql):
        return "max"
    if re.search(r"\bsmallest\b|\bminimum\b|\bmin\b|\blowest\b", ql):
        return "min"
    m = re.search(r"\b([A-Z]{1,3}-\d{3,6})\b", q)
    if m:
        return "lookup"
    return "unrouted"      # 不认识的问法一律不猜：交由上层转模型或拒答


def verify(ans, evidence):
    """证据链校验：答案值必须能从中抽出（count/range 校验条数；其余校验值出现）"""
    kind = ans.get("kind")
    if ans.get("refused"):
        return True
    ev = evidence or []
    if kind in ("count", "range"):
        listed = [e for e in ev if "=" in e]
        if not listed:                      # describe 型：证据是实体名列表
            listed = [e for e in ev if e]
        return int(ans["answer"]) == len(listed)
    if kind == "sum":
        vals = [int(e.split("=")[1]) for e in ev if "=" in e]
        return sum(vals) == int(ans["answer"])
    # lookup / max / min：值必须出现在证据文本里
    return any(str(ans["answer"]) in e for e in ev)


def answer(q, facts):
    kind = route(q)
    base = {"question": q, "kind": kind, "n_facts": len(facts)}

    if kind == "lookup":
        ent = re.search(r"\b([A-Z]{1,3}-\d{3,6})\b", q).group(1).upper()
        hit = [f for f in facts if f["ent"] == ent]
        if not hit:
            return {**base, "answer": "NOT_FOUND", "refused": True,
                    "note": f"语料中不存在实体 {ent}；拒答而非替换",
                    "evidence": []}
        f = hit[0]
        return {**base, "answer": str(f["val"]), "refused": False, "evidence": [f["line"]]}

    if kind == "count":
        w, thr = _num_after(q)
        if "described" in q.lower() or "are described" in q.lower():
            ents = {f["ent"] for f in facts}
            return {**base, "answer": str(len(ents)), "refused": False,
                    "evidence": sorted(ents)}
        if thr is None:
            return {**base, "answer": "NEED_THRESHOLD", "refused": True, "evidence": []}
        cmpfn = (lambda v: v > thr) if w in ("more than", "greater than", "over", "above") else (lambda v: v < thr)
        sel = [f for f in facts if cmpfn(f["val"])]
        return {**base, "answer": str(len(sel)), "refused": False,
                "evidence": [f"{f['ent']}={f['val']}" for f in sel]}

    if kind == "range":
        m = re.search(r"between\s+(\d+)\s+and\s+(\d+)", q, re.I)
        lo, hi = int(m.group(1)), int(m.group(2))
        sel = [f for f in facts if lo <= f["val"] <= hi]
        return {**base, "answer": str(len(sel)), "refused": False,
                "evidence": [f"{f['ent']}={f['val']}" for f in sel]}

    if kind == "sum":
        return {**base, "answer": str(sum(f["val"] for f in facts)), "refused": False,
                "evidence": [f"{f['ent']}={f['val']}" for f in facts]}

    if kind in ("max", "min"):
        if not facts:
            return {**base, "answer": "NOT_FOUND", "refused": True, "evidence": []}
        f = (max if kind == "max" else min)(facts, key=lambda x: x["val"])
        return {**base, "answer": str(f["val"]), "refused": False, "evidence": [f["line"]]}

    # 未识别问法：拒答（可审计），不猜测
    return {**base, "answer": "UNROUTED", "refused": True,
            "note": "问法不在路由表内；不猜测，交由上层（模型/问用户）",
            "evidence": []}


# ---------------------------------------------------------------- 回归
CASES = [
    # (语料, 问题, 期望答案)
    ("corpus/calib/probe_hard/calib_128_hard.txt",
     "How many archives in this document hold more than 7000 entries?", "6"),
    ("corpus/calib/probe_hard/calib_128_hard.txt",
     "What is the total of all entry counts reported for the archives in this document?", "102495"),
    ("corpus/calib/probe_hard/calib_128_hard.txt",
     "What is the largest entry count reported for any archive in this document?", "9564"),
    ("corpus/calib/probe_hard/calib_128_hard.txt",
     "What is the entry count reported for archive NX-7001?", "3242"),
    ("corpus/calib/probe_hard/calib_128_hard.txt",
     "What is the entry count reported for archive NX-9901?", "NOT_FOUND"),
    ("corpus/calib/probe_hard5/calib_128_hard5.txt",
     "What is the total of all entry counts reported for the archives in this document?", "30498"),
    ("corpus/calib/probe_hard5/calib_128_hard5.txt",
     "How many archives in this document hold fewer than 3000 entries?", "1"),
    ("corpus/calib/probe_hard5/calib_128_hard5.txt",
     "How many archives are described in this document?", "5"),
    ("corpus/calib/probe_type/calib_128_type.txt",
     "How many replicas does service SX-9901 run?", "NOT_FOUND"),
]


def self_test(root="."):
    ok = 0
    for corpus, q, want in CASES:
        path = f"{root}/{corpus}"
        try:
            text = open(path, encoding="utf-8").read()
        except FileNotFoundError:
            print(f"  SKIP {corpus}（缺文件）"); continue
        r = answer_checked(q, extract_facts(text))
        good = str(r["answer"]) == want
        ok += good
        print(f"  {'✓' if good else '✗'} {q[:62]:<62} → {r['answer']:<10} (期望 {want})")
    print(f"\n自检 {ok}/{len(CASES)}")


def main():
    ap = argparse.ArgumentParser(description="确定性结算器：检索 + 抽取 + 代码聚合")
    ap.add_argument("--corpus", help="语料文件")
    ap.add_argument("--ask", help="问题")
    ap.add_argument("--facts", action="store_true", help="只列出抽到的事实")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()

    if a.self_test:
        self_test(); return
    if not a.corpus:
        ap.error("需要 --corpus")

    facts = extract_facts(open(a.corpus, encoding="utf-8").read())
    if a.facts:
        print(json.dumps(facts, ensure_ascii=False, indent=1)); return
    if not a.ask:
        print(json.dumps({"n_facts": len(facts), "sample": facts[:3]}, ensure_ascii=False, indent=1)); return

    print(json.dumps(answer_checked(a.ask, facts), ensure_ascii=False, indent=1))


def answer_checked(q, facts):
    a = answer(q, facts)
    ev = a.get("evidence") or []
    if not verify(a, ev):
        return {**a, "answer": "EVIDENCE_MISMATCH", "refused": True,
                "note": "答案无法从证据行复现，按失败处理"}
    return a


if __name__ == "__main__":
    main()
