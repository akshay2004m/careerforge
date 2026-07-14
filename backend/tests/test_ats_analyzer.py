from app.services.ats_analyzer import combine_layers, extract_jd_keywords, layer1_rules


class TestLayer1Rules:
    def test_high_match_score(self):
        resume = """
        Senior Python Developer with 5+ years experience in FastAPI,
        SQLAlchemy, Docker, and AWS. Built multiple REST APIs and microservices.
        """
        jd = """
        We are looking for a Python Developer with strong experience in
        FastAPI, SQLAlchemy, Docker and cloud platforms like AWS.
        """
        result = layer1_rules(resume, jd)
        assert result["score"] >= 20
        assert result["components"]["keyword_coverage"]["ratio_pct"] > 60

    def test_low_match_score(self):
        resume = "I have experience in graphic design and video editing."
        jd = "Looking for a backend engineer with Python and FastAPI experience."
        result = layer1_rules(resume, jd)
        assert result["score"] < 15

    def test_extract_keywords(self):
        text = "Python, FastAPI, Docker, PostgreSQL, AWS, Machine Learning"
        keywords = extract_jd_keywords(text)
        assert "python" in keywords
        assert "fastapi" in keywords
        assert len(keywords) >= 4


class TestLayerCombination:
    def test_combine_layers_produces_valid_score(self):
        layer1 = {"score": 40, "details": {}}
        layer2 = {"score": 22, "details": {}}
        layer3 = {"score": 18, "details": {}}

        final = combine_layers(layer1, layer2, layer3)

        assert 0 <= final["ats_score"] <= 100
        assert "breakdown" in final
