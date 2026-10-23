# 语料来源与授权说明

本仓库的实验语料分四类，来源与处理方式如下。

## 1. 论文衍生针语料（`corpus/calib/`）

`calib_8k.txt` … `calib_full.txt`（长度阶梯）与 `probe_*/`（各实验电池变体）。

- **基底文本**取自以下公开 arXiv 论文的正文（排除参考文献与附录）：
  - DeepSeek-V2（2405.04434）、DeepSeek-V3（2412.19437）、DeepSeek-R1（2501.12948）、
    Native Sparse Attention（2502.11089）、DeepSeek-V3.2（2512.02556）、
    Conditional Memory via Scalable Lookup（2601.07372）
- **变换**：页段抽取 → 行切分 → **合成针注入**（`NX-xxxx` 事实行为本项目原创合成内容，
  与原论文无关）→ 按实验设计做散点/聚簇/密度/打乱等布局变体。
- 每份语料在实验 manifest 中登记 SHA256 与构建脚本；构建脚本随旧研究仓迁移（`fetch_arxiv_pdf.py`、
  `build_calib_corpus.py`、`build_scattered.py` 等），可从 arXiv 原文一键重建。
- **用途与边界**：仅用于非商业研究的实验复现，逐篇注明出处。各论文在 arXiv 上的许可
  不一（每篇 abs 页有 "view license" 链接；已抽查 DeepSeek-V3 = arXiv 非独占分发许可 1.0，
  第三方再分发未获明示授权），发布前逐篇复核并做最终取舍（保留语料+归属+可移除，或只保留
  重建脚本）；若权利方有异议，请开 issue，我们将移除对应语料。

## 2. 真实配置语料（`demo/corpus/real_k8s_t2.txt`）

来源为 GitHub `k8s-examples`（Apache-2.0）：195 个 manifest 按 `===== FILE: <path> =====`
分节拼接，文件路径名原样保留。200,403 字符 ≈ 50K token。

## 3. 合成长对话语料（三档 415K / 838K / 1.43M token）

脚本生成（`build_corpus_1m.py` 系，seed 入 manifest），无第三方版权内容；
用于 turns 模式的规模与预算悬崖测试。

## 4. demo 内置语料（`demo/run.py` 现场生成）

seed=20261024 的合成针语料，零外部依赖，用于无 API 演示；
其中部分数值（3242 / 9267 / 6713 / 4472 …）复刻自录得实验以保持叙事连续。

---

**私人数据声明**：实验期间使用过的真实对话语料（119 回合 GLM 会话）**不随仓分发**；
相关读数（r 预算悬崖 18 题）保留在 `results/eval_ratio.json`，语料本身可用合成回合语料替代复现。
