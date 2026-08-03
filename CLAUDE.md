# CLAUDE.md — ChemAI 智辅化学

> AI 编程助手的项目行为准则。精简、可执行、保持更新。

---

## 一、项目背景

ChemAI（智辅化学）是一个 **AI 驱动的中学化学教学辅助平台**，目标用户为中国初中和高中化学教师、学生及家长。

### 核心功能

| 模块 | 说明 |
|------|------|
| AI Agent 对话系统 | 自然语言驱动的教学助手，4 套 Persona（教师/学生/家长/助教）|
| 出题工作台 | AI 生成 + 手动录入 + OCR 扫描 + 考试管理，四 Tab 单页应用 |
| 四维审核引擎 | AI 生成题目的科学性/难度匹配/知识点覆盖/区分度校验 |
| 障碍诊断引擎 | 三维障碍模型（概念/审题/表述）+ 6 类迷思概念归类 |
| 题库管理与考试生命周期 | draft → published → in_progress → grading → completed → archived |
| 学生练习与错题本 | 自适应练习 + 间隔复习 + 最近发展区（ZPD）选题 |
| 家长端 | 学情周报 + 预警通知 + 亲子绑定 |

### 技术栈

| 层 | 选择 | 版本 |
|----|------|:---:|
| Web 框架 | FastAPI + Uvicorn | 0.109+ |
| ORM + 迁移 | SQLAlchemy + Alembic | 2.0 / 1.13 |
| 数据库 | SQLite + WAL 模式（生产可选 MySQL）| — |
| 向量检索 | ChromaDB（嵌入式）| 0.4+ |
| Agent 框架 | LangGraph `create_react_agent` | ≥0.2 |
| LLM Provider | 通义千问 DashScope API（主力）/ MiMo / DeepSeek | — |
| 前端 | Vanilla JS + Vue 3 CDN + KaTeX | — |
| 测试 | Pytest | 8.0+ |

---

## 二、行为准则（4 条核心原则）

### 原则 1：先思考再编码

- 开始实现前，**明确陈述你的假设**
- 不确定时**主动发问**，不做猜测
- 如果需求模糊，先写一个结构化计划再动手

### 原则 2：简单优先

- **只写解决问题所需的最少代码**
- 不过度设计、不提前抽象
- YAGNI（You Aren't Gonna Need It）——当下不需要的，就不要写

### 原则 3：手术式修改

- **只触及必须修改的代码**，不顺手重构无关模块
- **匹配已有代码风格**——包括命名、缩进、注释习惯
- 修改后确保存量测试全部通过

### 原则 4：目标驱动执行

- 将每个任务转化为**可验证的验收目标**
- 写完代码后立刻验证：测试通过了吗？行为符合预期吗？
- 如果无法验证，任务就没有完成

---

## 三、项目特定规范

### 3.1 通用规范

- **所有代码注释和文档使用中文**
- Python 代码遵循 **PEP 8**（4 空格缩进、88 字符行宽）
- 数据库模型使用 **SQLAlchemy ORM** 声明式映射
- API 遵循 **RESTful** 设计（资源命名用复数名词、HTTP 动词语义化）
- 采用 **TDD（测试驱动开发）**：先写测试 → 最小实现 → 重构

### 3.2 化学领域规范

- **化学方程式使用 LaTeX 格式**：`$...$` 包裹（如 `$H_2O$`、`$Fe^{3+}$`）
- 箭头：`\rightarrow`（单向）、`\rightleftharpoons`（可逆）、`\xrightarrow{条件}`（带条件）
- **所有 AI 生成内容须经审核引擎校验后方可输出**
- 方程式配平使用确定性算法（100% 准确），不使用 LLM

### 3.3 代码质量

- 所有函数签名必须标注参数和返回值类型
- API 输入输出一律使用 Pydantic 模型，不裸传 dict
- 使用 `app/core/enums.py` 中的枚举类，不硬编码字符串
- 通过 `app/config.py` 读取所有环境变量，不直接 `os.getenv()`

---

## 四、标准开发流程（工具链）

```
思考层 ──→ 规格层 ──→ 实现层 ──→ 质量层
  │           │          │          │
  │        OpenSpec     TDD       Evals
  │           │          │          │
  ▼           ▼          ▼          ▼
Gstack      /opsx       RED      L1 单元
          :propose     GREEN     L2 集成
          :apply      REFACTOR   L3 Golden
          :archive               基线对比
```

### 4.1 思考层（Gstack）

在做任何非 trivial 的变更前，先停下来思考：

| 命令 | 用途 |
|------|------|
| `/office-hours` | 向领域专家（AI 模拟）咨询方案 |
| `/plan-ceo-review` | 从 CEO 视角审视优先级和资源 |
| `/plan-eng-review` | 从工程视角审视可行性和架构 |

### 4.2 规格层（OpenSpec）

```
/opsx:propose  →  创建变更提案（specs/ + design/ + tasks/）
/opsx:apply    →  按 tasks 逐项实现
/opsx:archive  →  归档完成变更
```

任何非 trivial 的功能修改都走这个流程。`openspec/` 目录下管理所有活跃变更和规格。

### 4.3 实现层（TDD）

1. **RED**（写测试）— 先写 pytest，定义预期行为
2. **GREEN**（Claude 生成）— 生成最小实现，让测试通过
3. **REFACTOR**（重构）— 消除重复、改善结构，测试必须保持绿

TDD 内嵌在 `/opsx:apply` 循环中。写测试 → 生成代码 → 跑测试 → 重构 → 再跑测试。

### 4.4 质量层（Evals）

| 层级 | 内容 | 通过标准 |
|:--:|------|:--:|
| L1 单元测试 | 纯函数、模型、工具函数 | 覆盖率 ≥ 95% |
| L2 集成测试 | API 端点、Agent 工具链、数据库 | 通过率 ≥ 90% |
| L3 Golden 评测 | 100 条化学场景 Golden 数据集 | 准确率 ≥ 70% |
| 基线对比 | 每轮变更后 vs 基线得分 | 劣化 > 5% 阻断合并 |

### 4.5 流程层（Gstack）

| 命令 | 用途 |
|------|------|
| `/review` | 代码审查 |
| `/cso` | 安全审查（Chief Security Officer）|
| `/qa` | 质量保证检查 |
| `/ship` | 发布前最终确认 |
| `/retro` | 回顾总结 |
| `/investigate` | 问题调查 |

### 4.6 骨架层（Git）

| 命令 | 用途 |
|------|------|
| `branch` | 每个变更独立分支 |
| `commit` | 原子化提交（一个 commit = 一个逻辑变更）|
| `tag` | 通过全量评测后打 tag 标记质量节点 |
| `merge` | 合并前确保所有测试通过 |
| `revert` | 快速回滚 |
| `push` | 不强推、不跳过 hooks |

---

## 五、项目结构

```
chemai-backend/
├── app/                          # 主应用
│   ├── main.py                   # FastAPI 入口
│   ├── config.py                 # 环境变量集中管理
│   ├── api/v1/                   # REST 端点
│   ├── api/mcp/                  # MCP 工具服务器
│   ├── models/                   # SQLAlchemy ORM 模型
│   ├── schemas/                  # Pydantic 请求/响应模型
│   ├── services/                 # 业务逻辑层
│   ├── middleware/               # FastAPI 中间件（CORS、日志、限流等）
│   ├── utils/                    # 通用工具函数
│   ├── core/                     # 枚举、异常层次、安全
│   ├── infrastructure/           # 数据库连接、调度器
│   ├── agent/                    # Agent 引擎（engine、gateway、guard、planner、memory、context、sse、audit）
│   ├── chem_skills/              # 化学技能引擎实现（底层）
│   ├── llm/                      # LLM Provider 抽象层
│   └── knowledge/                # 知识图谱 + ChromaDB 向量检索
│
├── agent/                        # Agent 配置与工具定义
│   ├── tools/                    # 工具元数据注册
│   ├── channel/                  # 多渠道适配（Web / 微信 / 钉钉）
│   └── prompts/                  # Persona 提示词模板
│
├── chem_skills/                  # 化学技能引擎（顶层编排）
│   ├── chemistry_exam/engine/    # 出题引擎
│   ├── chemistry_exam/prompts/   # 出题提示词
│   ├── chemistry_diagnosis/engine/  # 诊断引擎
│   ├── chemistry_parser/engine/  # 化学式解析引擎
│   ├── chemistry_memory/         # 记忆与复习引擎
│   ├── chemistry_notification/   # 通知引擎
│   └── chemistry_improvement/    # 提升建议引擎
│
├── frontend/                     # 前端资源
│   ├── pages/                    # HTML 页面（教师端、学生端、家长端）
│   ├── js/                       # JavaScript 模块
│   ├── m/                        # 移动端（Mobile）适配页
│   └── css/                      # 样式表
│
├── data/                         # 静态数据
│   ├── exam_questions/           # 历年真题 JSON 文件
│   ├── knowledge_graph/          # 知识图谱 JSON 定义
│   └── chromadb/                 # ChromaDB 持久化向量库
│
├── tests/                        # 测试
│   ├── unit/                     # 单元测试
│   ├── integration/              # 集成测试
│   └── golden/                   # Golden 数据集评测
│
├── alembic/                      # 数据库迁移
│   ├── versions/                 # 迁移脚本
│   ├── env.py                    # Alembic 环境配置
│   └── script.py.mako            # 迁移模板
│
├── docker/                       # Docker 配置
├── scripts/                      # 运维脚本
├── CLAUDE.md                     # 本文件（项目行为准则）
└── CONTEXT.md                    # 领域词汇表
```

---

## 六、关键设计约束

1. **不做跨学科**：当前只覆盖初中和高中化学
2. **不做多 Agent 协作**：v2 主版本为单 Agent ReAct 模式
3. **不自动发布考试**：教师确认后方可发布
4. **不自动发送诊断给学生**：需教师确认后手动推送
5. **竞赛级题目不自动生成**：仅支持手动录入
6. **不做实时诊断**：当前仅支持批量诊断（单次 ≤10 条）
7. **破坏性操作需审批**：`assign_adaptive_practice`、`delete_bank` 等需教师审批门控
8. **OCR 异步轮询而非 WebSocket**：简化部署，5s 间隔可接受
9. **SQLite 状态表而非消息队列**：MVP 简单性优先

---

## 七、常用命令

```bash
# 开发服务器
uvicorn app.main:app --reload --port 8000

# 数据库迁移
alembic revision --autogenerate -m "描述"
alembic upgrade head

# 运行测试
pytest tests/unit -v
pytest tests/integration -v
pytest tests/golden -v

# Agent 测试
pytest -k "agent" -v

# Docker
docker compose up -d
```

---

## 八、参考资料

- **产品设计文档**：`D:\人工智能\01大模型应用方案专家\化学\`（01-19 号，共 19 份）
- **总体开发方案**：项目根目录 `00-总体开发方案.md`
- **OpenSpec 规格**：`openspec/specs/`（主规格）、`openspec/changes/`（变更提案）
- **领域术语**：`CONTEXT.md`（本目录）
