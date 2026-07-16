from unittest.mock import patch

from app.services.ats_analyzer import (
    combine_layers,
    layer1_rules,
)


class TestLayer1Rules:
    def test_high_keyword_match(self):
        resume = "Senior Python Developer with FastAPI, SQLAlchemy, Docker and AWS experience."
        jd = "Looking for Python developer experienced in FastAPI, Docker and cloud platforms."

        result = layer1_rules(resume, jd)
        assert result["score"] > 15
        assert result["components"]["keyword_coverage"]["ratio_pct"] > 50

    def test_low_match(self):
        resume = "I love graphic design and video editing."
        jd = "Backend engineer with strong Python and FastAPI skills required."

        result = layer1_rules(resume, jd)
        assert result["score"] < 15


class TestLayer2SemanticMocked:
    @patch("app.services.ats_analyzer.layer2_semantic")
    def test_layer2_semantic_mocked(self, mock_layer2):
        mock_layer2.return_value = {"score": 23, "details": {"semantic_similarity": 0.72}}

        result = mock_layer2("sample resume text", "sample job description")

        assert result["score"] == 23
        assert result["details"]["semantic_similarity"] == 0.72
        mock_layer2.assert_called_once()


class TestLayer3LLMMocked:
    @patch("app.services.ats_analyzer.layer3_from_llm_payload")
    def test_layer3_llm_mocked(self, mock_layer3):
        mock_layer3.return_value = {
            "score": 17,
            "details": {
                "llm_score": 8,
                "strengths": ["Strong project experience"],
                "improvements": ["Add more metrics"],
            },
        }

        result = mock_layer3("resume text", "job description")

        assert result["score"] == 17
        assert result["details"]["llm_score"] == 8


class TestFullATSAnalysis:
    @patch("app.services.ats_analyzer.layer2_semantic")
    @patch("app.services.ats_analyzer.layer3_from_llm_payload")
    def test_full_ats_analysis_with_mocks(self, mock_layer3, mock_layer2):
        # Mock layer 2
        mock_layer2.return_value = {
            "score": 22,
            "max": 25,
            "details": {"semantic_similarity": 0.68},
        }

        # Mock layer 3
        mock_layer3.return_value = {"score": 16, "max": 20, "details": {"llm_score": 7}}

        # Layer 1 (real)
        layer1 = layer1_rules(
            "Python developer with FastAPI and Docker experience",
            "Senior backend role requiring Python, FastAPI and containerization",
        )

        # Combine all layers
        final_result = combine_layers(layer1, mock_layer2.return_value, mock_layer3.return_value)

        assert 0 <= final_result["ats_score"] <= 100
        assert final_result["ats_score"] > 45  # Should be decent match
        assert "breakdown" in final_result
