# AI-AttentionSettlement

> **Models don't fail to understand — they fail to read.**
> 中文版 → [README.md](README.md)

An external, training-free **context-settlement layer** for LLMs. On every query, spans of the context are relevance-scored against the question; a compact **working view** is materialized and re-prefilled; the original text stays intact as an addressable **sediment layer**; formalizable tasks (count / sum / min / max / lookup) are settled by deterministic code instead of the model.

Zero training. Zero model internals. Works with any API model.

## Quickstart

```bash
python demo/run.py
```

Zero API keys, zero dependencies, ~0.1 s. Live in this run: a 200K-char corpus distilled to a 32-char view; the entire aggregation set inside a 1.2K-char view; count / sum / lookup settled by code with evidence rows; a clean `NOT_FOUND` refusal for a non-existent entity (no value substitution).

---

## Why

Modern LLMs hold 128K–1M token windows, yet measured behavior shows a **task-type cliff**, not a length cliff:

| Task (same 514K-char corpus, two models) | Score |
|---|---|
| Single-fact retrieval ("what is the value of NX-7001?") | **20/20** and **20/20** |
| Aggregation (threshold count / total sum) | **0–1 of 7** per battery |
| Absence (ask for a non-existent id — correct = refuse) | **0/5** (substitutes a real same-type value) |

Failure forensics: aggregation fails because **enumeration never happens** — the model emits a single already-read value (89% same-type substitution, an attractor we call *nearest-read-value substitution*). Position and order are ruled out: shuffling all 20 needles changes nothing; deleting the attractor sentence makes it disappear.

The response is not a smarter model, but a layer that knows **which small piece to put in front of it** — and that never destroys the original.

## Three measured results

1. **Minimal sufficient view = the evidence line itself.** A ~105-character line answers 10/10; the standard 2K-token view is ~20× larger than needed. Presence suffices — order, position and ranking within the view do not matter (15/15 in all arrangement arms).
2. **Views fix enumeration; code fixes arithmetic.** Putting all 5 values into a 3.1K-char view moved aggregation 1/5 → 3/5 (all five entered the addition; the residual error was one arithmetic digit). A deterministic settler finishes the job.
3. **Scale is not the bottleneck.** On a 1.43M-token / 5,000-turn corpus, a 1/8-budget view is assembled in **1.1 s** (BM25, zero dependencies) with 12/12 QA hit; on a 200K-char real-world config corpus, retrieval distills to a **32-character view**.

One honest artifact we keep visible: an early "aggregation ≈ 0%" reading was partly self-inflicted — `max_tokens=40` truncated the enumeration. With output budget restored, one model enumerates all 20 items at 130K and sums them correctly. Every "model can't" claim was re-audited for our own instrumentation first.

## What ships here

```
viewkit/     view builder — turns / lookup / gather / search modes,
             BM25 core (stdlib only), optional CE rerank (BGE-reranker-v2-m3)
aggsettle/   deterministic settler — formalizable tasks never enter the model;
             UNROUTED fallback refuses to guess
demo/        one command, zero API, <10s   (python demo/run.py)
docs/        research report + system design (Chinese)
results/     curated result JSONs — every number above is traceable here (see results/INDEX.md)
corpus/      experiment corpora + DATA_SOURCES.md (provenance & license notes)
```

## Positioning (verified against 2024–2026 literature)

| System | per-query | in-window | materialized view | pointers | lossless sediment | drill-down loop |
|---|---|---|---|---|---|---|
| LongLLMLingua | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| RAM (2602.01840) | ✅ | ✅ | partial | ❌ | ❌ | ❌ |
| Context-Picker | ✅ | ❌ | ✅ | ❌ | partial | ❌ |
| SelfElicit | ✅ | ✅ | ❌ | ❌ | ✅ | ❌ |
| NSA / MoBA (in-model) | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Platform compaction | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| **this repo** | ✅ | ✅ | ✅ | ✅ | ✅ | 🔶 pre-registered, not yet built |

*Everyone changes what the model reads this turn; nobody guarantees it can go back and re-read when the choice was wrong.* The drill-down loop (pointer-based rescue re-read) is the differentiating claim — it is specified, pre-registered, and honestly marked untested.

Cost note: per-turn re-selection beats carrying a cached context whenever `V < discount × C` (view size below the cache-discounted context); destructive compaction survives on amortization economics and graceful degradation, not on quality.

## Status & limitations

- Preliminary study + design + demo. Models measured: GLM-4.5-Air, GLM-4.7-Flash, DeepSeek-flash, NVIDIA Nemotron 3.5 Super VL (OpenRouter free tier).
- Untested parts are marked as such; two of our own early conclusions were retracted in writing when the data overturned them (kept in `docs/`).
- Citations re-verification pass pending before publication.

**Full documentation in Chinese → [`docs/`](docs/)**

License: MIT for code & docs (see [LICENSE](LICENSE)); corpora are governed by [`corpus/DATA_SOURCES.md`](corpus/DATA_SOURCES.md).
