"""v2 评分体系测试 — 评分计算模块 + 分流闸门"""
import pytest

from app.workflow.scoring import (
    compute_overall,
    extract_dimension_scores,
    get_weights,
)


class TestGetWeights:
    """权重配置测试"""

    def test_default_weights(self):
        w = get_weights()
        assert w == {"skill": 0.4, "experience": 0.4, "stability": 0.2}

    def test_category_override(self, monkeypatch):
        from app.config import settings
        monkeypatch.setattr(
            settings, "SCORE_WEIGHTS_BY_CATEGORY",
            {"销售": {"skill": 0.3, "experience": 0.4, "stability": 0.3}},
        )
        assert get_weights("销售") == {"skill": 0.3, "experience": 0.4, "stability": 0.3}
        # 其他类别不受影响
        assert get_weights("python") == {"skill": 0.4, "experience": 0.4, "stability": 0.2}

    def test_invalid_weights_fallback(self, monkeypatch):
        from app.config import settings
        monkeypatch.setattr(settings, "SCORE_WEIGHTS_DEFAULT",
                            {"skill": 0.5, "experience": 0.5, "stability": 0.5})
        # 求和 != 1，应回退到硬编码的安全默认值
        assert get_weights() == {"skill": 0.4, "experience": 0.4, "stability": 0.2}


class TestExtractDimensionScores:
    """维度分提取测试"""

    def test_all_present(self):
        dims = extract_dimension_scores(
            {"skill_match_score": 90}, {"experience_score": 80, "stability_score": 70}
        )
        assert dims == {"skill": 90.0, "experience": 80.0, "stability": 70.0}

    def test_missing_become_none(self):
        dims = extract_dimension_scores({}, {"experience_score": 80})
        assert dims == {"skill": None, "experience": 80.0, "stability": None}

    def test_invalid_value_become_none(self):
        dims = extract_dimension_scores({"skill_match_score": "abc"}, {})
        assert dims["skill"] is None

    def test_out_of_range_clamped(self):
        dims = extract_dimension_scores({"skill_match_score": 150}, {})
        assert dims["skill"] == 100.0


class TestComputeOverall:
    """综合分计算测试"""

    def test_full_weighted(self):
        result = compute_overall(
            {"skill": 90.0, "experience": 80.0, "stability": 70.0},
            {"skill": 0.4, "experience": 0.4, "stability": 0.2},
        )
        # 90*0.4 + 80*0.4 + 70*0.2 = 82
        assert result["overall"] == 82.0
        assert result["complete"] is True
        assert result["source"] == "weighted"
        assert result["missing"] == []

    def test_partial_renormalization(self):
        """缺 stability 时 0.4/0.4 重归一化为 0.5/0.5"""
        result = compute_overall(
            {"skill": 90.0, "experience": 80.0, "stability": None},
            {"skill": 0.4, "experience": 0.4, "stability": 0.2},
        )
        # 90*0.5 + 80*0.5 = 85
        assert result["overall"] == 85.0
        assert result["complete"] is False
        assert result["source"] == "weighted_partial"
        assert result["missing"] == ["stability"]
        assert result["weights_used"] == {"skill": 0.5, "experience": 0.5}

    def test_all_missing(self):
        """全部缺失：不产分，不静默给50"""
        result = compute_overall(
            {"skill": None, "experience": None, "stability": None},
            {"skill": 0.4, "experience": 0.4, "stability": 0.2},
        )
        assert result["overall"] is None
        assert result["source"] == "none"
        assert result["complete"] is False


class TestIncompleteRouting:
    """分析不完整时不自动分流"""

    def test_incomplete_blocks_routing(self):
        from app.workflow.graph import should_send_questionnaire

        # 即使分数 >=80，维度分不完整也不允许自动进面试
        state = {"match_score": 85, "analysis_complete": False}
        assert should_send_questionnaire(state) == "__end__"

    def test_complete_uses_thresholds(self):
        from app.workflow.graph import should_send_questionnaire

        state = {"match_score": 85, "analysis_complete": True}
        assert should_send_questionnaire(state) == "schedule_interview"

    def test_missing_flag_defaults_complete(self):
        """旧状态没有 analysis_complete 字段时默认放行（向后兼容）"""
        from app.workflow.graph import should_send_questionnaire

        assert should_send_questionnaire({"match_score": 85}) == "schedule_interview"
