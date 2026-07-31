# CLAUDE.md — ChemAI 智辅化学

> AI 编程助手的项目上下文。精简、可执行、保持更新。

## 一、项目定位

ChemAI（智辅化学）是一个 AI 驱动的化学教学辅助平台，面向**教师 / 学生 / 家长**三端。核心能力：OCR 答题卡批改 → 障碍诊断 → 自适应练习 → 间隔复习，形成教学闭环。Agent 系统（30 个工具、4 套 Persona）通过自然语言串联所有业务能力。

- **产品设计文档**：`D:\人工智能\01大模型应用方案专家\化学\`（20-39 号文档）
- **开发方案**：项目根目录 `00-总体开发方案.md`
- **OpenSpec 规格**：`openspec/` 目录

## 二、技术栈速查

| 层 | 选择 | 版本 |
|----|------|:---:|
| Web 框架 | FastAPI + Uvicorn | 0.109 / 0.27 |
| ORM + 迁移 | SQLAlchemy + Alembic | 2.0 / 1.13 |
| 数据库 | SQLite + WAL 模式（生产可选 MySQL） | — |
| Agent 框架 | LangGraph `create_react_agent` | ≥0.2 |
| 向量检索 | ChromaDB（嵌入式） | 0.4.22 |
| 化学配平 | 自定义系数平衡算法 + RDKit | 2024.3 |
| 调度 | APScheduler | 3.10 |
| 浏览器工具 | Playwright | ≥1.40 |
| 前端 | Vanilla JS + Vite + Tailwind + KaTeX | — |
| 桌面打包 | pywebview + PyInstaller | 6.x |
| 测试 | Pytest | 8.0 |
| 容器化 | Docker + Compose（python:3.11-slim） | — |

**LLM Provider 三级 Fallback**：MiMo-V2.5（视觉+联网）→ 通义千问 qwen-turbo（最高可用率 99.9%）→ DeepSeek-V4-Flash（化学满分、成本最低）。通过统一 `ChatOpenAI` 兼容接口访问。

**OCR 管道三引擎降级**：百度 OCR（主力）↔ MinerU（PDF 本地）→ VLM（GLM-4V / MiMo 兜底）。

## 三、项目结构

```
chemai-backend/
├── app/
│   ├── main.py              # FastAPI 入口
│   ├── config.py            # 环境变量集中管理
│   ├── api/v1/              # REST 端点（按模块分文件）
│   ├── api/mcp/             # MCP 工具服务器（16 个工具，供外部系统调用）
│   ├── models/              # SQLAlchemy ORM（23 个实体）
│   ├── schemas/             # Pydantic 请求/响应模型
│   ├── services/            # 业务逻辑层
│   ├── agent/               # Agent 系统（v2 单 Agent 主版本，v1 多 Agent 回退）
│   │   ├── engine.py        # ReAct Agent 工厂
│   │   ├── tools/           # 30 领域工具 + 5 浏览器工具
│   │   ├── persona/         # 4 套 Persona YAML 配置
│   │   ├── gateway.py       # Gateway 意图分类器（LLM + 关键词兜底）
│   │   ├── guard.py         # Guard 四层安全护栏
│   │   ├── planner.py       # PlanGenerator 目标拆解
│   │   ├── context.py       # 三层上下文裁剪
│   │   ├── memory.py        # 三层记忆架构
│   │   ├── sse.py           # SSE 事件协议适配器
│   │   └── audit.py         # 审计日志（JSONL）
│   ├── chem_skills/         # 10 个化学技能引擎（Agent 工具底层实现）
│   ├── llm/                 # LLM Provider 抽象层 + 多路回退
│   ├── knowledge/           # 知识图谱 + ChromaDB 向量检索 + 真题库
│   ├── infrastructure/      # 数据库连接、调度器、JWT 安全
│   └── core/                # 枚举、异常层次、常量
├── alembic/                 # 数据库迁移
├── tests/                   # unit / integration / golden
├── data/                    # 真题库、知识图谱、ChromaDB、审计日志
├── CLAUDE.md                # 本文件
└── CONTEXT.md               # 领域术语表
```

## 四、开发流程

### 4.1 规格驱动（OpenSpec）

```
/opsx:propose  →  创建变更提案（specs/ + design/ + tasks/）
/opsx:apply    →  按 tasks 逐项实现
/opsx:archive  →  归档完成变更
```

任何非 trivial 的功能修改都走这个流程。`openspec/` 目录下管理所有活跃变更和规格。

### 4.2 TDD 循环

1. **RED** — 你先写测试（pytest），定义预期行为
2. **GREEN** — Claude 生成最小实现，让测试通过
3. **REFACTOR** — 消除重复、改善结构，测试必须保持绿

TDD 内嵌在 `/opsx:apply` 循环中。写测试 → 生成代码 → 跑测试 → 重构 → 再跑测试。

### 4.3 Git 纪律

- **原子化 commit**：一个 commit = 一个逻辑变更
- **分支隔离**：每个变更独立分支
- **tag 标记质量节点**：通过全量评测后打 tag
- **不强推、不跳过 hooks**

### 4.4 质量门禁

| 层级 | 内容 | 通过标准 |
|:--:|------|:--:|
| L1 单元测试 | 纯函数、模型、工具函数 | 覆盖率 ≥ 95% |
| L2 集成测试 | API 端点、Agent 工具链、数据库 | 通过率 ≥ 90% |
| L3 Golden 评测 | 100 条化学场景 Golden 数据集 | 准确率 ≥ 70% |
| 基线对比 | 每轮变更后 vs 基线得分 | 劣化 > 5% 阻断合并 |

## 五、编码规范

### 5.1 Python

- **类型注解**：所有函数签名必须标注参数和返回值类型
- **异步优先**：IO 操作使用 `async/await`（FastAPI 原生 async）
- **Pydantic 模型**：API 输入输出一律用 Pydantic 定义，不裸传 dict
- **错误处理**：使用 `app/core/errors.py` 中定义的异常层次，不抛裸 Exception
- **环境变量**：所有配置通过 `app/config.py` 读取，不直接 `os.getenv()`

### 5.2 Agent 工具

- **工具设计规范**：每个工具 docstring 必须包含：何时用、执行逻辑、下一步、NOT for（排除的误用场景）
- **元数据注册**：新增工具必须在 `agent/tools/registry.py` 的 `TOOL_META` 中注册（persona 白名单 + call_limit）
- **Persona 过滤**：工具对 Persona 的可见性 = YAML 配置白名单 ∩ TOOL_META 注册
- **Guard 包装**：所有工具调用经过 Guard 四层检查（前置条件 → 限流 → 去重 → 审批门控）

### 5.3 数据模型

- **23 个实体**，5 个枚举类型（`BarrierType`, `ExamType`, `QuestionSource`, `AuditStatus`, `Difficulty`）
- **枚举优先**：涉及枚举字段一律使用 `app/core/enums.py` 中的枚举类，不硬编码字符串
- **JSON 字段**：复杂嵌套数据（障碍画像、错题统计、审核报告）使用 SQLAlchemy `JSON` 类型
- **多租户隔离**：数据查询沿"学校→年级→班级"链路，不跨校查询

### 5.4 化学领域特殊规范

- **化学式渲染**：所有化学式使用 LaTeX `$...$` 包裹（如 `$H_2O$`、`$Fe^{3+}$`）
- **方程式箭头**：`\rightarrow`（单向）、`\rightleftharpoons`（可逆）、`\xrightarrow{条件}`（带条件）
- **审核优先**：AI 生成的题目必须经过四维安全审核（系数配平 / 反应条件 / 产物稳定性 / 分子结构）
- **确定性配平**：方程式配平使用自定义系数平衡算法（100% 准确），不使用 LLM 配平（~80% 准确）

## 六、关键设计约束

1. **不做跨学科**：当前只覆盖高中化学
2. **不做多 Agent 协作**：v2 主版本为单 Agent ReAct，v1 多 Agent 仅保留为 fallback
3. **不自动发布考试**：教师确认后方可发布
4. **不自动发送诊断给学生**：需教师确认后手动推送
5. **竞赛级题目不自动生成**：仅支持手动录入
6. **不做实时诊断**：当前仅支持批量诊断（单次 ≤10 条）
7. **Agent 审批门控**：`assign_adaptive_practice`、`delete_bank` 等破坏性操作需教师审批
8. **OCR 异步轮询而非 WebSocket**：简化部署，5s 间隔可接受
9. **SQLite 状态表而非消息队列**：MVP 简单性优先，后续可迁移到 Celery + Redis

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
pytest tests/golden -v  # Golden 数据集评测

# Agent 测试
pytest -k "agent" -v

# Docker
docker compose up -d
```

## 八、参考资料

- **产品设计文档**：`D:\人工智能\01大模型应用方案专家\化学\`（20-39 号，共 20 份）
- **开发方案**：`00-总体开发方案.md`（工具链、流程、质量体系）
- **OpenSpec 规格**：`openspec/specs/`（主规格）、`openspec/changes/`（变更提案）
- **领域术语**：`CONTEXT.md`（本目录）
