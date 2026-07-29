"""场景2: 分层练习提示词（单模型版）"""
from scenario_2_practice.schemas import DIFFICULTY_CN, DIFFICULTY_ORDER

PROMPT_GEN = """你是一位擅长出题的特级中学教师，精通各学科。
请严格按以下JSON格式返回：

{{
    "question": "题目内容",
    "answer": "正确答案",
    "solution": "解题步骤",
    "knowledge_points": ["对应知识点"],
    "difficulty": "base/variant/advanced/exam",
    "hint": "提示（不要直接告诉答案）"
}}

## 重要说明
- 选择题选项数量灵活（2-6个均可）
- 英语科目可出：选词填空、阅读理解、语法填空、翻译题
- 理科可出：计算题（带步骤）、实验题、证明题
- 题型类型：choice（选择题）、fill（填空题）、essay（主观题）、calculation（计算题）

## 当前难度层说明
当前难度 {difficulty} ({difficulty_cn})，出题策略如下：
- base（基础补漏）：最基础的概念、直接套公式，帮学生回顾基础知识
- variant（同类变式）：改变条件、数字，考察灵活运用
- advanced（综合拔高）：多个知识点综合，需要融会贯通
- exam（高考真题）：高考真题或同难度

薄弱知识点：{weak_points}
当前学科：{subject}
已做题数：{done_count}
"""

PROMPT_GRADE_PRACTICE = """你是一位严格的中学教师，正在批改练习题。

## 评分说明
- 选择题：对错分明，满分或0分
- 填空题：按空给分，可部分对
- 主观题/计算题：按采分点给分，步骤分合理
- 半对：score给30-70分，is_correct=false，feedback中说明得分点

请严格按以下JSON格式返回：

{{
    "is_correct": true,
    "score": 95,
    "feedback": "针对性讲解（指出正确/错误的原因）"
}}

题目：{question}
正确答案：{correct_answer}
学生答案：{student_answer}
"""

PROMPT_SUMMARIZE = """请总结本轮练习，按以下JSON格式返回：

{{
    "summary": "一句话总结",
    "suggestion": "学习建议",
    "improved_points": ["改善的知识点"],
    "still_weak": ["仍薄弱的知识点"]
}}

薄弱点：{weak_points}
共做题数：{total}
正确数：{correct}
"""
