# Tools Design

## 1. Tool 设计目标

项目前期研究 Agent 使用 Tool 接入专业任务执行过程中所需的外部能力。

Tool 位于 Skill 下层：

```text
Agent / Graph
      ↓
Node
      ↓
Skill
      ↓
Tool
      ↓
External Provider / API
```

其中：

- **Agent / Graph**：决定任务流程；
- **Node**：读取 State、调用 Skill、更新 State；
- **Skill**：定义专业任务如何完成；
- **Tool**：封装外部能力调用；
- **Provider / API**：实际提供搜索、图像生成等能力。

Tool 的核心作用是：

> 将外部能力封装成稳定、统一、可替换的调用接口，避免 Skill 直接依赖具体 Provider API。

V1 Tool 设计遵循以下原则：

1. Tool 只完成单一外部能力，不承担完整专业任务；
2. Tool 不直接决定 Agent 下一步流程；
3. Tool 不直接读写 Agent State；
4. Skill 负责决定什么时候调用 Tool、调用什么能力；
5. Tool 对上层暴露统一接口；
6. Provider 差异在 Tool 层内部适配；
7. API Key、模型名称和运行参数由配置层统一管理；
8. Tool 层负责有限技术重试，但不负责 Agent 业务循环；
9. Tool 返回结构化结果，供 Skill 继续处理；
10. V1 只保留支撑核心闭环所必需的 Tool。

## 2. Tool 总体结构

V1 设置两个核心 Tool：

```text
Tools
│
├── Web Search Tool
│      ├── Query 接收
│      ├── 外部搜索调用
│      ├── 结果标准化
│      └── 错误处理
│
└── Image Generation Tool
       ├── text2img
       ├── img2img / Reference Image
       ├── Provider Adapter
       ├── 结果标准化
       └── 错误处理
```

对应代码：

```text
src/tools/
├── __init__.py
├── web_search.py
└── image_generation.py
```

V1 不设置：

```text
image_analysis.py
gis.py
rag.py
browser.py
```

其中：

- 场地图片由多模态模型直接读取，不单独设计 Image Analysis Tool；
- GIS 自动分析不属于 V1 Scope；
- RAG / 专业案例知识库属于后续版本；
- Web Search Tool 已承担外部案例信息获取能力。

## 3. Tool 与 Skill、State 的关系

### 3.1 调用关系

| Tool | 调用 Skill | 主要输入 | 主要输出 |
|---|---|---|---|
| Web Search Tool | Case Research Skill | 搜索 Query | 标准化搜索结果 |
| Image Generation Tool | Concept Generation Skill | Prompt、生成模式、参考图 | 图片结果 |

调用链：

```text
Case Research Skill
        ↓
Web Search Tool
        ↓
Search Provider
```

以及：

```text
Concept Generation Skill
        ↓
Image Generation Tool
        ↓
Image Provider
```

### 3.2 Tool 不直接读写 State

Tool 的接口只接收执行任务所需的具体参数，不接收完整 `AgentState`。

例如：

```text
site_images
    ↓
concept_generation Node
    ↓
Concept Generation Skill
    ↓
Image Generation Tool
    ↓
generated image
    ↓
Concept Generation Skill
    ↓
images
    ↓
Node 写回 State
```


## 4. Web Search Tool

### 4.1 Tool 目标

Web Search Tool 为 Case Research Skill 提供外部案例和公开资料检索能力。

Tool 只负责：

> 根据给定 Query 执行搜索，并将不同搜索 Provider 返回的数据转换成统一结果格式。

Tool 不负责：

- 判断是否需要案例研究；
- 决定案例研究方向；
- 判断哪些案例值得保留；
- 分析案例与当前项目的关联；
- 判断案例研究是否充分。

上述职责分别属于：

```text
check_case_need
Case Research Skill
check_research
```

### 4.2 输入

Web Search Tool 的核心输入：

```text
query
```

可选控制参数：

```text
max_results
search_depth
domain_filter
language
```

V1 不要求所有 Provider 都支持全部参数。

建议接口：

```python
def web_search(
    query: str,
    max_results: int = 10,
) -> list[dict]:
    ...
```

如果后续需要更多搜索控制参数，可以逐步扩展，不在 V1 预先设计复杂接口。

### 4.3 输出

Tool 返回统一结构的搜索结果列表。

建议结构：

```python
{
    "title": str,
    "url": str,
    "snippet": str,
    "source": str
}
```

例如：

```json
[
  {
    "title": "Example Waterfront Project",
    "url": "https://example.com/project",
    "snippet": "Project description...",
    "source": "example.com"
  }
]
```

字段说明：

| 字段 | 说明 |
|---|---|
| `title` | 搜索结果标题 |
| `url` | 原始来源链接 |
| `snippet` | 搜索 Provider 返回的摘要或内容片段 |
| `source` | 来源网站或域名 |

Web Search Tool 只负责返回外部搜索结果。

以下结构不由 Tool 产生：

```text
filtered_cases
case_analysis
relevance_reason
applicable_reference
```

这些属于 Case Research Skill 的专业分析结果。

### 4.4 调用流程

```text
Case Research Skill
        ↓
生成 search_queries
        ↓
逐个调用 Web Search Tool
        ↓
获得 raw search results
        ↓
合并与去重
        ↓
Skill 筛选案例
        ↓
Skill 分析案例
```

Tool 只覆盖：

```text
Query
  ↓
Search API
  ↓
Normalized Search Result
```

### 4.5 Provider 抽象

V1 可以只接入一个 Web Search Provider。

Tool 对 Skill 保持统一调用方式：

```python
results = web_search(
    query=query,
    max_results=10,
)
```

具体使用：

```text
Tavily
Serper
Bing
其他 Search API
```

不应影响 Case Research Skill 的接口。

如果后续需要切换 Provider，可在 `web_search.py` 内部处理。

V1 不要求单独建立完整的 Web Search Provider Adapter 层，除非实际开发中已经出现多个 Provider。

### 4.6 搜索结果处理边界

Web Search Tool 可以执行：

- API 请求；
- Provider 响应解析；
- 字段标准化；
- 基础去重；
- 无效 URL 过滤；
- 技术异常处理。

Web Search Tool 不执行：

- 案例专业筛选；
- 项目相关性判断；
- 城市设计策略提炼；
- 案例充分性判断。

因此：

```text
技术数据处理
→ Tool

专业意义判断
→ Skill
```

### 4.7 错误处理

Web Search Tool 负责处理 API 调用层面的瞬时错误。

例如：

```text
Timeout
Rate Limit
Temporary Network Error
Provider 5xx
```

处理逻辑：

```text
Search Request
     ↓
调用失败
     ↓
有限重试
     ↓
仍失败
     ↓
返回 Tool Error
```

Tool 的技术重试次数由配置控制。

Tool 不负责：

```text
research_sufficient
search_attempts
refine_search
```

这些属于 Agent 业务循环。

因此：

```text
Tool Retry
≠
Case Research Loop
```

如果 Tool 最终不可用，Case Research Skill 根据当前已有搜索结果进行降级处理。

## 5. Image Generation Tool

### 5.1 Tool 目标

V1 图像 Provider 统一为 Qwen Image，下一阶段默认 `IMAGE_PROVIDER=qwen`、`IMAGE_MODEL=qwen-image-3.0-pro`。调用关系保持 Concept Generation Skill → Image Generation Tool → Qwen Image。凭据复用 `DASHSCOPE_API_KEY`，Image Base URL 默认复用 `LLM_BASE_URL`；仅在后续真实 API 验证证明需要时再考虑独立配置。Stage 4.5 只同步设计，不实现图像生成。

Image Generation Tool 为 Concept Generation Skill 提供概念意向图生成能力。

V1 支持：

```text
text2img
img2img / Reference Image Generation
```

Tool 对上层提供统一的图像生成接口，并屏蔽不同 Image Generation Provider 的 API 差异。

Tool 不负责：

- 生成概念方向；
- 判断使用什么空间策略；
- 决定图像需要表达什么设计内容；
- 构建完整专业概念逻辑；
- 判断某个概念是否合理。

这些属于 Concept Generation Skill。

Tool 负责：

> 接收已经组织好的图像生成参数，并完成具体图像模型调用。

### 5.2 图像生成模式

V1 支持两种模式：

| 模式 | 说明 |
|---|---|
| `text2img` | 仅根据文本 Prompt 生成图像 |
| `img2img` | 在文本 Prompt 基础上，以场地图片作为视觉参考 |

模式选择由 Concept Generation Skill 根据以下条件判断：

```text
USE_IMG2IMG
+
site_images
+
Provider Capability
```

Tool 不自主决定业务上应该使用哪种模式。

### 5.3 统一输入接口

Image Generation Tool 使用统一业务参数：

```python
def generate_image(
    prompt: str,
    *,
    reference_images: list[str] | None = None,
    size: str | None = None,
) -> dict:
    ...
```

| 参数 | 说明 |
|---|---|
| `prompt` | Skill 已构建完成的图像生成 Prompt |
| `reference_images` | Skill 选择的本地参考图片；为空时执行 text2img，非空时执行 img2img |
| `size` | 可选输出尺寸，使用 `宽x高`；不指定时由模型选择 |

Stage 5 已确认 Qwen Image OpenAI-compatible 接口：复用现有 OpenAI SDK，text2img 与 reference-image 均使用 `client.images.generate()`（`/images/generations`）；参考图通过 `extra_body.image` 传入 Data URI 数组，不使用 `/images/edits`。3.0 系列支持 1–3 张参考图，本地 PNG/JPG/JPEG 在 Tool 层编码，不由 Skill 读取。

API 未提供明确的参考强度参数；V1 不启用 `reference_strength` 或 `REFERENCE_STRENGTH`，不伪造映射。其他章节的参考强度示例仅描述未来 Provider 差异，不适用于当前实现。

`IMAGE_TIMEOUT_SECONDS=120`、`IMAGE_MAX_RETRIES=2` 独立控制图像调用，SDK 内建 retry 关闭；LLM 和搜索预算不影响图像 retry。长耗时可通过环境变量提高超时，超时后仍遵循有限重试与失败降级。

Tool 对上层保持统一接口，不要求 Skill 了解 Provider 参数。接口依据：[Qwen 图像生成与编辑 API 参考](https://www.alibabacloud.com/help/zh/model-studio/qwen-image-generation-and-editing-api-reference)。

### 5.4 输出

Tool 返回单次图像生成结果。OpenAI-compatible 响应 `data[0].url` 标准化为 `image_url`；URL 有效期为 24 小时，V1 保留原始 URL，不增加下载、存储或 State 字段。

建议结构：

```python
{
    "image_url": str,
    "provider": str,
    "model": str,
    "mode": str
}
```

例如：

```json
{
  "image_url": "outputs/concept_01.png",
  "provider": "example_provider",
  "model": "example_model",
  "mode": "img2img"
}
```

Concept Generation Skill 在 Tool 返回结果后，再组合：

```text
concept_name
prompt
reference_images
```

形成写入 State 的完整 `images` 结构：

```json
{
  "concept_name": "滨水公共客厅",
  "image_url": "...",
  "prompt": "...",
  "mode": "img2img",
  "reference_images": ["..."]
}
```

因此：

```text
Tool Output
≠
State.images 完整对象
```

Tool 只返回外部生成结果；

Skill 负责将 Tool Result 与概念上下文组合。

## 6. Provider Adapter

### 6.1 设计目标

不同 Image Generation Provider 对图像生成的接口定义可能不同。

例如：

```text
Provider A
→ strength

Provider B
→ image_weight

Provider C
→ reference_strength

Provider D
→ 不支持参考图生成
```

如果 Skill 直接调用这些 Provider 原生参数，会导致 Concept Generation Skill 与具体模型强耦合。

因此 Image Generation Tool 内部设置 Provider Adapter。

其作用是：

> 将系统统一的图像生成参数转换为当前 Provider 所需的 API 参数，并将 Provider 返回结果转换为统一输出。

### 6.2 调用结构

```text
Concept Generation Skill
        ↓
统一业务参数
        ↓
Image Generation Tool
        ↓
Provider Adapter
        ↓
Provider API
```

例如：

```text
reference_strength = None # 尚未确认实际 API 参数，不强制传入
        ↓
Image Generation Tool
        ↓
Provider Adapter
        ↓
Provider-specific parameter
```

Skill 不需要知道最终 Provider 使用的是：

```text
strength
image_weight
control_strength
reference_weight
```

### 6.3 Adapter 职责

Provider Adapter 负责：

- Provider API 参数转换；
- text2img / img2img 能力映射；
- `reference_strength` 参数映射；
- 图片输入格式转换；
- Provider 响应解析；
- 生成结果路径标准化；
- Provider 能力检查；
- Provider 特定错误转换。

Provider Adapter 不负责：

- 判断当前应该使用 text2img 还是 img2img；
- 构建专业 Prompt；
- 选择概念方向；
- 修改 Agent State。

### 6.4 Provider Capability

不同 Provider 的能力不同，因此 Tool 需要能够判断：

```text
supports_text2img
supports_img2img
supports_multiple_reference_images
```

V1 至少需要判断：

```text
supports_img2img
```

逻辑示例：

```text
mode = img2img
        ↓
Provider supports img2img?
        ├── 是 → 调用 img2img
        └── 否 → 返回 capability 信息
```

是否回退到 `text2img`，由 Concept Generation Skill 根据 Tool 返回能力信息执行。

这样避免 Tool 层擅自改变业务生成模式。

### 6.5 V1 实现复杂度

Provider Adapter 是逻辑抽象，不要求 V1 一开始设计复杂的继承体系。

如果 V1 只接一个图像 Provider，可以直接在：

```text
image_generation.py
```

内部实现：

```python
def _build_provider_params(...):
    ...
```

后续接入多个 Provider 时，再扩展为：

```text
providers/
├── base.py
├── provider_a.py
└── provider_b.py
```

V1 不为了未来扩展提前创建复杂目录结构。

## 7. Image Generation 调用流程

### 7.1 text2img

```text
Concept Generation Skill
        ↓
构建 Prompt
        ↓
mode = text2img
        ↓
Image Generation Tool
        ↓
Provider Adapter
        ↓
Image Provider
        ↓
image_url
        ↓
Skill 组合 images 结果
```

### 7.2 img2img

```text
Concept Generation Skill
        ↓
构建 Prompt
+
site_images
+
reference_strength
        ↓
mode = img2img
        ↓
Image Generation Tool
        ↓
Provider Adapter
        ↓
Image Provider
        ↓
image_url
        ↓
Skill 组合 images 结果
```

其中：

```text
site_images
```

在 Tool 接口中映射为：

```text
reference_images
```

即：

```text
Agent State:
site_images

        ↓ Skill

Tool Input:
reference_images
```

两者属于不同层级的命名，不冲突。

## 8. Image Generation Fallback

当 Skill 请求：

```text
mode = img2img
```

但出现以下情况：

- `reference_images` 为空；
- 图片文件无效；
- Provider 不支持 img2img；
- Provider 的参考图调用失败；

V1 可以回退到：

```text
text2img
```

完整逻辑：

```text
请求 img2img
      ↓
检查 reference_images
      ↓
检查 Provider Capability
      ↓
是否可执行？
   ┌──────┴──────┐
   是            否
   ↓             ↓
img2img       text2img fallback
```

Fallback 不改变 Agent Graph。

Concept Generation Skill 仍然返回：

```text
concepts
images
```

其中 `images.mode` 记录实际执行模式，而不是最初请求模式。

例如：

```text
请求：
img2img

实际：
text2img

State:
mode = "text2img"
reference_images = []
```

这样 State 记录真实执行结果。

## 9. Tool 配置

Tool 相关系统配置统一由：

```text
src/config.py
```

管理。

V1 建议包含：

```text
WEB_SEARCH_PROVIDER
WEB_SEARCH_MAX_RESULTS

IMAGE_PROVIDER
IMAGE_MODEL

USE_IMG2IMG
REFERENCE_STRENGTH

TOOL_MAX_RETRIES
```

对应 `.env.example` 可包含：

```env
WEB_SEARCH_PROVIDER=
WEB_SEARCH_MAX_RESULTS=10

IMAGE_PROVIDER=qwen
IMAGE_MODEL=qwen-image-3.0-pro

USE_IMG2IMG=false

TOOL_MAX_RETRIES=2
```

配置职责：

| 配置项 | 作用 |
|---|---|
| `WEB_SEARCH_PROVIDER` | 指定搜索 Provider |
| `WEB_SEARCH_MAX_RESULTS` | 单次搜索默认结果数量 |
| `IMAGE_PROVIDER` | 指定图像生成 Provider |
| `IMAGE_MODEL` | 指定图像生成模型 |
| `USE_IMG2IMG` | 是否允许 Skill 使用 img2img |
| `REFERENCE_STRENGTH` | 非 V1 强制配置；Stage 5 确认实际 API 参数后再决定 |
| `TOOL_MAX_RETRIES` | Tool 技术调用最大重试次数 |

API Key 同样通过环境变量管理，不写入代码或 Agent State。

例如：

```env
TAVILY_API_KEY=
DASHSCOPE_API_KEY=
```

Qwen LLM / Qwen Image 共用 `DASHSCOPE_API_KEY`，不新增图像专用 Key。LLM 调用、JSON 解析与 Pydantic 校验由 `LLM_MAX_RETRIES` 控制；Tavily 技术重试继续由 `TOOL_MAX_RETRIES` 控制。

## 10. Tool 错误处理

### 10.1 错误分类

Tool 层主要处理技术执行错误：

```text
Timeout
Network Error
Rate Limit
Authentication Error
Provider Error
Invalid Response
Unsupported Capability
```

业务质量问题不属于 Tool Error。

例如：

```text
搜索结果不相关
→ Skill 问题 / Research Decision

概念不够好
→ Skill 问题

案例不充分
→ Agent Decision

API 超时
→ Tool Error
```

### 10.2 可重试错误

例如：

```text
Timeout
Temporary Network Error
部分 5xx
```

执行有限重试：

```text
Tool Call
    ↓
失败
    ↓
Retry <= TOOL_MAX_RETRIES
```

### 10.3 不可重试错误

例如：

```text
Invalid API Key
Unsupported Capability
Invalid Input
```

Tool 直接返回失败结果，不进行无意义重复调用。

### 10.4 Tool 失败返回

Tool 不建议直接抛出未经处理的 Provider 原始错误给 Skill。

建议统一成可识别的错误结构，例如：

```python
{
    "success": False,
    "error_type": "provider_unavailable",
    "message": "...",
    "retryable": False
}
```

成功时：

```python
{
    "success": True,
    "data": {...}
}
```

V1 可以根据实际代码复杂度选择使用：

```text
统一 Result Object
```

或：

```text
自定义 Exception + Skill 捕获
```

但对 Skill 应保持稳定错误语义。

## 11. Tool 与 Evaluation

Tool 本身主要评估：

```text
可调用性
稳定性
延迟
错误率
成本
Provider 能力
```

而不是直接评估专业结果质量。

### Web Search Tool

可记录：

```text
query
provider
result_count
latency
success / failure
```

### Image Generation Tool

可记录：

```text
provider
model
mode
reference_strength
latency
success / failure
```

专业质量评估仍由上层完成：

```text
案例是否相关
→ Case Research Evaluation

概念是否合理
→ Concept Evaluation

意向图是否符合概念
→ Concept / Image Evaluation
```

V1 不要求将所有 Tool telemetry 写入 Agent State。

如果后续需要系统级观测，可以通过 logging 或独立 tracing 系统记录。

## 12. Tool 边界

V1 不将以下能力定义为 Tool：

### Project Understanding

属于：

```text
parse_and_check
+
LLM
```

不是外部执行能力。

### SWOT Analysis

属于：

```text
Site Analysis Skill
```

不是 Tool。

### Case Filtering

属于：

```text
Case Research Skill
```

不是 Tool。

### Opportunity Identification

属于：

```text
Concept Generation Skill
```

不是 Tool。

### Prompt Construction

属于：

```text
Skill
```

Tool 只消费最终 Prompt。

### Image Analysis

V1 由多模态模型直接读取：

```text
site_images
```

不单独设计 Image Analysis Tool。

### Report Export

V1 输出：

```text
Markdown
```

不设置 PDF / PPT / DOCX Export Tool。

## 13. 与代码文件对应

| 文档内容 | 对应代码 |
|---|---|
| Web Search Tool | `src/tools/web_search.py` |
| Image Generation Tool | `src/tools/image_generation.py` |
| Tool 配置 | `src/config.py` |
| 环境变量示例 | `.env.example` |
| Case Research Skill | `src/skills/case_research.py` |
| Concept Generation Skill | `src/skills/concept_generation.py` |
| Tool 调用 Node | `src/agent/nodes.py` |

V1 如果只有单一 Provider，不提前创建：

```text
src/tools/providers/
```

当实际接入多个 Image Provider、且 Provider Adapter 已经出现明确复用需求时，再扩展目录。

## 14. Tools Design Summary

V1 Tool 层只保留两个核心外部能力：

```text
Web Search Tool
→ 获取外部案例和公开资料

Image Generation Tool
→ 生成概念意向图
```

整体关系：

```text
Agent / Graph
      ↓
Node
      ↓
Skill
      ↓
Tool
      ↓
Provider Adapter
      ↓
External API
```

其中 Provider Adapter 主要用于 Image Generation Tool，负责屏蔽不同图像模型之间的 API 差异。

各层职责为：

```text
Skill
→ 决定需要什么外部能力以及如何使用结果

Tool
→ 提供统一外部能力接口

Provider Adapter
→ 将统一参数适配为具体 Provider API

Provider
→ 实际执行搜索或图像生成
```

最终原则：

> **Skill 定义“要做什么”，Tool 定义“如何调用外部能力”，Provider Adapter 负责“如何适配不同供应商”，外部 Provider 负责“真正执行”。**

V1 不追求 Tool 数量和适配层复杂度，而优先保证 Tool 接口稳定、职责清晰、可替换，并能够支撑案例研究与概念意向图生成两个核心外部能力。
