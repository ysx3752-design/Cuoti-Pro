"""场景2: 分层练习业务逻辑"""
from __future__ import annotations

from tools.db_tool import get_mistakes
from tools.llm_tool import llm_invoke_json
from tools.memory_tool import recall_and_summarize

from scenario_2_practice.schemas import PracticeState
from scenario_2_practice.workflow import build_practice_workflow
from scenario_2_practice.prompts import PROMPT_GRADE_PRACTICE


def detect_weak_points_from_mistakes(
    student_id: str, subject: str = "数学", min_count: int = 2,
) -> list[str]:
    """从错题数据中自动识别薄弱知识点，按频次排序。

    对应场景2需求：基于错题数据，定位知识漏洞。
    """
    ms = get_mistakes(student_id, days=30, subject=subject)
    kp_count: dict[str, int] = {}
    for m in ms:
        for kp in m.get("knowledge_points", []):
            if kp:
                kp_count[kp] = kp_count.get(kp, 0) + 1
    weak = [kp for kp, c in sorted(kp_count.items(), key=lambda x: -x[1]) if c >= min_count]
    return weak[:5]


def run_practice(
    student_id: str,
    weak_points: list[str] | None = None,
    subject: str = "数学",
    difficulty: str = "base",
    max_questions: int = 10,
) -> dict:
    """运行分层练习（整轮：出题 → 批改 → 难度递进 → 总结 → 记忆）。

    Args:
        student_id: 学生ID
        weak_points: 薄弱知识点列表（为空时自动从错题检测）
        subject: 学科
        difficulty: 起始难度 base/variant/advanced/exam
        max_questions: 单次最大出题数

    Returns:
        PracticeState 完整状态字典
    """
    if not weak_points:
        weak_points = detect_weak_points_from_mistakes(student_id, subject)
    if not weak_points:
        return {"error": "未找到薄弱知识点，请先做题产生错题数据"}

    query_str = " ".join(weak_points)
    mem_summary = recall_and_summarize(student_id=student_id, query=query_str, max_count=5)

    app = build_practice_workflow()
    init: PracticeState = {
        "student_id": student_id,
        "subject": subject,
        "weak_points": weak_points,
        "difficulty": difficulty,
        "difficulty_changed": False,
        "questions": [],
        "current_index": 0,
        "current_question": {},
        "student_answer": "",
        "is_correct": False,
        "feedback": "",
        "correct_answer": "",
        "session_summary": "",
        "max_questions": max_questions,
        "covered_points": [],
        "memory_updates": None,
        "recalled_memory_summary": mem_summary,
    }
    return app.invoke(init)


def run_answer(
    student_id: str,
    question_json: dict,
    student_answer: str,
    weak_points: list[str] | None = None,
    subject: str = "数学",
) -> dict:
    """单题提交批改（不经过完整循环，用于单题问答场景）。"""
    import json as _json
    prompt = PROMPT_GRADE_PRACTICE.format(
        question=question_json.get("question", ""),
        correct_answer=question_json.get("answer", ""),
        student_answer=student_answer,
    )
    try:
        r = llm_invoke_json(prompt, temperature=0.1)
        return {
            "is_correct": bool(r.get("is_correct", False)),
            "score": float(r.get("score", 0)),
            "feedback": r.get("feedback", ""),
            "correct_answer": question_json.get("answer", ""),
        }
    except Exception as e:
        return {"is_correct": False, "score": 0, "feedback": f"批改异常: {e}", "correct_answer": ""}
