# CONTEXT.md — ChemAI 领域术语表

> 从产品设计文档（20-39 号）提取的核心领域术语。按类别分组，每个术语提供中英文名称和一句话定义。

---

## 一、核心实体（Core Entities）

| 术语 | 英文 | 定义 |
|------|------|------|
| 学校 | School | 顶层组织容器，包含年级和教师，是多租户隔离的根节点 |
| 年级 | Grade | 学校下的第二层组织，如"高一""高二""高三" |
| 班级 | Class | 年级下的最小组织单元，学生归属和考试关联的基本单位 |
| 教师 | Teacher | 归属于学校的教学人员，通过任课关系与班级关联 |
| 学生 | Student | 核心实体，归属于班级，携带障碍画像、练习追踪和家长绑定码 |
| 家长 | Parent | 通过绑定码与学生建立亲子关联，接收通知和报告 |
| 统一账户 | Account | 所有用户的登录凭证，通过角色字段区分教师/学生/家长身份 |
| 任课关系 | TeacherClassSubject | 教师与班级的多对多关联，标注是否为班主任 |

## 二、组织与权限（Organization & Permissions）

| 术语 | 英文 | 定义 |
|------|------|------|
| 组织链 | Organization Chain | 学校→年级→班级→学生的四级层级，所有数据查询沿此链路展开 |
| 多租户隔离 | Multi-Tenant Isolation | 通过组织链确保同校教师只能看到本校数据，家长只能看到绑定子女数据 |
| 教师入驻审批 | Teacher Onboarding Approval | 教师注册后的审核流程（待审核/已通过/已拒绝），控制登录权限 |
| 教师子角色 | Teacher Sub-Role | 系统管理员/教务管理员/学科组长/普通教师四个级别，控制功能权限范围 |

## 三、学习概念（Learning Concepts）

| 术语 | 英文 | 定义 |
|------|------|------|
| 知识点 | KnowledgePoint | 化学知识的基本单元（如"盐类水解""氧化还原反应"），带有分类、难度和考试频率 |
| 知识图谱 | Knowledge Graph | 知识点及其关联关系的网络，支撑出题推荐和诊断归因 |
| 学生障碍画像 | Student Barrier Profile | 每个学生的三维障碍分布 JSON（concept/reading/expression 占比和为 1） |
| 薄弱知识点 | Weak Knowledge Points | 学生频繁出错的知识点集合，由诊断引擎从错误作答中聚合提取 |
| 学习计划 | Learning Plan | 教师为学生制定的个性化干预方案，包含每日任务和练习题安排 |
| 掌握度 | Mastery Level | 通过连续正确次数衡量的知识点掌握程度 |

## 四、诊断概念（Diagnosis Concepts）

| 术语 | 英文 | 定义 |
|------|------|------|
| 三维障碍模型 | Three-Dimensional Barrier Model | 将学生错误归因为概念理解型(concept)、审题障碍型(reading)、表述障碍型(expression)三种 |
| 概念理解型 | Concept Barrier | 不理解底层化学概念和原理（如混淆摩尔与质量、不懂化学平衡本质） |
| 审题障碍型 | Reading Barrier | 读题不完整或落入题干陷阱（如漏看限定词、误读图表数据） |
| 表述障碍型 | Expression Barrier | 理解正确但表达不规范（如方程式少写条件、计算正确但漏写单位） |
| 主导障碍类型 | Dominant Barrier | 学生在三维分布中占比最高的障碍类型 |
| 障碍诊断配置 | BarrierConfig | 教师自定义的诊断阈值（概念/审题/表述各自连续错误触发次数、掌握标准） |
| 规则引擎初筛 | Rule Engine Pre-Classification | 基于关键词匹配的快速障碍初判（置信度 0.5-0.7），作为 LLM 诊断的前置环节 |
| LLM 深度诊断 | LLM Deep Diagnosis | 以教育心理学视角分析错误作答，输出障碍类型、置信度、推理和干预建议 |
| 置信度分级 | Confidence Tiering | ≥0.8 自动采纳 / 0.7-0.8 采纳但标记 / <0.7 建议人工复核 |
| 教师覆盖 | Teacher Override | 教师手动推翻 AI 诊断结果（教师指定类型占 90%，其余各 5%），记录操作日志 |
| 班级障碍分布 | Class Barrier Distribution | 全班学生按主导障碍类型的统计分布（concept/reading/expression 各多少人） |

## 五、题目与考试（Questions & Exams）

| 术语 | 英文 | 定义 |
|------|------|------|
| 考试记录 | ExamRecord | 一次考试/练习/作业的完整记录，关联班级、包含题目列表和错题统计 |
| 题目 | Question | 一道完整的化学试题，含正文、选项、答案、解析、知识点标签、难度、来源 |
| 学生作答 | StudentAnswer | 学生对一道题的单次作答记录，含作答内容、正误判定和障碍类型标签 |
| 题目类型 | Question Type | 单选(choice) / 填空(fill) / 计算(calc) / 实验(experiment) / 推断(inference) |
| 题目难度 | Difficulty | 简单(easy) / 中等(medium) / 困难(hard) / 竞赛(competition)，竞赛级不自动生成 |
| 题目来源 | Question Source | AI 生成 / 手动录入 / 日常练习 / OCR 导入，用于溯源和审核策略差异化 |
| 题库文件夹 | QuestionSet | 教师创建的题目组织容器，按知识点/考试分类管理 |
| 文件夹-题目关联 | QuestionSetItem | 题库文件夹与题目的多对多中间实体，含排序字段 |
| 历年真题库 | Historical Exam Bank | 全国卷(2008-2020, 143题) + 湖南卷(2021-2025, 107题)，作为 RAG 知识底座 |
| 变体题 | Variant Question | 基于指定蓝本题生成的同知识点、同难度变体（数值/物质/选项/题干/难度五维变体） |
| 出题工作台 | Exam Workbench | Vue 3 CDN 四 Tab 单页应用：AI生成 / 手动录入 / OCR扫描 / 考试管理 |
| 三层搜索策略 | Three-Tier Search | 真题检索：关键词匹配 → 向量召回补充 → 联网搜索兜底 |
| 考试生命周期 | Exam Lifecycle | Draft → AddingQuestions → Published → InProgress → Completed |
| 试卷导出 | Exam Export | Word (python-docx, A4 排版) / HTML 报告（含统计数据） |

## 六、Agent 概念（Agent Concepts）

| 术语 | 英文 | 定义 |
|------|------|------|
| Agent 对话系统 | Agent Dialogue System | ChemAI 的 AI 大脑，自然语言输入→意图理解→工具执行→结构化响应 |
| ReAct 模式 | ReAct Pattern | 思考(Thought)→选工具(Action)→执行→观察(Observation) 的循环推理模式 |
| v2 单 Agent | v2 Single-Agent | 当前主版本：30 个工具全量注入单个 ReAct Agent，LLM 自选工具，路由准确率 87% |
| v1 多 Agent | v1 Multi-Agent | 回退版本：Coordinator + Router + 6 Sub-Agent，路由准确率 ~75% |
| Persona | Persona | 四套角色配置（Teacher/Student/Tutor/Parent），通过 YAML 定义 system prompt 和工具白名单 |
| 教研助手 | Teacher Persona | 面向教师的 AI 分析助手，8 个数据工具为主，不含 tutoring |
| 化学助教-学生端 | Student Persona | 面向学生的苏格拉底式辅导，7 个 tutoring 工具，禁止直接给答案 |
| 化学助教-通用 | Tutor Persona | 默认 Persona，兼具辅导和出题能力，6 个工具 |
| 家长助手 | Parent Persona | 面向家长的学情报告助手，2 个工具，通俗语言、隐私保护、不制造焦虑 |
| Gateway 意图分类器 | Gateway Intent Classifier | LLM 优先 + 关键词兜底的双路径分类，将请求分为 chat（进入 Agent）或 navigate（快捷跳转） |
| Guard 护栏层 | Guard Layer | 四层安全防护：前置条件检查→调用次数限制→去重检查→审批门控 |
| 审批门控 | Approval Gate | 破坏性操作（布置练习、删除题库）需教师确认后方可执行 |
| Planner 规划器 | Planner | 将复杂教学目标的自然语言描述拆解为结构化执行步骤（最多 6 步，含依赖关系） |
| PlanStep | PlanStep | 单个执行步骤：技能名、参数、依赖步骤、描述、状态（pending→running→completed/failed） |
| SSE 事件协议 | SSE Event Protocol | Agent 执行过程转为结构化事件流：phase / tool_call / tool_result / text / component / navigate / done |
| 三层记忆 | Three-Layer Memory | 工作记忆（20 条滑动窗口）+ 情景记忆（本次对话关键事件）+ 学生档案（跨请求持久） |
| 三层上下文裁剪 | Three-Layer Context Pruning | 消息超 30 条时：最近 6 条无条件保留 + 教学关键词命中保留 + 被丢弃 ≥10 条时 LLM 摘要 |
| 对话检查点 | Conversation Checkpoint | 通过 LangGraph AsyncSqliteSaver 持久化到 SQLite，支持中断恢复和多轮对话 |
| 长期记忆 | Long-Term Memory | 跨会话持久化：学生诊断历史（最近 5 条）+ 教师偏好（教学风格、难度偏好） |
| MCP 工具服务器 | MCP Tool Server | 独立的 16 工具 API 端点，供外部系统集成和定时任务调用（与 Agent 工具分工） |
| 审计日志 | Audit Log | JSONL 格式记录所有技能执行，环形缓冲区 100 条 + 磁盘追加，敏感字段自动脱敏 |
| 依赖注入容器 | Dependency Injection Context | Agent 运行上下文对象（student_id, student_profile, persona, episodic, provider_name） |

## 七、OCR 概念（OCR Concepts）

| 术语 | 英文 | 定义 |
|------|------|------|
| 答题卡 OCR 批改 | Answer Sheet OCR Grading | 教学工具链入口：拍照/上传答题卡→OCR识别→LLM批改→结果入库→触发诊断 |
| 上传会话 | UploadSession | 追踪单次文件上传全生命周期的实体，状态机 10 个状态 |
| OCR 任务 | OCRTask | 单张答题卡的识别与批改任务，状态：pending→processing→done/failed |
| 十步批改管线 | 10-Step Grading Pipeline | 批量上传→OCR识别→学生信息提取→答案来源选择→LLM批改→教师确认→保存→诊断→统计→报告 |
| 三引擎降级 | Three-Engine Degradation | PDF→MinerU优先、图片→百度OCR优先、失败→VLM多模态模型兜底 |
| 百度 OCR | Baidu OCR | 主力 OCR 引擎：doc_analysis(预览+公式)、correct_edu(批改)、paper_cut_edu(切题) |
| MinerU | MinerU | 本地 PDF 解析引擎，化学式 LaTeX 提取优于百度 OCR |
| VLM 降级 | VLM Fallback | 多模态视觉模型（GLM-4V/MiMo/Qwen-VL-OCR）作为 OCR 最终兜底 |
| 答案来源选择 | Answer Source Selection | 三级优先级：题库匹配（有考试ID时）→教师录入→LLM自判（后续版本） |
| 批改结果 | Grading Result | 逐题判定（题号、学生答案、标准答案、正误、理由）+ 汇总统计 |
| APScheduler 轮询 | APScheduler Polling | 5 秒间隔扫描 pending 任务并拾取执行，替代 WebSocket 的方案 |
| OAuth Token 管理 | Baidu Auth Token | 内存缓存共享、300 秒安全边距、30 天有效期 |

## 八、复习概念（Review Concepts）

| 术语 | 英文 | 定义 |
|------|------|------|
| 间隔复习 | Spaced Repetition | 基于艾宾浩斯遗忘曲线的错题定时复习机制 |
| 复习任务 | ReviewTask | 每道错题自动创建的复习计划，5 级递进（1/3/7/14/30 天后→已掌握） |
| 复习历史 | ReviewHistory | 记录每次复习的级别、日期和结果（答对升级/答错降级），追踪遗忘曲线 |
| 最近发展区 | ZPD (Zone of Proximal Development) | 自适应练习引擎的核心理论：在学生当前水平和潜在水平之间选题 |
| 自适应练习 | Adaptive Practice | 根据学生障碍类型和 ZPD 动态生成个性化练习题（barrier→question 策略矩阵） |
| 错题强化训练 | Wrong-Question Reinforcement | 针对高频错题的变式训练子系统，含创建训练→提交→分析闭环 |

## 九、安全审核（Safety Audit）

| 术语 | 英文 | 定义 |
|------|------|------|
| 四维安全审核 | Four-Dimensional Safety Audit | AI 生成题目的四维度化学正确性校验 |
| 系数配平 | Coefficient Balancing | 审核维度1：方程式两侧各元素原子数是否相等（自定义算法保证 100% 准确） |
| 反应条件审核 | Reaction Condition Audit | 审核维度2：反应条件是否正确标注（加热、催化剂、压强等） |
| 产物稳定性 | Product Stability | 审核维度3：给定条件下产物是否热力学/动力学可行 |
| 分子结构审核 | Molecular Structure Audit | 审核维度4：有机分子结构式是否正确（通过 RDKit 验证） |
| 审核报告 | AuditReport | 综合判定（passed/warning/blocked）+ 四维度各自结果 + 详细说明 + 审核耗时 |
| 陷阱提示 | Trap Hint | 根据题目知识点自动生成的教学提示（如"盐类水解：注意区分水解与电离"） |

## 十、通知与家校（Notification & Home-School）

| 术语 | 英文 | 定义 |
|------|------|------|
| 亲子绑定 | Student-Parent Binding | 通过 6 位绑定码建立学生与家长的关联，支持多子女绑定 |
| 家长通知 | ParentNotification | 推送给家长的消息：学习报告/预警提醒/教师消息，含已读状态 |
| 学情预警 | Warning Log | 四类自动监控预警：连续未登录、成绩下滑、高错误率（知识点级）、新障碍出现 |
| 三端通知状态 | Tri-Notification State | 每条预警追踪：是否已通知教师/是否已通知家长/是否已通知学生 |
| 周报 | Weekly Report | LLM 生成的 200 字自然语言学情总结，家长端使用通俗语言、鼓励为主 |
