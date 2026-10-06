# AGENTS.md

## 1. 项目

基于 LangGraph 的 项目前期研究 Agent。

项目面向城市设计前期研究阶段，辅助完成：
项目资料理解→ 场地条件分析→ 案例研究判断→ 案例搜索与分析→ 设计机会识别→ 概念方向生成→ 意向图生成→ 研究报告输出

V1 默认技术栈：

```text
LangGraph
+ 通义千问
+ Tavily
+ Qwen Image
```

V1 目标：验证 Agent 能否根据 State 自主决策，完成从项目输入到研究报告的闭环。

详细产品与 Agent 设计见 `docs/`。开发前应优先阅读相关设计文档。

如果实现需要改变既有架构、State、Skill、Tool 或 V1 Scope，应同步修改对应 `docs/` 文档，不要静默改变设计。

## 2. 关键架构约束

- 单 Agent + 单 Graph，不使用 Multi-Agent
- V1 保持既定 9 个核心 Node 和条件路由结构
- 案例搜索最多 2 轮
- 概念重新生成最多 1 轮
- 不使用 Interrupt / Checkpoint
- 不引入 MCP / RAG / GIS / Multi-Agent
- 最终报告只输出 Markdown

完整架构见：

`docs/03-agent-design/agent-architecture.md`

## 3. 分层职责

```text
Graph → 编排、路由、循环控制
Node  → 读取 State、调用 Skill、返回更新字段
Skill → 完成专业任务
Tool  → 提供外部能力
```

**禁止：**

- Node 写大段专业 Prompt 或直接调用 Provider
- Skill 承担 Graph Routing
- Tool 直接读写 Agent State
- Tool 承担专业判断
- Provider-specific 逻辑泄漏到 Skill

## 4. State 规则

- 顶层使用 `TypedDict`，统一名称为 `AgentState`
- 复杂业务对象使用 Pydantic Schema 校验
- Node 只返回本次更新字段，不返回完整 State
- 初始 State 只写必要字段，不预填空值
- Skill 内部临时变量不进入 State
- 不随意新增 State 字段；新增字段必须具有跨 Node、路由判断、阶段结果或评测价值

完整字段见：

`docs/03-agent-design/state-design.md`

## 5. 容易违反的规则

### ask_user

- 图语义上：`ask_user → 用户补充 → parse_and_check`
- V1 实现上：`ask_user → END`
- 用户补充信息后由前端重新调用 `graph.invoke()`
- 不要添加：

```python
builder.add_edge("ask_user", "parse_and_check")
```

- 不要引入 `interrupt()` / Checkpoint

### img2img

- 默认使用 `text2img`
- `USE_IMG2IMG` 控制是否允许使用 img2img
- 只有存在 `site_images` 且 Provider 支持时才使用 img2img
- fallback 决策由 Concept Generation Skill 负责
- Tool 不自主改变生成模式
- 图像生成失败不阻断主流程

### search_attempts

- `search_attempts` 由 Node / Graph 层更新
- Case Research Skill 不修改 `search_attempts`
- Tool 技术重试与案例研究业务循环必须分离

### quality_check

- Concept Generation Skill 内部执行
- 最多自动重新生成 1 次
- `quality_check` 不写入 State
- 不增加 Graph-level Concept Quality Loop

### report_composition

- 只组织和表达已有 State 结果
- 不重新生成新的场地结论、案例判断、设计机会或概念方向
- 最终报告应与前序结构化结果保持一致

## 6. 配置

- 系统配置统一放在 `src/config.py`
- 配置不进入 Agent State
- API Key 通过 `.env` 管理，禁止提交
- `.env.example` 只保存变量名称和安全默认值

典型配置包括：

```text
LLM_PROVIDER
LLM_MODEL

WEB_SEARCH_PROVIDER
WEB_SEARCH_MAX_RESULTS

IMAGE_PROVIDER
IMAGE_MODEL

MAX_SEARCH_ATTEMPTS
MAX_CONCEPT_REGENERATIONS

USE_IMG2IMG
TOOL_MAX_RETRIES
LLM_MAX_RETRIES
```

V1 图像 Provider 为 Qwen Image，下一阶段默认 `IMAGE_PROVIDER=qwen`、`IMAGE_MODEL=qwen-image-3.0-pro`；凭据复用 `DASHSCOPE_API_KEY`，endpoint 默认复用 `LLM_BASE_URL`。不新增 `IMAGE_API_KEY`。参考强度不是 V1 强制配置，Stage 5 仅在真实 API 有明确对应参数时决定映射。

`TOOL_MAX_RETRIES` 控制 Tavily / Tool 技术重试，`LLM_MAX_RETRIES` 控制 LLM 调用与输出校验重试；两者都不改变业务轮次。

## 7. V1 Scope

未经设计文档明确调整，不要自行增加：

```text
Multi-Agent
RAG
Vector Database
GIS 自动分析
MCP
长期 Memory
Interrupt / Checkpoint
复杂 Human Review Graph
PDF / PPT / DOCX Export
复杂 Provider Router
```

不要为了未来可能的需求提前增加复杂抽象。

## 8. 实施顺序

```text
1. 配置 + Schema + State
        ↓
2. 基础 Skills + Nodes + Routes + Graph
        ↓
3. 跑通无外部依赖的最小闭环
        ↓
4. Web Search + Case Research 循环
        ↓
5. Image Generation text2img
        ↓
6. img2img + fallback
        ↓
7. Streamlit
        ↓
8. Tests
        ↓
9. Evaluation
        ↓
10. README / Demo
```

优先跑通 Agent 核心闭环，不要优先开发复杂前端、Provider 抽象或非 V1 能力。

## 9. 核心原则

> 先跑通稳定、可解释、可评测的 Agent 闭环，再逐步增加能力。

当实现方案有多个选择时，优先选择：

> 最符合设计文档、最容易验证、最少引入额外复杂度的方案。

当发现现有设计无法实现或需要改变时：

1. 先指出具体冲突；
2. 说明为什么需要修改；
3. 明确受影响的代码和设计文档；
4. 再实施修改。

不要未经说明自行改变核心架构。
