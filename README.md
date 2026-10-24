# AI-AttentionSettlement

> **模型不是"读不懂"，是"没读到"。**
> **Models don't fail to understand — they fail to read.**

一个外置的、零训练的**上下文结算层**：每次提问时，以该提问为锚点对上下文做 span 级相关性打分，物化出一份紧凑的**二级视图**（re-prefill，携带坐标指针）供模型阅读；原文完整保留为可寻址的**沉积层**。零训练、不动模型内部、适配任意 API 模型。

An external, training-free **context-settlement layer** for LLMs. On every query, spans of the context are relevance-scored against the question; a compact **working view** is materialized and re-prefilled; the original text stays intact as an addressable **sediment layer**. Zero training, no model internals, works with any API model.

> **个人零预算研究项目**：全部实验用免费 API 额度完成（约百发/天量级），无任何算力采买；本仓库为前期研究与设计的存档，代码非生产级。
> **A personal, zero-budget research project**: all experiments ran on free API quotas (~a hundred calls/day); this repo archives a preliminary study and design, and is not production software.

## 快速开始 · Quickstart

```bash
python demo/run.py
```

零 API key、零第三方依赖、约 0.1 秒。现场演示：20 万字符语料蒸馏成 32 字符视图；整个聚合集合装进 1.2K 字符视图；问不存在的实体返回空视图、交由上层拒答，绝不替换成别的值。

Zero API keys, zero dependencies, ~0.1 s: a 200K-char corpus distilled to a 32-char view; the entire aggregation set inside a 1.2K-char view; a non-existent entity returns an empty view for the upper layer to refuse — no value substitution.

---

## 为什么 · Why

2026 年的旗舰模型普遍持有 128K–1M token 窗口，但实测行为显示的是**任务类型悬崖**，不是长度悬崖：

Modern LLMs hold 128K–1M token windows, yet measured behavior shows a **task-type cliff**, not a length cliff:

| 任务 Task（同一份 514K 字符语料，两个模型 same corpus, two models） | 得分 Score |
|---|---|
| 单事实检索 Single-fact retrieval（"NX-7001 的条目数是多少？"） | **20/20** 与 and **20/20** |
| 聚合 Aggregation（阈值计数 / 全量求和 count / sum） | 每组 **0–1 / 7** per battery |
| 缺席 Absence（问不存在的 id，正确 = 拒答 refuse） | **0/5**（被替换成同类型真实值 substitutes a real value） |

失败法医：聚合失败的根源是**枚举从未发生**——模型直接抛出一个已读值（89% 同型替换，我们称之为*就近读值替换*吸引子）。位置与顺序已被排除：打乱全部 20 根针不改变任何读数；删掉吸引子句，现象随之消失。回应不是"更聪明的模型"，而是一层知道**该把哪一小段推到它面前**的外挂——并且永远不破坏原文。

Failure forensics: aggregation fails because **enumeration never happens** — the model emits a single already-read value (89% same-type substitution; we call it *nearest-read-value substitution*). Position and order are ruled out: shuffling all 20 needles changes nothing; deleting the attractor sentence makes it disappear. The response is not a smarter model, but a layer that knows **which small piece to put in front of it** — and never destroys the original.

## 三条实测结论 · Three measured results

1. **最小充分视图 = 证据行本身。** 约 105 字符的一行，10/10 答对；标准 2K token 视图比所需大近 20 倍。在场即充分——顺序、位置、精排全部不影响（各排布臂全部 15/15）。
   **Minimal sufficient view = the evidence line itself.** A ~105-char line answers 10/10; a 2K-token view is ~20× larger than needed. Presence suffices — order, position and ranking do not matter (15/15 in all arrangement arms).
2. **视图修的是枚举，不是算术。** 把全部 5 个值放进 3.1K 字符视图，聚合从 1/5 → 3/5——五项全进了加法，残余错误只是一位算术。模型能否在这份全量视图上自己完成聚合，是待跑的判定实验。
   **Views fix enumeration, not arithmetic.** All 5 values in a 3.1K-char view moved aggregation 1/5 → 3/5 — all five entered the addition; the residual error was one digit. Whether the model can finish aggregation on its own over such a full-set view is the pending adjudication experiment.
3. **规模不是瓶颈。** 1.43M token / 5,000 回合语料上，1/8 预算视图 **1.1 秒**组装完成（BM25、零依赖），12/12 命中；20 万字符真实配置语料检索蒸馏出 **32 字符视图**。
   **Scale is not the bottleneck.** On a 1.43M-token / 5,000-turn corpus, a 1/8-budget view assembles in **1.1 s** (BM25, zero dependencies), 12/12 QA hit; a 200K-char real-world config corpus distills to a **32-char view**.

一条保留可见的诚实翻案：早期"聚合 ≈ 0%"的读数有一部分是**我们自己造成的**——`max_tokens=40` 截断了枚举输出。放开输出上限后，其中一个模型在 130K 全档枚举全部 20 项并正确求和。此后每一条"模型做不到"的主张都先过自己的仪器复核。

One honest correction we keep visible: an early "aggregation ≈ 0%" reading was partly self-inflicted — `max_tokens=40` truncated the enumeration. With the output budget restored, one model enumerates all 20 items at 130K and sums them correctly. Every "model can't" claim is re-audited against our own instrumentation first.

## 仓库内容 · What ships here

```
viewkit/     视图构建器 view builder — turns / lookup / gather / search 四模式，
             BM25 内核（仅标准库），可选 CE 精排（BGE-reranker-v2-m3）
demo/        一条命令 one command、零 API、<10 秒（python demo/run.py）
docs/        研究报告 + 系统设计（中文 Chinese）
results/     精选结果 JSON — 每个数字可溯源 every number traceable（results/INDEX.md）
corpus/      实验语料 corpora + DATA_SOURCES.md（来源与授权 provenance & license）
```

## 定位 · Positioning

（对照 2024–2026 文献核查 verified against 2024–2026 literature）

| 系统 System | 每问重算 per-query | 窗口内 in-window | 物化视图 view | 指针 pointers | 无损沉积 lossless | 下钻闭环 drill-down |
|---|---|---|---|---|---|---|
| LongLLMLingua | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| RAM (2602.01840) | ✅ | ✅ | △ | ❌ | ❌ | ❌ |
| Context-Picker | ✅ | ❌ | ✅ | ❌ | △ | ❌ |
| SelfElicit | ✅ | ✅ | ❌ | ❌ | ✅ | ❌ |
| NSA / MoBA（模型内 in-model） | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| 平台 compaction（context editing 等） | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| **本仓库 this repo** | ✅ | ✅ | ✅ | ✅ | ✅ | 🔶 已预注册，未建 pre-registered |

*所有人都在改"模型这一轮读什么"；没有谁保证"选错了还能回去重读"。*下钻回路（按指针的救援式重读）是差异化主张——已设计、已预注册、如实标注未测。

*Everyone changes what the model reads this turn; nobody guarantees it can go back and re-read when the choice was wrong.* The drill-down loop (pointer-based rescue re-read) is the differentiating claim — specified, pre-registered, honestly marked untested.

成本注记：每轮重选在 **V < 折扣 × C**（视图尺寸小于缓存折价后的上下文）时反而更便宜；破坏性压缩靠摊销经济与优雅降级活着，不靠质量。

Cost note: per-turn re-selection beats carrying a cached context whenever `V < discount × C`; destructive compaction survives on amortization economics and graceful degradation, not on quality.

## 状态与局限 · Status & limitations

- 前期研究 + 设计 + demo。实测模型 Models：GLM-4.5-Air、GLM-4.7-Flash、DeepSeek-flash、NVIDIA Nemotron 3.5 Super VL（OpenRouter 免费档 free tier）。
- 未测部件如实标注 untested parts are marked；我们自己的两条早期结论被数据推翻时做了**书面撤回**（保留在 two early conclusions were **retracted in writing**, kept in `docs/`）。
- 公开前需逐条复核 arXiv 引用 citations re-verification pending。

**完整中文文档 Full docs → [`docs/`](docs/)**

许可 License：代码与文档 [MIT]；语料 corpora 受 [`corpus/DATA_SOURCES.md`](corpus/DATA_SOURCES.md) 约束。
