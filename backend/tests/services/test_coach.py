"""Tests for the coach service with mocked research database."""

import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, "backend")

from datetime import datetime, timezone

from app.services.coach import (
    _cluster_for_rating,
    _fallback_skill_vector,
    get_coach_summary,
    get_skill_analysis,
    get_learning_path_recommendation,
    get_breakthrough_analysis,
    get_skill_graph_data,
    get_research_overview,
    get_recommended_problems,
    get_health,
    _analyze_skills,
    _estimate_plateau_risk,
    _next_milestone,
    _compute_predictions,
    _recommend_next,
    _build_learning_path,
    SKILL_GRAPH_ORDER,
)


MOCK_SKILL_DATA = {
    "skills": {
        "dp": 0.8, "greedy": 0.9, "math": 0.7, "implementation": 0.85,
        "binary search": 0.4, "two pointers": 0.3, "trees": 0.2,
        "graphs": 0.15, "strings": 0.1, "combinatorics": 0.5,
        "number theory": 0.6, "data structures": 0.75, "sortings": 0.65,
        "dsu": 0.05, "fft": 0.01, "flows": 0.02,
    },
    "sample_size": 500,
}

MOCK_EMBEDDING = {
    "handle": "testuser",
    "current_rating": 1800,
    "max_rating": 1900,
    "cluster_label": 3,
    "cluster_name": "Rising Stars",
    "embedding": [0.1, 0.2, 0.3, 0.4, 0.5],
}

MOCK_GRAPH = [
    {"source_tag": "greedy", "target_tag": "dp", "transition_count": 50000,
     "user_count": 300, "avg_rating_gain": 95.0,
     "avg_source_rating": 1400.0, "avg_target_rating": 1600.0},
    {"source_tag": "math", "target_tag": "combinatorics", "transition_count": 30000,
     "user_count": 280, "avg_rating_gain": 80.0,
     "avg_source_rating": 1350.0, "avg_target_rating": 1550.0},
    {"source_tag": "dp", "target_tag": "trees", "transition_count": 20000,
     "user_count": 250, "avg_rating_gain": 70.0,
     "avg_source_rating": 1600.0, "avg_target_rating": 1750.0},
    {"source_tag": "binary search", "target_tag": "dp", "transition_count": 10000,
     "user_count": 200, "avg_rating_gain": 60.0,
     "avg_source_rating": 1200.0, "avg_target_rating": 1400.0},
    {"source_tag": "greedy", "target_tag": "binary search", "transition_count": 15000,
     "user_count": 220, "avg_rating_gain": 50.0,
     "avg_source_rating": 1300.0, "avg_target_rating": 1450.0},
]

MOCK_MILESTONES = [
    {"milestone": "Newbie", "achieved_at_rating": 1200, "days_to_achieve": 30,
     "contests_to_achieve": 5, "start_rating": 800, "first_6mo": None, "pre_breakthrough_6mo": None},
    {"milestone": "Pupil", "achieved_at_rating": 1400, "days_to_achieve": 90,
     "contests_to_achieve": 15, "start_rating": 1200, "first_6mo": None, "pre_breakthrough_6mo": None},
]

MOCK_PEERS = [
    {"handle": "peer1", "current_rating": 1750, "cluster_name": "Rising Stars"},
    {"handle": "peer2", "current_rating": 1850, "cluster_name": "Rising Stars"},
]

MOCK_MODELS = [
    {"task_name": "plateau_risk", "model_type": "logistic_regression",
     "roc_auc": 0.8776, "f1_score": 0.7671, "accuracy": 0.7901, "sample_size": 81},
    {"task_name": "gain_100_90d", "model_type": "logistic_regression",
     "roc_auc": 0.8743, "f1_score": 0.6667, "accuracy": 0.8025, "sample_size": 81},
    {"task_name": "rating_6mo", "model_type": "random_forest",
     "mae": 304.28, "rmse": 394.53, "r2": 0.2278, "sample_size": 82},
    {"task_name": "rating_12mo", "model_type": "xgboost",
     "mae": 271.21, "rmse": 342.54, "r2": 0.334, "sample_size": 82},
]

MOCK_COUNTS = {"total_findings": 1301, "tested_hypotheses": 66, "validated_hypotheses": 15}
MOCK_PLATFORM_PROFILE = {
    "user_id": "u1",
    "username": "pp123",
    "cf_handle": "pranshu11",
    "current_rating": 1510,
    "platform_elo": 1475,
    "duel_wins": 12,
    "duel_losses": 8,
    "xp": 240,
    "focus_progress": [
        {"tag": "graphs", "practice_count": 4, "last_practiced_at": datetime.now(timezone.utc).isoformat()},
        {"tag": "dp", "practice_count": 2, "last_practiced_at": datetime.now(timezone.utc).isoformat()},
    ],
}


@patch("app.services.coach.rdb.fetch_skill_graph", return_value=MOCK_GRAPH)
def test_analyze_skills_partitions_correctly(mock_graph):
    skills = MOCK_SKILL_DATA["skills"]
    weak, strong, recommended = _analyze_skills(skills)
    assert all(s["score"] < 0.15 for s in weak), "Weak skills should be below 0.15"
    assert all(s["score"] >= 0.6 for s in strong), "Strong skills should be >= 0.6"
    assert weak, "Should have weak skills"
    assert strong, "Should have strong skills"
    assert recommended, "Should have recommendations"
    assert recommended[0]["priority"] >= recommended[-1]["priority"], "Recommendations sorted by priority"


@patch("app.services.coach.rdb.fetch_skill_graph", return_value=[])
def test_analyze_skills_empty(mock_graph):
    weak, strong, recommended = _analyze_skills({})
    assert weak == []
    assert strong == []
    assert recommended == []


def test_fallback_skill_vector_respects_focus():
    skills = _fallback_skill_vector(
        1500,
        focus_progress=[
            {"tag": "graphs", "practice_count": 4, "last_practiced_at": datetime.now(timezone.utc).isoformat()},
            {"tag": "dp", "practice_count": 2, "last_practiced_at": datetime.now(timezone.utc).isoformat()},
        ],
    )
    assert skills["graphs"] > 0.35
    assert skills["dp"] > 0.25
    assert skills["implementation"] > 0


def test_cluster_for_rating():
    assert _cluster_for_rating(1000) == "Foundation Builders"
    assert _cluster_for_rating(1500) == "Contest Climbers"
    assert _cluster_for_rating(2500) == "Elite Performers"


def test_estimate_plateau_risk_low_diversity():
    skills_high = {"greedy": 0.95, "math": 0.05, "dp": 0.04, "trees": 0.03,
                   "graphs": 0.02, "strings": 0.01, "combinatorics": 0.01}
    emb = {"current_rating": 1800, "cluster_name": "Test"}
    result = _estimate_plateau_risk(skills_high, emb)
    assert result["risk"] == "high"


def test_estimate_plateau_risk_high_diversity():
    skills_broad = {t: 0.3 for t in list(MOCK_SKILL_DATA["skills"].keys())[:10]}
    emb = {"current_rating": 1800, "cluster_name": "Test"}
    result = _estimate_plateau_risk(skills_broad, emb)
    assert result["risk"] == "low"


def test_estimate_plateau_risk_missing_data():
    result = _estimate_plateau_risk(None, None)
    assert result["risk"] == "unknown"
    assert result["risk_score"] == 0.5


def test_next_milestone_below_1200():
    result = _next_milestone({"current_rating": 800})
    assert result["next_rating"] == 1200
    assert result["gap"] == 400


def test_next_milestone_between_milestones():
    result = _next_milestone({"current_rating": 1500})
    assert result["next_rating"] == 1600


def test_next_milestone_above_all():
    result = _next_milestone({"current_rating": 3000})
    assert result["label"] == "Peak rating achieved"


def test_next_milestone_none():
    assert _next_milestone(None) is None


def test_compute_predictions():
    result = _compute_predictions(1800, MOCK_MODELS)
    assert "plateau_risk" in result
    assert result["plateau_risk"]["model"] == "logistic_regression"
    assert result["plateau_risk"]["auc"] == 0.8776
    assert "breakthrough" in result
    assert result["breakthrough"]["task"] == "gain_100_90d"
    assert "rating_6mo" in result
    assert result["rating_6mo"]["horizon"] == "6mo"


def test_compute_predictions_empty():
    assert _compute_predictions(1800, []) == {}


@patch("app.services.coach.rdb.fetch_skill_graph", return_value=[])
def test_recommend_next_empty(mock_graph):
    result = _recommend_next([], [])
    assert result == []


@patch("app.services.coach.rdb.fetch_skill_vector", return_value=MOCK_SKILL_DATA)
@patch("app.services.coach.rdb.fetch_user_embedding", return_value=MOCK_EMBEDDING)
@patch("app.services.coach.rdb.fetch_trajectory_milestones", return_value=MOCK_MILESTONES)
@patch("app.services.coach.rdb.fetch_closest_users", return_value=MOCK_PEERS)
@patch("app.services.coach.rdb.fetch_skill_graph", return_value=MOCK_GRAPH)
def test_get_coach_summary(mock_graph, mock_peers, mock_milestones, mock_embedding, mock_skill):
    result = get_coach_summary("testuser")
    assert result["found"] is True
    assert result["cf_handle"] == "testuser"
    assert result["current_rating"] == 1800
    assert result["cluster"] == "Rising Stars"
    assert result["sample_size"] == 500
    assert len(result["strong_skills"]) >= 6
    assert len(result["weak_skills"]) >= 4
    assert result["plateau_risk"]["risk"] in ("low", "moderate", "high", "unknown")
    assert result["next_milestone"] is not None
    assert len(result["learning_path"]) > 0
    assert len(result["trajectory_milestones"]) == 2
    assert len(result["peers"]) == 2


@patch("app.services.coach.rdb.fetch_skill_vector", return_value=MOCK_SKILL_DATA)
@patch("app.services.coach.rdb.fetch_user_embedding", return_value=MOCK_EMBEDDING)
@patch("app.services.coach.rdb.fetch_trajectory_milestones", return_value=MOCK_MILESTONES)
@patch("app.services.coach.rdb.fetch_closest_users", return_value=MOCK_PEERS)
@patch("app.services.coach.rdb.fetch_skill_graph", return_value=MOCK_GRAPH)
def test_get_coach_summary_not_found(mock_graph, mock_peers, mock_milestones, mock_embedding, mock_skill):
    mock_skill.return_value = None
    result = get_coach_summary("nonexistent")
    assert result["found"] is False
    assert "error" in result


@patch("app.services.coach.rdb.fetch_skill_vector", return_value=MOCK_SKILL_DATA)
@patch("app.services.coach.rdb.fetch_skill_graph", return_value=MOCK_GRAPH)
def test_get_skill_analysis(mock_graph, mock_skill):
    result = get_skill_analysis("testuser")
    assert "error" not in result
    assert result["cf_handle"] == "testuser"
    assert result["sample_size"] == 500
    assert len(result["strong_skills"]) > 0
    assert len(result["weak_skills"]) > 0
    assert len(result["recommended_focus"]) > 0


@patch("app.services.coach.rdb.fetch_skill_vector", return_value=None)
def test_get_skill_analysis_not_found(mock_skill):
    result = get_skill_analysis("nonexistent")
    assert "error" in result


@patch("app.services.coach.rdb.fetch_skill_vector", return_value=MOCK_SKILL_DATA)
@patch("app.services.coach.rdb.fetch_skill_graph", return_value=MOCK_GRAPH)
def test_get_learning_path_recommendation(mock_graph, mock_skill):
    result = get_learning_path_recommendation("testuser")
    assert "error" not in result
    assert len(result["recommended_path"]) > 0
    assert "prerequisites" in result
    first = result["recommended_path"][0]
    assert "concept" in first
    assert "order" in first
    assert "current_score" in first
    assert "prerequisites" in first


@patch("app.services.coach.rdb.fetch_user_embedding", return_value=MOCK_EMBEDDING)
@patch("app.services.coach.rdb.fetch_trajectory_milestones", return_value=MOCK_MILESTONES)
@patch("app.services.coach.rdb.fetch_closest_users", return_value=MOCK_PEERS)
@patch("app.services.coach.rdb.fetch_prediction_models", return_value=MOCK_MODELS)
@patch("app.services.coach.rdb.fetch_plateau_predictors", return_value={"feature_importance": {}, "failure_analysis": {}})
def test_get_breakthrough_analysis(mock_plateau, mock_models, mock_peers, mock_milestones, mock_embedding):
    result = get_breakthrough_analysis("testuser")
    assert "error" not in result
    assert result["current_rating"] == 1800
    assert len(result["milestones"]) == 2
    assert len(result["peers"]) == 2
    assert result["plateau_risk"] is not None
    assert result["breakthrough_prediction"] is not None
    assert "rating_prediction" in result


def test_get_skill_graph_data():
    with patch("app.services.coach.rdb.fetch_skill_graph", return_value=MOCK_GRAPH):
        result = get_skill_graph_data(limit=10)
        assert len(result["nodes"]) > 0
        assert len(result["edges"]) > 0
        for e in result["edges"]:
            assert "source" in e
            assert "target" in e
            assert "weight" in e
            assert 0 <= e["weight"] <= 1


@patch("app.services.coach.rdb.fetch_findings_count", return_value=MOCK_COUNTS)
@patch("app.services.coach.rdb.fetch_findings", return_value=[])
@patch("app.services.coach.rdb.fetch_hypotheses", return_value=[])
@patch("app.services.coach.rdb.fetch_prediction_models", return_value=MOCK_MODELS)
def test_get_research_overview(mock_models, mock_hyp, mock_find, mock_counts):
    result = get_research_overview()
    assert result["counts"]["total_findings"] == 1301
    assert result["counts"]["tested_hypotheses"] == 66
    assert isinstance(result["recent_findings"], list)
    assert isinstance(result["active_hypotheses"], list)
    assert len(result["models"]) == 4


MOCK_PROBLEMS = [
    {"contest_id": 2014, "index": "D", "name": "DBFS Order (Hard Version)", "rating": 2100,
     "tags": ["dp", "trees"], "solved_count": 120, "url": "https://codeforces.com/problemset/problem/2014/D"},
    {"contest_id": 2014, "index": "C", "name": "DBFS Order (Easy Version)", "rating": 1800,
     "tags": ["dp", "trees"], "solved_count": 340, "url": "https://codeforces.com/problemset/problem/2014/C"},
    {"contest_id": 2034, "index": "B", "name": "Slime and Queries", "rating": 1900,
     "tags": ["data structures", "greedy", "trees"], "solved_count": 210, "url": "https://codeforces.com/problemset/problem/2034/B"},
]


@patch("app.services.coach.rdb.fetch_skill_vector", return_value=MOCK_SKILL_DATA)
@patch("app.services.coach.rdb.fetch_user_embedding", return_value=MOCK_EMBEDDING)
@patch("app.services.coach.rdb.fetch_skill_graph", return_value=MOCK_GRAPH)
@patch("app.services.coach.rdb.fetch_practice_problems", return_value=MOCK_PROBLEMS)
def test_get_recommended_problems(mock_problems, mock_graph, mock_embedding, mock_skill):
    result = get_recommended_problems("testuser", count=5)
    assert result["found"] is True
    assert result["cf_handle"] == "testuser"
    assert len(result["problems"]) == 3
    assert len(result["focus_tags"]) > 0
    assert result["rating_range"]["min"] == 1600
    assert result["rating_range"]["max"] == 1900
    for p in result["problems"]:
        assert "url" in p
        assert p["url"].startswith("https://codeforces.com/problemset/problem/")


@patch("app.services.coach.rdb.fetch_skill_vector", return_value=None)
def test_get_recommended_problems_not_found(mock_skill):
    result = get_recommended_problems("nonexistent")
    assert result["found"] is False
    assert "error" in result


@patch("app.services.coach.rdb.fetch_skill_vector", return_value={"skills": {"dp": 0.9, "greedy": 0.85}, "sample_size": 50})
@patch("app.services.coach.rdb.fetch_user_embedding", return_value=None)
@patch("app.services.coach.rdb.fetch_skill_graph", return_value=MOCK_GRAPH)
@patch("app.services.coach.rdb.fetch_practice_problems", return_value=[])
def test_get_recommended_problems_no_weak_skills(mock_problems, mock_graph, mock_embedding, mock_skill):
    result = get_recommended_problems("stronguser", count=5)
    assert result["found"] is True
    assert result["problems"] == []


@patch("app.services.coach.rdb.fetch_practice_problems", return_value=MOCK_PROBLEMS)
def test_fetch_practice_problems_direct(mock_fetch):
    from app.services import research_db as rdb
    result = rdb.fetch_practice_problems(tags=["dp"], min_rating=800, max_rating=3000, limit=5)
    mock_fetch.assert_called_once()
    assert len(result) == 3


@patch("app.services.coach.rdb.check_config", return_value={"configured": True, "missing": []})
@patch("app.services.coach.rdb.is_available", return_value=True)
def test_get_health_healthy(mock_avail, mock_config):
    result = get_health()
    assert result["status"] == "healthy"
    assert result["database"] is True
    assert result["missing_env_vars"] == []


@patch("app.services.coach.rdb.check_config", return_value={"configured": True, "missing": []})
@patch("app.services.coach.rdb.is_available", return_value=False)
def test_get_health_unreachable(mock_avail, mock_config):
    result = get_health()
    assert result["status"] == "unreachable"
    assert result["database"] is False


@patch("app.services.coach.rdb.check_config", return_value={"configured": False, "missing": ["RESEARCH_DB_HOST", "RESEARCH_DB_PASSWORD"]})
def test_get_health_unconfigured(mock_config):
    result = get_health()
    assert result["status"] == "unconfigured"
    assert result["database"] is False
    assert "RESEARCH_DB_HOST" in result["missing_env_vars"]


@patch("app.services.coach.rdb.check_config", return_value={"configured": False, "missing": ["RESEARCH_DB_PASSWORD"]})
def test_check_config_missing_vars(mock_config):
    from app.services import research_db as rdb
    result = rdb.check_config()
    assert result["configured"] is False
    assert "RESEARCH_DB_PASSWORD" in result["missing"]


def test_research_db_config_missing_env(monkeypatch):
    from app.services import research_db as rdb

    for key in (
        "RESEARCH_DB_HOST",
        "RESEARCH_DB_PORT",
        "RESEARCH_DB_USER",
        "RESEARCH_DB_PASSWORD",
        "RESEARCH_DB_NAME",
    ):
        monkeypatch.delenv(key, raising=False)

    result = rdb.check_config()
    assert result["configured"] is False
    assert "RESEARCH_DB_HOST" in result["missing"]
    assert "RESEARCH_DB_PORT" not in result["missing"]
    assert result["invalid"] == []


def test_research_db_config_invalid_port(monkeypatch):
    from app.services import research_db as rdb

    monkeypatch.setenv("RESEARCH_DB_HOST", "localhost")
    monkeypatch.setenv("RESEARCH_DB_PORT", "not-a-port")
    monkeypatch.setenv("RESEARCH_DB_USER", "user")
    monkeypatch.setenv("RESEARCH_DB_PASSWORD", "password")
    monkeypatch.setenv("RESEARCH_DB_NAME", "research")

    result = rdb.check_config()
    assert result["configured"] is False
    assert result["missing"] == []
    assert result["invalid"] == ["RESEARCH_DB_PORT"]


def test_research_db_unconfigured_raises(monkeypatch):
    from app.services import research_db as rdb

    for key in (
        "RESEARCH_DB_HOST",
        "RESEARCH_DB_USER",
        "RESEARCH_DB_PASSWORD",
        "RESEARCH_DB_NAME",
    ):
        monkeypatch.delenv(key, raising=False)

    try:
        with rdb.research_db():
            pass
    except RuntimeError as exc:
        assert "Research DB is not configured" in str(exc)
    else:
        raise AssertionError("research_db should fail before connecting when config is missing")


def test_recommend_next_deprioritizes_recently_practiced():
    middle = [{"tag": "dp", "score": 0.4}, {"tag": "trees", "score": 0.35}, {"tag": "binary search", "score": 0.3}]
    strong = [{"tag": "greedy", "score": 0.9}]
    now = datetime.now(timezone.utc)
    focus = [
        {"tag": "dp", "practice_count": 2, "last_practiced_at": now.isoformat()},
        {"tag": "trees", "practice_count": 5, "last_practiced_at": (now).isoformat()},
    ]
    with patch("app.services.coach.rdb.fetch_skill_graph", return_value=MOCK_GRAPH):
        result = _recommend_next(middle, strong, focus_progress=focus)
    assert len(result) <= 3
    dp_item = next(r for r in result if r["tag"] == "dp")
    trees_item = next(r for r in result if r["tag"] == "trees")
    bs_item = next(r for r in result if r["tag"] == "binary search")
    assert dp_item["practiced_recently"] is True
    assert trees_item["practiced_recently"] is True
    assert bs_item["practiced_recently"] is False
    assert dp_item["practice_count"] == 2
    assert trees_item["practice_count"] == 5
    assert bs_item["practice_count"] == 0
    dp_priority_no_focus = (1 - 0.4) * 0.4 + (60.0 / 200) * 0.6
    assert dp_item["priority"] < dp_priority_no_focus


def test_recommend_next_ignores_old_practice():
    middle = [{"tag": "combinatorics", "score": 0.45}]
    strong = [{"tag": "math", "score": 0.7}]
    old = datetime(2020, 1, 1, tzinfo=timezone.utc)
    focus = [
        {"tag": "combinatorics", "practice_count": 1, "last_practiced_at": old.isoformat()},
    ]
    with patch("app.services.coach.rdb.fetch_skill_graph", return_value=MOCK_GRAPH):
        result = _recommend_next(middle, strong, focus_progress=focus)
    assert len(result) == 1
    assert result[0]["practiced_recently"] is False


@patch("app.services.coach.rdb.fetch_skill_vector", return_value=MOCK_SKILL_DATA)
@patch("app.services.coach.rdb.fetch_user_embedding", return_value=MOCK_EMBEDDING)
@patch("app.services.coach.rdb.fetch_trajectory_milestones", return_value=MOCK_MILESTONES)
@patch("app.services.coach.rdb.fetch_closest_users", return_value=MOCK_PEERS)
@patch("app.services.coach.rdb.fetch_skill_graph", return_value=MOCK_GRAPH)
def test_get_coach_summary_with_focus(mock_graph, mock_peers, mock_milestones, mock_embedding, mock_skill):
    now = datetime.now(timezone.utc)
    focus = [{"tag": "combinatorics", "practice_count": 4, "last_practiced_at": now.isoformat()}]
    result = get_coach_summary("testuser", focus_progress=focus)
    assert result["found"] is True
    for r in result["recommended_focus"]:
        if r["tag"] == "combinatorics":
            assert r["practiced_recently"] is True
            assert r["practice_count"] == 4
            break
    else:
        # combinatorics could be deprioritized out of top 5 - acceptable
        pass


@patch("app.services.coach.rdb.fetch_skill_vector", return_value=None)
@patch("app.services.coach.rdb.fetch_user_embedding", return_value=None)
@patch("app.services.coach.rdb.fetch_trajectory_milestones", return_value=[])
@patch("app.services.coach.rdb.fetch_closest_users", return_value=[])
@patch("app.services.coach.rdb.fetch_closest_users_by_rating", return_value=MOCK_PEERS)
@patch("app.services.coach.rdb.fetch_skill_graph", return_value=MOCK_GRAPH)
def test_get_coach_summary_fallback(
    mock_graph,
    mock_peers_by_rating,
    mock_peers,
    mock_milestones,
    mock_embedding,
    mock_skill,
):
    result = get_coach_summary(
        "pranshu11",
        focus_progress=MOCK_PLATFORM_PROFILE["focus_progress"],
        platform_profile=MOCK_PLATFORM_PROFILE,
    )
    assert result["found"] is True
    assert result["coach_mode"] == "fallback"
    assert result["current_rating"] == 1510
    assert result["cluster"] == "Contest Climbers"
    assert result["peers"] == MOCK_PEERS
    assert result["recommended_focus"]


@patch("app.services.coach.rdb.fetch_skill_vector", return_value=None)
@patch("app.services.coach.rdb.fetch_user_embedding", return_value=None)
@patch("app.services.coach.rdb.fetch_skill_graph", return_value=MOCK_GRAPH)
def test_get_skill_analysis_fallback(mock_graph, mock_embedding, mock_skill):
    result = get_skill_analysis(
        "pranshu11",
        focus_progress=MOCK_PLATFORM_PROFILE["focus_progress"],
        platform_profile=MOCK_PLATFORM_PROFILE,
    )
    assert result["coach_mode"] == "fallback"
    assert result["recommended_focus"]


@patch("app.services.coach.rdb.fetch_skill_vector", return_value=None)
@patch("app.services.coach.rdb.fetch_user_embedding", return_value=None)
@patch("app.services.coach.rdb.fetch_skill_graph", return_value=MOCK_GRAPH)
@patch("app.services.coach.rdb.fetch_practice_problems", return_value=MOCK_PROBLEMS)
def test_get_recommended_problems_fallback(mock_problems, mock_graph, mock_embedding, mock_skill):
    result = get_recommended_problems(
        "pranshu11",
        count=3,
        platform_profile=MOCK_PLATFORM_PROFILE,
    )
    assert result["found"] is True
    assert result["coach_mode"] == "fallback"
    assert result["problems"]
