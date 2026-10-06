# Design Decisions

## 文档目的

本文档记录项目前期研究 Agent 在 V1 设计阶段的关键架构决策（ADR，Architecture Decision Record）。

每条 ADR 包含：

- **背景**：为什么需要做这个决策；
- **决策**：最终选择了什么；
- **理由**：为什么这样选；
- **代价**：选择了什么就要放弃什么；
- **替代方案**：考虑过哪些其他选项；
- **演进路径**：未来什么时候可能需要重新审视。

**上游依据：**
- `agent-architecture.md`
- `state-design.md`
- `skills.md`
- `tools.md`

**用途：**
- 面试时能讲清每个设计取舍；
- Vibe Coding 时 AI 理解为什么这样设计；
- 后续迭代时知道哪些决策可以重新考虑。


## ADR-001：采用单 Agent + 单 Graph 架构

| 项目 | 内容 |
|---|---|
| **背景** | 城市设计前期研究包含多个专业环节，考虑是否采用 Multi-Agent 架构 |
| **决策** | V1 采用单 Agent + 单 Graph，不采用 Multi-Agent |
| **理由** | 各环节之间有明确先后关系和共享状态，使用一个主 Graph 编排即可；Multi-Agent 会增加通信成本和调试难度 |
| **代价** | 扩展性有限，单点复杂 |
| **替代方案** | Multi-Agent（分诊 Agent、处理 Agent、审核 Agent） |
| **演进路径** | 当任务显著分化（如需要独立并行研究）时，再考虑 Multi-Agent |


## ADR-002：Skill 按完整专业任务划分，不按 Prompt 拆分

| 项目 | 内容 |
|---|---|
| **背景** | 城市设计前期研究包含多个专业环节，需要考虑 Skill 的划分粒度 |
| **决策** | 按完整专业任务划分 Skill，V1 设置 4 个：Site Analysis、Case Research、Concept Generation、Report Composition |
| **理由** | 一个 Skill 可以包含多个 Prompt 和多次 LLM 调用；按 Prompt 拆分会导致 Skill 数量过多，接口碎片化 |
| **代价** | Skill 内部逻辑较多 |
| **替代方案** | 按单个 Prompt 拆分（如 SWOT Skill、Opportunity Skill、Vision Skill） |
| **演进路径** | 如果某个 Skill 内部逻辑过于复杂，可考虑拆分，但需要满足「独立目标 + 明确输入输出 + 可复用」标准 |


## ADR-003：项目理解不单独成 Skill

| 项目 | 内容 |
|---|---|
| **背景** | 「项目理解」既可以理解为「解析输入」，也可以理解为「分析项目定位」 |
| **决策** | 项目原始信息解析由 `parse_and_check` Node 直接完成，项目定位专业分析归入 Site Analysis Skill |
| **理由** | 只调 1 次 LLM 的解析不是复合能力；将其独立成 Skill 会导致职责重叠 |
| **代价** | 无 |
| **替代方案** | 独立 Project Understanding Skill |
| **演进路径** | 如果项目理解需要独立的专业逻辑（如行业专属分析），可考虑独立 |


## ADR-004：机会识别合并进 Concept Generation Skill

| 项目 | 内容 |
|---|---|
| **背景** | 设计机会识别是从场地分析进入概念生成的中间推理 |
| **决策** | 机会识别、目标愿景、概念方向、意向图合并为 Concept Generation Skill |
| **理由** | 属于连续创作过程，拆开增加 LLM 调用次数，降低连贯性 |
| **代价** | Skill 内部逻辑较多 |
| **替代方案** | 独立 Opportunity Identification Skill |
| **演进路径** | 无 |


## ADR-005：概念质量检查放在 Skill 内部，不单独设 Node

| 项目 | 内容 |
|---|---|
| **背景** | 概念方向生成后需要检查质量 |
| **决策** | 概念质量检查属于 Concept Generation Skill 内部逻辑，不进入 State；最多自动重新生成 1 次，第二次生成后直接返回当前结果，不再继续循环，不形成额外 Graph Node 或 Graph 循环 |
| **理由** | 自检是一次 LLM 调用，放在 Skill 内部即可；独立成 Node 会增加条件边和循环 |
| **代价** | 自检逻辑不显式体现在状态机图中 |
| **替代方案** | 独立 `check_concept` Node + 条件边 |
| **演进路径** | 如果需要更复杂的概念评估（如多维度评分），可考虑独立成 Node |


## ADR-006：案例搜索循环上限 2 轮

| 项目 | 内容 |
|---|---|
| **背景** | 案例搜索可能需要多次调整关键词才能找到足够案例 |
| **决策** | 案例搜索最多 2 轮；超过后带限制说明继续 |
| **理由** | 平衡覆盖面和效率，避免无限循环 |
| **代价** | 两轮不够时可能案例质量不足 |
| **替代方案** | 无上限（会死循环）或 1 轮（覆盖面不足） |
| **演进路径** | 根据实际评测结果调整上限 |


## ADR-007：场地图片可选作为 img2img 参考

| 项目 | 内容 |
|---|---|
| **背景** | 意向图生成是否应该参考场地图片 |
| **决策** | 默认 `text2img`；通过配置项 `USE_IMG2IMG` 可选启用 img2img |
| **理由** | 概念探索阶段需要创意自由，text2img 更合适；甲方要求「像我们的场地」时，img2img 更合适 |
| **代价** | 增加配置项和分支逻辑；img2img 需要 Provider 支持 |
| **替代方案** | 纯 text2img（无场地参考）或默认 img2img（创意受限） |
| **默认值** | `USE_IMG2IMG=false`；V1 不强制参考强度配置，Stage 5 确认 Qwen Image 实际参数后再决定映射 |
| **演进路径** | 根据实际使用效果调整默认值和 strength 参数 |


## ADR-008：img2img 不增加 Graph 复杂度

| 项目 | 内容 |
|---|---|
| **背景** | 引入 img2img 后，是否需要增加 Node、State 字段、条件边 |
| **决策** | img2img 完全在 Concept Generation Skill 内部判断，不增加 Node、State 字段、条件边 |
| **理由** | img2img 是 Skill 内部实现细节，不影响 Graph 结构；`site_images` 本来就在 State 中 |
| **代价** | 判断逻辑藏在 Skill 内部 |
| **替代方案** | 增加 `check_img2img` Node 或 `use_img2img` State 字段 |
| **演进路径** | 如果需要按任务区分 img2img 行为，可增加 State 字段 |


## ADR-009：img2img 失败自动回退 text2img

| 项目 | 内容 |
|---|---|
| **背景** | img2img 可能因参考图无效、Provider 不支持、调用失败而失败 |
| **决策** | img2img 失败时自动回退 text2img，不阻断主流程 |
| **理由** | 意向图属于增强能力，不是概念生成成功的必要条件 |
| **代价** | 生成结果可能不包含场地参考 |
| **替代方案** | 报错中断或跳过意向图 |
| **演进路径** | 记录回退原因，供后续评测分析 |


## ADR-010：Provider Adapter 屏蔽不同 Provider 差异

| 项目 | 内容 |
|---|---|
| **背景** | 不同图像生成 Provider 对参考图约束强度使用不同参数名 |
| **决策** | V1 图像 Provider 为 Qwen Image，默认 `IMAGE_MODEL=qwen-image-3.0-pro`；Image Generation Tool 内部完成必要参数映射。凭据复用 `DASHSCOPE_API_KEY`，endpoint 默认复用 `LLM_BASE_URL`，不新增 `IMAGE_API_KEY`。`reference_strength` 非强制，Stage 5 仅在实际 API 存在明确对应参数时决定映射 |
| **理由** | 避免 Concept Generation Skill 与具体 Provider 强耦合；切换 Provider 不需修改 Skill |
| **代价** | Tool 内部增加映射逻辑 |
| **替代方案** | Skill 直接调用 Provider 原生 API |
| **演进路径** | 新增 Provider 时只增加 Adapter，不改上层 |


## ADR-011：Tool 技术重试与业务循环分离

| 项目 | 内容 |
|---|---|
| **背景** | Tool 调用可能失败，需要考虑重试 |
| **决策** | Tool 技术重试由 `TOOL_MAX_RETRIES` 控制；LLM 调用、JSON 解析、Pydantic 校验技术重试由 `LLM_MAX_RETRIES` 控制；图像调用技术重试由独立的 `IMAGE_MAX_RETRIES` 控制；业务循环仍由 Graph 层控制 |
| **理由** | 职责清晰，避免 Tool 承担 Agent 流程逻辑 |
| **代价** | 无 |
| **替代方案** | Tool 内部做完整重试和降级 |
| **演进路径** | 无 |


## ADR-012：不使用独立的 Image Analysis Tool

| 项目 | 内容 |
|---|---|
| **背景** | 项目地图、卫星图、现状照片等需要被解析 |
| **决策** | V1 不封装 Image Analysis Tool；图片解析由多模态模型直接读取 |
| **理由** | 图片解析本质是多模态 LLM 的一次调用，不涉及外部服务；封装成 Tool 反而增加抽象层 |
| **代价** | 图片解析逻辑在 Skill 内部直接调用 LLM |
| **替代方案** | 封装 Image Analysis Tool |
| **演进路径** | 如果后续引入专业图像分析 API（如 GIS 解析），再封装为 Tool |


## ADR-013：V1 不引入 MCP

| 项目 | 内容 |
|---|---|
| **背景** | MCP 是 AI 与外部工具之间的标准化协议 |
| **决策** | V1 使用 LangGraph 原生 Function Calling，不引入 MCP |
| **理由** | 当前工具仅 2 个且固定，Function Calling 更简单、迭代更快；MCP 的标准化和动态发现优势在此阶段不明显 |
| **代价** | 工具扩展需手动适配 |
| **替代方案** | 通过 `langchain-mcp-adapters` 集成 MCP |
| **演进路径** | 当工具数量超过 10 个，或需要接入外部 MCP Server 时再引入 |


## ADR-014：种子案例先不做

| 项目 | 内容 |
|---|---|
| **背景** | 案例研究可以采用纯搜索或「种子案例库 + 搜索」混合方案 |
| **决策** | V1 先做纯搜索，种子案例后续再加 |
| **理由** | 先跑通主流程，搜索失败降级可后补 |
| **代价** | 搜索失败时无种子案例兜底，只能基于当前已有结果带限制说明继续 |
| **替代方案** | 建 5-10 个种子案例库作为降级 |
| **演进路径** | 加 `seed_retriever` Tool，在 Case Research Skill 内降级 |


## ADR-015：不加独立人工审核节点

| 项目 | 内容 |
|---|---|
| **背景** | 是否需要在关键决策点暂停等人工确认 |
| **决策** | V1 只用 `ask_user`，不加 `human_review`；研究方向或指定案例在初始输入或重新发起任务时提供，不增加运行中人工确认或修改的暂停流程 |
| **理由** | 无高风险操作，概念选择由前端交互完成 |
| **代价** | 无强制人工确认 |
| **替代方案** | 加 `human_review` Node + Interrupt |
| **演进路径** | 接入真实业务系统时再加 |


## ADR-016：`ask_user` 用前端重新调用，不用图内 Interrupt

| 项目 | 内容 |
|---|---|
| **背景** | 信息不足时，`ask_user` 输出追问后需要等用户补充信息 |
| **决策** | V1 不用 `interrupt`，用户补充信息后由前端重新发起 `graph.invoke()` |
| **理由** | 避免引入 Interrupt 和 Checkpointer 的复杂度；前端逻辑更简单 |
| **代价** | 每次用户补充都是「新的图调用」，不是「同一个任务继续」 |
| **替代方案** | 用 LangGraph Interrupt + Checkpoint |
| **演进路径** | 当需要「任务连续上下文」时，改为 Interrupt 模式 |


## ADR-017：前端用 Streamlit

| 项目 | 内容 |
|---|---|
| **背景** | 需要给规划师一个输入输出界面 |
| **决策** | 用 Streamlit 做简单界面 |
| **理由** | 快速出界面，无需 HTML/CSS/JS；适合 MVP |
| **代价** | 定制性有限 |
| **替代方案** | React / Vue |
| **演进路径** | 需要复杂交互时再迁移 |


## ADR-018：报告格式 Markdown

| 项目 | 内容 |
|---|---|
| **背景** | 报告输出格式有 Markdown、PDF、PPT、HTML 等选择 |
| **决策** | V1 只输出 Markdown |
| **理由** | 快速、可评测、易展示；PDF/PPT 生成成本高且收益低 |
| **代价** | 无 PDF/PPT 导出 |
| **替代方案** | 直接输出 PDF 或 PPT |
| **演进路径** | V1 不实现 HTML / PDF / PPT / DOCX；其他格式仅在后续版本明确调整范围后考虑 |


## ADR-019：config.py 放 src 顶层，不放 agent 里

| 项目 | 内容 |
|---|---|
| **背景** | 配置项集中管理，需要决定放哪 |
| **决策** | 放 `src/config.py` 顶层 |
| **理由** | config 是最底层，agent、skills、tools 都要用；放 agent 里会造成反向依赖 |
| **代价** | 无 |
| **替代方案** | `src/agent/config.py` 或 `src/utils/config.py` |
| **演进路径** | 无 |


## ADR-020：V1 用 TypedDict 定义 State，不引入 Pydantic

| 项目 | 内容 |
|---|---|
| **背景** | State 定义可以选择 TypedDict 或 Pydantic |
| **决策** | V1 用 TypedDict 定义 State；复杂业务对象用 Pydantic Schema 校验 |
| **理由** | TypedDict 轻量，LangGraph 原生支持；Pydantic 用于复杂字段校验 |
| **代价** | State 本身无运行时校验 |
| **替代方案** | 全用 Pydantic |
| **演进路径** | 需要 State 运行时校验时再迁移 |


## ADR-021：Skill 输出经过 Schema 校验后再写入 State

| 项目 | 内容 |
|---|---|
| **背景** | LLM 输出结构不稳定，可能污染 State |
| **决策** | Skill 返回的复杂结构通过 `schemas/` 中的 Pydantic Model 校验后再写入 State |
| **理由** | 避免 LLM 输出结构不稳定的数据直接进入 State |
| **代价** | 增加校验代码 |
| **替代方案** | 直接写入 State |
| **演进路径** | 无 |


## ADR-022：Node 只返回需要更新的字段，不返回完整 State

| 项目 | 内容 |
|---|---|
| **背景** | Node 执行后需要更新 State |
| **决策** | Node 只返回本次需要更新的字段，LangGraph 自动合并 |
| **理由** | 避免 Node 覆盖其他字段；方便调试 |
| **代价** | 无 |
| **替代方案** | Node 返回完整 State |
| **演进路径** | 无 |


## ADR-023：Tool 不直接读写 Agent State

| 项目 | 内容 |
|---|---|
| **背景** | Tool 需要 State 中的字段（如 `site_images`）作为输入 |
| **决策** | Tool 输入由 Skill 传入，输出由 Skill 接收，Node 负责写回 State |
| **理由** | 职责清晰；Tool 不应关心 Agent 流程 |
| **代价** | 数据传递经过 Skill 中转 |
| **替代方案** | Tool 直接读 State |
| **演进路径** | 无 |


## ADR-024：V1 不提前创建复杂目录结构

| 项目 | 内容 |
|---|---|
| **背景** | 是否为未来扩展提前创建 `providers/`、`nodes/` 等目录 |
| **决策** | V1 用单文件 `nodes.py`、单文件 `image_generation.py`，不提前抽象 |
| **理由** | 先跑通主流程；文件超过 500 行或出现多个 Provider 时再拆 |
| **代价** | 文件可能膨胀 |
| **替代方案** | 提前创建完整目录 |
| **演进路径** | 超过阈值时再拆分 |


## ADR-025：State 区分 missing_critical 和 missing_optional

| 项目 | 内容 |
|---|---|
| **背景** | 信息不足时，是否需要区分「必须补充」和「可选补充」 |
| **决策** | State 中拆分为 `missing_critical` 和 `missing_optional` |
| **理由** | 区分严重程度，避免过度追问；`missing_critical` 非空才触发 `ask_user` |
| **代价** | 增加一个字段 |
| **替代方案** | 单一缺失信息列表（未采用） |
| **演进路径** | 无 |


## 决策索引

| ADR | 决策 | 分类 |
|---|---|---|
| 001 | 单 Agent + 单 Graph | 架构 |
| 002 | Skill 按专业任务划分 | Skill |
| 003 | 项目理解不单独成 Skill | Skill |
| 004 | 机会识别合并进 Concept Generation | Skill |
| 005 | 概念质量检查放 Skill 内部 | Skill |
| 006 | 案例搜索循环上限 2 轮 | 循环 |
| 007 | 场地图片可选作为 img2img 参考 | img2img |
| 008 | img2img 不增加 Graph 复杂度 | img2img |
| 009 | img2img 失败自动回退 text2img | img2img |
| 010 | Provider Adapter 屏蔽差异 | Tool |
| 011 | Tool 技术重试与业务循环分离 | Tool |
| 012 | 不使用 Image Analysis Tool | Tool |
| 013 | V1 不引入 MCP | Tool |
| 014 | 种子案例先不做 | 案例研究 |
| 015 | 不加独立人工审核节点 | HITL |
| 016 | ask_user 用前端重新调用 | HITL |
| 017 | 前端用 Streamlit | 前端 |
| 018 | 报告格式 Markdown | 输出 |
| 019 | config.py 放 src 顶层 | 工程 |
| 020 | V1 用 TypedDict 定义 State | State |
| 021 | Skill 输出经过 Schema 校验 | State |
| 022 | Node 只返回需要更新的字段 | State |
| 023 | Tool 不直接读写 Agent State | Tool |
| 024 | V1 不提前创建复杂目录结构 | 工程 |
| 025 | State 区分 missing_critical 和 missing_optional | State |


## Summary

V1 的设计决策可以归纳为以下几条核心原则：

**1. 简化优先**

单 Agent、单 Graph、不引入 MCP、不用 Interrupt、不提前创建复杂目录。V1 聚焦跑通主流程，不为未来过度设计。

**2. 职责分离**

Agent / Node / Skill / Tool 四层职责清晰。Tool 不读写 State，Skill 不做路由，Node 不写业务逻辑。

**3. 配置驱动**

img2img、模型、搜索、图像生成都通过配置项切换。配置不进 State，不进 Graph。

**4. 有限控制**

案例搜索 2 轮上限，概念重新生成 1 轮上限。所有循环都有边界。

**5. 状态显式**

所有决策依据都在 State 中。`info_sufficient`、`need_case_research`、`research_sufficient`、`search_attempts` 都是显式字段。

**6. 可评测**

State 的 `images` 记录 `mode`、`reference_images` 等元信息，支持 Agent Evaluation；`quality_check` 只存在于 Concept Generation Skill 内部，不进入 State。Tool 层记录 `latency`、`provider` 等运行数据。

**7. 可选增强**

img2img 是可选增强，默认关闭；意向图默认尝试生成，失败时允许 `images` 为空并继续报告。V1 不实现种子案例或 seed retriever；信息补充通过 `ask_user → END` 和前端重新调用完成，不使用 Interrupt / Checkpoint。
