# Evaluation Results

## 1. Evaluation Setup

本项目评价城市设计前期研究 Agent 的决策、专业输出与运行表现。使用冻结的 **Dataset V1.0（10 cases）**；数据输入、人工 Ground Truth 和固定 Rubric 在迭代中保持不变。每次完整运行均按顺序执行十个 Case，各一次，不补跑或替换较差结果。

评价分为三层，分别汇报，**不计算 Overall Score**：

- **A — Decision & Workflow**：规则与预期行为检查，覆盖入口判断、案例必要性、研究循环与 Completion。
- **B — Quality**：固定 1–5 Rubric 的 LLM-as-Judge，按 Case 的 evaluation_focus 调用；同时进行少量人工抽检。
- **C — Operational**：Agent runtime、真实 SDK calls、tokens 和失败，Judge 消耗单独统计。

指标本来不适用记 **N/A**；本来适用但没有足够输出或 Judge 失败记 **unavailable**；只有真实可评价输出才进入 Judge 并记录 **scored**。质量均值只统计 scored，N/A 与 unavailable 均不进入分母。下游失败不会取消已有专业输出的评分资格。

正式 Evaluation 使用 Eval-only **image quota override**：真实 Image Generation 关闭，image_calls=0；Concept 文本逻辑照常执行，Case 02 的固定输入图片照常用于多模态理解。真实图片生成已在独立 Smoke 中验证，本报告不包含 Image Quality benchmark，Judge 不因 quota 主动跳过图片而扣分。

完整定义见 [Evaluation Framework](evaluation-framework.md) 与 [Dataset Design](dataset-design.md)。原始运行资料位于被 Git 忽略的 outputs/evals/，下面的目录名用于本地证据定位，不要求公开本地日志或凭据。

## 2. Initial Baseline

初始正式 Baseline：**v0.1-baseline / 527909a**，运行目录 `baseline-final-quota-20261007-011740`，模型为 `qwen3.7-flash-2026-07-15`。

| Metric | Initial Baseline |
|---|---:|
| Info Sufficiency Accuracy | 30%（3/10） |
| Completion | 10%（1/10） |
| Report completed | 0 |
| ask_user early-stop | 8 |
| Agent execution failures | 2（20%） |
| Site Analysis / Groundedness valid_cases | 1 / 1（均值均为 4.0） |
| Case Research / Concept / E2E valid_cases | 0 / 0 / 0 |

唯一正确完成的预期终点是 Case 03 的 ask_user。两个 execution failure 分别为 source_consistency_validation 和 llm_call_or_validation。正常 early-stop 不计 execution failure，但错误追问不满足 Completion。

该 Baseline 的作用是定位阻断闭环的主要瓶颈。低质量覆盖率说明缺少可评分输出，不能据此判断案例研究、概念或 E2E 内容质量差。

## 3. Failure Analysis

### P0 — Info Sufficiency Gate 过严 / Task Boundary 错位

Case 02、04、05、06、08、09、10 本应足以启动前期研究，却被提前 ask_user。城市名、精确坐标、图纸、红线、FAR、高度或定量交通数据等提高精度的资料，被误当成启动研究的必要资料。

Agent 要判断的是“能否开展有意义的前期研究”，而不是“能否完成正式规划或详细设计”。Case 09 已有区位关系、规模、功能、资源、问题和目标，仍因缺少绝对定位被阻断，是该边界错位的代表。

### P1-A — LLM 生成 provenance metadata 不可靠

入口改善后，主要瓶颈转移至 Case Research。安全诊断发现模型没有稳定遵守来源字段契约：Case.source 有时写成裸域名，而不是完整 evidence URL；Case.name 有时被改写、截断、删除括号或前缀。exact source guard 对这类不一致的拒绝是正确的。

历史 Case 07 确实出现过 HTML entity 与 Unicode 引号的表示差异（如 `&rsquo;` 与 `’`），但这不能解释所有后续失败。真实诊断确认过裸域名和标题改写；后一轮 Prompt 改进后，URL exact 已达 64/64，title exact 仍为 61/64，三次失败均来自标题变化。最终修复针对来源字段的生成方式，未放宽 Validator 或加入 normalization acceptance。

历史 Provider 403 与无法确定底层原因的 llm_call_or_validation 分开记录，不推断成同一种 Agent 逻辑问题。旧 P0 Run #1（`p0-regression-quota-20261007-114647`）保留为受 Provider 403 干扰的历史观察，未与其他运行拼接。

## 4. Optimization

### P0 — Minimum viable research input

Info Gate 明确判断三个最低条件：

1. 研究对象可识别；
2. 至少一组有意义的场地条件；
3. 研究意图可识别。

三类满足且没有严重核心矛盾时应继续前期研究。城市名、精确定位、FAR、高度、CAD、红线或图片缺失不能单独阻断；保留缺乏基本场地信息时的追问能力。Case 03 用作 negative control，防止变成全部放行。

### P1-A — Deterministic provenance

原流程要求 LLM 重新输出 title 与 URL，Prompt 强化后仍存在标题改写。最终改为：

```text
当前去重 evidence → src_001 / src_002 / …
LLM → 选择 source_id + 专业分析字段
程序 → 根据同一 source_id 回填原始 title、完整 URL 与分析关联
既有 exact guard → 校验
```

source_id 只在 Case Research 内部使用。未知或空 ID 明确失败；重复选择继续由原有重复案例 guard 拒绝。最终 Case Schema、AgentState、Graph、Tavily 接口和 exact provenance guard 不变。

这种方式把来源元数据从概率性文本生成转为确定性查表，避免模型翻译、润色或组合来源字段。专业筛选与分析仍由模型完成；metadata exact match 不等于案例专业质量已被证明，仍需质量评价与人工审阅。

## 5. Final Regression

最终运行：`p1a-source-id-regression-quota-20261007-142026`。Dataset V1.0、模型 **qwen3.7-flash**。代码 revision 为 `e54847b` 加本轮尚未提交的来源映射修改；metadata 保存工作区状态与 relevant file hashes，不能仅用该 commit 代表全部修改。离线验收为 **297 passed / 7 skipped**。

十 Case 各执行一次。9 个应继续研究的 Case 全部生成报告，Case 03 正确追问。真实 Image API 未调用，Case 02 多模态输入成功执行。

### A. Decision & Workflow

| Metric | Correct | Incorrect | N/A | unavailable | Valid denominator | Accuracy |
|---|---:|---:|---:|---:|---:|---:|
| Info Sufficiency | 10 | 0 | 0 | 0 | 10 | 100% |
| Case Research Decision | 7 | 1 | 2 | 0 | 8 | 87.5% |
| Research Sufficiency | 9 | 0 | 1 | 0 | 9 | 100% |
| Search attempts ≤ 2 | 10 | 0 | 0 | 0 | 10 | 100% |
| Concept regeneration ≤ 1 | 10 | 0 | 0 | 0 | 10 | 100% |
| Fallback correctness | 7 | 0 | 3 | 0 | 7 | 100% |
| Completion | 10 | 0 | 0 | 0 | 10 | 100% |

Completion 包含 Case 03 按预期 ask_user → END，**不等于十个报告**。实际报告数为 9。Research Sufficiency 规则检查判断、gaps 与实际路由的一致性，不证明专业证据完全充分。九个研究 Case 均执行两轮，七个触发研究不足达上限后的继续路径；未超出搜索上限。Case 05 的案例必要性判断仍不正确。

### B. Quality

| Metric | Mean | valid_cases | N/A | unavailable |
|---|---:|---:|---:|---:|
| Site Analysis | 4.83 | 6 | 4 | 0 |
| Case Research | 3.75 | 4 | 6 | 0 |
| Groundedness | 4.57 | 7 | 3 | 0 |
| Concept Quality | 4.20 | 5 | 5 | 0 |
| End-to-End Usability | 4.00 | 2 | 8 | 0 |

质量有效分母由冻结的 applicability 和实际输出可用性决定，不要求所有 Case 都评五项。Case Research、Concept 与 E2E 已开始具备有效样本；这些是项目级结果，不能外推为通用质量保证。

### C. Operational

| Metric | Final Regression |
|---|---:|
| Agent runtime median / P95 | 182.08 / 244.02 秒 |
| Agent LLM SDK calls | 124 |
| Search SDK calls | 88 |
| Image SDK calls | 0 |
| Agent tokens | 951,298 |
| Judge SDK calls / tokens | 24 / 1,603,427 |
| Cost | null（未可靠计算） |
| Agent execution failure rate | 0% |
| Judge failures | 0 |
| source_consistency_validation | 0 |

Calls 包含技术重试，不等于业务搜索轮次；Judge 消耗不混入 Agent runtime/calls/tokens。64/64 个案例候选的 title 与完整 URL 精确对应同一 evidence；裸域名、标题变化和 cross-source mixing 均为 0。最终运行无 Agent failure type。

结果与 metadata 已保留并冻结。单独记录了 console.log 在 checksum 写入后追加结束行的日志封存差异；Case JSON、summary 与 metadata 校验通过，未篡改原始记录。

## 6. Baseline vs Final

### Initial v0.1 → Final：整体迭代结果

| Metric | Initial v0.1 | Final |
|---|---:|---:|
| Info Sufficiency | 30% | 100% |
| Completion | 10% | 100% |
| Report completed | 0 | 9 |
| Agent execution failure rate | 20% | 0% |
| source_consistency_validation | 1 | 0 |
| Case Research valid_cases | 0 | 4 |
| Concept valid_cases | 0 | 5 |
| E2E valid_cases | 0 | 2 |

v0.1 中只有两个 Case 到达案例研究阶段，因此来源失败的绝对数量不能直接解释为来源稳定性已经较好。20% failure rate 也受大量正常返回的错误 early-stop 影响。

历史阶段曾变更模型配置与 Prompt，不把全部中间 Run 当成严格单变量实验。早期 P0 Run #1 的 Info Accuracy 为 88.9%（8/9，有一项 unavailable），后续无代码变化的 Run #2 使用 qwen3.7-flash，Info Accuracy 为 100%；两轮独立保留，不能拼接或把随机差异当确定因果。

### v0.2 → Final：同模型来源稳定性对照

v0.2 对照运行：`p0-regression-recheck-quota-20261007-122944`，tag **v0.2-baseline / 04c766b**，同为 qwen3.7-flash、Dataset V1.0 与固定 Framework/Rubric，真实图片生成均关闭。

| Metric | v0.2 Baseline | Final |
|---|---:|---:|
| Info Sufficiency | 100% | 100% |
| Case Research Decision | 87.5% | 87.5% |
| Completion | 20% | 100% |
| Report completed | 1 | 9 |
| Agent failure rate | 80% | 0% |
| source_consistency_validation | 8 | 0 |
| Research Sufficiency valid_cases | 2 | 9 |
| Case Research / Concept / E2E valid_cases | 0 / 0 / 0 | 4 / 5 / 2 |

同模型对照更适合观察来源绑定的稳定性；但期间还有最低输入规则和来源 Prompt 调整，且检索与模型具有随机性，不能称为仅 source_id 一项变量的严格消融实验。最近 Prompt-only 完整运行还出现三次标题 provenance failure，而确定性映射后的 64/64 exact pairs 与 guard 失败清零，为该机制提供了直接执行证据。

## 7. Human Spot Check

人工评分由项目审阅者提供，抽检最终 Regression 的四项代表性判断；本阶段未重新生成或重新评分。

| Case | Metric | LLM Judge | Human Score | Human Rationale |
|---|---|---:|---:|---|
| Case 02 | Site Analysis | 5 | 5 | 信息识别无误，SWOT 与场地信息一致，并能提炼设计机会 |
| Case 02 | Groundedness | 5 | 5 | 信息有来源，未发现明显编造 |
| Case 08 | Concept Quality | 5 | 5 | 概念有差异，每个概念有具体细节，并与场地特征相关 |
| Case 10 | E2E Usability | 4 | 4 | 推导清楚，整体基本可用 |

**4 representative judgments manually reviewed. Human scores broadly aligned with LLM-as-Judge. No material systematic over- or under-estimation observed in this spot check.**

这是少量抽检的一致性观察，不是全面 Human Calibration，不证明 Judge 完全可靠，也不等同于独立核验全部网页事实。仍需专业人员确认可迁移策略与落地条件。

## 8. Known Limitations

- **Case Research Necessity**：Case 05 的低案例研究边际价值场景仍输出 need_case_research=true，Ground Truth 为 false，可能增加不必要搜索成本。当前保留，不继续优化。
- **Evaluation Scale**：Dataset V1.0 仅十 Case，用于项目级回归和 failure-driven iteration，不代表大规模 benchmark；部分质量指标有效样本仅 2–5 个。
- **Image Evaluation**：真实生图能力已完成独立 Smoke，正式 Eval 因 quota 关闭，未建立 Image Quality benchmark，也不以本轮 image_calls=0 判断生图能力不可用。
- **External Provider Variability**：动态搜索 evidence、LLM 输出和 Provider 运行状态存在波动；单次回归不代表长期确定性结果。
- **Evidence and Transfer**：搜索摘要不等于网页全文核验；部分材料是导则或研究文章，存在研究 gaps。来源绑定只保证 provenance，对事实与专业迁移仍需判断。

公开 Demo 直接提取本轮既有报告：[Case 02 多模态 TOD](../demo/case-02.md)、[Case 08 多约束更新](../demo/case-08.md)。没有重生成专业内容；正式 Eval 的 quota override 同样适用于这两份文本展示。
