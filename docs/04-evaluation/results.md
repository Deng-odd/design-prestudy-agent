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

## 7. P0 Regression Results

P0 Regression 为 `outputs/evals/p0-regression-quota-20261007-114647/`，Dataset V1.0 与 Evaluation Framework / Rubric 不变，十 Case 各执行一次，无补跑。模型保持 `qwen3.7-flash-2026-07-15`，endpoint host 保持 `ws-pdhycrq105jayqi9.cn-beijing.maas.aliyuncs.com`。Run metadata 记录 revision `e03c4e0` 与尚未提交的 parse_input.md、test_nodes.py 两项 P0 改动及文件哈希；不能把 commit 单独当成包含 P0 的完整代码快照。

真实 Image Generation 全部按 quota override 禁用，image_calls=0。Case 02 固定输入图片成功用于 parse、site_analysis 和适用 Judge。运行结束的保护文件与输出校验和检查通过，未发现新的 Evaluation Infrastructure bug。

### 7.1 Decision & Workflow

| 指标 | correct | incorrect | N/A | unavailable | 有效分母 | Accuracy |
|---|---:|---:|---:|---:|---:|---:|
| Info Sufficiency | 8 | 1 | 0 | 1 | 9 | 88.9% |
| Case Research Decision | 6 | 0 | 2 | 2 | 6 | 100% |
| Research Sufficiency | 0 | 0 | 10 | 0 | 0 | — |
| Search <=2 | 10 | 0 | 0 | 0 | 10 | 100% |
| Concept regeneration <=1 | 10 | 0 | 0 | 0 | 10 | 100% |
| Fallback correctness | 0 | 0 | 10 | 0 | 0 | — |
| Completion | 1 | 9 | 0 | 0 | 10 | 10% |

原七个 Info bad cases 中，02/04/06/08/09 五个正确继续；05 仍 false，10 因 parse 请求失败没有产生 Decision。Case 03 仍正确 ask_user。Case 09 将城市/坐标、用地红线/CAD、容积率/高度列 optional，未再被绝对定位阻断。

Case 05 仍要求范围、形态、尺度和路径关系，check_case_need 未执行，其 no-case-research 路由尚未验证。将其保留为 residual bad case，本轮后不继续针对单个样本改 P0，以避免过拟合和扩大变量。

### 7.2 Quality 与 Coverage

| 指标 | Mean | valid_cases | N/A | unavailable |
|---|---:|---:|---:|---:|
| Site Analysis | 4.6 | 5 | 4 | 1 |
| Case Research | — | 0 | 6 | 4 |
| Groundedness | 4.2 | 5 | 3 | 2 |
| Concept Quality | — | 0 | 5 | 5 |
| End-to-End Usability | — | 0 | 8 | 2 |

Site Analysis / Case Research 实际节点执行覆盖从 2/10 增至 7/10，但七个案例研究节点都失败，没有正式案例输出；Concept / Report 执行覆盖仍为 0。Site 与 Groundedness 有效评分均从 1 增至 5，质量覆盖改善局限于前序专业输出。不能以新增均值断言整个研究质量或 E2E 质量已经提升。

### 7.3 Operational 与执行结果

报告完成 0、early-stop 2、execution failure 8。Agent runtime median 85.52 秒、P95 148.31 秒；LLM SDK calls 45、Search calls 35、Image calls 0；Agent tokens=null、cost=null。Judge SDK calls 11，tokens=null、cost=null；11 次适用且输出可用的指标 Judge 调用中 10 次 scored，1 次失败，指标调用失败率 9.1%。SDK calls 包括技术重试，不能一般性等同指标调用数。

Agent failure rate=80%，四次 source_consistency_validation、四次 llm_call_or_validation。case_09 Groundedness Judge 的 llm_call_or_validation 单独记 unavailable，不计 Agent failure，也没有阻断 Case 10。部分 SDK 请求失败导致可靠 token 总量 unavailable，不补估未知消耗。

| Case | 路径 / 终点 |
|---|---|
| 01 | parse → site → check_case_need → case_research；LLM 输出处理失败 |
| 02 | 同上；来源一致性失败 |
| 03 | parse → ask_user → END，符合预期 |
| 04 | parse → site → check_case_need → case_research；来源一致性失败 |
| 05 | parse → ask_user → END，残留 Info 错判 |
| 06 | parse → site → check_case_need → case_research；来源一致性失败 |
| 07 | 同上；LLM 输出处理失败 |
| 08 | 同上；来源一致性失败 |
| 09 | 同上；最终包含 Provider PermissionDeniedError |
| 10 | parse 请求 PermissionDeniedError，没有 Decision 输出 |

### 7.4 与 Baseline 对比及判定

| Metric | v0.1 Baseline | P0 Regression | Change |
|---|---:|---:|---:|
| Info Accuracy | 30%（3/10） | 88.9%（8/9） | +58.9 个百分点，分母不同 |
| Completion | 10% | 10% | 不变 |
| Case Decision 有效分母 | 2 | 6 | +4 |
| Research Decision 有效分母 | 0 | 0 | 不变 |
| Site Analysis valid_cases | 1 | 5 | +4 |
| Groundedness valid_cases | 1 | 5 | +4 |
| Case / Concept / E2E valid_cases | 0 / 0 / 0 | 0 / 0 / 0 | 不变 |
| Agent execution failure rate | 20% | 80% | +60 个百分点 |

判定为 **partially passed**：Gate 与早期覆盖改善，negative control 保持；仍有残留错判和不可用 Decision，未改善 Completion。更多 Case 暴露到后续执行失败，不应把 failure rate 增加直接等同 P0 造成业务逻辑退化。单轮比较、动态检索与模型输出波动不能证明所有变化具有确定因果。

## 8. P1 Failure Diagnosis

本节只检查上述 Regression 已保存的 Case JSON、Trace、evidence、当前调用链和历史独立诊断。不追加运行、不修改 Agent/Prompt/Schema/Validator，也不调用 Provider。以下 unknown 不是确认的模型或 Schema 缺陷。

### 8.1 Source Consistency Failures

Validator 对合并 evidence 建立原始 URL 字典，逐 Case 检查：`case.source in evidence` 且 `case.name == evidence[case.source]["title"]`。前者是精确 URL membership，后者是精确标题比较。前序合并使用 _url_identity 去重（含尾斜杠、追踪参数等处理），但候选来源 guard 仍使用保留的原始 URL；它没有把同一种身份归一化应用于候选匹配。此差异是静态敏感点，不是本轮已确认的触发原因。

| Case | Search source exists | URL match | Title match | Representation difference | Genuine mismatch | Root cause confidence |
|---|---|---|---|---|---|---|
| 02 | 6 query 成功，55 条合并 evidence；候选对应项未知 | 未知 | 未知 | 未确认 | 未确认 | 确认来源 guard 拒绝；具体原因 unresolved due to insufficient observability |
| 04 | 5 query 最终成功，49 条 evidence；候选对应项未知 | 未知 | 未知 | 未确认 | 未确认 | 同上 |
| 06 | 4 query 成功，35 条 evidence；候选对应项未知 | 未知 | 未知 | 未确认 | 未确认 | 同上 |
| 08 | 5 query 成功，46 条 evidence；候选对应项未知 | 未知 | 未知 | 未确认 | 未确认 | 同上 |

实际 error 均为“案例来源或标题不属于检索证据”，不是重复标识或分析关联错误。按 Skill 顺序，候选已通过 _CaseResults Schema 后触发 guard；URL 或 title 至少一项不满足，但日志不能分辨被拒字段。

原始 title/URL/snippet/source 已保存在 retrieval_evidence 与逐 query search_observations。示例包括 Case 02 的《案例借鉴∣TOD：城市流量的新磁场》（urbanchina.org）、Case 04 德国鲁尔园区与红旗坊项目、Case 06 mooool / Hassell 滨水材料、Case 08 TOD 社区与历史保护材料。这只能证明材料存在，不能把这些示例当成模型实际选择的候选。

四个 Case 均未保存被拒 LLM 候选的 name/source，也没有原始模型文本。因此无法对标题改写、跨来源合并、HTML entity、大小写/空白/标点、Unicode、尾斜杠或 URL 编码逐项判断。本轮**未确认 HTML entity 为真实根因**；历史 Case 07 同 URL 的 `&rsquo;` → `’` 仅证明此类误拒曾发生。

Case 04 有一次 Search SDK ConnectionError，随后技术重试成功：5 query 最终均有结果，Search SDK calls=6。该临时错误不是最终来源 guard 失败的充分解释。候选证据仍必须补齐后再决定 normalization 范围。

### 8.2 LLM Failures 分层分类

分类使用请求结果与输出处理两层。当前 llm_call_or_validation 聚合标签不能区分 Provider 4xx 和 JSON/Pydantic 错误。raw JSON、finish_reason、HTTP 原始状态、request_id、validation field 均未持久化。

| Case / stage | SDK / Provider observation | JSON / Schema observation | Retry 可确认范围 | 分类与置信边界 |
|---|---|---|---|---|
| 01 / analyze_cases | case_research 内 4 次 SDK calls，无 LLM SDK 异常，usage 已记录；HTTP 具体状态未保存 | evidence 已送入分析；未保存 finish_reason、raw JSON、parse/validation 结果 | 两个 structured 调用（query + analysis）合计 2 次额外技术调用；不能分配到各 stage | I unknown，定位于分析输出处理；E/F/G/H 均待证据 |
| 07 / analyze_cases | 同为 4 次，无 LLM SDK 异常，usage 已记录 | 同上 | 同上 | I unknown；不能认定与历史 nullability 同因 |
| 09 / analyze_cases | 内 4 次，最终记录 PermissionDeniedError；前序请求亦可能发生输出重试 | 未保存成功与失败调用的逐次 JSON/校验信息 | query + analysis 合计 2 次额外技术调用；最终 403 本身不可重试，无法定位此前重试原因 | A provider_permission 的粗分类；具体记 provider_permission_or_account_failure，B quota/billing 未证实 |
| 10 / parse_and_check | 1 次 SDK call，PermissionDeniedError，无有效 Decision | 没有可供解析/校验的成功响应记录；不能定性 Schema 失败 | 0 次重试 | A 粗分类；provider_permission_or_account_failure，账户/模型/endpoint/计费子类未明 |

上述合计 retry 推断依据当前调用链：每个失败案例研究已成功生成 query 且进入 analyze_cases，共两个公共 structured 调用；SDK 自带重试为 0。4 次 SDK 调用说明合计两个额外应用层尝试，但不是“每个阶段都重试两次”。没有逐 attempt trace，不能声称三次分析输出都是同一种错误。

Case 01/07 的 SDK 调用未出现 provider_wrapper 捕获的异常，说明响应对象已返回；这不证明响应 content 是完整合法 JSON。_request 还会拒绝非 stop finish_reason、空文本、invalid JSON、Pydantic 非法结果，最终统一抛出 LLMError 并隐藏异常链。因此目前无法在 invalid_json / schema_validation / nullability / truncation 中进一步分类。

Case 09 Groundedness Judge 另有一次 llm_call_or_validation；Judge scope 未保存底层 SDK 异常类型，不能依据前后时间邻近就断定同为 403 或相同 quota 问题。

### 8.3 PermissionDeniedError：Operational / Provider

静态读取当前安装 OpenAI SDK：HTTP 403 映射为 PermissionDeniedError，该类型 status_code 为 403。故 Case 09/10 的 HTTP 403 可以由实际异常类型与 SDK 映射推断，但不是日志中保存的 status_code 字段；没有安全 provider code、响应摘要或 request_id。

现有证据不能区分 API 权限、模型权限、Workspace/endpoint 权限、账户额度/计费或其他 403 业务原因，也不能把它归为 429 rate limit、timeout/5xx、JSON 或 nullability。已观察到请求到达 Provider 并遭拒，不是“请求未发送”。

按现有冻结统计，这两项仍属于 execution failure；根因分析应独立标注 Operational / Provider failure，没有证据证明是 Agent 专业判断或业务逻辑错误。应独立核查账户与 Provider 配置，不用 Agent Prompt/Schema 改动掩盖。当前不切模型、不改配置、不真实验证。

### 8.4 安全 Observability 改进建议（未实施）

当前已具备 node、成功/失败状态、partial State、实际 query、逐 query 标准化结果、合并 evidence、节点 SDK 次数与安全 error。缺口主要在统一 LLM 输出处理和 Skill 来源 guard，Eval wrapper 当前只保存输入 evidence，不保存返回候选。

建议最小诊断记录：run/case/node、逻辑 stage（generate_search_queries / analyze_cases 等）、调用与 attempt 标识、attempt_index / retries_used；SDK outcome、exception_type、http_status、脱敏 provider_error_code、request_id、finish_reason、响应长度；json_parse_success、validation_success、validation_field/error_type、预期类型及实际类型、字段缺失/null/额外字段标记。字段值默认不记录；确需原文时仅限受控、脱敏、权限受限的显式诊断副本，不默认保存完整敏感内容。

Source mismatch 单独记录被拒候选索引、candidate title/URL、对应 evidence title/URL 或不存在标记、exact_url_match/exact_title_match、规范化差异类别；只保留公开检索来源的必要片段，移除 URL secret/query token，避免记录完整专业分析或用户资料。输出已通过 Schema 时在 guard 前保存诊断候选来源对照，不把候选提前写入 AgentState。

不记录 API Key、敏感 header、完整敏感 Prompt、data URI 或私有文件内容。异常处理层保留对外受控错误，同时另行记录白名单诊断字段；不增加 State 字段、不改变 retry、路由或 fallback 行为。建议先用离线测试证明诊断不改变业务结果、不会泄露 secret，并能区分请求失败与输出失败。

### 8.5 Failure Modes 与下一轮最小顺序

P1 应拆为 **P1-A Source validation robustness** 与 **P1-B LLM / structured-output robustness（具体根因未明）**。Provider 403 独立列为 **Operational / Provider failure**，不把三者混成一个 Schema 或 normalization 问题。

1. **Fix 1：先补安全 observability。** 在另行授权的最小范围中捕获 per-attempt 输出状态和被拒来源对照，保持业务行为不变；无需再次跑完整 Regression 才能设计这些字段。
2. **Provider issue：独立核查。** 使用安全 code/status/request_id 确认权限或账户原因；解决后再按授权进行最小能力验证，避免把账户故障与 Agent 改动混入同一归因实验。
3. **Fix 2：source normalization 条件式实施。** 历史证据足以支持考虑表示等价，但本轮无法决定四项失败应如何修。先确认候选差异，再最小处理已证明的等价；保留 genuine URL/title mismatch 的拒绝与离线反例。不泛化删除标点或任意模糊匹配。
4. **Fix 3：structured compatibility 按具体错误修。** 只有看到字段、类型、finish_reason 或解析异常后才选择对应最小修复；不复用此前 nullability 修补作猜测，不放宽整套 Schema，不静默转换任意 null。与 source fix 分开验证以利归因。

P0 本轮停止继续优化，Case 05 作为 residual bad case 原样保留。任何后续修复不按 Case ID 特判、不改 Dataset Ground Truth，不以改善本 Dataset 得分为由取消来源/类型约束。本节仅诊断与建议，未进入 P1 Optimization。
