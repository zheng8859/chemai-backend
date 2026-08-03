# CONTEXT.md — ChemAI 领域词汇表

> 从产品设计文档（01-19 号）及项目开发方案中提取的核心领域术语。按类别分组，每个术语提供中英文名称和一句话定义。

---

## 一、核心实体（Core Entities）

| 术语 | 英文 | 定义 |
|------|------|------|
| 学校 | School | 顶层组织容器，包含年级和教师，是多租户隔离的根节点 |
| 年级 | Grade | 学校下的第二层组织，如"高一""高二""高三" |
| 班级 | Class | 年级下的最小组织单元，学生归属和考试关联的基本单位 |
| 教师 | Teacher | 归属于学校的教学人员，通过任课关系与班级关联，含子角色（系统管理员/教务管理员/学科组长/普通教师）|
| 学生 | Student | 核心实体，归属于班级，携带障碍画像、练习追踪和家长绑定码 |
| 家长 | Parent | 通过 6 位绑定码与学生建立亲子关联，接收学情报告和预警通知 |
| 统一账户 | Account | 所有用户通过手机号登录的统一凭证，通过角色字段区分教师/学生/家长身份 |
| 任课关系 | TeacherClassSubject | 教师与班级的多对多关联，标注是否为班主任及所授学科 |

---

## 二、学习概念（Learning Concepts）

| 术语 | 英文 | 定义 |
|------|------|------|
| 障碍类型 | Barrier Type | 将学生错误归因为三种类型：概念理解型(concept)、审题障碍型(reading)、表述障碍型(expression) |
| 概念理解型 | Concept Barrier | 不理解底层化学概念和原理（如混淆摩尔与质量、不懂化学平衡本质）|
| 审题障碍型 | Reading Barrier | 读题不完整或落入题干陷阱（如漏看限定词、误读图表数据）|
| 表述障碍型 | Expression Barrier | 理解正确但表达不规范（如方程式少写条件、计算正确但漏写单位）|
| 障碍分布 | Barrier Distribution | 学生三维障碍的占比分布，总和为 1，如 `{concept: 0.5, reading: 0.3, expression: 0.2}` |
| 主导障碍类型 | Dominant Barrier | 在三维分布中占比最高的障碍类型，用于确定干预策略的优先级 |
| 知识点 | Knowledge Point | 化学知识的基本单元（如"盐类水解""氧化还原反应"），带有分类、难度和考试频率标签 |
| 知识图谱 | Knowledge Graph | 知识点及其先修/后修/相关关系的网络结构，支撑出题推荐和诊断归因 |
| 薄弱知识点 | Weak Knowledge Points | 学生频繁出错的知识点集合，由诊断引擎从错误作答中聚合提取 |
| 诊断 | Diagnosis | 对学生的错误作答进行障碍类型判定，规则引擎初筛（置信度 0.5-0.7）+ LLM 深度诊断（教育心理学视角）|
| 自适应练习 | Adaptive Practice | 根据学生障碍类型和最近发展区（ZPD）动态生成个性化练习题，采用 barrier→question 策略矩阵 |
| 练习会话 | PracticeSession | 一次自适应练习的完整记录，追踪针对的障碍类型、覆盖知识点、推送/正确题目数和状态（进行中/已/已弃） |
| 最近发展区 | ZPD (Zone of Proximal Development) | 在学生当前水平和潜在水平之间选题的学习理论，是自适应练习引擎的核心依据 |
| 间隔复习 | Spaced Repetition | 基于艾宾浩斯遗忘曲线的错题定时复习机制，5 级递进（1/3/7/14/30 天后→已掌握）|
| 掌握度 | Mastery Level | 通过连续正确次数衡量的知识点掌握程度 |

---

## 三、内容实体（Content Entities）

| 术语 | 英文 | 定义 |
|------|------|------|
| 试卷 | Exam Paper | 可复用的试卷模板，定义题目集合、分值、时限，状态：草稿→已发布→已归档 |
| 考试记录 | ExamRecord | 一次考试在某个班级的执行实例，引用试卷模板，独立状态：待开始→进行中→批改中→已完成→已归档(可取消) |
| 试卷-题目关联 | ExamPaperQuestion | 试卷与题目的多对多关联，含排序和该题在此试卷中的分值 |
| 题目 | Question | 一道完整的化学试题，含正文、选项、答案、解析、知识点标签、难度和来源 |
| 学生作答 | StudentAnswer | 学生对一道题的单次作答记录，含作答内容、正误判定和障碍类型标签 |
| 题库 | Question Set / Bank | 教师创建的题目组织容器，按知识点或考试分类管理，支持文件夹层级 |
| 历年真题库 | Historical Exam Bank | 全国卷 (2008-2020) + 湖南卷 (2021-2025)，共 250 道真题，作为 RAG 知识底座 |
| 变体题 | Variant Question | 基于指定蓝本题生成的同知识点、同难度变体（数值/物质/选项/题干/难度五维变体）|
| 周报 | Weekly Report | LLM 生成的 200 字自然语言学情总结，家长端使用通俗语言、鼓励为主 |
| 出题工作台 | Exam Workbench | Vue 3 CDN 四 Tab 单页应用：AI 生成 / 手动录入 / OCR 扫描 / 考试管理 |

---

## 四、诊断概念（Diagnosis Concepts）

### 4.1 迷思概念类别（Misconception Categories）

| 类别 | 英文 | 定义 |
|------|------|------|
| 化学平衡 | Chemical Equilibrium | 涉及平衡移动、勒夏特列原理、平衡常数计算等概念的常见误解 |
| 氧化还原 | Redox | 涉及化合价判断、氧化剂/还原剂识别、电子转移计算的常见误解 |
| 摩尔计算 | Mole Calculation | 涉及物质的量、摩尔质量、气体摩尔体积、物质的量浓度等计算的常见误解 |
| 有机化学 | Organic Chemistry | 涉及官能团识别、同分异构体、有机反应类型的常见误解 |
| 化学用语 | Chemical Notation | 涉及化学式书写、方程式配平、离子方程式书写的常见误解 |
| 物构知识 | Structure of Matter | 涉及原子结构、元素周期律、化学键与分子结构的常见误解 |

### 4.2 障碍类型 vs 迷思概念（正交关系）

障碍类型（Barrier Type）和迷思概念类别（Misconception Category）是一个 **正交的二维诊断框架**：

- **障碍类型回答"怎么错"**（错误的认知过程）：是概念没懂？还是审题粗心？还是表述不规范？
- **迷思概念类别回答"错在哪"**（错误的知识领域）：是化学平衡出了问题？还是氧化还原？还是摩尔计算？

两者组合形成一个 3×6 = 18 格的诊断矩阵，精确定位学生的错误根源。例如：一道化学平衡题目答错了，可能是「concept × 化学平衡」（真的不懂平衡原理），也可能是「reading × 化学平衡」（看漏了"恒温恒压"条件）。

### 4.3 诊断流程相关

| 术语 | 英文 | 定义 |
|------|------|------|
| 规则引擎初筛 | Rule Engine Pre-Classification | 基于关键词匹配的快速障碍初判（置信度 0.5-0.7），作为 LLM 诊断的前置环节 |
| LLM 深度诊断 | LLM Deep Diagnosis | 以教育心理学视角分析错误作答，输出障碍类型、迷思概念、置信度、推理和干预建议 |
| 置信度分级 | Confidence Tiering | ≥0.8 自动采纳 / 0.7-0.8 采纳但标记 / <0.7 建议人工复核 |
| 教师覆盖 | Teacher Override | 教师手动推翻 AI 诊断结果（教师指定类型占 90%，其余各 5%），记录操作日志 |
| 诊断来源 | Diagnosed By | 标记每道作答的障碍类型来自 ai_rule（规则引擎）/ ai_llm（LLM 深度诊断）/ teacher（教师覆盖） |
| 覆盖时间 | Diagnosis Overridden At | 教师手动覆盖诊断的时间戳，为空表示未被覆盖 |
| 障碍诊断配置 | BarrierConfig | 教师自定义的诊断阈值（概念/审题/表述各自连续错误触发次数、掌握标准）|
| 班级障碍分布 | Class Barrier Distribution | 全班学生按主导障碍类型的统计分布（concept/reading/expression 各多少人）|

---

## 五、题目与考试概念（Question & Exam Concepts）

### 5.1 题目类型（Question Types）

| 类型 | 英文 | 定义 |
|------|------|------|
| 选择题 | choice | 从选项中选择正确答案（单选/多选统一） |
| 填空题 | fill_blank | 在空白处填写正确答案（化学式、数值、方程式等）|
| 计算题 | calculation | 需要进行化学计算并写出过程的题目 |
| 方程式配平 | equation_balancing | 配平化学方程式，验证反应物与产物原子数守恒 |
| 实验探究 | experiment_inquiry | 涉及实验操作、现象分析、方案设计的题目 |

### 5.2 题目难度（Difficulty）

| 难度 | 英文 | 定义 |
|------|------|------|
| 简单 | easy | 基础概念和基本技能的直接应用 |
| 中等 | medium | 多个知识点的综合运用 |
| 困难 | hard | 需要深度理解和分析推理 |
| 竞赛 | competition | 竞赛级题目，仅支持手动录入，ZPD 不自动分配 |

### 5.3 四维审核（Four-Dimension Review）

| 维度 | 英文 | 定义 |
|------|------|------|
| 科学性 | Scientific Accuracy | 题目内容在化学原理上是否正确（含系数配平、反应条件、产物稳定性、分子结构四子维度）|
| 难度匹配 | Difficulty Matching | 题目难度是否与目标年级和知识点要求匹配 |
| 知识点覆盖 | Knowledge Coverage | 题目是否准确覆盖标注的知识点，不超纲不遗漏 |
| 区分度 | Discrimination | 题目是否能有效区分不同水平的学生 |

### 5.4 考试状态（Exam State）

```
draft → published → in_progress → grading → completed → archived
  ↓                                                      ↑
cancelled ────────────────────────────────────────────────┘
```

| 状态 | 英文 | 定义 |
|------|------|------|
| 草稿 | draft | 教师创建中，尚未发布，可自由编辑 |
| 已发布 | published | 已向班级发布，等待学生开始作答 |
| 进行中 | in_progress | 学生正在作答中 |
| 批改中 | grading | 作答截止，正在批改（OCR 或人工）|
| 已完成 | completed | 批改完毕，成绩和诊断已生成 |
| 已归档 | archived | 历史考试，仅可查看不可修改 |
| 已取消 | cancelled | 发布后被教师取消 |

---

## 六、Agent 概念（Agent Concepts）

| 术语 | 英文 | 定义 |
|------|------|------|
| 意图 | Intent | 用户输入的目标分类，当前支持 chat（进入 Agent 对话）和 navigate（快捷页面跳转）|
| 单 Agent | Single Agent (ReAct) | 基于 LangGraph `create_react_agent` 构建的单一推理 Agent，30 个工具全量注入，LLM 自选工具执行 |
| 工具 | Tool | Agent 可调用的能力单元，每个工具有独立的 docstring（何时用、执行逻辑、下一步、NOT for）、Persona 白名单和调用次数限制 |
| 角色 | Persona | 四套角色配置——教师(Teacher)、化学助教(Tutor)、学生(Student)、家长(Parent)，通过 YAML 定义 system prompt 和工具白名单 |
| 护栏状态 | Guard State | Agent 的四层安全防护：前置条件检查 → 调用次数限制 → 去重检查 → 审批门控，防止不当或危险操作 |
| 网关 | Gateway | LLM 优先 + 关键词兜底的双路径意图分类器，将请求路由到 Agent 对话或快捷页面跳转 |
| 规划器 | Planner | 将复杂教学目标的自然语言描述拆解为结构化执行步骤（最多 6 步，含依赖关系）|
| SSE 事件协议 | SSE Event Protocol | Agent 执行过程转为结构化事件流：phase / tool_call / tool_result / text / component / navigate / done |
| 三层记忆 | Three-Layer Memory | 工作记忆（20 条滑动窗口）+ 情景记忆（本次对话关键事件）+ 学生档案（跨请求持久）|
| 三层上下文裁剪 | Context Pruning | 消息超 30 条时：最近 6 条无条件保留 + 教学关键词命中保留 + 被丢弃 ≥10 条时 LLM 摘要 |
| 审批门控 | Approval Gate | 破坏性操作（布置练习、删除题库）需教师在 UI 确认后方可执行 |
| 审批请求 | ApprovalRequest | Agent 审批请求的结构化记录，含线程 ID、工具名、参数快照、状态（待审批/已通过/已拒绝/已过期）、审批人和超时 |
| MCP 工具服务器 | MCP Tool Server | 独立的工具 API 端点，供外部系统集成和定时任务调用 |

---

## 七、OCR 概念（OCR Concepts）

| 术语 | 英文 | 定义 |
|------|------|------|
| 上传会话 | Upload Session | 追踪单次文件上传全生命周期的实体，状态机 10 个状态（pending→processing→...→done/failed）|
| 预览 | Preview | 上传答题卡图片后、正式批改前的识别结果预览，教师可修正识别错误 |
| 试卷导入 | Exam Import | 通过 OCR 将纸质试卷/答题卡转为数字化题目和作答的过程 |
| 判卷 | Grading | 对答题卡进行 OCR 识别→LLM 批改→结果入库的完整流程，含 10 步批改管线 |
| 降级（Fallback） | Fallback | OCR 三引擎降级策略：PDF→MinerU 优先，图片→百度 OCR 优先，失败→VLM 多模态模型兜底 |
| 任务轮询 | Task Polling | APScheduler 5 秒间隔扫描 pending OCR 任务并拾取执行，替代 WebSocket 方案 |
| 答案来源选择 | Answer Source Selection | 三级优先级：题库匹配（有考试 ID 时）→ 教师录入标准答案 → LLM 自判 |
| 十步批改管线 | 10-Step Grading Pipeline | 批量上传→OCR 识别→学生信息提取→答案来源选择→LLM 批改→教师确认→保存→诊断→统计→报告 |

---

## 八、通知与家校（Notification & Home-School）

| 术语 | 英文 | 定义 |
|------|------|------|
| 亲子绑定 | Student-Parent Binding | 通过 6 位绑定码建立学生与家长的关联，支持一个家长绑定多个子女 |
| 学情预警 | Warning Log | 四类自动监控：连续未登录、成绩下滑、高错误率（知识点级）、新障碍出现 |
| 三端通知状态 | Tri-Notification State | 每条预警追踪：是否已通知教师/是否已通知家长/是否已通知学生 |
| 家长通知 | ParentNotification | 推送给家长的消息：学习报告/预警提醒/教师消息，含已读状态 |

---

## 九、安全审核（Safety Audit）

| 术语 | 英文 | 定义 |
|------|------|------|
| 系数配平 | Coefficient Balancing | 审核维度：方程式两侧各元素原子数是否相等（自定义算法保证 100% 准确）|
| 反应条件审核 | Reaction Condition Audit | 审核维度：反应条件是否正确标注（加热、催化剂、压强等）|
| 产物稳定性 | Product Stability | 审核维度：给定条件下产物是否热力学/动力学可行 |
| 分子结构审核 | Molecular Structure Audit | 审核维度：有机分子结构式是否正确（通过 RDKit 验证）|
| 审核报告 | AuditReport | 综合判定（passed/warning/blocked）+ 四维度各自结果 + 详细说明 |
| 陷阱提示 | Trap Hint | 根据题目知识点自动生成的教学提示（如"盐类水解：注意区分水解与电离"）|

---

## 十、补充索引

### 10.1 题目来源（Question Source）

| 来源 | 英文 | 定义 |
|------|------|------|
| AI 生成 | ai_generated | LLM 根据知识点和难度自动生成的题目 |
| 手动录入 | manual | 教师手动输入的题目 |
| 日常练习 | daily_practice | 从日常作业中收集的题目 |
| OCR 导入 | ocr_import | 从纸质试卷 OCR 识别导入的题目 |

### 10.2 教师子角色（Teacher Sub-Role）

| 角色 | 英文 | 权限范围 |
|------|------|------|
| 系统管理员 | admin | 全校管理、教师审批、系统配置 |
| 教务管理员 | academic_admin | 排课、考试安排、成绩管理 |
| 学科组长 | subject_lead | 题库审核、教研资源管理 |
| 普通教师 | teacher | 班级教学、出题、诊断 |

---

> **维护说明**：本文档随项目迭代持续更新。新增领域概念时，请按上述分类添加，每个术语保持"中英文名称 + 一句话定义"的格式。
