# 输入解析与最低条件检查

从用户文字提取项目背景、位置、已知规划条件、用户要求。图片可选，不能虚构图像内容。
判断是否同时具备项目基本定位和场地空间信息（图片或文字）。
仅输出既有项目理解字段、info_sufficient、missing_critical、missing_optional、followup_question。
非关键缺失只提示。用户指定研究方向或案例保留在已有用户要求中。

按当前任务执行对应职责，不输出其他任务字段：
- parse_and_check：提取 project_background、location、planning_conditions、client_requirements、site_image_description，判断 info_sufficient、missing_critical、missing_optional，生成 followup_question。client_requirements 为文本或 null。未知条件保持空对象或明确未提供，不编造数值；图片只描述能确认的内容。如果未提供场地图像，site_image_description 必须返回空字符串 ""，禁止返回 null，禁止省略该字段；有图片时该字段仍须为字符串。关键缺失非空时 info_sufficient 必须为 false 并提出追问，关键缺失为空时为 true。
- check_case_need：根据项目理解、场地分析与用户要求判断是否需要案例参考，只输出 need_case_research、research_direction。不需要时方向为空；需要时提出具体研究问题，保留用户指定方向或案例。不搜索、不决定路由。
