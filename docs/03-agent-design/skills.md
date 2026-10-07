# Skills Design

## 1. Skill 设计目标

项目前期研究 Agent 使用 Skill 封装城市设计前期研究中的专业任务能力。

Skill 位于 Agent 编排层与 Tool 执行层之间：

```text
Agent / Graph
    ↓
Node
    ↓
Skill
    ↓
Tool
```

其中：

- **Agent / Graph**：决定任务流程和下一步行动；
- **Node**：负责读取 State、调用 Skill、更新 State；
- **Skill**：定义专业任务如何完成；
- **Tool**：提供搜索、图像生成等外部执行能力。

Skill 的核心作用不是控制 Agent 流程，而是将可复用的专业任务方法封装为稳定能力。

V1 Skill 设计遵循以下原则：

1. 按完整专业任务划分 Skill，不按单个 Prompt 拆分；
2. 同一专业任务中的连续推理过程尽量保持内聚；
3. Skill 不负责 Graph 路由和流程控制；
4. Skill 可以调用 LLM、Prompt、Schema 和 Tool；
5. Skill 输入输出保持结构化；
6. Skill 输出经过 Schema 校验后再由 Node 写入 State；
7. 避免为了架构复杂度拆分过多细粒度 Skill；
8. Skill 接口保持稳定，内部 Prompt 数量和 LLM 调用方式可以根据实现效果调整。

## 2. Skill 总体结构

V1 设置四个核心 Skill：

```text
Skills
│
├── Site Analysis Skill
│      ├── 项目定位分析
│      ├── 场地条件分析
│      └── SWOT
│
├── Case Research Skill
│      ├── 检索策略生成
│      ├── 案例搜索
│      ├── 案例筛选
│      └── 案例分析
│
├── Concept Generation Skill
│      ├── 设计机会识别
│      ├── 目标愿景提炼
│      ├── 概念方向生成
│      ├── 概念质量检查
│      └── 意向图生成
│
└── Report Composition Skill
       ├── 内容组织
       ├── 来源整理
       └── Markdown 报告生成
```

对应代码：

```text
src/
├── skills/
│   ├── __init__.py
│   ├── site_analysis.py
│   ├── case_research.py
│   ├── concept_generation.py
│   └── report_composition.py
│
├── prompts/
│
├── schemas/
│   ├── site_info.py
│   ├── case.py
│   └── concept.py
│
└── tools/
    ├── web_search.py
    └── image_generation.py
```

V1 不预先创建没有实际用途的 `report.py`。最终报告以 Markdown String 形式输出，如后续需要结构化 Report Model，再增加对应 Schema。

## 3. Skill 与 Node、State、Tool 的关系

### 3.1 Skill 与 Node / Tool 对应关系

| Skill | 调用 Node | 主要 Tool | 典型 LLM 调用 | 主要输出 |
|---|---|---|---|---|
| Site Analysis | `site_analysis` | 无 | 1–2 次 | `site_analysis` |
| Case Research | `case_research` | Web Search | 1–2 次 / 轮 | `search_queries`、`filtered_cases`、`case_analysis` |
| Concept Generation | `concept_generation` | Image Generation | 2–4 次 | `opportunities`、`vision`、`concepts`、`images` |
| Report Composition | `report_composition` | 无 | 1 次 | `final_report` |

LLM 调用次数仅表示 V1 的典型实现方式，不属于 Skill 接口契约。

实际调用次数可以根据以下因素调整：

- Prompt 是否合并；
- 模型结构化输出能力；
- 质量评估结果；
- 响应时间；
- Token 成本。

因此 Skill 的稳定接口由输入输出定义，而不是由固定 LLM 调用次数定义。

### 3.2 不单独设计 Skill 的任务

| 任务 | 实现位置 | 原因 |
|---|---|---|
| 输入解析 | `parse_and_check` Node | 属于 Agent 输入处理 |
| 信息充分性判断 | `parse_and_check` Node | 属于流程决策 |
| 是否需要案例研究 | `check_case_need` Node | 属于流程决策 |
| 案例充分性判断 | `check_research` Node | 属于流程决策 |
| 搜索策略调整 | `refine_search` Node | 服务于 Graph 循环控制 |
| 案例研究轮次记录 | `case_research` Node | 属于流程控制状态 |

因此：

> Skill 负责专业任务执行，Decision Node 负责流程判断，Execution Node 负责调用 Skill 并更新 State。

### 3.3 Skill 与 State 字段映射

| Skill | 读取字段 | 写入字段 |
|---|---|---|
| Site Analysis | `project_background`、`location`、`planning_conditions`、`client_requirements`、`site_image_description`、`site_images` | `site_analysis` |
| Case Research | `site_analysis`、`research_direction`、`search_queries` | `search_queries`、`filtered_cases`、`case_analysis` |
| Concept Generation | `project_background`、`client_requirements`、`site_analysis`、`case_analysis`、`site_images`（可选，仅 img2img） | `opportunities`、`vision`、`concepts`、`images` |
| Report Composition | `project_background`、`location`、`planning_conditions`、`client_requirements`、`site_analysis`、`case_analysis`、`opportunities`、`vision`、`concepts`、`images` | `final_report` |

其中：

```text
search_attempts
```

不属于 Case Research Skill 的业务输出。

其更新逻辑由 `case_research` Node 负责：

```python
result = research_cases(...)

return {
    **result,
    "search_attempts": state.get("search_attempts", 0) + 1,
}
```

这样可以避免 Skill 承担 Graph 循环控制职责。

### 3.4 Skill 调用关系图

flowchart TD
    A[site_analysis Node] --> B[Site Analysis Skill]
    B --> B1[LLM: 项目定位分析]
    B --> B2[LLM: 场地条件分析]
    B --> B3[LLM: SWOT 分析]

    C[case_research Node] --> D[Case Research Skill]
    D --> D1[LLM: 生成搜索词]
    D --> D2[Web Search Tool]
    D --> D3[LLM: 筛选和分析案例]

    E[concept_generation Node] --> F[Concept Generation Skill]
    F --> F1[LLM: 设计机会识别]
    F --> F2[LLM: 目标愿景提炼]
    F --> F3[LLM: 概念方向生成]
    F --> F4[LLM: 概念质量检查]
    F --> F5[Image Generation Tool]

    G[report_composition Node] --> H[Report Composition Skill]
    H --> H1[LLM: 汇总生成报告]

## 4. Site Analysis Skill

### 4.1 Skill 目标

根据已经结构化的项目基础信息、场地图片及已有规划条件，对项目定位和场地条件进行专业分析，为案例研究和概念生成建立基础。

该 Skill 不再负责原始输入解析。

原始文本与图片中的基础信息已经由：

```text
parse_and_check
```

完成初步识别和结构化。

Site Analysis Skill 负责进一步回答：

> 当前项目是什么类型、场地具有什么条件、主要问题和资源是什么，以及这些条件对后续设计意味着什么。

对应人工工作流程：

```text
项目定位分析
    ↓
区位与功能条件分析
    ↓
场地资源和空间关系分析
    ↓
SWOT
    ↓
形成综合判断
```

### 4.2 输入

| 输入 | 来源 | 必需 |
|---|---|---:|
| `project_background` | State | 是 |
| `location` | State | 是 |
| `planning_conditions` | State | 否 |
| `client_requirements` | State | 否 |
| `site_image_description` | State | 否 |
| `site_images` | State | 否，有空间文字描述时可不提供 |

场地空间信息至少需要来自以下一种来源：

```text
site_images
或
用户提供的场地空间文字描述
```

`site_image_description` 作为已有图片理解结果使用，但 Skill 仍可直接读取 `site_images`，由多模态模型对原始图片进行进一步分析。

无图片时，`parse_and_check` 将用户提供的空间文字信息保留在既有项目理解字段中（如 `project_background`、`location`、`planning_conditions`），由 Node 传给 Skill；不要求 `site_image_description` 非空，也不新增 State 字段。`client_requirements` 统一为 `str | None`。

### 4.3 分析维度

Site Analysis Skill 重点分析以下内容：

| 维度 | 分析内容 |
|---|---|
| 项目定位 | 项目类型、功能定位、发展目标 |
| 区位条件 | 城市位置、周边功能、重要节点及联系 |
| 功能条件 | 已有功能、周边功能及潜在功能关系 |
| 景观资源 | 河流、湖泊、山体、绿地、绿道等蓝绿资源 |
| 公共空间 | 开放空间、公共节点、活动空间及连续性 |
| 交通与联系 | 主要道路、慢行联系、公共交通及主要出入口 |
| 空间界面 | 临街、滨水、城市界面及重要空间关系 |
| SWOT | 优势、劣势、外部机会、威胁 |

V1 主要基于：

```text
用户资料
+
多模态模型
+
规划条件
```

完成定性分析，不执行精确 GIS 测算。

### 4.4 内部流程

```text
读取项目结构化信息
        ↓
读取场地图片及图片描述
        ↓
分析项目定位
        ↓
分析场地资源与空间关系
        ↓
形成 SWOT
        ↓
形成综合分析结论
        ↓
Schema 校验
        ↓
返回 site_analysis
```

### 4.5 输出

输出对象：

```text
site_analysis
```

建议结构：

```json
{
  "project_positioning": "",
  "location_conditions": {},
  "functional_conditions": {},
  "landscape_resources": {},
  "public_space": {},
  "transportation": {},
  "spatial_conditions": {},
  "swot": {
    "strengths": [],
    "weaknesses": [],
    "opportunities": [],
    "threats": []
  },
  "analysis_summary": ""
}
```

其中：

```text
swot.opportunities
```

指 SWOT 语义中的外部机会条件，不等同于后续 Concept Generation Skill 输出的设计机会。

具体 Schema 在：

```text
src/schemas/site_info.py
```

中定义。

### 4.6 质量要求

Site Analysis Skill 的输出应满足：

- 分析内容能够追溯到用户输入或场地图像；
- 不虚构场地中无法确认的信息；
- 明确区分已有事实与分析判断；
- SWOT 与前序场地条件存在对应关系；
- 分析结果能够支持后续案例研究和概念生成；
- 不输出超出 V1 能力范围的精确 GIS 或规划测算结论。

### 4.7 接口签名

```python
def analyze_site(
    project_background: str,
    location: str,
    planning_conditions: dict | None = None,
    client_requirements: str | None = None,
    site_image_description: str | None = None,
    site_images: list[str] | None = None, # 图片可选，也可使用项目理解字段中的空间文字描述
) -> dict:
    """
    Returns:
    {
        "site_analysis": {...}
    }
    """
```

## 5. Case Research Skill

### 5.1 Skill 目标

根据 Agent 已确定的研究方向搜索相关案例，并从搜索结果中筛选具有参考价值的项目，提炼可用于当前项目的设计经验。

Case Research Skill 不负责判断：

> 是否需要案例研究。

该判断由：

```text
check_case_need
```

完成。

Case Research Skill 负责：

> 已经确定需要研究案例后，如何找到并分析合适的案例。

### 5.2 输入

| 输入 | 来源 | 必需 |
|---|---|---:|
| `site_analysis` | State | 是 |
| `research_direction` | State | 是 |
| `search_queries` | State | 否 |

首次执行时：

```text
research_direction
    ↓
生成 search_queries
```

重新执行时：

```text
refine_search
    ↓
更新 search_queries
    ↓
Case Research Skill 使用新的搜索方向
```

### 5.3 案例检索逻辑

案例研究不要求寻找与当前项目完全相同的项目，而是围绕“哪些项目能够回答当前设计问题”进行检索。

主要分为两类。

**同类型项目：**

```text
滨水中心区
中央商务区
TOD
商业中心
产业园区
城市公共空间
```

**同类资源或问题：**

```text
滨水空间处理
蓝绿资源整合
公共空间组织
城市界面处理
慢行系统
商业与开放空间融合
```

搜索逻辑为：

```text
项目类型
+
场地资源
+
核心设计问题
        ↓
形成研究方向
        ↓
生成 Search Query
```

### 5.4 内部流程

```text
读取 research_direction
        ↓
生成 / 读取 search_queries
        ↓
调用 Web Search Tool
        ↓
获得候选案例
        ↓
筛选相关案例
        ↓
提取案例事实
        ↓
分析案例策略
        ↓
分析与当前项目的关联
        ↓
Schema 校验
        ↓
返回案例研究结果
```

### 5.5 Tool 调用

调用：

```text
Web Search Tool
```

Skill 负责决定：

```text
搜什么
如何组合关键词
哪些案例值得保留
哪些信息属于可靠事实
如何分析案例
哪些策略具有参考价值
```

Tool 只负责：

```text
执行搜索
返回搜索结果
```

因此：

```text
Case Research Skill
    ↓
Web Search Tool
```

体现的是：

> Skill 定义研究方法，Tool 提供外部信息获取能力。

### 5.6 输出

Case Research Skill 返回：

```text
search_queries
filtered_cases
case_analysis
```

`filtered_cases` 建议结构：

```json
[
  {
    "name": "",
    "location": "",
    "project_type": "",
    "source": "",
    "relevance": ""
  }
]
```

`case_analysis` 建议结构：

```json
[
  {
    "case": "",
    "relevance_reason": "",
    "spatial_strategy": [],
    "applicable_reference": [],
    "limitations": []
  }
]
```

其中：

```text
filtered_cases
```

属于案例筛选结果；

```text
case_analysis
```

属于可供后续专业任务直接使用的案例研究结果。

### 5.7 案例筛选标准

| 维度 | 判断内容 |
|---|---|
| 类型相关性 | 是否属于相似项目类型 |
| 问题相关性 | 是否解决类似空间问题 |
| 资源相关性 | 是否具有类似蓝绿或公共空间资源 |
| 策略可参考性 | 是否存在可迁移的设计方法 |
| 信息可信度 | 是否具有明确、可追溯的来源 |

不要求所有案例同时满足所有维度。

优先选择：

> 与当前项目的核心问题具有明确关联，并能够提供具体空间策略参考的案例。

### 5.8 来源要求

案例事实信息必须保留来源。

包括：

```text
案例名称
项目位置
设计团队
公开项目信息
设计策略依据
```

不得将模型自身推测包装为案例事实。

案例研究中应明确区分：

```text
Source Fact
→ 来源中明确存在的信息

Agent Analysis
→ Agent 根据案例与当前项目进行的分析
```

### 5.9 质量要求

Case Research Skill 输出应满足：

- 案例与 `research_direction` 存在明确关联；
- 每个保留案例具有来源；
- 不仅返回案例名称，还需要提炼可参考策略；
- 不直接将案例策略复制为当前项目方案；
- 明确案例适用价值及局限；
- `case_analysis` 能够直接支持后续 `check_research` 和 `concept_generation`。

### 5.10 接口签名

```python
def research_cases(
    site_analysis: dict,
    research_direction: list[str],
    search_queries: list[str] | None = None,
) -> dict:
    """
    Returns:
    {
        "search_queries": [...],
        "filtered_cases": [...],
        "case_analysis": [...]
    }
    """
```

`search_attempts` 不由该 Skill 返回，由调用它的 `case_research` Node 负责更新。

## 6. Concept Generation Skill

### 6.1 Skill 目标

综合场地分析和案例研究结果，识别设计机会，形成项目愿景，并生成 2–3 个具有明显差异的概念方向。

该 Skill 是整个 Agent 从“研究”进入“方向生成”的核心专业能力。

基本逻辑：

```text
场地条件
    +
案例参考
    ↓
设计机会
    ↓
目标愿景
    ↓
概念方向
    ↓
空间意向表达
```

### 6.2 输入

| 输入 | 来源 | 必需 |
|---|---|---:|
| `project_background` | State | 是 |
| `client_requirements` | State | 否 |
| `site_analysis` | State | 是 |
| `case_analysis` | State | 否 |
| `site_images` | State | 否（仅当 `USE_IMG2IMG=true` 时使用） |

关于 `site_image_description`： 场地特征已经通过 Site Analysis Skill 提取到 `site_analysis` 中，Concept Generation 消费 `site_analysis` 即可，不重复读取图片解析结果。

关于 `site_images`： 仅用于 img2img 参考，Skill 不重新解析图片，只将图片路径传递给 Image Generation Tool。默认 `USE_IMG2IMG=false`，不启用。

**`site_images` 的双重消费路径：**

```text
site_images
    ├──→ parse_and_check（初步解析为 site_image_description）
    │           ↓
    │       Site Analysis Skill（进一步分析图片或空间文字描述）
    │           ↓
    │       site_analysis（含场地特征）
    │           ↓
    └──→ Concept Generation Skill（作为 img2img 参考图，可选）
                ↓
            Image Generation Tool

```

案例研究信息流为：

```text
Web Search
    ↓
filtered_cases
    ↓
case_analysis
    ↓
Concept Generation
```

案例研究不是 Concept Generation 的强制前置条件。

如果：

```text
need_case_research = false
```

则 Concept Generation Skill 可以仅基于：

```text
project_background
+
site_analysis
+
client_requirements
```

继续执行。

### 6.3 设计机会识别

本节中的：

```text
opportunities
```

指 **Design Opportunities，设计机会**。

它与 SWOT 中：

```text
site_analysis.swot.opportunities
```

所表示的外部机会条件不同。

设计机会不是简单重复 SWOT，而是将已有分析转化为可以指导概念设计的行动方向。

例如：

```text
场地条件：
具有连续滨水资源，
但城市空间与滨水界面联系较弱

        ↓

设计机会：
通过公共空间和慢行系统，
强化城市核心功能与滨水空间之间的连接
```

设计机会识别主要考虑：

```text
场地优势如何被放大
场地问题如何被改善
资源如何转化为空间价值
案例经验是否提供可借鉴方法
项目定位需要什么空间支撑
```

输出：

```text
opportunities
```

建议 Schema 中使用：

```text
DesignOpportunity
```

或：

```text
design_opportunities
```

等明确命名，避免与 SWOT Opportunity 混淆。

### 6.4 目标愿景提炼

基于项目定位、场地条件和设计机会，形成总体目标愿景。

统一包含四个字符串字段：

```text
theme
positioning
core_goal
spatial_idea
```

目标愿景负责回答：

> 项目希望形成什么样的空间，以及为什么形成这样的空间。

输出：

```text
vision
```

### 6.5 概念方向生成

基于：

```text
opportunities
+
vision
```

生成 2–3 个概念方向。

不同方向应体现真正的设计策略差异，而不是只修改名称和表达方式。

每个方向至少包含：

```text
name
core_concept
design_opportunities
spatial_strategy
key_actions
case_references
```

例如不同方向可能分别强调：

```text
方向 A：蓝绿空间组织

方向 B：公共活动与商业活力

方向 C：城市轴线与空间联系
```

具体方向由 Agent 根据项目条件生成，不预设固定模板。

### 6.6 概念依据

每个概念方向必须能够回溯到前序分析。

基本关系：

```text
Site Condition
      ↓
Design Opportunity
      ↓
Concept
      ↓
Spatial Strategy
```

如果存在案例研究：

```text
Case Reference
      ↓
Applicable Strategy
      ↓
Concept Support
```

因此概念方向不能只由语言创意产生，而需要建立明确的推导链条：

```text
事实 / 条件
→ 分析
→ 设计机会
→ 概念方向
→ 空间策略
```

### 6.7 概念质量检查

概念生成后进行内部质量检查。

| 检查项 | 判断标准 |
|---|---|
| 条件关联 | 是否回应主要场地条件 |
| 机会关联 | 是否对应已识别的设计机会 |
| 方向差异 | 2–3 个方向之间是否存在明显策略差异 |
| 空间性 | 是否包含可理解的空间策略，而非只有口号 |
| 依据完整 | 是否能够说明方向产生的依据 |
| 项目一致性 | 是否符合项目定位和用户要求 |

如果明显不满足要求：

```text
第一次生成
    ↓
质量检查失败
    ↓
根据问题重新生成
    ↓
第二次生成后直接返回当前结果，不再继续循环
```

V1 最多自动重新生成 1 次。`quality_check` 仅存在于 Skill 内部，不写入 State；第二次结果无需再次通过质量检查才允许返回。

该过程属于 Concept Generation Skill 内部逻辑，不作为独立 Graph Node，也不形成额外 Graph 循环。

### 6.8 意向图生成

概念方向生成完成后，Concept Generation Skill 默认尝试调用：

```text id="9yznyw"
Image Generation Tool
```

生成与各概念方向对应的空间意向图。

V1 不增加“是否生成意向图”的任务级 State 字段；生成失败时允许 `images` 为空或部分成功，并继续报告生成。

意向图的目标不是输出精确设计效果图，而是将概念方向、空间策略和场地特征转化为可视化表达，帮助设计人员理解和比较不同概念方向。

#### 6.8.1 图像生成模式

V1 支持两种图像生成模式：

| 模式 | 说明 | 默认 |
|---|---|---|
| `text2img` | 基于文本 Prompt 生成意向图 | 默认 |
| `img2img` | 以场地图片作为视觉参考生成意向图 | 可选，需配置 |

图像生成模式主要由以下配置控制：

| 配置项 | 默认值 | 说明 |
|---|---:|---|
| `USE_IMG2IMG` | `false` | 是否允许使用 img2img 模式 |
| `REFERENCE_STRENGTH` | 未设置 | 非 V1 强制参数，Stage 5 确认 Qwen Image 实际参数后决定 |

上述配置由：

```text id="lttndj"
src/config.py
```

统一管理，不进入 Agent State。

基本判断逻辑为：

```text id="zxy7lg"
USE_IMG2IMG = true
+
site_images 存在
+
当前 Image Generation Provider 支持参考图生成
        ↓
img2img
```

否则：

```text id="m649e8"
text2img
```

当 img2img 条件不满足、参考图不可用或当前 Provider 不支持参考图生成时，系统自动回退至 `text2img`，不阻断 Concept Generation Skill 的正常执行。

#### 6.8.2 Prompt 构建

Concept Generation Skill 根据每个概念方向组织图像生成 Prompt。

基本输入包括：

```text id="lodbf5"
项目类型
+
场地特征
+
概念方向
+
空间策略
+
空间氛围
```

其中：

```text id="jonnd1"
项目类型
```

来自 `project_background`；

```text id="7p3pdb"
场地特征
```

主要来自 `site_analysis`；

```text id="39kbd5"
概念方向 + 空间策略
```

来自当前 `concept`；

```text id="9gbaj9"
空间氛围
```

由 Skill 根据概念方向、设计目标和空间策略组织。

因此基本生成逻辑为：

```text id="kek9fv"
project_background
+
site_analysis
+
concept
        ↓
Image Prompt
        ↓
Image Generation Tool
```

当使用 img2img 模式时，在上述文本信息之外额外传入：

```text id="uxofyn"
site_images
```

作为原始视觉参考。

此时：

```text id="plaucr"
site_analysis
```

负责提供 Agent 已经理解和抽象出的场地特征；

```text id="qggxxe"
site_images
```

负责提供未经文本抽象的原始视觉信息。

两者共同用于约束意向图生成，使结果既回应概念方向，也尽可能保持与真实场地语境的一致性。

#### 6.8.3 img2img 模式

当满足以下条件时：

```text id="abzk7u"
USE_IMG2IMG = true
+
site_images 存在
+
当前 Image Generation Provider 支持参考图生成
```

Concept Generation Skill 采用 img2img 模式调用 Image Generation Tool。

在 V1 中，参考图直接来自 State 中的：

```text id="x7vq9n"
site_images
```

并作为 Tool 层的：

```text id="94scmp"
reference_images
```

传入。

同时，Concept Generation Skill 向 Image Generation Tool 传入统一的：

```text id="at36lk"
reference_strength
```

参数仅在 Stage 5 确认 Qwen Image 存在明确对应参数时传入，不设 V1 强制默认值；可选配置为：

```text id="nx918a"
REFERENCE_STRENGTH
```

不同图像 Provider 的具体参数名称和映射方式由 Image Generation Tool 负责处理，Skill 不直接依赖具体 Provider 的原生 API。

img2img 模式的核心目标是在概念意向表达阶段增强生成结果与真实场地环境之间的一致性，包括：

- 主要景观资源；
- 滨水、山体、绿地等自然环境特征；
- 道路和城市界面；
- 建筑及公共空间环境；
- 整体空间关系和场地氛围。

img2img 并不要求模型严格复原原始场地，而是通过参考图降低生成结果与真实项目语境之间的偏差。

**主要参数：**

| 参数 | 来源 | 说明 |
|---|---|---|
| `reference_images` | `site_images` | 场地参考图片路径列表 |
| `use_img2img` | `USE_IMG2IMG` | 是否启用参考图生成模式 |
| `reference_strength` | Stage 5 待确认 | 非 V1 强制参数，不预设默认强度 |

`reference_strength` 使用统一业务语义，不直接绑定某一个图像模型的原生参数。

数值越高，生成结果通常越受参考图视觉特征约束；数值越低，模型具有更大的生成自由度。具体效果取决于所使用的图像模型。

**不启用 img2img 的典型场景：**

- 当前处于概念探索阶段，需要保留较大的创意自由度；
- 场地现状杂乱，可能对概念表达形成明显干扰；
- 当前任务重点在方向发散，而不是场地贴合；
- 没有可用的 `site_images`；
- 当前 Image Generation Provider 不支持参考图生成。

**启用 img2img 的典型场景：**

- 甲方或设计团队希望生成结果“看起来像这个场地”；
- 概念方向已经相对收敛，需要更贴合场地环境的视觉表达；
- 希望保留滨水、山体、道路界面、植被等关键场地特征；
- 希望不同概念方向建立在同一场地视觉基础上进行比较；
- 当前 Image Generation Provider 支持参考图生成。

**边界说明：**

img2img 模式用于增强意向图与真实场地环境之间的关联性，不等同于生成严格精确的场地改造效果图。

输出结果仍属于概念意向表达，不要求：

- 完整保持原始场地几何关系；
- 精确控制建筑、道路或景观的落位；
- 保证空间尺度和工程参数准确；
- 作为设计实施或技术深化依据。

因此 V1 中 img2img 的目标是：

```text id="r1gb4h"
增强场地语境一致性
```

而不是：

```text id="yr17tf"
生成精确设计效果图
```

#### 6.8.4 输出

每个概念方向默认生成：

```text id="v4blnt"
1–2 张意向图
```

生成结果需要与对应概念方向建立明确关联。

建议输出结构：

```json id="khu0iy"
{
  "concept_name": "滨水公共客厅",
  "image_url": "...",
  "prompt": "...",
  "mode": "img2img",
  "reference_images": ["..."]
}
```

当使用 `text2img` 时：

```json id="2orb4i"
{
  "concept_name": "滨水公共客厅",
  "image_url": "...",
  "prompt": "...",
  "mode": "text2img",
  "reference_images": []
}
```

字段说明：

| 字段 | 说明 |
|---|---|
| `concept_name` | 对应的概念方向名称 |
| `image_url` | 生成图片的文件路径、URL 或对象存储地址 |
| `prompt` | 实际用于图像生成的 Prompt |
| `mode` | 本次生成使用的模式：`text2img` 或 `img2img` |
| `reference_images` | 本次生成实际使用的场地参考图片；text2img 时为空列表 |

其中，`mode` 和 `reference_images` 同时写入 State 中的 `images` 结果结构，用于记录实际执行方式。

保留 `prompt`、`mode` 和 `reference_images`，便于后续：

- 调试图像生成结果；
- 分析不同生成模式的效果；
- 进行 Agent Evaluation；
- 追踪图片与场地输入之间的关系。

最终意向图主要用于：

- 表达空间氛围；
- 辅助理解概念方向；
- 比较不同概念策略；
- 为设计人员提供视觉参考。

不作为精确设计方案或最终设计成果。

### 6.9 输出

Concept Generation Skill 返回：

```text
opportunities
vision
concepts
images
```

### 6.10 质量要求

Concept Generation Skill 输出应满足：

- 设计机会具有明确场地依据；
- 愿景与项目定位一致；
- 生成 2–3 个具有明显差异的概念方向；
- 概念不是抽象口号，应包含空间策略；
- 概念能够回溯到场地条件、设计机会或案例依据；
- 不生成超出已有资料能够支持的精确空间结论；
- 意向图与对应概念方向保持一致；
- 案例仅作为参考依据，不直接替代项目自身分析。

### 6.11 接口签名

```python
def generate_concepts(
    project_background: str,
    site_analysis: dict,
    client_requirements: str | None = None,
    case_analysis: list[dict] | None = None,
    site_images: list[str] | None = None,   # 仅 USE_IMG2IMG=true 时使用
) -> dict:
    """
    Returns:
    {
        "opportunities": [...],
        "vision": {...},
        "concepts": [...],
        "images": [...]
    }
    """
```

## 7. Report Composition Skill

### 7.1 Skill 目标

将 Agent 前序阶段产生的结构化成果组织为完整、可阅读、可追溯的项目前期研究报告。

Report Composition Skill 不重新进行核心专业分析，而主要负责：

```text
组织
+
压缩
+
表达
+
来源整理
```

其核心原则是：

> 报告负责表达已有结果，不重新创造新的专业判断。

### 7.2 输入

主要读取：

```text
project_background
location
planning_conditions
client_requirements

site_analysis

case_analysis

opportunities
vision
concepts
images
```

案例研究被跳过时，可以：

```text
省略案例研究章节
```

或：

```text
标注本次任务未执行案例研究
```

不要求为了保持固定章节数量而生成无依据内容。

### 7.3 报告结构

V1 默认报告结构：

```text
1. 项目理解
2. 场地条件分析
3. 案例研究
4. 设计机会识别
5. 目标愿景
6. 概念方向建议
7. 空间意向图
```

实际输出根据 State 中已有内容动态组织。

不存在的数据可以：

```text
省略
```

或：

```text
标注信息不足
```

不强制生成空章节。

### 7.4 内部流程

```text
读取 State 中前序成果
        ↓
检查章节数据完整性
        ↓
组织报告结构
        ↓
整理案例来源与分析依据
        ↓
组织概念方向与意向图
        ↓
生成 Markdown
        ↓
检查章节完整性和一致性
        ↓
返回 final_report
```

### 7.5 可追溯要求

报告需要区分不同信息来源：

```text
用户提供信息
场地图像分析
外部案例事实
Agent 分析判断
Agent 生成的概念建议
```

案例相关事实应保留来源链接。

设计机会和概念方向应能够回溯到：

```text
项目条件
场地分析
SWOT
案例参考
用户要求
```

Report Composition Skill 不重新判断这些依据是否正确，而是保证它们在报告中被正确表达。

### 7.6 输出

输出：

```text
final_report: str
```

格式：

```text
Markdown
```

V1 不要求 Report Composition Skill 直接生成：

```text
PDF
PPT
DOCX
```

如后续需要其他格式，由应用层或独立导出能力处理。

### 7.7 质量要求

最终报告应满足：

- 章节结构完整；
- 内容与 State 中的结构化结果一致；
- 不重新编造前序阶段不存在的信息；
- 案例事实保留来源；
- 设计机会和概念方向具有明确依据；
- 图片与对应概念方向正确匹配；
- 事实、分析和设计建议之间语义清晰；
- Markdown 格式可直接由前端展示。

### 7.8 接口签名

```python
def compose_report(
    project_context: dict,
    site_analysis: dict,
    case_analysis: list[dict] | None,
    opportunities: list[dict],
    vision: dict,
    concepts: list[dict],
    images: list[dict],
) -> str:
    """
    Returns:
        Markdown string
    """
```

其中：

```text
project_context
```

可由 Node 根据以下 State 字段组装：

```text
project_background
location
planning_conditions
client_requirements
```

避免 Report Composition Skill 接口参数过度膨胀。

## 8. Skill 输入输出汇总

| Skill | 输入 | 输出 |
|---|---|---|
| Site Analysis | 项目结构化信息、规划条件、可选场地图片或空间文字描述 | `site_analysis` |
| Case Research | `site_analysis`、`research_direction`、`search_queries` | `search_queries`、`filtered_cases`、`case_analysis` |
| Concept Generation | 项目理解、`site_analysis`、`case_analysis` | `opportunities`、`vision`、`concepts`、`images` |
| Report Composition | 前序最终成果 | `final_report` |

Skill 的输入主要来自 State。

其执行过程遵循：

```text
State
  ↓
Node
  ↓
Skill
  ↓
Schema 校验
  ↓
Node
  ↓
State Update
```

### 8.1 配置项

Skill 内部依赖以下配置项，由 `src/config.py` 统一管理：

| 配置项 | 默认值 | 用途 |
|---|---|---|
| `USE_IMG2IMG` | `false` | 是否允许使用 img2img 模式生成意向图 |
| `REFERENCE_STRENGTH` | 未设置 | 非 V1 强制参数，Stage 5 确认 Qwen Image 实际参数后决定 |

配置项通过 `.env` 文件设置，代码中通过 `os.getenv` 读取。

**与 Skill 的关系：**

| Skill | 依赖的配置项 |
|---|---|
| Site Analysis | 无 |
| Case Research | 无 |
| Concept Generation | `USE_IMG2IMG`；参考强度映射由 Stage 5 实际 API 验证后决定 |
| Report Composition | 无 |

配置项不进入 State，不属于 Graph 路由判断依据，仅在 Skill 内部使用。

## 9. Skill 与 Prompt 的关系

Skill 与 Prompt 不建立一一对应关系。

一个 Skill 可以使用一个或多个 Prompt。

例如：

```text
Site Analysis Skill
├── analyze_site.md
└── analyze_swot.md

Case Research Skill
├── generate_search_queries.md
├── filter_cases.md
└── analyze_cases.md

Concept Generation Skill
├── identify_opportunities.md
├── generate_vision.md
├── generate_concepts.md
└── check_concepts.md

Report Composition Skill
└── compose_report.md
```

但以上结构只是实现参考。

V1 可以根据模型能力和测试结果合并 Prompt。

例如：

```text
analyze_site
+
analyze_swot
```

可以合并为一次 Structured Output 调用。

因此：

```text
Skill ≠ Prompt
```

更准确的关系为：

```text
Skill
├── LLM
├── Prompt
├── Schema
└── Tool（必要时）
```

其中：

- Skill 定义专业任务；
- Prompt 定义一次模型调用的具体指令；
- Schema 约束模型输出；
- Tool 提供外部能力。

## 10. Skill 与 Schema 的关系

Skill 输出的复杂结构由 `schemas/` 中的 Pydantic Model 负责校验。

对应关系建议如下：

| Skill | Schema |
|---|---|
| Site Analysis | `SiteAnalysis`、`SWOT` |
| Case Research | `Case`、`CaseAnalysis` |
| Concept Generation | `DesignOpportunity`、`Vision`、`Concept` |
| Report Composition | 不单独定义，最终输出为 Markdown String |

代码结构：

```text
src/
├── skills/
│   ├── site_analysis.py
│   ├── case_research.py
│   ├── concept_generation.py
│   └── report_composition.py
│
└── schemas/
    ├── site_info.py
    ├── case.py
    └── concept.py
```

Schema 的职责是：

```text
约束输出结构
+
校验字段类型
+
降低 LLM 输出不稳定性
```

Skill 的职责是：

```text
完成专业任务
```

两者不混合。

## 11. Skill 错误处理

Skill 内部只处理属于自身职责范围的业务降级。

API 级瞬时错误优先由 Tool 层处理有限重试。

### 11.1 Site Analysis

模型无法可靠识别某项场地信息时：

```text
证据不足
    ↓
不生成确定性结论
    ↓
标记 unknown / insufficient evidence
    ↓
继续分析已有信息
```

Skill 不为了完成字段而编造场地条件。

### 11.2 Case Research

Web Search Tool 出现瞬时错误时：

```text
Tool Layer
    ↓
有限重试
```

Tool 最终失败时：

```text
Case Research Skill
    ↓
返回当前已有结果
+
记录 limitation
```

是否重新进行案例研究，不由 Skill 决定，而由：

```text
check_research
+
Conditional Route
```

负责。

### 11.3 Concept Generation

概念质量检查失败时：

```text
第一次生成
    ↓
质量检查失败
    ↓
根据问题重新生成
    ↓
第二次生成后直接返回当前结果，不再继续循环
```

V1 最多重新生成一次。

如果 Image Generation Tool 失败：

```text
保留 concepts
+
images 为空或部分成功
+
继续报告生成
```

图片不是概念方向生成成功的必要条件。

### 11.4 Report Composition

部分非关键内容缺失时：

```text
省略对应章节
```

或：

```text
标注信息不足
```

不得为了保证报告形式完整而编造缺失内容。

## 12. Skill 边界

V1 不将以下能力单独拆分为 Skill：

```text
Project Understanding Skill
SWOT Skill
Opportunity Identification Skill
Vision Generation Skill
Image Generation Skill
```

对应关系为：

```text
原始项目理解
→ parse_and_check Node

项目定位分析
→ Site Analysis Skill

SWOT
→ Site Analysis Skill

设计机会识别
→ Concept Generation Skill

目标愿景
→ Concept Generation Skill

意向图生成
→ Concept Generation Skill
   ↓
Image Generation Tool
```

### 12.1 为什么不拆 Project Understanding Skill

项目描述中的基础信息提取属于：

```text
Input Processing
```

由 `parse_and_check` 完成。

Site Analysis Skill 不重复解析原始输入，而负责进一步形成专业判断。

### 12.2 为什么不拆 SWOT Skill

SWOT 是场地分析结论的一部分。

其输入和输出均依赖完整场地分析上下文，因此保持在 Site Analysis Skill 内部更符合任务内聚性。

### 12.3 为什么不拆 Opportunity Identification Skill

设计机会是从：

```text
site_analysis
+
case_analysis
```

过渡到概念生成的中间推理结果。

它与 Vision、Concept 属于连续专业推理链：

```text
Analysis
    ↓
Opportunity
    ↓
Vision
    ↓
Concept
```

单独拆分会增加接口复杂度，但不会增加明显复用价值。

### 12.4 为什么 Image Generation 是 Tool

Image Generation 的本质是：

```text
输入 Prompt
→ 调用外部图像模型
→ 返回图片
```

它不承担完整专业判断，因此属于 Tool，而不是 Skill。

生成什么样的图片以及 Prompt 如何构造，由 Concept Generation Skill 决定。

### 12.5 Skill 拆分原则

Skill 是否应该独立，不取决于：

```text
是否调用了一次 LLM
```

也不取决于：

```text
是否能够单独写一个 Prompt
```

而取决于：

> 是否构成一个具有独立目标、明确输入输出、完整专业逻辑，并具有实际复用价值的能力单元。

## 13. Skills Design Summary

V1 将项目前期研究能力收敛为四个核心 Skill：

```text
Site Analysis
      ↓
理解项目定位与场地条件

Case Research
      ↓
寻找外部案例参考依据

Concept Generation
      ↓
将研究结果转化为设计方向

Report Composition
      ↓
将过程成果组织为研究报告
```

完整职责关系为：

```text
Agent / Graph
│
├── Decision Node
│      ├── 信息是否充分
│      ├── 是否需要案例研究
│      └── 案例研究是否充分
│
├── Execution Node
│      ↓
│    Skill
│      ├── Site Analysis
│      ├── Case Research
│      ├── Concept Generation
│      └── Report Composition
│
└── Tool
       ├── Web Search
       └── Image Generation
```

三层职责可以概括为：

```text
Node
→ 决定什么时候执行并负责 State 更新

Skill
→ 定义专业任务如何完成

Tool
→ 提供执行专业任务所需的外部能力
```

与其他设计文档之间的关系为：

```text
agent-architecture.md
→ Agent 如何运行

state-design.md
→ Agent 运行过程中保存什么

skills.md
→ 每个专业任务如何完成
```

最终原则：

> **Agent 决定“下一步做什么”，Node 负责“何时调用并如何更新状态”，Skill 定义“专业任务怎么完成”，Tool 提供“完成任务需要的外部能力”。**

V1 不追求 Skill 数量，而优先保证核心能力边界清晰、输入输出稳定、职责不重叠，并能够支撑完整的项目前期研究闭环。


### Case Research 内部来源绑定

去重后的当前检索 evidence 按顺序分配 `src_001`、`src_002` 等 source_id。
案例筛选/分析的内部结构只由 LLM 输出 source_id 与专业字段；程序从该 ID 对应的同一条 evidence 回填 Case.name、Case.source 与 CaseAnalysis.case。
未知或空 ID 明确失败，不猜测、不模糊匹配。重复选择继续由已有重复案例 guard 拒绝。
公开 Skill 返回、Case / CaseAnalysis Schema、State 与 exact provenance guard 保持不变；source_id 不进入业务 State。
