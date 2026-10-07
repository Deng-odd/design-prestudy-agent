# Evaluation Results

## 1. Baseline Setup

正式 Baseline：`outputs/evals/baseline-final-quota-20261007-011740/`。代码版本为 `v0.1-baseline`，commit `527909a`；Dataset V1.0、10 Case、frozen。每个 Case 按顺序执行一次，无补跑或结果替换。

运行使用 Qwen `qwen3.7-flash-2026-07-15`，LLM 技术重试上限为 2。Framework、Rubric 和 Ground Truth 保持冻结。Quality 按 Design Applicability + Output Availability 判断，缺失输出为 unavailable，不以低分代替；后续失败不取消已有专业输出的评分资格。

本轮使用 Eval-only image quota override，所有真实 Image Generation 被跳过，image_calls=0。Case 02 的固定输入图片仍正常传给多模态模型。图像生成能力在此前 Smoke 验证，本 Baseline 不评价图像质量。分析只使用保存的 Case JSON、Trace、evidence、summary、metadata 及历史诊断，不重新调用 Provider。

证据索引：正式目录中的 `case_01.json` 至 `case_10.json`、`summary.json`、`metadata.json`、`checksums.json`；历史参考为 `outputs/evals/baseline-quota-20261006-233311/` 与 `outputs/case07-diagnostic-20261006-202947/observation.json`。设计依据为 PRD §2.2、state-design §8、agent-architecture 的 parse_and_check / ask_user 职责及 task-boundary。

## 2. Baseline Results

### A. Decision & Workflow

| 指标 | 正确 | 错误 | N/A | unavailable | 有效分母 | Accuracy |
|---|---:|---:|---:|---:|---:|---:|
| Info Sufficiency Decision | 3 | 7 | 0 | 0 | 10 | 30% |
| Case Research Decision | 2 | 0 | 2 | 6 | 2 | 100% |
| Research Sufficiency Decision | 0 | 0 | 10 | 0 | 0 | — |
| 搜索轮次上限 | 10 | 0 | 0 | 0 | 10 | 100% |
| Concept regeneration 上限 | 10 | 0 | 0 | 0 | 10 | 100% |
| Fallback correctness | 0 | 0 | 10 | 0 | 0 | — |
| Completion | 1 | 9 | 0 | 0 | 10 | 10% |

完成报告 0、ask_user early-stop 8、execution failure 2。Completion 的唯一正确项为 Case 03 按预期追问结束。搜索与重生成上限通过不能证明对应完整业务能力已得到覆盖；没有执行 check_research 的 Case 按当前 Rule Metric 记 N/A。

### B. Quality Evaluation Coverage

| 指标 | Mean | valid_cases | N/A | unavailable |
|---|---:|---:|---:|---:|
| Site Analysis | 4.0 | 1 | 4 | 5 |
| Case Research | — | 0 | 6 | 4 |
| Groundedness | 4.0 | 1 | 3 | 6 |
| Concept Quality | — | 0 | 5 | 5 |
| End-to-End Usability | — | 0 | 8 | 2 |

有效质量分数仅来自 Case 01 的 Site Analysis 和 Groundedness，各 4 分。两次 Judge 均成功。Case Research、Concept 和 E2E 没有有效评分样本，不能据此断言专业质量差；上游流程阻断使这些能力尚不可判断。均值只统计 scored，不计算 Overall Score。

### C. Operational

Agent runtime median 4.18 秒、P95 156.92 秒；LLM SDK calls 22、Search calls 10、Image calls 0、tokens 206,365、cost=null。Judge 独立统计：SDK calls 2、tokens 51,206、failure 0、cost=null。

Agent execution failure rate 20%：source_consistency_validation 1 次、llm_call_or_validation 1 次。正常返回的 early-stop 不计 execution failure，但除 Case 03 外不满足 Completion。失败的案例 Node 未返回 partial update，因此 search_attempts 仍为 0；Trace 证明已执行搜索，不能把该数值理解为未检索。

## 3. Bad Case Analysis

### 3.1 Info Sufficiency Gate 与任务边界

冻结设计的最低启动条件是：能判断项目类型、功能定位或发展目标，并具备图片或基本空间文字描述。不是具备正式规划、详细设计或审批所需的全部资料。以下七个 Case 均具备这两项条件，却被判为 false。

Critical：缺失后无法开展有意义的前期研究，例如项目定位完全未知、没有任何场地空间信息。Optional：能提高准确度，但可在声明限制后继续，例如具体城市、地址、坐标、红线、现状图、FAR、高度、开发条件、交通与人口统计。Unnecessary：本阶段不要求的详细设计成果、施工图及强制 CAD 输入；CAD 不在 V1 接受格式内。Optional 资料可以有研究价值，但不能因此自动成为启动门槛。

| Case | Expected | Actual | Actual missing_critical | 正确分类 | Root Cause |
|---|---|---|---|---|---|
| 02 | true | false | 具体城市/地理位置；详细规划指标（FAR、限高、用地比例）；交通流量及人流特征 | 均 optional | 已有站点、功能、目标和图像，仍以定量开发/交通评估资料作为启动条件 |
| 04 | true | false | 具体地理位置（城市/区域）；场地图像或更详细平面布局图 | 均 optional | 忽略已有厂房、仓储、内部道路、开放空间问题等文字空间信息 |
| 05 | true | false | 具体地理位置/城市区域；平面布局图、现状照片或空间尺寸 | 均 optional | 将小尺度方向性改善升级为需精确尺度与图纸支持的设计任务 |
| 06 | true | false | 平面图/照片以确认高差、植被细节、路径走向和宽度；设计目标层级（概念/初设/施工图）；人口规模/社区结构以量化设施需求 | 图像、测量和人口数据 optional；再次确认是否施工图阶段 unnecessary | 以详细方案和量化设施配置为门槛，未采用 Agent 固定前期研究任务边界 |
| 08 | true | false | 精确地理位置用于气候/法规；边界坐标、红线和地形；交通流量或轨道线路/站点细节 | 均 optional；最终法规合规判断 unnecessary | 将多约束方向探索升级为精确规划与法规评估 |
| 09 | true | false | 具体城市名称或精确位置坐标 | optional | 相对区位、范围、功能、资源、问题、目标已经充分，却要求绝对地理标识 |
| 10 | true | false | 城市名称/地理位置；详细平面图或现状照片 | 均 optional | 忽略已有公共空间网络与节点关系文字，追求更准确分析而阻断 E2E |

以上是对当前前期研究任务的分类，不意味这些资料在后续设计阶段无用。七个 Case 都没有可证实的真正 critical 缺口。预算、时间、产权等额外资料也不应成为当前任务默认门槛。

### 3.2 实际 optional 与 followup_question

模型把以下资料记录为 optional：Case 02 为建筑高度/密度分布图、换乘线路、开发时序/产权、任务阶段时间节点；Case 06 为预算、工期、文化/生态指标；Case 08 为历史保护等级、社区人口结构、FAR/高度限制。Case 04、05、09、10 的 missing_optional 均为空。

追问内容与门槛错位一致：Case 02 要求城市、控制指标和交通数据以评估站城一体化；Case 04 要求具体园区位置、平面图/照片；Case 05 要求位置与图像以理解尺度、人流和设施；Case 06 要求平面/航拍、设计阶段，并询问预算/时间；Case 08 要求城市、红线/平面图以及历史建筑与河道控制要求；Case 09 要求城市、红线或详细现状图；Case 10 要求片区名称/城市与平面图/照片。具体措辞保留在相应 Case JSON。

部分追问还扩大到未列入 missing_critical 的资料。例如 Case 09 只列城市/坐标，却同时询问红线/图纸；Case 06 已将预算/工期列 optional，仍在追问中索取。此现象支持“更精确”被误用为“必须先补齐”的判断。

当前 parse_input.md 虽写明“基本定位”“图片或文字”“非关键缺失只提示”，但未显式强调前期研究与最终设计的界限，也未给出常见 optional 项和已有相对空间描述足够的反例。“已知规划条件”“关键缺失”保留较大的模型解释空间。Node 的 Pydantic validator 仅保证 info_sufficient 与 missing_critical 自洽，无法判断模型是否把 optional 错列为 critical。这是语义 Decision boundary 问题，不是路由或类型校验错误。

### 3.3 Case 09：Boundary Case

输入已提供城市副中心边缘、40 公顷、住宅/商业/办公、公园/轨道站、零散公共空间和联通目标，并明确要求先做方向性研究。实际唯一 critical 为城市名/精确坐标；追问又要求红线/详细图纸。不能将本轮错误描述为“FAR 被列 critical”：实际 missing_critical 没有 FAR 或高度，missing_optional 也没有记录它们。

边界问题是：基本相对区位被误判为缺乏可执行空间信息。后续最小修复原则应同时明确绝对定位可选、文字空间关系可执行、FAR/高度/详细指标缺失应列 optional；不填造这些数据，也不强制变更 Schema 或 Graph。

### 3.4 Case 02：视觉理解与 Gate 分离

Trace 记录 parse_and_check 包含 1 张输入图片，SDK 成功返回。site_image_description 明确识别中央 Transit Station、东侧 Park、西侧 High-density Blocks、红色虚线/叉号连接断点以及东西两侧联系。

但该描述将中央垂直线路称为轨道交通线路，没有明确识别南北向主干道及其分隔作用；虽提到断点，也没有明确数出两处。因此视觉理解是部分成功，不能声称五项 Ground Truth 全部识别。主要 early-stop 原因仍是城市、规划指标、人流数据被列 critical，不是请求失败或完全无法理解图片。site_analysis 未执行，所以本轮无法评价完整多模态 Site Analysis；道路识别应作为后续人工核验点，不单独扩大为新的优化模块。

### 3.5 Case 05：下游决策覆盖丢失

任务限定为公共空间微更新，明确不调整功能、开发强度或业态，且已给出四项具体问题。地点、尺寸与图像有助于细化，但不妨碍整理改善机会和初步方向。parse early-stop 导致 check_case_need 根本未执行，因此 expected_need_case_research=false 无实际判断可比较，Case Research Decision 为 unavailable；不能推断 Agent 会正确或错误跳过搜索。

Regression 应观察 info_sufficient=true 后能否执行 check_case_need，输出 false 并直接进入 Concept，Search calls=0，同时保持小尺度改善边界。Concept Quality 仅为 supporting metric。

### 3.6 Case 01：来源一致性失败

五个 Tavily query 均成功，分别返回 10、9、10、10、10 条，合并 evidence 为 44 条。保存内容包含政府滨水规划、公共空间研究与案例页面；title/url/snippet/source 结构完整，说明检索有有效材料，但不等于入选案例质量已被证明。

异常为“案例来源或标题不属于检索证据”。按当前 Skill 的执行顺序，分析结果已通过 _CaseResults Pydantic 校验，随后在以下条件被拒：case.source 不属于合并 evidence 的精确 URL，或 case.name 不等于该 URL 对应原始 title。故可确认的执行根因是候选输出与严格来源契约不一致，不是 Tavily 无结果或该次最终 Schema 校验失败。

本轮 Trace 只保存 evidence 和失败信息，没有保存 analyze_cases 的候选返回值或原始模型响应。因此无法确定是哪条候选、title 还是 URL，以及是否属于 HTML entity、引号、标点、Unicode 或空白差异，也不能确认候选实际指向正确来源。具体错配根因：**root cause unresolved due to insufficient observability**。

历史 Case 07 专用诊断确实证明：同一 `https://www.mdpi.com/2073-445X/15/1/59`，原始标题中的 `Shanghai&rsquo;s` 被模型返回为 `Shanghai’s`，语义等价却被精确字符串比较拒绝。这证明现有 validator 存在表示差异敏感性，但不能代替 Case 01 缺失的候选证据；不能直接断言 Case 01 只是此类误拒。

### 3.7 Case 07：输出处理失败

五个 Tavily query 均成功，各 10 条，合并 evidence 为 48 条。case_research 内记录 4 次 LLM SDK 调用（整 Case 为 7 次），tool_failures 为空且记录了响应 tokens；没有 SDK/HTTP 异常被观察到。检索 evidence 已在 analyze_cases 调用前保存，所以失败发生于案例分析的统一 LLM 输出处理流程。

最终异常被保存为 `LLMError: llm_call_or_validation`。src/llm.py 会将输出不完整、JSON parsing、Pydantic validation 等最终失败隐藏为同一受控错误；当前日志无原始文本、finish_reason、具体 validation field 或异常链。无法确认 JSON 是否成功，也无法定位字段、重试分配或证明与此前 site_image_description nullability mismatch 相同。具体根因：**root cause unresolved due to insufficient observability**。输出合同兼容性是待证实方向，不应直接定性为 nullability、billing、rate limit 或某字段错误。

### 3.8 历史行为漂移

旧 `baseline-quota-20261006-233311` 的 A 类记录为 Info 70%、Completion 50%，四个报告加 Case 03 预期终止；该 Run 的 B 类已因 applicability 问题失效，不使用其质量分数比较。与本轮比对，Info bool 改变的是 Case 02、06、08、09 共四项；粗粒度路径/终点改变约六项（另含 Case 01、07 从报告完成转为执行失败）。不能把“六个路径变化”写成“六个 Info 错判变化”。

模型及 Prompt 条件曾改变，搜索也具有动态性，以上不是严格 Regression，不能归因为某项修改造成性能退化。它支持将 Gate 稳定性作为风险观察：宽泛 critical 定义容易随模型解释转向保守追问，但现有运行不足以分离模型、Prompt、检索变化的各自因果贡献。

## 4. Failure Modes

### Failure Mode 1 — Info Gate 过严与 Task Boundary 错位（P0）

**现象与 Evidence：**七个 expected true 被判 false；常见门槛为城市、图纸、精确参数及定量数据，已有文字或图片未被认可为最低空间信息。Info accuracy=30%、Completion=10%、报告完成=0。

**影响范围：**Case 02/04/05/06/08/09/10；阻断 Site、Case Research Decision、Concept 和报告的覆盖。历史漂移为稳定性表现，不构成受控性能退化结论。

**Root Cause：**当前短 Prompt 没有充分操作化设计已有的最低门槛和 optional 边界，模型将准确性提升、详细设计或法规判断前置为必要条件；Schema 只验证内部一致性。

**最小方向：**仅明确 parse_and_check 的前期研究任务、两项最低条件、optional/不要求资料和可继续边界；保留真正缺定位/空间信息时追问。不改 State、Graph、Routes，不对 Case ID 硬编码。

**Regression 观察：**七个 false negative、Case 03 的不足信息识别、Case 09 optional、Case 05 无搜索路径，以及各专业阶段输出覆盖。

### Failure Mode 2 — 来源契约对表示差异敏感（P1）

**现象与 Evidence：**本轮 Case 01 schema-valid 候选被来源 guard 拒绝；历史独立诊断已证明同 URL 的 HTML entity / Unicode 差异误拒。两者不可直接视为相同根因。

**影响范围：**案例结果不能写入 State，后续研究充分性、Concept、Report 均不可达；正常技术重试不能解决 Skill 之后的来源 guard。

**Root Cause：**已证实的历史问题是语义等价标题与严格字符契约冲突；本轮具体候选错配尚未定位。

**最小方向：**先获得可安全审阅的被拒候选与 evidence 对照，再考虑仅对证实的表示等价做规范化；不删除来源约束，不接受生成/错配 URL，不改变检索专业筛选职责。本阶段不执行。

**Regression 观察：**原文与表示等价通过、真正来源错配仍被拒、可追溯性与 Groundedness；保留 Case 07 的检索挑战 Ground Truth。

### Failure Mode 3 — 案例 Structured Output 失败可观测性不足（P1；具体兼容修复待证据）

**现象与 Evidence：**Case 07 检索成功并进入 analyze_cases，最终 llm_call_or_validation；没有能区分 JSON、输出截断、字段类型或 nullability 的安全诊断。

**影响范围：**当前已观察到的 Case 07；不能据单例泛化所有 Schema 或判断模型完全不可用。

**Root Cause：**业务失败具体原因未解决；诊断不足的原因是统一 LLM 最终错误与 Eval safe_error 隐去了底层细节。二者与 FM2 来源 guard 处于不同校验层，不合并成单一根因。

**最小方向：**后续另行授权时先加有限、脱敏、诊断型可观测性，不放宽 Schema、不把任意 null 静默转换。确定具体失败后再做字段级兼容修复。

**Regression 观察：**SDK 成功与输出合法性分别统计、错误阶段/字段可定位、有限 retry、非法结果不进入 State。P2 的质量润色、概念多样性或图像美学暂缓：当前覆盖不足以证明这些是待优化问题。

## 5. Optimization Priorities

建议 Stage 7B-3 第一轮只修 P0 的 parse_and_check 指令边界及对应离线验证，再对冻结十 Case 做完整 Regression。这样最小变量、可归因，也更适合作品集展示“Gate 修复 → 路由覆盖提升 → 质量可评价”的链路。

P0 + P1 一起修可能提高完成数，但无法区分 Gate 与来源/输出兼容性的贡献，不建议作为首轮。P1 后续分开：先完成诊断，再只修已证实的最小问题。若 P0 Regression 被 P1 阻断，如实报告其覆盖限制，不即时叠加补丁或替换差结果。

明确不改 Dataset、Framework/Rubric、State/Schemas、Graph/Routes/9 Nodes、搜索轮次与 Concept regeneration 上限、Search Tool、Image Tool、Concept/Report 专业逻辑及模型配置。其他 Prompt 不扩大修改；不为了避免 early-stop 伪造规划指标，也不取消真正的信息不足追问。当前阶段只建议，不实施。

## 6. Regression Plan

后续授权后，同 Dataset V1.0 全十 Case 各一次，固定当前模型及冻结 Evaluation Infrastructure，记录代码/Prompt 版本与改动范围。继续禁用真实 Image Generation；Case 02 固定输入图保持。动态检索不能保证完全相同 evidence，因此保留每轮实际来源并说明限制。

优先观察 Info accuracy/false negatives、Case 03 true negative、Completion/报告完成/early-stop、Case Research Decision 的有效分母（尤其 Case 05 skip）、Research Sufficiency 路由与两轮上限、各阶段 Quality valid/N/A/unavailable、Agent 与 Judge 分离的 failures、runtime/calls/tokens。Quality Evaluation Coverage 是关键观察结果：在有效专业输出增加后才能讨论质量均值的变化，不以零样本 mean=null 判断质量差。

Case 09 检查 FAR/高度/详细指标为 optional 且不编造；Case 02 人工核验主干道与断点；Case 08 保留历史建筑/居民/滨水约束；Case 01/07 保留来源与输出失败证据。未触发的路径或 fallback 不能声称已验证。

本次只新增分析文档，不修改任何运行结果，不执行 Optimization 或 Regression。
