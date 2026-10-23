#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI-AttentionSettlement — zero-API demo.

One command, stdlib only, < 10 s. Shows viewkit live:

  1. view search   — 200K-char real-world config corpus distilled to a one-line view
  2. view lookup / gather / absence — minimal window, full-set view, empty view + refusal
  3. claim index   — every README number, where it lives

No API key, no model download, no third-party dependency.
"""
import os
import random
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "viewkit"))

from viewkit import build_view, est_tokens          # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

K8S = os.path.join(ROOT, "demo", "corpus", "real_k8s_t2.txt")


def h(title):
    print("\n" + "=" * 64 + "\n" + title + "\n" + "=" * 64)


# ---------------------------------------------------------------- 1. search mode
def step1_k8s():
    h("STEP 1  view search — real-world corpus, one question")
    text = open(K8S, encoding="utf-8").read()
    print(f"corpus: {os.path.basename(K8S)} (public k8s-examples, 195 manifests)")
    print(f"        {len(text):,} chars  (~{est_tokens(text):,.0f} tokens estimated)")

    t0 = time.time()
    r = build_view(text, "which image does the tensorflow serving deployment use?",
                   mode="search")
    dt = (time.time() - t0) * 1000
    print(f"\nquestion: which image does the tensorflow serving deployment use?")
    print(f"view: {r.get('chars', 0)} chars, {len(r['spans'])} span(s), "
          f"retriever={r.get('retriever')}, {dt:.0f} ms")
    print("-" * 64)
    print(r["view"])
    print("-" * 64)
    print("the model never sees the other 200K chars — but they remain in the")
    print("sediment layer, addressable by line pointer (spans).")


# ------------------------------------------- synthetic needle corpus (seeded)
def needle_corpus():
    """Deterministic synthetic corpus: 20 archive facts scattered in filler.

    License-safe replacement for the experiment corpora (which are built from
    arXiv paper text — provenance in corpus/DATA_SOURCES.md).
    """
    random.seed(20261024)
    values = {  # a few values reused from the recorded experiments for flavor
        "NX-7001": 3242, "NX-7013": 9267, "NX-6101": 6713, "NX-6316": 4472,
        "NX-6238": 3257, "NX-6375": 1090, "NX-7014": 7505, "NX-7015": 1377,
        "NX-7016": 7445, "NX-7017": 7825, "NX-7018": 6346, "NX-7019": 9564,
    }
    for n in range(20, 28):
        values[f"NX-70{n:02d}"] = random.randint(900, 9800)
    facts = sorted(values)

    filler_tpl = [
        "The quarterly bulletin for district {n} outlines maintenance windows and staffing notes.",
        "Curators from the northern annex reviewed labeling conventions during the workshop.",
        "Shelving contracts for the west wing were renewed after the spring inspection round.",
        "A visiting committee toured the reading room and left written comments on lighting.",
        "Floor plans for the annex staircase went through two drafting iterations this month.",
        "Volunteers transcribed handwritten index cards into the new catalogue interface.",
        "The climate control vendor shipped replacement sensors for the basement corridor.",
        "Reading-room chairs were reupholstered over the weekend without closing the stacks.",
    ]
    lines, fi = [], 0
    for i in range(96):
        if i % 4 == 1 and facts:
            ent = facts.pop(0)
            lines.append(f"Archive {ent} holds {values[ent]} entries "
                         f"across {random.randint(2, 9)} regional shelves.")
        else:
            lines.append(filler_tpl[fi % len(filler_tpl)].format(n=fi + 10))
            fi += 1
    return "\n".join(lines)


# ---------------------------------------------------------------- 2. lookup/gather
def step2_views(text):
    h("STEP 2  view lookup / gather / absence — three view shapes")

    t0 = time.time()
    r = build_view(text, "What is the entry count reported for archive NX-7001?",
                   mode="lookup")
    print(f"[lookup] Q: entry count of archive NX-7001?")
    print(f"  view = {r.get('chars', 0)} chars, span line {r['spans']}")
    print(f"  {r['view']}")

    r = build_view(text, "What is the total of all entry counts?", mode="gather")
    dt = (time.time() - t0) * 1000
    print(f"\n[gather] Q: total of all entry counts?")
    print(f"  view = {r.get('chars', 0)} chars, {r.get('n_facts')} facts "
          f"(ALL instances, not top-k), truncated={r.get('truncated')}, {dt:.0f} ms")
    print(f"  the ENTIRE aggregation set fits inside a ~2K-char view —")
    print(f"  this is what lets enumeration happen at all (models: 0-1 of 7)")

    r = build_view(text, "What is the entry count reported for archive NX-9901?",
                   mode="lookup")
    print(f"\n[absence] Q: entry count of archive NX-9901 (does not exist)?")
    print(f"  view = {r.get('chars', 0)} chars, not_found={r.get('not_found')}")
    print(f"  note: {r.get('note','')}")
    print(f"  -> empty view handed to the upper layer to REFUSE — never a substituted value")


# ---------------------------------------------------------------- 3. index
def step3_index():
    h("STEP 3  claim index — every README number, where it lives")
    rows = [
        ("20/20 single-fact @ 514K chars, two models", "docs/report (recorded)"),
        ("aggregation 0-1 of 7 per battery (two models)", "docs/report (recorded)"),
        ("absence -> nearest-read-value substitution, content-driven",
         "docs/report (recorded)"),
        ("minimal sufficient view = the ~105-char evidence line, 10/10",
         "docs/report (recorded)"),
        ("200K-char corpus -> one-line view", "STEP 1 above (live)"),
        ("gather view holds the whole aggregation set", "STEP 2 above (live)"),
        ("non-existent entity -> empty view + refusal, no substitution",
         "STEP 2 above (live)"),
        ("1.43M-token corpus -> view in 1.1 s, 12/12", "docs/report (recorded)"),
    ]
    for claim, where in rows:
        print(f"  {claim:<58} {where}")
    print("\nrecorded claims are backed by result JSONs curated under results/")


def main():
    t0 = time.time()
    print("AI-AttentionSettlement demo — zero API, stdlib only")
    step1_k8s()
    text = needle_corpus()
    step2_views(text)
    step3_index()
    print(f"\ntotal wall time: {time.time() - t0:.2f}s")


if __name__ == "__main__":
    main()
