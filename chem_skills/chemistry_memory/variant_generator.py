"""变式题生成引擎 — LLM prompt 构造的纯函数。

设计文档 29 号 §7.5：
    - 同知识点、同难度、不同题面/条件/数据
    - 一次调用生成 3 道变式题
    - prompt 明确要求返回 JSON 数组
"""


def build_variant_prompt(
    question: dict,
    count: int = 3,
) -> str:
    """构造 LLM prompt 用于生成变式题。

    Args:
        question: 原题信息，包含 content, answer, knowledge_points, difficulty,
                  question_type, options（如有）。
        count: 需要生成的变式题数量，默认 3。

    Returns:
        可直接发送给 LLM 的完整 prompt 字符串。
    """
    q_type = question.get("question_type", "choice")
    difficulty = question.get("difficulty", "medium")
    kps = question.get("knowledge_points", [])
    original_content = question.get("content", "")
    original_answer = question.get("answer", "")

    kp_str = "、".join(kps) if kps else "未指定"

    if q_type == "choice":
        return _build_choice_variant_prompt(
            original_content, original_answer, difficulty, kp_str, count
        )
    else:
        return _build_generic_variant_prompt(
            original_content, original_answer, difficulty, kp_str, q_type, count
        )


def _build_choice_variant_prompt(
    content: str,
    answer: str,
    difficulty: str,
    kp_str: str,
    count: int,
) -> str:
    """构造选择题变式题的 prompt。"""
    return f"""你是一位经验丰富的中学化学教师，请为以下题目生成 {count} 道变式题。

**原题信息：**
- 知识点：{kp_str}
- 难度：{difficulty}
- 题型：选择题（4 选项）

**原题内容：**
{content}

**原题答案：**
{answer}

**变式要求：**
1. 保持相同的知识点（{kp_str}）和难度（{difficulty}）
2. 改变题面数据（如替换物质、改变化学计量数、更换反应条件）
3. 改变选项表述（确保不通过记忆原题答案就能作答）
4. 每道题必须有 4 个选项（A/B/C/D），标注正确答案
5. 每道题包含简要解析（一句话即可）

**输出格式（必须是合法的 JSON 数组）：**
```json
[
  {{
    "content": "题面内容",
    "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
    "answer": "正确答案（如 B）",
    "analysis": "简要解析"
  }}
]
```

请直接返回 JSON 数组，不要包含其他文字。"""


def _build_generic_variant_prompt(
    content: str,
    answer: str,
    difficulty: str,
    kp_str: str,
    q_type: str,
    count: int,
) -> str:
    """构造非选择题（填空/计算/实验/推断）变式题的 prompt。"""
    return f"""你是一位经验丰富的中学化学教师，请为以下题目生成 {count} 道变式题。

**原题信息：**
- 知识点：{kp_str}
- 难度：{difficulty}
- 题型：{q_type}

**原题内容：**
{content}

**原题答案：**
{answer}

**变式要求：**
1. 保持相同的知识点（{kp_str}）和难度（{difficulty}）
2. 改变题面数据（如替换物质、改变化学计量数、更换反应条件）
3. 每道题包含正确答案和简要解析

**输出格式（必须是合法的 JSON 数组）：**
```json
[
  {{
    "content": "题面内容",
    "answer": "正确答案",
    "analysis": "简要解析"
  }}
]
```

请直接返回 JSON 数组，不要包含其他文字。"""
