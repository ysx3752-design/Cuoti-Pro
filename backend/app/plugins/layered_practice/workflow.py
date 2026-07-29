"""场景2: 分层练习工作流（LangGraph）—— 逐题循环 + 难度递进 + 知识点轮换"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from langgraph.graph import StateGraph, END
from scenario_2_practice.schemas import PracticeState
from scenario_2_practice.prompts import PROMPT_GEN, PROMPT_GRADE_PRACTICE, PROMPT_SUMMARIZE
from tools.llm_tool import llm_invoke_json
from tools.db_tool import update_mastery


def build_practice_workflow():
    """构建分层练习LangGraph。

    工作流：gen → grade → {gen (继续) | sum (完成)} → smart_memory → END
    """
    g = StateGraph(PracticeState)

    def generate_question_node(state):
        wps = state.get("weak_points", [])
        diff = state.get("difficulty", "base")
        qs = state.get("questions", [])
        covered = state.get("covered_points", [])

        # 知识点轮换：选择被覆盖最少的薄弱点
        if len(wps) > 1:
            kp_priority = {kp: 0 for kp in wps}
            for q in qs:
                for kp in q.get("question", {}).get("knowledge_points", []):
                    if kp in kp_priority:
                        kp_priority[kp] += 1
            min_count = min(kp_priority.values())
            focus_points = [kp for kp, c in kp_priority.items() if c == min_count]
        else:
            focus_points = wps

        from scenario_2_practice.schemas import DIFFICULTY_CN
        diff_cn = DIFFICULTY_CN.get(diff, diff)
        prompt = PROMPT_GEN.format(
            subject=state.get("subject", "数学"),
            difficulty=diff, difficulty_cn=diff_cn,
            weak_points=", ".join(focus_points),
            done_count=len(qs),
        )
        try:
            r = llm_invoke_json(prompt, temperature=0.8)
            new_covered = list(set(covered + r.get("knowledge_points", [])))
            return {
                **state,
                "current_question": r,
                "current_index": len(qs),
                "student_answer": "",
                "is_correct": False,
                "feedback": "",
                "correct_answer": r.get("answer", ""),
                "covered_points": new_covered,
            }
        except Exception as e:
            return {**state, "current_question": {"question": f"出题失败:{e}", "answer": ""}, "feedback": "重试"}

    def grade_practice_node(state):
        q = state["current_question"]
        sa = state.get("student_answer", "")
        ca = q.get("answer", "")
        prompt = PROMPT_GRADE_PRACTICE.format(
            question=q.get("question", ""),
            correct_answer=ca,
            student_answer=sa,
        )
        try:
            r = llm_invoke_json(prompt, temperature=0.1)
            ic = r.get("is_correct", False)
            qs = list(state.get("questions", []))
            qs.append({
                "question": q, "student_answer": sa, "is_correct": ic,
                "score": r.get("score", 0),
            })
            for kp in q.get("knowledge_points", state.get("weak_points", [])):
                update_mastery(state["student_id"], kp, 0.1 if ic else -0.15)

            # 难度递进逻辑
            order = ["base", "variant", "advanced", "exam"]
            cur = state.get("difficulty", "base")
            idx = order.index(cur) if cur in order else 0
            new_diff = cur
            if ic and idx < len(order) - 1:
                new_diff = order[idx + 1]  # 正确则升难度
            elif not ic and idx > 0:
                new_diff = order[idx - 1]  # 错误则降难度
            changed = new_diff != cur

            return {
                **state,
                "is_correct": ic,
                "feedback": r.get("feedback", ""),
                "correct_answer": ca,
                "questions": qs,
                "difficulty": new_diff,
                "difficulty_changed": changed,
            }
        except Exception as e:
            return {**state, "is_correct": False, "feedback": f"批改异常:{e}", "difficulty_changed": False}

    def decide_next(state):
        qs = state.get("questions", [])
        max_q = state.get("max_questions", 10)
        if len(qs) >= max_q:
            return "sum"
        return "gen"

    def summarize_node(state):
        qs = state.get("questions", [])
        total = len(qs)
        correct = sum(1 for q in qs if q.get("is_correct"))
        prompt = PROMPT_SUMMARIZE.format(
            weak_points=", ".join(state.get("weak_points", [])),
            total=total, correct=correct,
        )
        try:
            s = llm_invoke_json(prompt, temperature=0.3)
            return {**state, "session_summary": __import__("json").dumps(s, ensure_ascii=False), "memory_updates": None}
        except Exception:
            return {**state, "session_summary": "总结失败", "memory_updates": None}

    def smart_memory_node(state):
        from tools.memory_tool import smart_update_from_session, reflect_after_session
        sid = state["student_id"]
        wps = state.get("weak_points", [])
        qs = state.get("questions", [])
        total = len(qs)
        correct = sum(1 for q in qs if q.get("is_correct"))
        ss = state.get("session_summary", "")
        summary_text = f"分层练习：共{total}题，正确{correct}题，薄弱点: {', '.join(wps)}"
        if ss:
            summary_text += f"\n总结: {ss}"
        updates = []
        try:
            updates = smart_update_from_session(
                student_id=sid, question=summary_text,
                answer_summary=f"正确率: {correct / max(total, 1) * 100:.0f}%, 薄弱点: {', '.join(wps)}",
                kb_used="practice", kb_titles=f"练习知识点: {', '.join(wps)}",
            )
        except Exception:
            updates = []
        try:
            reflect_after_session(student_id=sid, agent_type="practice", summary_md=summary_text)
        except Exception:
            pass
        return {**state, "memory_updates": updates}

    g.add_node("gen", generate_question_node)
    g.add_node("grade", grade_practice_node)
    g.add_node("sum", summarize_node)
    g.add_node("smart_memory", smart_memory_node)
    g.set_entry_point("gen")
    g.add_edge("gen", "grade")
    g.add_conditional_edges("grade", decide_next, {"gen": "gen", "sum": "sum"})
    g.add_edge("sum", "smart_memory")
    g.add_edge("smart_memory", END)
    return g.compile()


if __name__ == "__main__":
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.stdout.reconfigure(encoding="utf-8")
    import json
    from scenario_2_practice.schemas import PracticeState
    from tools.memory_tool import recall_and_summarize

    mem = recall_and_summarize(student_id="test001", query="二次函数 配方法", max_count=5)
    app = build_practice_workflow()
    s: PracticeState = {
        "student_id": "test001",
        "subject": "数学",
        "weak_points": ["二次函数", "配方法"],
        "difficulty": "base",
        "difficulty_changed": False,
        "questions": [],
        "current_index": 0,
        "current_question": {},
        "student_answer": "",
        "is_correct": False,
        "feedback": "",
        "correct_answer": "",
        "session_summary": "",
        "max_questions": 3,
        "covered_points": [],
        "memory_updates": None,
        "recalled_memory_summary": mem,
    }
    r = app.invoke(s)
    print("=== 场景2 分层练习测试 ===")
    print(f"共做题: {len(r.get('questions', []))}")
    for i, q in enumerate(r.get("questions", [])):
        qd = q.get("question", {})
        print(f"  {i+1}. [{'✓' if q['is_correct'] else '✗'}] {qd.get('question','')[:60]}")
    print(f"总结: {r.get('session_summary', '')[:100]}")
