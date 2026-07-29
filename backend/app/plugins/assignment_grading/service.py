"""场景1: 批改业务逻辑（单模型版）"""
from __future__ import annotations
import hashlib, os

from tools.llm_tool import llm_invoke_json, parse_json_from_text, llm_invoke_with_image
from tools.pdf_tool import extract_pdf_auto
from tools.db_tool import add_mistake, update_mastery, add_knowledge_point, get_mistakes
from tools.memory_tool import recall_and_summarize, smart_update_from_session, reflect_after_session

from scenario_1_grading.schemas import SingleGradeState, GradeResult
from scenario_1_grading.prompts import GRADE_PROMPT, PAPER_PARSE_PROMPT, PAPER_GRADE_SYSTEM
from scenario_1_grading.workflow import build_grader_workflow


# ═══════════════════════════════════════════════════════════
# 单题批改
# ═══════════════════════════════════════════════════════════

def run_grader(
    student_id: str,
    question: str,
    student_answer: str = "",
    subject: str = "数学",
    image_path: str = "",
) -> SingleGradeState:
    """单题批改入口（支持文本和图片）。

    使用单一模型完成 OCR + 判分，不走双模型分离路线。
    """
    # 如果是图片题，用单模型视觉能力同时做识别和判分
    if image_path:
        prompt = GRADE_PROMPT.format(question=question, student_answer=student_answer, subject=subject)
        try:
            raw = llm_invoke_with_image(prompt, image_path, temperature=0.1)
        except FileNotFoundError:
            raw = "{}"
        result = parse_json_from_text(raw) if raw.strip() else {}
        for kp in result.get("knowledge_points", []):
            add_knowledge_point(kp, subject=subject)
        state = {
            "student_id": student_id, "question": question,
            "student_answer": student_answer, "subject": subject,
            "image_path": image_path, "ocr_text": "",
            "correct_answer": result.get("correct_answer", ""),
            "is_correct": bool(result.get("is_correct", False)),
            "score": float(result.get("score", 0)),
            "analysis": result.get("analysis", ""),
            "knowledge_points": result.get("knowledge_points", []),
            "difficulty": result.get("difficulty", "medium"),
        }
    else:
        # 纯文本批改 → 走 LangGraph workflow
        app = build_grader_workflow()
        mem_summary = recall_and_summarize(student_id=student_id, query=question, max_count=5)
        state = {
            "student_id": student_id, "question": question,
            "student_answer": student_answer, "subject": subject,
            "image_path": None, "ocr_text": None,
            "correct_answer": "", "is_correct": False,
            "score": 0.0, "analysis": "", "knowledge_points": [],
            "difficulty": "medium", "memory_updates": None,
            "recalled_memory_summary": mem_summary,
        }
        state = app.invoke(state)
    return state


def _build_question_id(student_id: str, subject: str, question: str, student_answer: str) -> str:
    payload = f"{student_id}|{subject}|{question}|{student_answer}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def _is_duplicate_mistake(student_id: str, question: str, student_answer: str, subject: str) -> bool:
    try:
        qid = _build_question_id(student_id, subject, question, student_answer)
        mistakes = get_mistakes(student_id, subject=subject)
        return any(m.get("question_id") == qid for m in mistakes)
    except Exception:
        return False


def _source_from_path(image_path: str) -> str:
    if not image_path:
        return ""
    ext = os.path.splitext(image_path.lower())[1]
    if ext == ".pdf":
        return "pdf"
    if ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"):
        return "image"
    return "text"


def _grade_single_question(
    question: str, student_answer: str, subject: str, student_id: str,
) -> dict:
    """批改单道题，返回结果字典。"""
    try:
        prompt = GRADE_PROMPT.format(question=question, student_answer=student_answer, subject=subject)
        r = llm_invoke_json(prompt, temperature=0.1)
        for kp in r.get("knowledge_points", []):
            add_knowledge_point(kp, subject=subject)
        return {
            "correct_answer": r.get("correct_answer", ""),
            "is_correct": bool(r.get("is_correct", False)),
            "score": float(r.get("score", 0)),
            "analysis": r.get("analysis", ""),
            "knowledge_points": r.get("knowledge_points", []),
            "difficulty": r.get("difficulty", "medium"),
        }
    except Exception as e:
        return {
            "correct_answer": "", "is_correct": False, "score": 0,
            "analysis": f"批改异常: {e}", "knowledge_points": [], "difficulty": "medium",
        }


# ═══════════════════════════════════════════════════════════
# 整卷批改
# ═══════════════════════════════════════════════════════════

def parse_paper(raw_text: str, subject: str = "数学") -> list[dict]:
    """将OCR识别的整页文字解析为逐题结构。"""
    if not raw_text or len(raw_text.strip()) < 5:
        return []
    prompt = PAPER_PARSE_PROMPT.format(ocr_text=raw_text, subject=subject)
    try:
        questions = llm_invoke_json(prompt, temperature=0.1)
    except Exception:
        return [{
            "number": "1", "question": raw_text[:500],
            "student_answer": "", "question_type": "other",
        }]
    if not isinstance(questions, list):
        return []
    validated = []
    for q in questions:
        if not isinstance(q, dict):
            continue
        qt = (q.get("question", "") or "").strip()
        if not qt:
            continue
        validated.append({
            "number": q.get("number", str(len(validated) + 1)),
            "question": qt,
            "student_answer": (q.get("student_answer", "") or "").strip(),
            "question_type": q.get("question_type", "other"),
        })
    return validated if validated else [{
        "number": "1", "question": raw_text[:500],
        "student_answer": "", "question_type": "other",
    }]


def _archive_single_result(student_id: str, subject: str, q: dict, result: dict) -> None:
    if not result["is_correct"]:
        qid = _build_question_id(student_id, subject, q.get("question", ""), q.get("student_answer", ""))
        if not _is_duplicate_mistake(student_id, q.get("question", ""), q.get("student_answer", ""), subject):
            add_mistake(student_id, {
                "question": q.get("question", ""), "subject": subject,
                "student_answer": q.get("student_answer", ""),
                "correct_answer": result.get("correct_answer", ""),
                "analysis": result.get("analysis", ""),
                "knowledge_points": result.get("knowledge_points", []),
                "score": result.get("score", 0),
                "question_id": qid,
                "question_number": q.get("number", ""),
                "question_type": q.get("question_type", "other"),
            })
        for kp in result["knowledge_points"]:
            update_mastery(student_id, kp, -0.2)
    else:
        for kp in result["knowledge_points"]:
            update_mastery(student_id, kp, 0.1)


def run_paper_grader(
    student_id: str,
    subject: str = "数学",
    image_path: str = "",
    raw_text: str = "",
) -> dict:
    """整卷批改入口（单模型版）。

    工作流:
    1. 获取试卷文本（PDF提取/OCR/直接传入）
    2. 拆题
    3. 逐题批改
    4. 归档错题 + 更新掌握度
    5. 会话记忆
    """
    # 第1步：获取试卷文本
    if image_path:
        source_type = _source_from_path(image_path)
        if source_type == "pdf":
            ocr_result = extract_pdf_auto(image_path)
        else:
            ocr_result = ""
        if not ocr_result:
            return {"questions": [], "summary": {"total": 0, "correct": 0, "wrong": 0, "partial": 0, "avg_score": 0},
                    "error": "未能识别到试卷文字", "memory_updates": []}
    else:
        ocr_result = raw_text
        source_type = "text"

    if not ocr_result or len(ocr_result.strip()) < 5:
        return {"questions": [], "summary": {"total": 0, "correct": 0, "wrong": 0, "partial": 0, "avg_score": 0},
                "error": "未能识别到试卷文字", "memory_updates": []}

    # 第2步：拆题
    questions = parse_paper(ocr_result, subject)
    if not questions:
        return {"questions": [], "summary": {"total": 0, "correct": 0, "wrong": 0, "partial": 0, "avg_score": 0},
                "error": "未能从文字中识别出题目-答案对", "memory_updates": []}

    # 第3步：逐题批改
    results = []
    for q in questions:
        if not q["student_answer"]:
            results.append({**q, "correct_answer": "", "is_correct": False, "score": 0,
                           "analysis": "未检测到学生作答内容", "knowledge_points": [], "difficulty": "unknown"})
            continue
        g = _grade_single_question(q["question"], q["student_answer"], subject, student_id)
        results.append({**q, **g})

    # 第4步：归档
    for i, q in enumerate(questions):
        if i < len(results) and results[i].get("student_answer"):
            _archive_single_result(student_id, subject, q, results[i])

    # 第5步：统计 + 记忆
    total = len(results)
    correct = sum(1 for r in results if r["is_correct"])
    wrong = sum(1 for r in results if not r["is_correct"] and r.get("student_answer"))
    partial = sum(1 for r in results if r.get("score") and 0 < r["score"] < 100 and not r["is_correct"])
    scores = [r["score"] for r in results if r.get("student_answer")]
    avg_score = sum(scores) / len(scores) if scores else 0
    summary = {"total": total, "correct": correct, "wrong": wrong, "partial": partial, "avg_score": round(avg_score, 1)}

    memory_updates = _paper_smart_memory(student_id, subject, questions, results, summary)

    return {"questions": results, "summary": summary, "memory_updates": memory_updates, "error": None}


def _paper_smart_memory(student_id: str, subject: str, questions: list, results: list, summary: dict) -> list:
    wrong_kps = []
    for r in results:
        if not r["is_correct"]:
            wrong_kps.extend(r.get("knowledge_points", []))
    summary_text = f"整卷批改：共{summary['total']}题，正确{summary['correct']}题，错误{summary['wrong']}题"
    updates = []
    try:
        updates = smart_update_from_session(
            student_id=student_id, question=summary_text,
            answer_summary=f"错题知识点: {', '.join(set(wrong_kps))}" if wrong_kps else "全部正确",
        )
    except Exception:
        pass
    try:
        reflect_after_session(student_id=student_id, agent_type="paper_grader", summary_md=summary_text)
    except Exception:
        pass
    return updates
