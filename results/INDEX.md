# results/ 索引 —— 每条主张 ↔ 证据文件

> 文件统一 schema：`date / stage / model / corpus_hash / details[]`，
> `details` 内逐题记录 `pair / want / got / raw / hit / usage`。
> 对应叙述见 `docs/research-report.md` 与 `demo/run.py` STEP 4。

## 任务类型悬崖（硬语料 128K 档散点，513,381 字符，20 针，5 种措辞）

| 主张 | 文件 |
|---|---|
| 单事实 20/20（两模型） | `rep_glm45_hard_L1.json`、`rep_n35_hard_L1.json` |
| 阈值计数崩（真值 6） | `rep_glm45_hard_L2.json`、`rep_n35_hard_L2.json` |
| 全量求和崩（真值 102,495） | `rep_glm45_hard_L3.json`、`rep_n35_hard_L3.json` |
| 5 种聚合问法 0/5 与 1/5 | `rep_glm45_hard_AGG5.json`、`rep_n35_hard_AGG5.json` |
| 缺席档：N3.5 4/5 vs glm-4.5-air 0/5 | `rep_glm45_hard_L0.json`、`rep_n35_hard_L0.json` |
| 聚合失败对打乱稳健（20/20 针位置换不变） | `rep_g45_shuf_AGG5.json`、`rep_g45_shuf_L2.json`、`rep_g45_shuf_L3.json` |
| 五针长度曲线（16K–128K，非单调） | `rep_glm45_h5_16k/64k.json`、`rep_glm45_u_32k/128.json`、`rep_n35_hard5_32k.json` |
| 枚举重编码（聚合各格枚举均值 0.0–0.6，满值 5） | `reencode_all.json` |

## 吸引子（nearest-read-value substitution）

| 主张 | 文件 |
|---|---|
| ① 原档：5/5 答 9267（语料真值 NX-7013） | `rep_g45_anchor_orig.json` |
| ② 打乱 20/20 针位：仍 5/5 答 9267（内容驱动） | `rep_g45_shuf_L0.json` |
| ③ 删掉 9267 针：吸引子消失 → 9 / 9902（问句 id 回声）/ 9 | `rep_g45_no9267_L0.json` |
| 类型驱动（替换 9 次同型 8 次，89%） | `rep_g45_type.json` |

## 视图与换场

| 主张 | 文件 |
|---|---|
| 主关口 H₂′ 105 格（①前置/②居中/③结尾/④打乱/⑤高亮/⑦直答/⑧′窗口/⑨原序） | `view_arms.json` |
| 视图尺寸 A 试验（105 字符 → 10/10） | `view_size.json` |
| 2×2：聚簇×全档 2/5、聚簇×视图 3/5（视图修枚举不修算术） | `rep_g45_aggclust_full.json`、`rep_g45_aggclust_view.json`（散点×全档 = `rep_glm45_hard_AGG5.json`） |
| 电池 A（glm-4.7-flash 密簇：31 错误全单值泄漏，30 次同一值 4472） | `anchor_arm_adj2.json`、`anchor_arm_adj2h.json`、`anchor_arm_adj2k.json` |
| 相对预算悬崖 r=0.25/0.20（119 回合真实语料 18 题） | `eval_ratio.json` |

## 指称侧在场（T3 resolver）

| 主张 | 文件 |
|---|---|
| R4 LLM 关键格 4/9，Wilson CI [18.9%, 73.3%] 排除"LLM 可靠解" | `t3_r4.json` |
| R0–R5 五臂 + 弃权重读（R2 静默答错 0 / 覆盖率 68%） | `t3_resolver.json` |

## 真实载体与锚

| 主张 | 文件 |
|---|---|
| 注入判别 23/26 = 88.5%：强塌排除（裕量 2.2pp）、强保护未确证（差 1.4 题） | `inject16_direct.json` |
| 锚反向臂（散文 40% / 仅键名 40% / 空边界 55% / 边界带 id 75%） | `anchor_arm.json` |

## 翻案与纪律

| 主张 | 文件 |
|---|---|
| max_tokens 假失败：40→200→1500 三档，1500 时枚举 20 项算对 | `rep_ds_A2_L3_200.json` vs `rep_ds_A2_L3_1500.json` |
| DS 复现电池：视图 1/7、全档 2/7 | `rep_ds_rep_view_1-3.json`、`rep_ds_rep_full_1-3.json` |
| 第 0 步分歧检验（三问 Jaccard，动工闸门） | `step0_jaccard.json` |
| 基座天花板探测（16K 直答 10 针） | `ceiling_probe.json` |

## 其余记录（未随仓收录，可按需索取）

真实任务轴 k8s T2 系列（`realtask_t2*`）、DeepSeek 复现全套（`rep_ds_*` 其余）、锚阶梯（`anchor_arm*` 其余）、768K 长档、代码单元准备（`code_units_prep.json`）。语料对应关系见 `corpus/DATA_SOURCES.md`。
