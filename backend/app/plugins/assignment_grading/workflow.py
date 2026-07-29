"""场景1: 批改工作流（LangGraph）—— 单模型集成"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from langgraph.graph import StateGraph, END
from scenario_1_grading.schemas import SingleGradeState
from tools.llm_tool import llm_invoke_json


def build_grader_workflow():
    """构建单题批改工作流：grade → archive"""
    g = StateGraph(SingleGradeState)

    def grade_node(state):
        q = state.get("question", "")
        a = state.get("student_answer", "")
        from scenario_1_grading.prompts import GRADE_PROMPT
        from tools.db_tool import add_knowledge_point
        prompt = GRADE_PROMPT.format(question=q, student_answer=a, subject=state.get("subject", "数学"))
        try:
            r = llm_invoke_json(prompt, temperature=0.1)
            for kp in r.get("knowledge_points", []):
                add_knowledge_point(kp, subject=state.get("subject", "数学"))
            return {
                **state,
                "correct_answer": r.get("correct_answer", ""),
                "is_correct": bool(r.get("is_correct", False)),
                "score": float(r.get("score", 0)),
                "analysis": r.get("analysis", ""),
                "knowledge_points": r.get("knowledge_points", []),
                "difficulty": r.get("difficulty", "medium"),
            }
        except Exception as e:
            return {
                **state,
                "correct_answer": "",
                "is_correct": False,
                "score": 0,
                "analysis": f"批改异常: {e}",
                "knowledge_points": [],
            }

    def archive_node(state):
        from tools.db_tool import add_mistake, update_mastery
        if not state["is_correct"]:
            add_mistake(state["student_id"], {
                "question": state["question"],
                "subject": state.get("subject", "数学"),
                "student_answer": state["student_answer"],
                "correct_answer": state["correct_answer"],
                "analysis": state.get("analysis", ""),
                "knowledge_points": state.get("knowledge_points", []),
                "score": state.get("score", 0),
            })
            for kp in state.get("knowledge_points", []):
                update_mastery(state["student_id"], kp, -0.2)
        else:
            for kp in state.get("knowledge_points", []):
                update_mastery(state["student_id"], kp, 0.1)
        return state

    def memory_node(state):
        from tools.memory_tool import smart_update_from_session, reflect_after_session
        sid = state["student_id"]
        q = state.get("question", "")
        kps = ", ".join(state.get("knowledge_points", []))
        try:
            updates = smart_update_from_session(
                student_id=sid, question=q,
                answer_summary=f"批改结果: {'正确' if state['is_correct'] else '错误'}, 得分{state['score']}, 知识点:{kps}",
            )
        except Exception:
            updates = []
        try:
            reflect_after_session(student_id=sid, agent_type="grader",
                summary_md=f"批改题目：{q}\n判断：{'正确' if state['is_correct'] else '错误'}，得分：{state['score']}")
        except Exception:
            pass
        return {**state, "memory_updates": updates}

    g.add_node("grade", grade_node)
    g.add_node("archive", archive_node)
    g.add_node("memory", memory_node)
    g.set_entry_point("grade")
    g.add_edge("grade", "archive")
    g.add_edge("archive", "memory")
    g.add_edge("memory", END)
    return g.compile()


if __name__ == "__main__":
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.stdout.reconfigure(encoding="utf-8")
    from scenario_1_grading.schemas import SingleGradeState
    from tools.memory_tool import recall_and_summarize

    mem = recall_and_summarize(student_id="test001", query="数学", max_count=3)
    app = build_grader_workflow()
    state: SingleGradeState = {
        "student_id": "test001",
        "question": "求函数 f(x)=x²-4x+3 的顶点坐标",
        "student_answer": "顶点为(2,-1)",
        "subject": "数学",
        "image_path": None,
        "ocr_text": None,
        "correct_answer": "",
        "is_correct": False,
        "score": 0.0,
        "analysis": "",
        "knowledge_points": [],
        "difficulty": "medium",
        "memory_updates": None,
        "recalled_memory_summary": mem,
    }
    r = app.invoke(state)
    print("=== 场景1 单题批改测试 ===")
    print(f"正确: {r['is_correct']}")
    print(f"得分: {r['score']}")
    print(f"正确答案: {r['correct_answer']}")
    print(f"分析: {r.get('analysis', '')[:100]}")
    print(f"知识点: {r.get('knowledge_points', [])}")
