# State Design

## 1. State 设计目标

项目前期研究 Agent 使用统一的 State 保存任务执行过程中的上下文、分析结果、中间产物和流程控制信息。

State 是 Agent 各 Node 之间共享的信息载体，也是 Agent 进行下一步决策的主要依据。

State 设计需要满足以下目标：

1. 保存用户输入和项目基础信息；
2. 保存各阶段产生的结构化分析结果；
3. 支持 Node 之间传递中间结果；
4. 支持 Conditional Routing 判断下一步任务；
5. 支持有限循环记录执行次数；
6. 保存最终报告及概念成果；
7. 避免将临时变量和业务逻辑混入 State。

**核心原则：**

> State 保存“任务当前知道什么、已经完成什么、还需要做什么”，不负责定义“应该怎么做”。

## 2. State 整体结构

V1 State 按照任务生命周期划分为六类信息：

```text
AgentState
│
├── 1. User Input
│      ├── user_input
│      └── site_images
│
├── 2. Project Understanding
│      ├── project_background
│      ├── location
│      ├── planning_conditions
│      ├── client_requirements
│      └── site_image_description
│
├── 3. Information Check
│      ├── info_sufficient
│      ├── missing_critical
│      ├── missing_optional
│      └── followup_question
│
├── 4. Site & Case Research
│      ├── site_analysis
│      ├── need_case_research
│      ├── research_direction
│      ├── search_queries
│      ├── filtered_cases
│      ├── case_analysis
│      ├── research_sufficient
│      ├── research_gaps
│      └── search_attempts
│
├── 5. Concept Generation
│      ├── opportunities
│      ├── vision
│      ├── concepts
│      └── images
│
└── 6. Final Output
       └── final_report
```

## 3. State Schema

V1 使用 `TypedDict` 定义 Agent State 的顶层结构。

```python
from typing import TypedDict


class AgentState(TypedDict, total=False):

    # ===== User Input =====
    user_input: str
    site_images: list[str]

    # ===== Project Understanding =====
    project_background: str
    location: str
    planning_conditions: dict
    client_requirements: str | None
    site_image_description: str

    # ===== Information Check =====
    info_sufficient: bool
    missing_critical: list[str]
    missing_optional: list[str]
    followup_question: str

    # ===== Site Analysis =====
    site_analysis: dict

    # ===== Case Research =====
    need_case_research: bool
    research_direction: list[str]
    search_queries: list[str]
    filtered_cases: list[dict]
    case_analysis: list[dict]
    research_sufficient: bool
    research_gaps: list[str]
    search_attempts: int

    # ===== Concept Generation =====
    opportunities: list[dict]
    vision: dict
    concepts: list[dict]
    images: list[dict]

    # ===== Final Output =====
    final_report: str
```

该代码用于定义 State 的整体结构，不代表所有复杂字段最终都以 `dict` 实现。

具体业务对象的数据结构和运行时校验由 `schemas/` 中的 Pydantic Model 定义。

## 4. 字段设计

### 4.1 User Input

#### `user_input`

**类型：** `str`

**用途：**保存当前任务中用户提供的项目描述、任务要求及后续补充信息。

`user_input` 表示当前任务的输入内容汇总，不承担完整对话历史记录功能。

**来源：**用户。

**读取方：**

- `parse_and_check`

#### `site_images`

**类型：** `list[str]`

**用途：**保存用户上传的场地相关图片。

支持：

- 地图；
- 卫星图；
- 现状照片；
- 规划分析图。

初始阶段不要求用户提供设计完成后的总平面图。

**来源：**用户。

**读取方：**

- `parse_and_check`
- `site_analysis`

---

### 4.2 Project Understanding

#### `project_background`

**类型：** `str`

**用途：**保存 Agent 对项目基本背景和定位的结构化理解。

例如：

```text
项目位于城市核心区，目标打造面向商业及公共活动的滨水中心空间。
```

**产生节点：** `parse_and_check`

**主要读取方：**

- `site_analysis`
- `concept_generation`
- `report_composition`

#### `location`

**类型：** `str`

**用途：**保存项目区位及与城市结构相关的信息。

包括：

- 城市 / 区域；
- 周边主要功能；
- 城市区位；
- 与主要交通节点的关系。

**产生节点：** `parse_and_check`

**主要读取方：**

- `site_analysis`

#### `planning_conditions`

**类型：** `dict`

**用途：**保存已知规划条件和场地约束。

V1 建议保持以下稳定字段：

```text
land_use
site_area
floor_area_ratio
building_density
road_conditions
public_space_requirements
other_constraints
```

该字段不要求在 V1 中进行完整 GIS 解析，仅保存用户输入或模型识别出的已有条件。

**产生节点：** `parse_and_check`

**主要读取方：**

- `site_analysis`

#### `client_requirements`

**类型：** `str | None`

**用途：**保存用户或项目方提出的设计目标、重点关注事项及特殊要求。

有要求时保存文字，无要求时为 `None`。用户指定研究方向或案例作为任务初始输入或重新发起任务时的输入，统一并入 `user_input`；提取出的要求可保存在本字段，不新增 State 字段。

**产生节点：** `parse_and_check`

**主要读取方：**

- `site_analysis`
- `check_case_need`（读取用户指定研究方向或案例）
- `concept_generation`

#### `site_image_description`

**类型：** `str`

**用途：**保存多模态模型对用户上传场地图片的综合理解。

例如：

```text
场地北侧临主要城市道路，南侧存在连续滨水空间，
西侧为成熟居住区，东侧与商业功能区相邻。
```

该字段作为后续场地分析的输入之一。

**产生节点：** `parse_and_check`

**主要读取方：**

- `site_analysis`

---

### 4.3 Information Check

#### `info_sufficient`

**类型：** `bool`

**用途：**判断当前项目资料是否达到继续执行场地分析的最低要求。

主要由 `parse_and_check` 写入。

用于路由：

```text
info_sufficient = false
        ↓
ask_user

info_sufficient = true
        ↓
site_analysis
```

#### `missing_critical`

**类型：** `list[str]`

**用途：**记录缺失且会影响后续分析的关键信息。

V1 主要关注：

- 项目基本定位；
- 场地基本空间信息。

例如：

```text
[
    "项目定位",
    "场地位置"
]
```

#### `missing_optional`

**类型：** `list[str]`

**用途：**记录缺失但不影响 Agent 继续执行的非关键信息。

例如：

```text
[
    "具体容积率",
    "明确设计目标"
]
```

该字段主要用于提醒和结果解释，不直接阻断主流程。

#### `followup_question`

**类型：** `str`

**用途：**保存 Agent 根据关键缺失信息生成的用户补充问题。

例如：

```text
请补充项目的主要功能定位，以及场地所在城市或区域。
```

---

### 4.4 Site Analysis

#### `site_analysis`

**类型：** `dict`

**用途：**保存场地分析阶段的完整结构化结果。

统一包含：

```text
project_positioning
location_conditions
functional_conditions
landscape_resources
public_space
transportation
spatial_conditions
swot
  strengths
  weaknesses
  opportunities
  threats
analysis_summary
```

`project_positioning`、`analysis_summary` 为字符串；其余场地条件字段为对象，`swot` 的四个子字段为 `list[str]`。SWOT 只使用嵌套 `swot`，不保留平铺字段；具体结构与 `skills.md` §4.5 一致。

该字段由 `site_analysis` Node 写入。

**主要读取方：**

- `check_case_need`
- `concept_generation`
- `report_composition`

---

### 4.5 Case Research

#### `need_case_research`

**类型：** `bool`

**用途：**记录 Agent 是否认为当前项目需要外部案例研究。

由 `check_case_need` 写入。

用于路由：

```text
need_case_research = false
        ↓
concept_generation

need_case_research = true
        ↓
case_research
```

#### `research_direction`

**类型：** `list[str]`

**用途：**记录案例研究方向。

例如：

```text
[
    "滨水公共空间",
    "TOD商业中心",
    "城市公共开放空间"
]
```

该字段同时作为 `case_research` 的研究依据。

**产生节点：** `check_case_need`

**主要读取方：**

- `case_research`

#### `search_queries`

**类型：** `list[str]`

**用途：**记录 Agent 当前轮执行的搜索关键词。

例如：

```text
[
    "waterfront mixed-use public space urban design",
    "TOD commercial center public realm"
]
```

主要用于：

- 跟踪 Agent 行为；
- 调试搜索结果；
- 评估搜索策略；
- 复盘失败案例。

`refine_search` 写入时替换当前轮搜索词，不累积历史。

历史搜索词如需追溯，通过日志记录，不进入 State。

**产生节点：**

- `case_research`
- `refine_search`

**主要读取方：**

- Web Search Tool
- `refine_search`

#### `filtered_cases`

**类型：** `list[dict]`

**用途：**保存经过初步筛选、认为具有参考价值的案例。

每个案例建议至少包含：

```text
name
location
project_type
source
relevance
```

**产生节点：** `case_research`

**主要读取方：**

- `check_research`
- `concept_generation`

#### `case_analysis`

**类型：** `list[dict]`

**用途：**保存案例与当前项目之间的关联分析。

每个案例建议包含：

```text
case
relevance_reason
spatial_strategy
applicable_reference
limitations
```

与 `filtered_cases` 的区别：

- `filtered_cases`：哪些案例值得继续研究；
- `case_analysis`：这些案例对当前项目有什么参考价值。

**产生节点：** `case_research`

**主要读取方：**

- `check_research`
- `concept_generation`
- `report_composition`

#### `research_sufficient`

**类型：** `bool`

**用途：**判断当前案例研究是否已经达到概念生成所需的信息要求。

由 `check_research` 写入。

用于：

```text
research_sufficient = true
        ↓
concept_generation

research_sufficient = false
        ↓
refine_search
```

#### `research_gaps`

**类型：** `list[str]`

**用途：**记录当前案例研究仍存在的信息缺口。

例如：

```text
[
    "缺少与滨水商业中心相似的案例",
    "公共空间组织方式仍缺乏参考"
]
```

`refine_search` 根据该字段调整下一轮搜索方向。

#### `search_attempts`

**类型：** `int`

**用途：**记录案例研究执行轮次。

初始值为 `0`，每完成一轮案例研究后递增。

由 `case_research` Node 更新，Graph 条件路由读取并控制轮次；Case Research Skill 不返回或修改 `search_attempts`，Tool 技术重试不计为案例研究轮次。

V1 最大值为 `2`。

该字段用于限制案例研究循环，避免 Agent 无限执行。

---

### 4.6 Concept Generation

#### `opportunities`

**类型：** `list[dict]`

**用途：**保存从场地条件和案例研究中识别出的设计机会。

本字段中的 `opportunities` 指 **Design Opportunities（设计机会）**，用于描述场地条件可以进一步转化为什么设计行动方向，与 `site_analysis.swot.opportunities` 中的 SWOT 外部机会含义不同。

例如：

```json
[
  {
    "opportunity": "强化滨水公共空间与城市商业空间的联系",
    "basis": "滨水资源 + 商业中心定位",
    "priority": "high"
  }
]
```

**产生节点：** `concept_generation`

**主要读取方：**

- `report_composition`

---

#### `vision`

**类型：** `dict`

**用途：**保存项目目标愿景及其核心表达。

统一包含四个字符串字段：

```text
theme
positioning
core_goal
spatial_idea
```

例如：

```json
{
  "theme": "城市滨水活力中心",
  "positioning": "融合商业、公共活动与滨水空间的城市核心节点",
  "core_goal": "建立连续开放的滨水公共空间体系",
  "spatial_idea": "通过公共空间串联商业、城市道路和滨水界面"
}
```

**产生节点：** `concept_generation`

**主要读取方：**

- `report_composition`

---

#### `concepts`

**类型：** `list[dict]`

**用途：**保存 Concept Generation Skill 返回的概念方向，正常目标为 2–3 个方向。第一次生成不满足要求时最多重新生成 1 次；第二次生成后直接返回当前结果，不再继续循环，也不要求第二次必须通过质量检查才允许写入 State。

每个概念建议包含：

```text
name
core_concept
design_opportunities
spatial_strategy
key_actions
case_references
```

例如：

```json
[
  {
    "name": "滨水公共客厅",
    "core_concept": "...",
    "design_opportunities": [],
    "spatial_strategy": "...",
    "key_actions": [],
    "case_references": []
  },
  {
    "name": "城市活力轴",
    "core_concept": "...",
    "design_opportunities": [],
    "spatial_strategy": "...",
    "key_actions": [],
    "case_references": []
  }
]
```

概念质量检查属于 Concept Generation Skill 的内部执行过程。

V1 不将 `quality_check` 作为 State 字段保存，只将 Skill 按上述有限生成规则返回的当前概念结果写入 `concepts`。

**产生节点：** `concept_generation`

**主要读取方：**

- Concept Generation Skill（用于组织对应意向图生成）
- `report_composition`

---

#### `images`

**类型：** `list[dict]`

**用途：**保存各概念方向对应的意向图生成结果，并记录本次图像生成实际使用的模式和参考图片。

V1 默认尝试生成意向图，不增加“是否生成意向图”的任务级 State 字段；失败时允许 `images` 为空或部分成功，并继续生成报告。

建议结构：

```python
{
    "concept_name": str,
    "image_url": str,
    "prompt": str,
    "mode": str,
    "reference_images": list[str]
}
```

字段说明：

| 字段 | 说明 |
|---|---|
| `concept_name` | 对应的概念方向名称 |
| `image_url` | 图片 URL、本地文件路径或对象存储地址 |
| `prompt` | 实际用于本次图像生成的 Prompt |
| `mode` | 本次实际使用的图像生成模式：`text2img` 或 `img2img` |
| `reference_images` | 本次实际使用的场地参考图片；`text2img` 时为空列表 |

例如，img2img 模式：

```json
{
  "concept_name": "滨水公共客厅",
  "image_url": "...",
  "prompt": "...",
  "mode": "img2img",
  "reference_images": [
    "data/site_plan.png"
  ]
}
```

例如，text2img 模式：

```json
{
  "concept_name": "滨水公共客厅",
  "image_url": "...",
  "prompt": "...",
  "mode": "text2img",
  "reference_images": []
}
```

保留 `prompt`、`mode` 和 `reference_images`，主要用于：

- 调试图像生成结果；
- 分析不同图像生成模式的表现；
- 进行 Agent Evaluation；
- 追踪生成结果与原始场地输入之间的关系。

图片结果可以保存为：

```text
图片 URL
本地文件路径
对象存储地址
```

具体存储方式由 Image Generation Tool 的实现决定。

**产生节点：** `concept_generation`

**主要读取方：**

- `report_composition`

Image Generation Tool 在 `concept_generation` Node 内由 Concept Generation Skill 调用，不作为独立 Graph Node，也不直接读写 Agent State。

`mode` 和 `reference_images` 用于记录本次图像生成的实际执行方式。

`USE_IMG2IMG`、`REFERENCE_STRENGTH` 等系统配置不进入 Agent State，由系统配置层统一管理。

### 4.7 Final Output

#### `final_report`

**类型：** `str`

**用途：**保存最终生成的 Markdown 研究报告。

报告由 `report_composition` 根据 State 中的结构化结果统一生成。

主要读取：

```text
project_background
site_analysis
case_analysis
opportunities
vision
concepts
images
```

**产生节点：** `report_composition`

**消费方：**前端。

## 5. 字段来源与消费汇总

| 字段 | 产生节点 | 主要消费节点 / Tool |
|---|---|---|
| `user_input` | 初始输入 / 用户补充 | `parse_and_check` |
| `site_images` | 初始输入 | `parse_and_check`、`site_analysis``concept_generation`（可选，仅 img2img） |
| `project_background` | `parse_and_check` | `site_analysis`、`concept_generation`、`report_composition` |
| `location` | `parse_and_check` | `site_analysis` |
| `planning_conditions` | `parse_and_check` | `site_analysis` |
| `client_requirements` | `parse_and_check` | `site_analysis`、`check_case_need`、`concept_generation` |
| `site_image_description` | `parse_and_check` | `site_analysis` |
| `info_sufficient` | `parse_and_check` | 条件边 A |
| `missing_critical` | `parse_and_check` | `ask_user` |
| `missing_optional` | `parse_and_check` | `ask_user`（仅提示） |
| `followup_question` | `parse_and_check` | `ask_user` |
| `site_analysis` | `site_analysis` | `check_case_need`、`check_research`、`concept_generation`、`report_composition` |
| `need_case_research` | `check_case_need` | 条件边 C |
| `research_direction` | `check_case_need` | `case_research`、`check_research` |
| `search_queries` | `case_research`、`refine_search` | Web Search Tool、`refine_search` |
| `filtered_cases` | `case_research` | `check_research`、`concept_generation` |
| `case_analysis` | `case_research` | `check_research`、`concept_generation`、`report_composition` |
| `search_attempts` | `case_research` | 条件边 B |
| `research_sufficient` | `check_research` | 条件边 B |
| `research_gaps` | `check_research` | `refine_search` |
| `opportunities` | `concept_generation` | `report_composition` |
| `vision` | `concept_generation` | `report_composition` |
| `concepts` | `concept_generation` | `report_composition`、Image Generation Tool |
| `images` | `concept_generation`（含 mode、reference_images 元信息） | `report_composition` |
| `final_report` | `report_composition` | 前端 |

## 6. 节点读写汇总

| Node | 主要读取 | 写入 |
|---|---|---|
| `parse_and_check` | `user_input`、`site_images` | 项目理解字段、信息检查字段 |
| `ask_user` | `followup_question`、`missing_critical`、`missing_optional` | 不更新 State；输出追问后结束本次 Graph execution |
| `site_analysis` | 项目理解字段、`site_images` | `site_analysis` |
| `check_case_need` | `site_analysis`、`client_requirements` | `need_case_research`、`research_direction` |
| `case_research` | `site_analysis`、`research_direction`、`search_queries` | `search_queries`、`filtered_cases`、`case_analysis`、`search_attempts` |
| `check_research` | `research_direction`、`filtered_cases`、`case_analysis`、`site_analysis` | `research_sufficient`、`research_gaps` |
| `refine_search` | `research_direction`、`search_queries`、`research_gaps`、`search_attempts` | `search_queries` |
| `concept_generation` | `site_analysis`、`filtered_cases`、`case_analysis`、项目理解字段、`site_images`（可选，仅 img2img） | `opportunities`、`vision`、`concepts`、`images` |
| `report_composition` | 前序阶段最终结果 | `final_report` |

其中 `check_research` 的核心判断依据是 `research_direction`、`filtered_cases` 和 `case_analysis`，`site_analysis` 作为项目背景上下文使用。

**关于 `ask_user` 的执行机制：** `ask_user` 输出追问后，图执行结束。用户在前端补充信息后，前端重新发起 `graph.invoke()`，从 `parse_and_check` 开始执行。MVP 阶段不使用 `interrupt`，避免图内暂停的复杂度。

## 7. 条件边判断依据

| 条件边 | 判断字段 | 判断条件 | 分支 |
|---|---|---|---|
| A | `info_sufficient` | `true` | `site_analysis` |
| A | `info_sufficient` | `false` | `ask_user` |
| C | `need_case_research` | `true` | `case_research` |
| C | `need_case_research` | `false` | `concept_generation` |
| B | `research_sufficient` | `true` | `concept_generation` |
| B | `research_sufficient` | `false` 且 `search_attempts < 2` | `refine_search` |
| B | `research_sufficient` | `false` 且 `search_attempts >= 2` | `concept_generation` |

三个条件边均直接读取 State 中的决策字段，不需要额外保存 `next_action` 等路由状态。

## 8. 信息充分性判断标准

### 8.1 最低可执行条件

Agent 不要求项目资料完整，而只判断是否具备继续进行场地分析的最低条件。

| 检查项 | 判断标准 | 是否必须 | 缺失后 |
|---|---|---:|---|
| 项目基本定位 | 能判断项目类型、功能定位或发展目标 | 是 | `missing_critical` |
| 场地空间信息 | 有场地图片，或文字中包含基本空间描述 | 是 | `missing_critical` |
| 具体规划指标 | 如容积率、建筑密度等 | 否 | `missing_optional` |
| 明确设计目标 | 用户已明确提出重点关注方向 | 否 | `missing_optional` |

### 8.2 判断逻辑

```text
如果缺少任一关键条件：
    info_sufficient = false
    生成 followup_question

否则：
    info_sufficient = true
    对缺失的非关键条件进行记录
```

例如：

```text
项目定位缺失
→ 必须追问

场地没有任何空间信息
→ 必须追问

容积率缺失
→ 可以继续

设计目标不明确
→ 可以继续，但概念结果可能较泛
```

### 8.3 追问示例

| 缺失信息 | 追问问题 |
|---|---|
| 项目定位 | 请补充项目背景，例如项目类型、功能定位或发展目标。 |
| 场地空间信息 | 请补充场地位置及基本空间条件，或上传地图、卫星图、现状照片等场地图片。 |
| 其他规划条件 | 如果已有容积率、用地性质等规划条件，可以一并补充。 |

## 9. State 生命周期

State 随 Agent 执行过程逐步丰富，而不是一次性生成完整对象。

```text
用户输入
   ↓
user_input + site_images
   ↓
parse_and_check
   ↓
项目理解 + 信息判断
   ↓
site_analysis
   ↓
场地分析
   ↓
check_case_need
   ↓
案例研究决策
   ↓
case_research
   ↓
案例研究结果
   ↓
concept_generation
   ↓
设计机会 + 愿景 + 概念 + 意向图
   ↓
report_composition
   ↓
final_report
```

其中案例研究可能发生一次有限循环：

```text
case_research
      ↓
check_research
      ↓
研究不足
      ↓
refine_search
      ↓
case_research
```

因此 State 既保存当前结果，也保存支持循环控制所需的状态信息。

## 10. State 更新原则

### 10.1 Node 只更新自己负责的字段

```text
parse_and_check
→ 更新项目理解和信息检查字段

site_analysis
→ 更新 site_analysis

check_case_need
→ 更新 need_case_research / research_direction

case_research
→ 更新 search_queries / filtered_cases / case_analysis / search_attempts

check_research
→ 更新 research_sufficient / research_gaps

refine_search
→ 更新 search_queries

concept_generation
→ 更新 opportunities / vision / concepts / images

report_composition
→ 更新 final_report
```

这样可以避免不同 Node 随意修改 State，降低调试和评估难度。

### 10.2 决策字段与结果字段分离

**结果字段：**

```text
site_analysis
case_analysis
opportunities
vision
concepts
```

**决策字段：**

```text
info_sufficient
need_case_research
research_sufficient
search_attempts
```

结果字段描述“已经得到什么”，决策字段描述“Agent 当前应如何继续”。

### 10.3 不保存无必要的临时变量

State 不保存只在单个函数内部使用的临时数据。

例如：

```text
search_url
parsed_text
temporary_score
```

如果不会被后续 Node 使用，也不进入 State。

## 11. State 初始化

State 初始化时只写入真正已经存在的用户输入和必要的流程控制字段。

```python
def create_initial_state(
    user_input: str,
    site_images: list[str] | None = None,
) -> AgentState:
    return {
        "user_input": user_input,
        "site_images": site_images or [],
        "search_attempts": 0,
    }
```

其他字段在对应 Node 执行后逐步写入。

这样可以区分：

```text
字段不存在
→ 当前阶段尚未产生该结果

字段存在但为空
→ 当前阶段已经产生结果，但结果为空
```

对于 V1，除 `search_attempts` 等必要控制字段外，不提前创建大量空字段。

## 12. 节点更新示例

Node 只返回本次需要更新的字段，LangGraph 根据 State Schema 合并更新结果。

```python
def parse_and_check(state: AgentState) -> dict:
    return {
        "project_background": "...",
        "location": "...",
        "info_sufficient": True,
        "missing_critical": [],
        "missing_optional": ["设计目标"],
    }


def site_analysis_node(state: AgentState) -> dict:
    return {
        "site_analysis": {
            # structured result
        }
    }


def check_research(state: AgentState) -> dict:
    return {
        "research_sufficient": True,
        "research_gaps": [],
    }
```

关键原则：

> Node 返回本次需要更新的字段，而不是返回完整 State。

## 13. State 与 Agent 决策

Agent 的决策依赖 State 中的关键字段。

### 信息判断

```text
info_sufficient
        ↓
决定
ask_user / site_analysis
```

### 案例研究决策

```text
site_analysis
        ↓
check_case_need
        ↓
need_case_research
        ↓
决定
case_research / concept_generation
```

### 案例研究迭代

```text
research_sufficient + search_attempts
        ↓
决定
concept_generation / refine_search
```

因此 Agent 的自主性不是来源于单独的“Agent Prompt”，而是来源于：

```text
State
  ↓
Decision Node
  ↓
Conditional Route
  ↓
Next Node
```

## 14. State 与 Human-in-the-Loop

State 同样用于保存人工介入产生的信息。

### 14.1 项目资料补充

```text
parse_and_check
      ↓
missing_critical
      ↓
ask_user
      ↓
当前 Graph execution 结束（ask_user → END）
      ↓
前端接收补充信息并合并 user_input
      ↓
前端重新调用 graph.invoke()
      ↓
parse_and_check（新的 execution）
```

### 14.2 研究方向调整

V1 不在 Graph 运行过程中暂停等待研究方向人工确认或修改。用户指定研究方向或案例应作为任务初始输入，或在重新发起任务时提供：

```text
用户指定研究方向或案例
      ↓
并入 user_input（初始输入或重新发起任务）
      ↓
parse_and_check → site_analysis → check_case_need
      ↓
research_direction → case_research
```

人工输入由前端汇总后发起新的 `graph.invoke()`；`check_case_need` 结合场地分析及已有用户要求确定研究方向。V1 不使用 Interrupt / Checkpoint，不恢复同一次 Graph execution，也不新增 State 字段。

## 15. State 与 Evaluation

State 不仅用于运行，也为 Agent Evaluation 提供可追踪的数据。

可以记录：

```text
输入
 ↓
Agent 判断
 ↓
研究方向
 ↓
搜索结果
 ↓
案例判断
 ↓
概念结果
 ↓
最终报告
```

因此可以进一步评估：

- `info_sufficient` 判断是否正确；
- `need_case_research` 判断是否合理；
- `research_direction` 是否准确；
- `search_queries` 是否有效；
- `research_sufficient` 判断是否合理；
- `concepts` 是否符合项目条件；
- `final_report` 是否完整。

这使评估对象从单纯的“最终答案质量”扩展到 Agent 的**决策过程和中间结果**。

## 16. 字段类型与数据校验

### 16.1 TypedDict 与 Pydantic 的职责

V1 采用 `TypedDict + Pydantic` 的组合。

| 方案 | 用途 | 选择 |
|---|---|---|
| TypedDict | 定义 AgentState 顶层结构 | 使用 |
| Pydantic | 定义复杂业务对象并进行运行时校验 | 使用 |
| dataclass | 替代 TypedDict 的 State 定义 | 暂不使用 |

`TypedDict` 负责定义 Agent State 的整体结构和字段类型；Pydantic 负责校验 `site_analysis`、`case`、`concept` 等复杂对象。

### 16.2 复杂字段结构

以下字段使用 `schemas/` 中的 Pydantic Model 定义具体结构：

```text
site_analysis
filtered_cases
case_analysis
concepts
```

例如：

```python
# schemas/site_info.py

from pydantic import BaseModel


class SWOT(BaseModel):
    strengths: list[str]
    weaknesses: list[str]
    opportunities: list[str]
    threats: list[str]


class SiteAnalysis(BaseModel):
    project_positioning: str
    location_conditions: dict
    functional_conditions: dict
    landscape_resources: dict
    public_space: dict
    transportation: dict
    spatial_conditions: dict
    swot: SWOT
    analysis_summary: str
```

Node 内部：

```python
from schemas.site_info import SiteAnalysis


def site_analysis_node(state: AgentState) -> dict:
    raw = site_analysis_skill(...)
    parsed = SiteAnalysis(**raw)

    return {
        "site_analysis": parsed.model_dump()
    }
```

这样可以避免 LLM 输出结构不稳定的数据直接进入 State。

## 17. 与代码文件对应

| 本文档内容 | 对应代码文件 |
|---|---|
| State 定义 | `src/agent/state.py` |
| State 初始化 | `src/agent/state.py` |
| 节点读写 | `src/agent/nodes.py` |
| 路由判断 | `src/agent/routes.py` |
| 复杂字段校验 | `src/schemas/` |
| Graph 组装 | `src/agent/graph.py` |
| 前端输入 / 输出 | `src/frontend/app.py` |

## 18. State Design Summary

V1 State 的核心结构可以概括为：

```text
用户输入
   ↓
项目理解
   ↓
信息是否充分
   ↓
场地分析
   ↓
是否需要案例研究
   ↓
案例研究状态
   ↓
研究是否充分
   ↓
设计机会
   ↓
目标愿景
   ↓
概念方向
   ↓
最终报告
```

State 在整个系统中承担三个核心作用：

**上下文载体：**保存项目资料和历史分析结果。

**决策依据：**为 Agent 的条件判断和流程路由提供状态信息。

**过程记录：**保存 Agent 的中间结果，为调试、评估和迭代提供依据。

最终形成：

> **State 不负责完成任务，而是记录任务当前状态；Agent 基于 State 做决策，Node 执行任务，Skill 完成专业能力，Tool 提供外部能力。**
