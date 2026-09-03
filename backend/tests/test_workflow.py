"""招聘流程编排测试 — LangGraph 状态机 + 阈值分流"""
class TestWorkflowState:
    """工作流状态定义测试"""

    def test_state_fields_exist(self):
        """RecruitmentState 应包含所有必要字段"""
        from app.workflow.state import RecruitmentState

        # 验证 TypedDict 字段存在（允许可选）
        required_fields = [
            "candidate_id", "candidate_name", "position",
            "status", "pipeline_stage", "match_score",
            "errors", "retry_count", "notifications_sent",
        ]
        for field in required_fields:
            assert field in RecruitmentState.__annotations__, f"缺少字段: {field}"

    def test_state_has_optional_fields(self):
        """RecruitmentState 应有可选字段"""
        from app.workflow.state import RecruitmentState

        optional_fields = [
            "analysis_result", "match_analysis",
            "questionnaire_id", "questionnaire_status",
            "interview_id", "interview_status",
        ]
        for field in optional_fields:
            assert field in RecruitmentState.__annotations__, f"缺少可选字段: {field}"


class TestThresholdRouting:
    """阈值分流逻辑测试"""

    def test_fast_track_threshold(self):
        """>=80 分应走快速通道"""
        from app.workflow.graph import should_send_questionnaire

        state = {"match_score": 85}
        route = should_send_questionnaire(state)
        assert route == "schedule_interview"

    def test_questionnaire_threshold(self):
        """60-79 分应走问卷通道"""
        from app.workflow.graph import should_send_questionnaire

        state = {"match_score": 65}
        route = should_send_questionnaire(state)
        assert route == "generate_questionnaire"

    def test_talent_pool_threshold(self):
        """40-59 分应进人才池"""
        from app.workflow.graph import should_send_questionnaire

        state = {"match_score": 45}
        route = should_send_questionnaire(state)
        assert route == "talent_pool"

    def test_reject_threshold(self):
        """<40 分应拒绝"""
        from app.workflow.graph import should_send_questionnaire

        state = {"match_score": 35}
        route = should_send_questionnaire(state)
        assert route == "__end__"

    def test_none_score_fallback(self):
        """match_score 为 None 时应安全处理"""
        from app.workflow.graph import should_send_questionnaire

        state = {"match_score": None}
        route = should_send_questionnaire(state)
        # None 应视为 0，走拒绝
        assert route == "__end__"


class TestGraphStructure:
    """LangGraph 结构测试"""

    def test_graph_builds_successfully(self):
        """编译状态图不应报错"""
        from app.workflow.graph import build_recruitment_graph

        graph = build_recruitment_graph()
        assert graph is not None

    def test_graph_has_expected_nodes(self):
        """状态图应包含所有必要节点"""
        from app.workflow.graph import build_recruitment_graph

        graph = build_recruitment_graph()
        expected_nodes = {
            "parse_resume", "classify", "analyze",
            "generate_questionnaire", "wait_questionnaire",
            "score_questionnaire", "schedule_interview",
            "confirm_interview", "complete_interview",
            "make_decision", "move_to_talent_pool",
        }
        # 验证所有节点都注册了
        for node in expected_nodes:
            assert node in graph.nodes, f"缺少节点: {node}"
