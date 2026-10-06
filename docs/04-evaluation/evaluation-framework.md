# Evaluation Framework

## 1. Evaluation Goals

验证 V1 的 Agent 自主判断、工作流、专业质量和运行表现。Stage 7A 只提供基础设施；Stage 7B 才执行正式 baseline。固定 Dataset V1，后续以同一版本比较 Regression，不根据结果改 Ground Truth。

## 2. A/B/C Framework

### A. Agent Decision & Workflow Correctness

Rule-based + expected behavior：Info Sufficiency Decision、Case Research Decision、Research Sufficiency Decision、Workflow Compliance。

Info Sufficiency 对比 frozen expected_info_sufficient；信息不足时还检查追问、missing_critical、ask_user → END 与禁止后续业务节点。Case Research Decision 对比 expected_need_case_research 和实际执行案例节点。未定义 expected 值时为 N/A，不自行补 Ground Truth。

Research Sufficiency 依据实际 check_research partial update、当轮 search_attempts、下一节点，检查充分 → concept_generation、不充分且未达上限 → refine_search、达两轮上限 → concept_generation；不充分须输出 research_gaps。该规则只检查可观察一致性与路由，不能自动证明专业证据充分。Case 07 不固定执行两轮；语义充分性结合 Case Research Judge 与后续 Human Calibration 审阅。

Workflow 分项：search_attempts 和实际案例节点次数均 <= 2；concept_regenerations <= 1；触发图片失败或两轮研究不足时仍进入概念和报告；Completion 根据 Case 的预期终点检查（Case 03 为 ask_user → END，其他为非空 final_report）。未触发 fallback 时该项 N/A。文字同义的 missing_critical、forbidden_claims、expected_points 不做脆弱的精确词匹配，作为 Judge 和人工审阅依据。

### B. Quality Evaluation

LLM Judge 1–5 + 后续 Human Calibration。只执行 Case evaluation_focus 中适用的五项质量指标。使用统一 call_llm_structured，独立于业务 Prompt，严格 Pydantic 校验；单项输出 score、reason、key_issues。End-to-End Usability >= 4 派生 usable=true，否则 false；无有效评分时 null。

### Site Analysis Rubric

1. 分析缺失或高度泛化，与场地输入关系弱。
2. 识别部分条件，但遗漏关键资源或问题；SWOT / 场地判断较通用。
3. 覆盖主要条件和资源；判断基本合理；SWOT 与项目有一定关联。
4. 准确识别关键空间条件、资源、问题和约束；重点清晰；SWOT 与输入紧密对应。
5. 在 4 的基础上，进一步提炼关键矛盾、资源潜力和空间机会，能够直接支持后续设计判断，具有较强专业洞察。

### Case Research Rubric

1. 案例基本不相关、不可追溯或无法支持当前任务。
2. 部分相关，但匹配逻辑较弱；案例介绍泛化；设计参考价值较低。
3. 案例总体相关且来源可追溯；能够提取部分有用策略；但与当前项目的映射较弱。
4. 案例与当前项目类型、资源或空间问题高度相关；来源清晰；能够提取具体、可迁移策略。
5. 案例组合具有明确研究逻辑和差异性；覆盖关键问题；能够直接支撑 Design Opportunities 和 Concept。

### Groundedness Rubric

1. 存在大量编造事实、错误事实或无依据具体信息。
2. 存在多个无支持判断；事实、推断和假设混杂。
3. 整体基于输入和来源，但仍有少量过度推断或缺乏依据的具体描述。
4. 事实基本有输入或来源支持；事实与推断区分较清楚；仅存在轻微不确定性表达问题。
5. 严格基于用户输入与可追溯来源；事实、推断、不确定性明确区分；不存在实质性幻觉或无依据扩展。

### Concept Quality Rubric

1. 概念泛化，与场地及前序分析关系弱；多个方向高度重复。
2. 部分回应项目条件，但策略较通用；差异性弱；可操作性低。
3. 能够回应主要条件和机会；具有一定空间策略；2–3 个方向基本可区分。
4. 概念能够清楚追溯到前序分析和机会；空间策略具体；方向差异明显；具有较强设计参考价值。
5. 概念推导完整；策略明确；差异度高；能够有效利用项目独特资源和约束；具有较强设计启发与转译价值。

### End-to-End Usability Rubric

1. 流程输出碎片化或逻辑断裂，难以直接使用。
2. 具备完整流程，但阶段之间联系较弱；需要大量人工重做。
3. 流程完整且基本连贯；可作为前期参考，但仍需要较多人工筛选和补充。
4. Research → Opportunity → Concept 推导较清楚；报告结构明确；大部分内容可直接用于前期讨论和设计参考。
5. 整体高度连贯；内容完整、清晰、Grounded；能够显著减少人工前期研究工作，并直接支持设计讨论与方向判断。

### C. Operational Metrics

Runtime 使用 Agent Graph 执行墙钟时间（含其技术重试，不含 Judge）。汇总 median、P95（nearest-rank）。SDK 实际请求次数分别记录 LLM calls、Search calls、Image calls，包括技术重试；它们不等于 search_attempts 或 Concept regeneration。Mock 公共接口测试没有 SDK 请求，calls=0。

LLM tokens 来自响应 usage.total_tokens。任一 LLM 请求失败或缺失 usage 时总量 unavailable/null，避免把未知消耗记成 0。Image token 用量、Search credits 和可靠定价当前不汇总为 token/cost；cost=null，不猜测价格。Judge SDK calls/tokens/cost 单独记录 judge_execution，不混入 Agent 指标。

Failure Rate = execution.status != success 的 Case 数 / 实际执行 Case 数。降级但成功完成的 Case 不记 Agent failure，保留 image_failures 和 tool_failures。按 failure_type 汇总。运行异常只保存安全类型，不保存 Key、鉴权、原始敏感 response。

## 3. N/A Rules and Aggregation

内部形式：{"applicable": false, "score": null, "reason": "..."}。适用但 Judge 未运行/失败/Agent 中断：applicable=true、score=null，表示 unavailable，与 N/A 区分。成功 Judge：applicable=true、score=1..5、reason、key_issues。

metric average = sum(valid scores) / count(valid cases)。N/A 和 unavailable 均不进入有效分母；每项报告 valid_cases，避免掩盖覆盖率。Case 03 正常 ask_user 后全部专业质量项 N/A，不记 0。Case 02 若模型已知不支持视觉，使用 --vision-unsupported 将多模态相关 Site Analysis / Groundedness 标为 N/A；仍传入固定图片，不切换模型、不删除图片。若模型拒绝输入，Agent 执行仍记录失败，不伪造完成。

分层输出 A_decision_workflow、B_quality、C_operational；不计算 A/B/C 合并分数，不生成 Overall Score。

## 4. Image Generation Evaluation Policy

required：执行正常 Image Generation，不允许 --images off 覆盖。disabled：不得发起 Image SDK 请求。optional：默认关闭，仅 --images on 开启。Case 01/08 optional，Case 10 required，其余 disabled。Case 02 上传的 site image 是输入，不受生成开关影响。

Eval-only 临时包装 Concept Skill 的 LLM/Tool 入口：关闭时跳过 image_reference_check / image_prompt 与图像 Tool，使用已有受控异常降级；Opportunities、Vision、Concept、Quality Check 和 Concept Regeneration 原样执行，返回 images=[]。不修改业务 State、Skill、Graph 或产品配置默认值。包装限定 Runner 独立进程，串行运行，退出上下文恢复；禁止与同进程产品调用并发使用。

## 5. Failure Logging

source_consistency_validation：标题/URL 来源校验、重复案例标识或分析关联失败；保留 Case 07 HTML entity / Unicode known issue，不修复。
llm_call_or_validation、search_tool_failure、image_tool_failure、input_asset_missing、model_capability_or_parameters、agent_execution_error：最小安全分类。LLM 层已隐藏原始错误时不猜测具体原因。单 Case 失败仍保存 partial AgentState、已完成节点 trace、检索 evidence、运行指标和适用性；继续所选其他 Case。Judge 错误记录 judge_failures，不改变 Agent status。

## 6. Evaluation Process and Runner

加载严格校验的 dataset.jsonl → 固定输入 create_initial_state → 现有 Graph.stream updates → trace / Rule Metrics → 适用单项 Judge → 保存 Case JSON → 独立 A/B/C 聚合。trace 每项含 node、update、当时 State，仅属于 Evaluation 记录，不写回 AgentState。Concept regeneration 从公共 LLM task 调用观察；技术重试不增加该业务计数。检索 evidence 保存实际送入案例分析的标准化片段，Judge 不额外联网核验网页。

```bash
python -m evals.run_eval --case case_01
python -m evals.run_eval --case case_01 --case case_08 --images on
python -m evals.run_eval --case case_05 --no-judge
# Stage 7B 明确授权后才运行：
python -m evals.run_eval --all
```

默认无 Case 参数时报错，不自动运行全部 Dataset。--no-judge 仅用于诊断，不作为正式质量 baseline。--output 指定新的结果目录，默认 outputs/evals/<run_id>/。保存 case_XX.json 和 summary.json；单 Case 包含 dataset_version、case_id、execution、decision_metrics、quality_metrics、agent_output，另含 trace、检索 evidence、Judge 操作日志和 usable。数据是运行结果，不是 Golden Answer。

Stage 7A 验收只运行离线测试，真实 Provider 和正式 10-case baseline 未执行。后续 Human Calibration 对照 Ground Truth 与 evidence 审阅，不能根据评分直接修改 Dataset。
