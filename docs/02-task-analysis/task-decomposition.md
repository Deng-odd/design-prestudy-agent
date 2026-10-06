# Task Decomposition

## 1. 文档目的

本文档将 `human-workflow.md` 中的 7 阶段人工流程，拆解为 Agent 可执行的任务单元，明确：

- 哪些任务适合由 LLM 完成
- 哪些任务需要调用外部工具
- 哪些任务需要人工参与
- 各任务之间的数据依赖关系
- 任务如何映射到节点、Skill 和 Tool


## 2. 人工流程 vs Agent 分工

| 人类阶段 | 人工做什么 | Agent 能做什么 | 分工 | 是否封装 Skill |
|---|---|---|---|---|
| 1. 项目资料理解 | 读资料，提取区位、定位、功能、资源 | 解析文字+图片，提取结构化信息 | Agent 独立 | 不封装，直接调 LLM |
| 2. 场地条件分析 | 分析区位、资源、空间条件，形成 SWOT | 基于图片或空间文字描述，输出分析 | Agent 独立 | Site Analysis |
| 3. 案例研究 | 判断方向，搜索案例，分析空间策略 | 生成检索方向 + 搜索 + 过滤 + 总结 | Agent 独立 | Case Research |
| 4. 设计机会识别 | 综合条件和案例，提炼机会 | 基于 SWOT 和案例输出机会点 | Agent 独立 | Concept Generation |
| 5. 概念方向提出 | 结合机会，提出 2-3 个方向 | 生成方向描述 | Agent 辅助，人决策 | Concept Generation |
| 6. 意向表达 | 找参考图或画草图 | AI 生成意向图 | Agent 独立 | Concept Generation |
| 7. 研究报告整理 | 汇总成报告 | 自动汇总 Markdown | Agent 独立 | Report Composition |

### 分工判断标准

| 标准 | 说明 | 对应分工 |
|---|---|---|
| 有明确输入输出 | 结构化任务 | Agent 独立 |
| 需要价值判断 | 涉及设计决策 | Agent 辅助，人决策 |
| 需要创意选择 | 涉及方案取舍 | Agent 辅助，人决策 |
| 重复性劳动 | 整理、汇总、搜索 | Agent 独立 |


## 3. 一级任务拆解

| 任务阶段 | 任务目标 | 主要输入 | 主要输出 | 执行方式 | 对应节点 |
|---|---|---|---|---|---|
| 项目理解 | 理解项目背景和设计条件 | 项目描述、场地图像 | 结构化项目信息 | LLM + 图像分析 | `parse_and_check` |
| 信息充分性判断 | 判断信息是否支持后续研究 | 项目结构化信息 | 判断结果 | LLM | `parse_and_check` |
| 场地分析 | 分析空间条件和资源 | 项目信息、地图、照片 | 场地分析结果 + SWOT | LLM + 图像分析 | `site_analysis` |
| 案例研究 | 判断是否研究，寻找参考项目并提炼策略 | 项目特征、设计问题、用户要求 | 案例分析结果 | LLM + 搜索工具 | `check_case_need` + `case_research` + `check_research` + `refine_search` |
| 机会识别 | 发现设计机会 | 场地分析、案例结果 | 机会点和愿景 | LLM 推理 | `concept_generation`（内部） |
| 概念生成 | 形成多个设计方向 | 机会点、案例策略 | 概念方向 | LLM 生成 | `concept_generation` |
| 意向表达 | 形成空间视觉参考 | 概念方向 | 意向图 | 图像生成工具 | `concept_generation`（内部调 Tool） |
| 报告整理 | 组织研究成果 | 全部中间结果 | 研究报告 | LLM 生成 | `report_composition` |


## 4. 详细任务拆解

### Task 1：项目理解（Project Understanding）

**目标：** 将非结构化项目资料转换为结构化项目认知。

**输入：**
- 项目文字描述
- 项目背景
- 区位信息
- 规划条件
- 甲方诉求
- 场地图像

**子任务：**

| 编号 | 子任务 | 动作 | 实现方式 |
|---|---|---|---|
| T1.1 | 信息提取 | 提取项目类型、区位条件、规划条件、甲方诉求 | LLM |
| T1.2 | 图像理解 | 分析地图范围、周边空间关系、自然资源、城市界面 | Vision Model |
| T1.3 | 信息结构化 | 生成结构化 JSON | LLM |

**输出：**

```json
{
  "project_background": "",
  "location": "",
  "planning_conditions": {},
  "client_requirements": null,
  "site_image_description": ""
}
```

**注意：** 项目定位、功能定位、发展目标不在此处输出，由 Task 3 场地分析后得出。

`client_requirements` 统一为 `str | None`，无要求时为 `None`（JSON 中为 `null`）。用户指定研究方向或案例统一并入初始 `user_input`，或在重新发起任务时提供，不新增 State 字段。

**对应节点：** `parse_and_check`
**对应 Skill：** 无（直接调 LLM）

### Task 2：信息充分性判断（Information Check）

**目标：** 判断当前信息是否支持后续研究。

**输入：** 结构化项目信息

**判断逻辑：**

| 检查项 | 判断标准 | 是否必须 |
|---|---|---|
| 项目基本信息 | 能判断项目类型、功能定位或发展目标 | 是 |
| 场地空间信息 | 有图片，或文字中有基本空间描述 | 是；图片本身可选 |
| 设计目标 | 用户明确提出关注方向 | 否 |

**输出：**

```json
{
  "info_sufficient": true,
  "missing_critical": [],
  "missing_optional": [],
  "followup_question": ""
}
```

**决策：**

| 情况 | 处理 |
|---|---|
| 信息满足 | 进入场地分析 |
| 缺少关键资料 | 请求用户补充 |

**对应节点：** `parse_and_check` → 条件边 A → `ask_user`
**对应 Skill：** 无（直接调 LLM）

仅 `missing_critical` 非空时阻断流程。实际 Graph 为 `ask_user → END`，用户补充后由前端合并输入并重新调用 `graph.invoke()`，从 `parse_and_check` 开始；V1 不使用 Interrupt / Checkpoint。


### Task 3：场地分析（Site Analysis）

**目标：** 形成设计研究基础。

**输入：**
- 项目信息
- 场地图像

**子任务：**

| 编号 | 子任务 | 动作 |
|---|---|---|
| T3.1 | 项目定位分析 | 分析项目类型、功能属性、城市角色 |
| T3.2 | 资源分析 | 识别山水资源、蓝绿空间、公共空间、特色资源 |
| T3.3 | 城市关系分析 | 分析周边功能、交通联系、城市界面 |
| T3.4 | 空间条件分析 | 分析场地边界、空间连续性、潜在问题 |
| T3.5 | SWOT 分析 | 形成优势、劣势、机会、挑战 |

**输出：**

```json
{
  "site_analysis": {
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
}
```

**对应节点：** `site_analysis`
**对应 Skill：** `Site Analysis Skill`
**图像读取：** 多模态模型直接读取场地图像，不设置独立 Image Analysis Tool；无图片时使用用户提供的空间文字描述。


### Task 4：案例研究（Case Research）

**目标：** 寻找与项目问题相关的参考案例。

**输入：**
- 项目定位
- 场地条件
- SWOT 结果

**子任务：**

| 编号 | 子任务 | 动作 |
|---|---|---|
| T4.1 | 判断研究需求 | `check_case_need` 判断是否需要案例参考并确定研究方向 |
| T4.2 | 生成搜索策略 | 根据项目类型、空间资源、核心问题生成搜索方向 |
| T4.3 | 案例检索 | 调用 Web Search |
| T4.4 | 案例筛选 | 判断类型相关性、策略相关性、可借鉴价值 |
| T4.5 | 案例分析 | 提取项目背景、设计策略、空间组织方式、启发 |

**搜索循环：**

```text
用初始关键词搜索
  ↓
判断结果是否相关
  ├─ 不相关 → 换关键词再搜
  └─ 相关 → 分析案例
  ↓
判断是否够 3-5 个
  ├─ 不够且 attempts < 2 → refine_search
  └─ 够 或 attempts ≥ 2 → 进入机会识别
```

**输出：**

```json
{
  "research_direction": [],
  "filtered_cases": [
    {
      "name": "",
      "location": "",
      "project_type": "",
      "source": "",
      "relevance": ""
    }
  ],
  "case_analysis": [
    {
      "case": "",
      "relevance_reason": "",
      "spatial_strategy": [],
      "applicable_reference": [],
      "limitations": []
    }
  ],
  "research_sufficient": true,
  "search_attempts": 1
}
```

以上是案例研究阶段的 State 结果，不是 Case Research Skill 的完整返回值。`research_direction` 由 `check_case_need` 产生，`research_sufficient` 由 `check_research` 产生，`search_attempts` 由 `case_research` Node 更新；Skill 不返回或修改计数。

**对应节点：** `check_case_need` + `case_research` + `check_research` + `refine_search`
**对应 Skill：** `Case Research Skill`
**调用 Tool：** `Web Search`


### Task 5：设计机会识别（Opportunity Identification）

**目标：** 从条件分析转向设计方向。

**输入：**
- SWOT
- 案例策略

**推理过程：**

```text
场地优势 + 案例经验 + 项目目标
  ↓
设计机会
  ↓
目标愿景
```

**子任务：**

| 编号 | 子任务 | 动作 |
|---|---|---|
| T5.1 | 问题发现 | 识别当前限制和潜在价值 |
| T5.2 | 机会转换 | 优势转化、问题解决、资源组合 |
| T5.3 | 愿景提炼 | 形成一句话目标 |

**输出：**

```json
{
  "opportunities": [
    {
      "opportunity": "",
      "basis": "",
      "priority": "high"
    }
  ],
  "vision": {
    "theme": "",
    "positioning": "",
    "core_goal": "",
    "spatial_idea": ""
  }
}
```

**对应节点：** `concept_generation`（内部）
**对应 Skill：** `Concept Generation Skill`


### Task 6：概念方向生成（Concept Generation）

**目标：** 生成多个可讨论的设计方向。

**输入：**
- 设计机会
- 项目定位
- 案例策略

**子任务：**

| 编号 | 子任务 | 动作 |
|---|---|---|
| T6.1 | 方向生成 | 生成 2-3 个方向 |
| T6.2 | 策略描述 | 每个方向包含概念名称、核心理念、空间策略、依据 |
| T6.3 | 方向评价 | 检查是否回应场地问题、是否具有差异性、是否有依据 |

**概念质量自检：**

| 指标 | 判断标准 |
|---|---|
| 方向数量 | 是否达到 2-3 个 |
| 差异性 | 不同方向是否具有明显区别 |
| 依据充分 | 是否基于场地条件或案例 |
| 表达完整 | 是否包含理念和空间策略 |

不满足 → 重新生成一次（最多 1 轮）

第二次生成后直接返回当前结果，不再继续循环。`quality_check` 仅存在于 Concept Generation Skill 内部，不进入 State，也不增加 Graph Node。

**输出：**

```json
{
  "concepts": [
    {
      "name": "",
      "core_concept": "",
      "design_opportunities": [],
      "spatial_strategy": "",
      "key_actions": [],
      "case_references": []
    }
  ]
}
```

**对应节点：** `concept_generation`
**对应 Skill：** `Concept Generation Skill`


### Task 7：意向图生成（Image Generation）

**目标：** 将概念方向转化为视觉表达。

**输入：**
- 概念方向
- 空间策略
- 场地特征

**子任务：**

| 编号 | 子任务 | 动作 |
|---|---|---|
| T7.1 | Prompt 生成 | 生成图像描述，含空间类型、氛围、视角、设计元素 |
| T7.2 | 图像生成 | 调用 Image Generation Tool |

**输出：** 概念空间意向图（每个方向 1-2 张）

**失败处理：** 生成失败 → 跳过意向图，报告继续输出

V1 默认尝试生成意向图，不增加“是否生成意向图”的任务级 State 字段；失败时允许 `images` 为空或部分成功。

**对应节点：** `concept_generation`（内部调 Tool）
**调用 Tool：** `Image Generation`


### Task 8：报告生成（Report Composition）

**目标：** 整理完整研究成果。

**输入：** 所有中间状态

**子任务：**

| 编号 | 子任务 | 动作 |
|---|---|---|
| T8.1 | 内容组织 | 按项目理解→场地分析→案例研究→设计机会→概念方向→意向图组织 |
| T8.2 | 格式生成 | 输出 Markdown 报告 |

**输出：** `research_report.md`

**对应节点：** `report_composition`
**对应 Skill：** `Report Composition Skill`


## 5. Skill 划分

### 5.1 识别标准

一个能力值得封装成 Skill，看四条：

| 标准 | 说明 |
|---|---|
| 调多个 Tool | 需要组合搜索、检索、图像生成等 |
| 多次 LLM 调用 | 需要分步推理，不是一次生成 |
| 需要独立测试 | 能单独跑，单独评测 |
| 会被复用 | 多个节点或流程会调用 |

**满足两条以上，才值得封装成 Skill。**

### 5.2 4 个 Skill

| Skill | 对应 Task | 内部做什么 | 调用 Tool | 调用 LLM 次数 |
|---|---|---|---|---|
| **Site Analysis** | Task 3 | 场地条件分析 + SWOT，多模态模型直接读取图片 | 无 | 2 次 |
| **Case Research** | Task 4 | 检索策略生成 + 搜索 + 案例分析 | Web Search | 2 次 |
| **Concept Generation** | Task 5+6+7 | 机会识别 + 愿景提炼 + 概念方向 + 意向图 | Image Generation | 3 次 + 1 次自检 |
| **Report Composition** | Task 8 | 报告组织 | 无 | 1 次 |

### 5.3 每个 Skill 详细定义

#### Site Analysis Skill

| 项目 | 说明 |
|---|---|
| 职责 | 场地条件分析 + SWOT |
| 输入 | 项目理解字段、可选 `site_images`，或用户提供的空间文字描述 |
| 输出 | `site_analysis`（结构见 Task 3，SWOT 使用嵌套 `swot`） |
| 调用 Tool | 无，图片由多模态模型直接读取 |
| 调用 LLM | 2 次（场地分析、SWOT） |
| 失败降级 | 无图片时，仅基于文字分析 |
| 对应节点 | `site_analysis` |

#### Case Research Skill

| 项目 | 说明 |
|---|---|
| 职责 | 根据已确定的研究方向生成检索词 + 搜索 + 分析案例 |
| 输入 | `site_analysis`、`research_direction`、可选 `search_queries` |
| 输出 | `search_queries`、`filtered_cases`、`case_analysis`；`research_sufficient` 由 `check_research` 判断，Skill 不返回或修改 `search_attempts` |
| 调用 Tool | Web Search |
| 调用 LLM | 2 次（生成检索方向、分析案例） |
| 失败降级 | 搜索失败 → 返回当前已有结果；两轮不够 → 带限制说明继续；不使用种子案例 |
| 调用节点 | `case_research`；`check_case_need`、`check_research` 和 `refine_search` 为 Graph 决策与策略节点，不调用该 Skill |

#### Concept Generation Skill

| 项目 | 说明 |
|---|---|
| 职责 | 机会识别 + 愿景提炼 + 概念方向 + 意向图 |
| 输入 | 项目背景、`site_analysis`、可选 `case_analysis`、`client_requirements` 和 `site_images` |
| 输出 | `opportunities`、`vision`、`concepts`、`images` |
| 调用 Tool | Image Generation |
| 调用 LLM | 3 次（机会识别、愿景、概念方向）+ 1 次质量自检 |
| 失败降级 | 图像生成失败 → 跳过意向图，报告继续输出 |
| 对应节点 | `concept_generation` |

#### Report Composition Skill

| 项目 | 说明 |
|---|---|
| 职责 | 组织研究报告 |
| 输入 | 全部前序输出 |
| 输出 | `final_report`（Markdown） |
| 调用 Tool | 无 |
| 调用 LLM | 1 次（汇总） |
| 失败降级 | 无 |
| 对应节点 | `report_composition` |

### 5.4 为什么是这 4 个

| 曾经的候选 | 是否独立 | 原因 |
|---|---|---|
| Project Analysis | 否 | 只调 1 次 LLM，由 `parse_and_check` 直接完成，不封装 Skill |
| Opportunity Identification | 否 | 只调 1 次 LLM，合并进 Concept Generation |
| Concept Quality Check | 否 | Skill 内部自检，不单独成节点 |
| Report Export | 否 | MVP 不做，后续扩展 |


## 6. Tool 划分

### 6.1 2 个 Tool

| Tool | 职责 | 被哪个 Skill 调用 | 外部依赖 |
|---|---|---|---|
| **Web Search** | 搜索案例资料 | Case Research | Tavily |
| **Image Generation** | 生成空间意向图 | Concept Generation | Qwen Image |

### 6.2 Tool 详细定义

#### Web Search Tool

| 项目 | 说明 |
|---|---|
| 输入 | `query`（检索词）、`max_results`（由 `WEB_SEARCH_MAX_RESULTS` 配置，默认 10） |
| 输出 | 搜索结果列表（标题、摘要、链接） |
| 失败处理 | 按 `TOOL_MAX_RETRIES` 有限技术重试，仍失败则由 Skill 返回当前已有结果；不使用种子案例 |
| 成本 | Tavily 免费 1000 次/月 |

#### 场地图像读取

场地图像由多模态模型直接读取，不封装独立 Image Analysis Tool。无图片时使用用户提供的空间文字描述；无法可靠识别的信息标记为证据不足，不虚构场地条件。

#### Image Generation Tool

| 项目 | 说明 |
|---|---|
| 输入 | Skill 构建完成的 Prompt、生成模式、可选参考图及参考强度 |
| 输出 | 意向图（每个方向 1-2 张） |
| 失败处理 | 跳过，报告继续输出 |
| 成本 | Qwen Image 计费以实际账号和调用规格为准，Stage 5 验证 |


## 7. 节点与 Skill 对应

### 7.1 9 个节点

| 节点 | 类型 | 调用的 Skill | 职责 |
|---|---|---|---|
| `parse_and_check` | 判断节点 | 无（直接调 LLM） | 解析输入，判断信息是否充分 |
| `ask_user` | 输出节点 | 无 | 输出追问，结束流程 |
| `site_analysis` | Skill 节点 | Site Analysis | 场地分析 + SWOT |
| `check_case_need` | 判断节点 | 无（直接调 LLM） | 判断是否需要案例研究并确定研究方向 |
| `case_research` | Skill 节点 | Case Research | 根据研究方向生成检索词 + 搜索及分析案例，Node 更新轮次 |
| `check_research` | 判断节点 | 无（直接调 LLM） | 判断案例是否充分 |
| `refine_search` | 策略节点 | 无（直接调 LLM） | 换关键词，重新搜索 |
| `concept_generation` | Skill 节点 | Concept Generation | 机会识别 + 概念方向 + 意向图 |
| `report_composition` | Skill 节点 | Report Composition | 汇总报告 |

### 7.2 节点与 Task 对应

| Task | Agent 节点 |
|---|---|
| Task 1 项目理解 | `parse_and_check` |
| Task 2 信息充分性判断 | `parse_and_check` |
| Task 3 场地分析 | `site_analysis` |
| Task 4 案例研究 | `check_case_need` + `case_research` + `check_research` + `refine_search` |
| Task 5 设计机会识别 | `concept_generation`（内部） |
| Task 6 概念方向生成 | `concept_generation` |
| Task 7 意向图生成 | `concept_generation`（内部调 Tool） |
| Task 8 报告生成 | `report_composition` |


## 8. 状态机草图

```text
START
  ↓
parse_and_check          ← 判断信息是否充分
  ↓
[条件边A]
  ├─ 不足 → ask_user → END
  └─ 足够 → site_analysis
              ↓
          check_case_need   ← 判断是否需要案例研究
              ├─ 不需要 → concept_generation
              └─ 需要 → case_research
              ↓
          check_research    ← 判断案例是否够
              ↓
          [条件边B]
            ├─ 不够 且 attempts < 2 → refine_search → case_research（循环）
            ├─ 不够 且 attempts ≥ 2 → concept_generation（带限制说明）
            └─ 够 → concept_generation
                      ↓
                  report_composition
                      ↓
                     END
```

### 条件边定义

| 条件边 | 判断依据 | 分支 |
|---|---|---|
| A | `info_sufficient` | true → `site_analysis`；false → `ask_user` |
| C | `need_case_research` | true → `case_research`；false → `concept_generation` |
| B | `research_sufficient` + `search_attempts` | 够 → `concept_generation`；不够且 <2 → `refine_search`；不够且 ≥2 → `concept_generation` |

### 循环上限

| 循环 | 上限 | 超限处理 |
|---|---|---|
| 案例搜索 | 2 轮 | 带限制说明继续，报告中标注 |
| 概念重新生成 | 1 轮（Skill 内部） | 使用当前结果继续 |


## 9. Agent 能力体现

| Agent 能力 | 体现在哪 | 对应字段 |
|---|---|---|
| 判断是否需要补充研究 | `parse_and_check` 判断信息充分性 | `info_sufficient` |
| 选择研究动作 | `check_case_need` 决定是否研究，`check_research` 决定是否再搜 | `need_case_research`、`research_sufficient` |
| 选择检索方向 | Case Research 生成检索词 | `search_queries` |
| 管理状态 | State 贯穿所有节点 | 全部字段 |
| 有限循环 | 条件边 B 最多 2 轮 | `search_attempts` |
| 质量自检 | Concept Generation 内部自检 | Skill 内部逻辑 |


## 10. State 字段来源

| 字段 | 谁产生 | 谁消费 |
|---|---|---|
| 项目理解字段 | `parse_and_check` | Site Analysis |
| `info_sufficient` | `parse_and_check` | 条件边 A |
| `missing_critical` | `parse_and_check` | `ask_user` |
| `missing_optional` | `parse_and_check` | `ask_user`（仅提示） |
| `followup_question` | `parse_and_check` | `ask_user` |
| `site_analysis` | Site Analysis | Concept Generation |
| `search_queries` | Case Research | Web Search |
| `need_case_research` | `check_case_need` | 条件边 C |
| `research_direction` | `check_case_need` | Case Research、`check_research` |
| `filtered_cases` | Case Research | Concept Generation |
| `research_sufficient` | `check_research` | 条件边 B |
| `search_attempts` | `case_research` Node | 条件边 B |
| `opportunities` | Concept Generation | Report Composition |
| `vision` | Concept Generation | Report Composition |
| `concepts` | Concept Generation | Image Generation、Report Composition |
| `images` | `concept_generation` Node（Skill 调用 Tool 后返回） | Report Composition |
| `final_report` | Report Composition | 用户 |


## 11. Agent 自主任务与人工任务

### Agent 自主执行

| 任务 | 原因 | 对应节点 |
|---|---|---|
| 信息提取 | 规则明确 | `parse_and_check` |
| 场地分析初稿 | 适合 LLM 辅助 | `site_analysis` |
| 案例搜索 | 适合工具调用 | `case_research` |
| 案例总结 | 结构化任务 | `case_research` |
| 概念生成 | 探索性任务 | `concept_generation` |
| 意向图生成 | 适合工具调用 | `concept_generation` |
| 报告整理 | 重复性任务 | `report_composition` |

### 人工参与

| 任务 | 原因 | 触发时机 |
|---|---|---|
| 确认项目目标 | 需要业务判断 | 信息不足时 |
| 指定研究方向或案例 | 需要设计经验 | 任务初始输入或重新发起任务时提供，不暂停 Graph |
| 选择概念方向 | 需要方案决策 | 报告输出后 |
| 深化设计方案 | 专业创造过程 | 报告输出后 |


## 12. V1 实现范围

### 必须实现

- 项目理解
- 信息充分性判断
- 场地分析
- 案例研究
- 机会识别
- 概念生成
- 意向图生成
- 报告输出

### 简化实现

- 图像分析采用多模态模型
- 案例搜索采用外部搜索 API
- 意向图采用外部生成服务

### 暂不实现

- GIS 自动分析
- 自动空间布局
- 专业规划计算
- 完整方案设计
- PDF/PPT 导出
- 多 Agent 协作


## 13. 设计决策记录

| 决策 | 选择 | 理由 |
|---|---|---|
| Skill 数量 | 4 个 | 每个都是复合能力，不冗余 |
| 项目理解是否独立 Skill | 否 | 只调 1 次 LLM，由 `parse_and_check` 直接完成 |
| 机会识别是否独立 Skill | 否 | 只调 1 次 LLM，合并进 Concept Generation |
| 概念质量判断是否独立节点 | 否 | Skill 内部自检，不增加节点 |
| 案例搜索循环上限 | 2 轮 | 平衡覆盖面和效率 |
| 概念重新生成上限 | 1 轮 | 避免无限循环 |
| 图片解析是否独立 Tool | 否 | 场地图像由多模态模型直接读取 |
| 报告导出格式 | Markdown | MVP 阶段，PDF/PPT 后续扩展 |
```
