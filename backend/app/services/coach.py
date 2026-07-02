import logging
from datetime import datetime, timezone

from . import research_db as rdb

logger = logging.getLogger(__name__)

FUNDAMENTAL_TAGS = {
    "implementation",
    "greedy",
    "math",
    "sortings",
    "binary search",
    "two pointers",
    "data structures",
}

STRETCH_TAGS = {
    "dp",
    "graphs",
    "trees",
    "combinatorics",
    "number theory",
    "shortest paths",
    "bitmasks",
}

SKILL_GRAPH_ORDER = [
    "implementation",
    "math",
    "greedy",
    "brute force",
    "sortings",
    "binary search",
    "two pointers",
    "constructive algorithms",
    "dfs and similar",
    "trees",
    "graphs",
    "dp",
    "data structures",
    "shortest paths",
    "combinatorics",
    "number theory",
    "strings",
    "bitmasks",
    "divide and conquer",
    "games",
    "hashing",
    "probabilities",
    "geometry",
    "matrices",
    "flows",
    "dsu",
    "meet-in-the-middle",
    "fft",
    "ternary search",
    "2-sat",
    "graph matchings",
    "expression parsing",
    "chinese remainder theorem",
    "schedules",
]


def _milestone_targets() -> list[int]:
    return [1200, 1400, 1600, 1900, 2100, 2400, 2600]


def _current_rating(platform_profile: dict | None) -> int:
    if not platform_profile:
        return 1200
    rating = (
        platform_profile.get("current_rating")
        or platform_profile.get("platform_elo")
        or 1200
    )
    return max(800, int(rating))


def _cluster_for_rating(rating: int) -> str:
    if rating < 1200:
        return "Foundation Builders"
    if rating < 1400:
        return "Ladder Learners"
    if rating < 1700:
        return "Contest Climbers"
    if rating < 2000:
        return "Structured Solvers"
    if rating < 2400:
        return "Advanced Specialists"
    return "Elite Performers"


def _sample_size_from_focus(focus_progress: list[dict] | None) -> int:
    if not focus_progress:
        return 0
    return sum(max(0, int(item.get("practice_count", 0))) for item in focus_progress)


def _rating_band_targets(current_rating: int) -> list[str]:
    if current_rating < 1200:
        return ["implementation", "math", "greedy", "sortings", "binary search"]
    if current_rating < 1400:
        return ["implementation", "greedy", "math", "binary search", "two pointers"]
    if current_rating < 1700:
        return ["dp", "graphs", "data structures", "binary search", "greedy"]
    if current_rating < 2000:
        return ["dp", "trees", "graphs", "data structures", "combinatorics"]
    if current_rating < 2400:
        return ["trees", "graphs", "dp", "number theory", "combinatorics"]
    return ["graphs", "dp", "number theory", "combinatorics", "bitmasks"]


def _recent_form(platform_profile: dict | None) -> dict:
    profile = platform_profile or {}
    recent_results = [str(result).lower() for result in profile.get("recent_results", []) if result]
    recent_duel_count = int(profile.get("recent_duel_count") or len(recent_results) or 0)
    recent_win_rate = profile.get("recent_win_rate")
    delta_sum = int(profile.get("recent_delta_sum") or 0)
    current_streak = int(profile.get("current_streak") or 0)
    longest_streak = int(profile.get("longest_streak") or 0)

    if recent_duel_count == 0:
        trend = "cold-start"
    elif recent_win_rate is not None and recent_win_rate >= 0.6 and delta_sum > 0:
        trend = "surging"
    elif recent_win_rate is not None and recent_win_rate <= 0.4 and delta_sum < 0:
        trend = "slipping"
    else:
        trend = "steady"

    return {
        "recent_duel_count": recent_duel_count,
        "recent_win_rate": recent_win_rate,
        "recent_delta_sum": delta_sum,
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "trend": trend,
        "recent_results": recent_results,
    }


def _elite_benchmark(current_rating: int, skills: dict[str, float]) -> dict:
    try:
        top_users = rdb.fetch_top_user_skill_benchmarks(limit=100)
    except Exception:
        top_users = []

    tag_totals: dict[str, float] = {}
    tag_counts: dict[str, int] = {}
    higher_rated_count = 0

    for user in top_users:
        user_rating = user.get("current_rating")
        if user_rating is None or int(user_rating) <= current_rating:
            continue
        higher_rated_count += 1
        for tag, value in (user.get("skills") or {}).items():
            try:
                score = float(value)
            except (TypeError, ValueError):
                continue
            tag_totals[tag] = tag_totals.get(tag, 0.0) + score
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    if not tag_totals:
        target_tags = _rating_band_targets(current_rating)
        return {
            "sample_size": 0,
            "target_tags": [
                {"tag": tag, "average_score": None, "gap": None}
                for tag in target_tags
            ],
            "insight": f"At {current_rating}, progress usually comes from broadening into {', '.join(target_tags[:3])}.",
        }

    target_tags = []
    for tag, total in sorted(tag_totals.items(), key=lambda item: item[1] / max(1, tag_counts[item[0]]), reverse=True):
        avg_score = total / max(1, tag_counts[tag])
        user_score = float(skills.get(tag, 0.0))
        target_tags.append(
            {
                "tag": tag,
                "average_score": round(avg_score, 3),
                "gap": round(max(0.0, avg_score - user_score), 3),
            }
        )

    target_tags = sorted(
        target_tags,
        key=lambda item: (item["gap"] or 0, item["average_score"] or 0),
        reverse=True,
    )[:5]
    leading_tags = ", ".join(item["tag"] for item in target_tags[:3])
    return {
        "sample_size": higher_rated_count,
        "target_tags": target_tags,
        "insight": f"Higher-rated players around the top cohort separate themselves with stronger depth in {leading_tags}.",
    }


def _practice_strategy(
    current_rating: int,
    recommended: list[dict],
    platform_profile: dict | None,
    elite_benchmark: dict,
) -> dict:
    trend = _recent_form(platform_profile)
    target_tags = [item["tag"] for item in elite_benchmark.get("target_tags", [])[:3]]
    top_focus = [item["tag"] for item in recommended[:3]]
    selected_tags = top_focus or target_tags or _rating_band_targets(current_rating)[:3]

    if trend["trend"] == "cold-start":
        headline = "Start with a rating-band practice lane"
        summary = (
            f"Newer profiles improve faster when practice is organized around a few repeatable tags instead of random problem picks. "
            f"For your band, build reps in {', '.join(selected_tags)}."
        )
    elif trend["trend"] == "slipping":
        headline = "Stabilize form before pushing difficulty"
        summary = (
            f"Your recent duel form is down, so the coach is pulling you back toward tags that restore contest consistency: "
            f"{', '.join(selected_tags)}."
        )
    elif trend["trend"] == "surging":
        headline = "Use momentum to add one harder tag"
        summary = (
            f"Your recent form is positive. Keep one reliable tag, then add stretch work in {', '.join(selected_tags[:2])} "
            f"to convert momentum into rating growth."
        )
    else:
        headline = "Practice where rating movement usually comes from"
        summary = (
            f"At your current level, rating gains usually come from structured repetition in {', '.join(selected_tags)} "
            f"rather than solving more of the same comfort-zone problems."
        )

    return {
        "headline": headline,
        "summary": summary,
        "target_tags": selected_tags,
        "trend": trend["trend"],
    }


def _fallback_skill_vector(
    current_rating: int,
    focus_progress: list[dict] | None = None,
) -> dict[str, float]:
    skills = {tag: 0.06 for tag in SKILL_GRAPH_ORDER}

    base_weights = {
        "implementation": 0.32,
        "greedy": 0.24,
        "math": 0.18,
        "sortings": 0.18,
        "binary search": 0.12,
        "two pointers": 0.12,
        "data structures": 0.1,
        "graphs": 0.08,
        "dp": 0.08,
        "strings": 0.06,
    }
    rating_lift = min(0.28, max(0, current_rating - 900) / 3500)
    for tag, base in base_weights.items():
        skills[tag] = min(0.9, base + rating_lift)

    if current_rating >= 1400:
        skills["dp"] = min(0.9, skills["dp"] + 0.12)
        skills["graphs"] = min(0.9, skills["graphs"] + 0.1)
        skills["data structures"] = min(0.9, skills["data structures"] + 0.08)
    if current_rating >= 1800:
        skills["trees"] = min(0.9, skills["trees"] + 0.12)
        skills["combinatorics"] = min(0.9, skills["combinatorics"] + 0.08)
        skills["number theory"] = min(0.9, skills["number theory"] + 0.08)
    if current_rating >= 2100:
        skills["shortest paths"] = min(0.9, skills["shortest paths"] + 0.08)
        skills["bitmasks"] = min(0.9, skills["bitmasks"] + 0.08)

    now = datetime.now(timezone.utc)
    for item in focus_progress or []:
        tag = str(item.get("tag", "")).strip().lower()
        if not tag:
            continue
        if tag not in skills:
            skills[tag] = 0.08

        count = max(0, int(item.get("practice_count", 0)))
        boost = min(0.45, 0.08 * count)
        last_practiced_at = item.get("last_practiced_at")
        if last_practiced_at:
            try:
                last_dt = datetime.fromisoformat(last_practiced_at)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                age_days = max(0, (now - last_dt).days)
                if age_days <= 7:
                    boost += 0.12
                elif age_days <= 30:
                    boost += 0.06
            except (TypeError, ValueError):
                pass
        skills[tag] = min(0.95, skills[tag] + boost)

    return {tag: round(score, 4) for tag, score in skills.items()}


def _fallback_milestones(current_rating: int) -> list[dict]:
    milestones = []
    previous = 800
    for target in _milestone_targets():
        if target > current_rating:
            break
        milestones.append(
            {
                "milestone": f"Reach {target}",
                "achieved_at_rating": target,
                "days_to_achieve": None,
                "contests_to_achieve": None,
                "start_rating": previous,
            }
        )
        previous = target
    return milestones


def _fallback_coach_context(
    cf_handle: str,
    focus_progress: list[dict] | None = None,
    platform_profile: dict | None = None,
) -> dict | None:
    if not platform_profile:
        return None

    current_rating = _current_rating(platform_profile)
    skills = _fallback_skill_vector(current_rating, focus_progress)
    try:
        peers = rdb.fetch_closest_users_by_rating(current_rating, n=5)
    except Exception:
        peers = []
    milestones = _fallback_milestones(current_rating)
    elite_benchmark = _elite_benchmark(current_rating, skills)
    performance_snapshot = _recent_form(platform_profile)

    return {
        "found": True,
        "coach_mode": "fallback",
        "cf_handle": cf_handle,
        "current_rating": current_rating,
        "cluster": _cluster_for_rating(current_rating),
        "skill_vector": skills,
        "trajectory_milestones": milestones,
        "peers": peers,
        "sample_size": _sample_size_from_focus(focus_progress),
        "elite_benchmark": elite_benchmark,
        "performance_snapshot": performance_snapshot,
        "embedding": {
            "current_rating": current_rating,
            "cluster_name": _cluster_for_rating(current_rating),
        },
    }


def get_coach_summary(
    cf_handle: str,
    focus_progress: list[dict] | None = None,
    platform_profile: dict | None = None,
) -> dict:
    skill_data = rdb.fetch_skill_vector(cf_handle)
    embedding = rdb.fetch_user_embedding(cf_handle)
    milestones = rdb.fetch_trajectory_milestones(cf_handle)
    peers = rdb.fetch_closest_users(cf_handle)

    if skill_data:
        coach_mode = "exact"
        skills = skill_data["skills"]
        current_rating = embedding["current_rating"] if embedding else None
        cluster = embedding["cluster_name"] if embedding else None
        sample_size = skill_data["sample_size"]
        elite_benchmark = _elite_benchmark(current_rating or 1200, skills)
        performance_snapshot = _recent_form(platform_profile)
    else:
        fallback = _fallback_coach_context(
            cf_handle,
            focus_progress=focus_progress,
            platform_profile=platform_profile,
        )
        if not fallback:
            return {"error": "user not found in research database", "found": False}
        coach_mode = fallback["coach_mode"]
        skills = fallback["skill_vector"]
        embedding = fallback["embedding"]
        milestones = fallback["trajectory_milestones"]
        peers = fallback["peers"]
        current_rating = fallback["current_rating"]
        cluster = fallback["cluster"]
        sample_size = fallback["sample_size"]
        elite_benchmark = fallback["elite_benchmark"]
        performance_snapshot = fallback["performance_snapshot"]

    weak, strong, recommended = _analyze_skills(skills, focus_progress, platform_profile, elite_benchmark)
    plateau_risk = _estimate_plateau_risk(skills, embedding)
    next_milestone = _next_milestone(embedding)
    learning_path = _build_learning_path(weak, strong, recommended)
    practice_strategy = _practice_strategy(current_rating or 1200, recommended, platform_profile, elite_benchmark)

    return {
        "found": True,
        "coach_mode": coach_mode,
        "cf_handle": cf_handle,
        "current_rating": current_rating,
        "cluster": cluster,
        "skill_vector": skills,
        "strong_skills": strong,
        "weak_skills": weak,
        "recommended_focus": recommended,
        "plateau_risk": plateau_risk,
        "next_milestone": next_milestone,
        "learning_path": learning_path,
        "trajectory_milestones": milestones,
        "peers": peers,
        "sample_size": sample_size,
        "elite_benchmark": elite_benchmark,
        "performance_snapshot": performance_snapshot,
        "practice_strategy": practice_strategy,
    }


def get_skill_analysis(
    cf_handle: str,
    focus_progress: list[dict] | None = None,
    platform_profile: dict | None = None,
) -> dict:
    skill_data = rdb.fetch_skill_vector(cf_handle)
    if skill_data:
        coach_mode = "exact"
        skills = skill_data["skills"]
        sample_size = skill_data["sample_size"]
    else:
        fallback = _fallback_coach_context(
            cf_handle,
            focus_progress=focus_progress,
            platform_profile=platform_profile,
        )
        if not fallback:
            return {"error": "user not found"}
        coach_mode = fallback["coach_mode"]
        skills = fallback["skill_vector"]
        sample_size = fallback["sample_size"]

    elite_benchmark = _elite_benchmark(_current_rating(platform_profile), skills)
    weak, strong, recommended = _analyze_skills(skills, focus_progress, platform_profile, elite_benchmark)

    return {
        "cf_handle": cf_handle,
        "coach_mode": coach_mode,
        "skill_vector": skills,
        "strong_skills": strong,
        "weak_skills": weak,
        "recommended_focus": recommended,
        "sample_size": sample_size,
    }


def get_learning_path_recommendation(
    cf_handle: str,
    platform_profile: dict | None = None,
) -> dict:
    skill_data = rdb.fetch_skill_vector(cf_handle)
    if skill_data:
        coach_mode = "exact"
        skills = skill_data["skills"]
    else:
        fallback = _fallback_coach_context(
            cf_handle,
            focus_progress=(platform_profile or {}).get("focus_progress"),
            platform_profile=platform_profile,
        )
        if not fallback:
            return {"error": "user not found"}
        coach_mode = fallback["coach_mode"]
        skills = fallback["skill_vector"]

    weak, strong, recommended = _analyze_skills(skills)
    graph = rdb.fetch_skill_graph(limit=100)
    path = _build_learning_path(weak, strong, recommended, graph)

    return {
        "cf_handle": cf_handle,
        "coach_mode": coach_mode,
        "recommended_path": path,
        "prerequisites": _prerequisites_for(path, graph),
    }


def get_breakthrough_analysis(
    cf_handle: str,
    platform_profile: dict | None = None,
) -> dict:
    milestones = rdb.fetch_trajectory_milestones(cf_handle)
    embedding = rdb.fetch_user_embedding(cf_handle)
    peers = rdb.fetch_closest_users(cf_handle)

    if embedding or milestones:
        coach_mode = "exact"
    else:
        fallback = _fallback_coach_context(
            cf_handle,
            focus_progress=(platform_profile or {}).get("focus_progress"),
            platform_profile=platform_profile,
        )
        if not fallback:
            return {"error": "user not found"}
        coach_mode = fallback["coach_mode"]
        embedding = fallback["embedding"]
        milestones = fallback["trajectory_milestones"]
        peers = fallback["peers"]

    current = embedding["current_rating"] if embedding else None
    current = current or (milestones[-1]["achieved_at_rating"] if milestones else 0)
    models = rdb.fetch_prediction_models()
    plateau_data = rdb.fetch_plateau_predictors()

    predictions = _compute_predictions(current, models)

    return {
        "cf_handle": cf_handle,
        "coach_mode": coach_mode,
        "current_rating": current,
        "milestones": milestones,
        "peers": peers,
        "rating_prediction": predictions.get("rating"),
        "breakthrough_prediction": predictions.get("breakthrough"),
        "plateau_risk": predictions.get("plateau_risk"),
        "plateau_factors": plateau_data,
    }


def get_skill_graph_data(limit: int = 100) -> dict:
    transitions = rdb.fetch_skill_graph(limit=limit)
    nodes = sorted(set(t["source_tag"] for t in transitions) | set(t["target_tag"] for t in transitions))
    max_trans = max(t["transition_count"] for t in transitions) if transitions else 1

    edges = []
    for t in transitions:
        if t["source_tag"] != t["target_tag"]:
            edges.append({
                "source": t["source_tag"],
                "target": t["target_tag"],
                "weight": t["transition_count"] / max_trans,
                "count": t["transition_count"],
                "avg_rating_gain": round(t["avg_rating_gain"], 1),
            })

    return {"nodes": nodes, "edges": edges}


def get_research_overview() -> dict:
    counts = rdb.fetch_findings_count()
    findings = rdb.fetch_findings(limit=10)
    hypotheses = rdb.fetch_hypotheses(limit=10)
    models = rdb.fetch_prediction_models()

    return {
        "counts": counts,
        "recent_findings": findings,
        "active_hypotheses": hypotheses,
        "models": models,
    }


def get_research_findings(category: str | None = None, limit: int = 20) -> list[dict]:
    return rdb.fetch_findings(category=category, limit=limit)


def get_research_hypotheses(limit: int = 20) -> list[dict]:
    return rdb.fetch_hypotheses(limit=limit)


def get_research_categories() -> list[dict[str, int]]:
    return rdb.fetch_findings_categories()


def _analyze_skills(
    skills: dict[str, float],
    focus_progress: list[dict] | None = None,
    platform_profile: dict | None = None,
    elite_benchmark: dict | None = None,
) -> tuple[list[dict], list[dict], list[dict]]:
    sorted_skills = sorted(skills.items(), key=lambda x: x[1], reverse=True)
    weak = [{"tag": t, "score": round(s, 4)} for t, s in sorted_skills if s < 0.15]
    strong = [{"tag": t, "score": round(s, 4)} for t, s in sorted_skills if s >= 0.6]
    middle = [{"tag": t, "score": round(s, 4)} for t, s in sorted_skills if 0.15 <= s < 0.6]

    recommended = _recommend_next(middle, strong, focus_progress, platform_profile, elite_benchmark)

    return weak, strong, recommended


def _recommend_next(
    middle: list[dict],
    strong: list[dict],
    focus_progress: list[dict] | None = None,
    platform_profile: dict | None = None,
    elite_benchmark: dict | None = None,
) -> list[dict]:
    strong_tags = {s["tag"] for s in strong}
    graph = rdb.fetch_skill_graph(limit=100)
    trend = _recent_form(platform_profile)
    benchmark_targets = {
        item["tag"]: item for item in (elite_benchmark or {}).get("target_tags", [])
    }

    focus_map: dict[str, dict] = {}
    if focus_progress:
        for fp in focus_progress:
            focus_map[fp["tag"].lower().strip()] = fp

    now = datetime.now(timezone.utc)

    candidates = []
    for t in middle:
        gain = 0.0
        count = 0
        for edge in graph:
            if edge["source_tag"] == t["tag"] and edge["target_tag"] not in strong_tags:
                gain += edge["avg_rating_gain"]
                count += 1
            if edge["target_tag"] == t["tag"] and edge["source_tag"] in strong_tags:
                gain += edge["avg_rating_gain"] * 0.5
                count += 1
        avg_gain = gain / count if count else 0
        priority = (1 - t["score"]) * 0.4 + (avg_gain / 200) * 0.6

        if t["tag"] in benchmark_targets:
            priority += min(0.25, float(benchmark_targets[t["tag"]].get("gap") or 0))

        if trend["trend"] == "slipping" and t["tag"] in FUNDAMENTAL_TAGS:
            priority += 0.12
        elif trend["trend"] == "surging" and t["tag"] in STRETCH_TAGS:
            priority += 0.12
        elif trend["trend"] == "cold-start" and t["tag"] in _rating_band_targets(_current_rating(platform_profile)):
            priority += 0.1

        practiced_recently = False
        pcount = 0
        matched = focus_map.get(t["tag"].lower().strip())
        if matched:
            pcount = matched.get("practice_count", 0)
            last_str = matched.get("last_practiced_at")
            if last_str:
                try:
                    last_dt = datetime.fromisoformat(last_str)
                    if (now - last_dt).days < 7:
                        priority *= 0.5
                        practiced_recently = True
                except (ValueError, TypeError):
                    pass
            if pcount > 3:
                priority *= 0.75

        candidates.append({
            **t,
            "estimated_gain": round(avg_gain, 1),
            "priority": round(priority, 4),
            "practiced_recently": practiced_recently,
            "practice_count": pcount,
            "benchmark_gap": round(float(benchmark_targets.get(t["tag"], {}).get("gap") or 0), 3),
        })

    candidates.sort(key=lambda x: x["priority"], reverse=True)
    return candidates[:5]


def _build_learning_path(
    weak: list[dict], strong: list[dict], recommended: list[dict],
    graph: list[dict] | None = None,
) -> list[dict]:
    if graph is None:
        graph = rdb.fetch_skill_graph(limit=100)

    strong_tags = {s["tag"] for s in strong}

    path = []
    for rec in recommended:
        prereqs = [
            e["source_tag"] for e in graph
            if e["target_tag"] == rec["tag"]
            and e["source_tag"] in strong_tags
        ]
        path.append({
            "concept": rec["tag"],
            "current_score": rec["score"],
            "estimated_gain": rec["estimated_gain"],
            "prerequisites": prereqs,
            "order": len(path) + 1,
        })

    for w in weak[:3]:
        if w["tag"] not in {p["concept"] for p in path}:
            path.append({
                "concept": w["tag"],
                "current_score": w["score"],
                "estimated_gain": 0,
                "prerequisites": [],
                "order": len(path) + 1 + 100,
            })

    path.sort(key=lambda x: x["order"])
    return path


def _prerequisites_for(path: list[dict], graph: list[dict]) -> dict[str, list[str]]:
    prereq_map: dict[str, list[str]] = {}
    for node in path:
        prereq_map[node["concept"]] = [
            e["source_tag"] for e in graph
            if e["target_tag"] == node["concept"]
        ]
    return prereq_map


def _estimate_plateau_risk(
    skills: dict[str, float] | None,
    embedding: dict | None,
) -> dict:
    if not skills or not embedding:
        return {"risk": "unknown", "risk_score": 0.5}

    skill_values = list(skills.values())
    skill_diversity = len([s for s in skill_values if s > 0.1]) / len(skill_values)
    top_skill = max(skill_values) if skill_values else 0

    if skill_diversity < 0.2 and top_skill > 0.7:
        risk = "high"
        score = 0.8
        reason = "Narrow skill focus with high single-skill specialization"
    elif skill_diversity < 0.3 and top_skill > 0.5:
        risk = "moderate"
        score = 0.5
        reason = "Below-average skill breadth for this rating level"
    elif skill_diversity > 0.5:
        risk = "low"
        score = 0.2
        reason = "Good skill diversity across multiple categories"
    else:
        risk = "low"
        score = 0.3
        reason = "Healthy skill distribution"

    return {"risk": risk, "risk_score": round(score, 2), "reason": reason, "skill_diversity": round(skill_diversity, 2)}


def _compute_predictions(current_rating: int, models: list[dict]) -> dict:
    result: dict = {}

    for m in models:
        task = m.get("task_name", "")
        if "plateau" in task:
            result["plateau_risk"] = {
                "model": m["model_type"],
                "auc": m.get("roc_auc"),
                "f1": m.get("f1_score"),
                "accuracy": m.get("accuracy"),
            }
        elif "gain" in task or "breakthrough" in task:
            result["breakthrough"] = {
                "model": m["model_type"],
                "auc": m.get("roc_auc"),
                "f1": m.get("f1_score"),
                "task": task,
            }
        elif task.startswith("rating_"):
            horizon = task.split("_")[1]
            result[task] = {
                "model": m["model_type"],
                "mae": m.get("mae"),
                "rmse": m.get("rmse"),
                "r2": m.get("r2"),
                "horizon": horizon,
            }

    return result


def get_health() -> dict:
    config = rdb.check_config()
    if not config["configured"]:
        return {
            "status": "unconfigured",
            "database": False,
            "missing_env_vars": config["missing"],
            "invalid_env_vars": config.get("invalid", []),
        }
    available = rdb.is_available()
    return {
        "status": "healthy" if available else "unreachable",
        "database": available,
        "missing_env_vars": [],
        "invalid_env_vars": [],
    }


def get_recommended_problems(
    cf_handle: str,
    count: int = 5,
    platform_profile: dict | None = None,
) -> dict:
    skill_data = rdb.fetch_skill_vector(cf_handle)
    if skill_data:
        coach_mode = "exact"
        embedding = rdb.fetch_user_embedding(cf_handle)
        skills = skill_data["skills"]
        focus_progress = None
    else:
        embedding = None
        fallback = _fallback_coach_context(
            cf_handle,
        focus_progress=(platform_profile or {}).get("focus_progress"),
        platform_profile=platform_profile,
    )
        if not fallback:
            return {"error": "user not found", "found": False}
        coach_mode = fallback["coach_mode"]
        skills = fallback["skill_vector"]
        embedding = fallback["embedding"]
        focus_progress = (platform_profile or {}).get("focus_progress")

    elite_benchmark = _elite_benchmark(_current_rating(platform_profile), skills)
    weak, strong, recommended = _analyze_skills(skills, focus_progress, platform_profile, elite_benchmark)

    if not recommended:
        return {"cf_handle": cf_handle, "coach_mode": coach_mode, "problems": [], "found": True}

    focus_tags = [r["tag"] for r in recommended[:3]]
    current_rating = embedding["current_rating"] if embedding else None

    min_rating = max(800, (current_rating or 1200) - 200)
    max_rating = (current_rating or 1200) + 100

    problems = rdb.fetch_practice_problems(
        tags=focus_tags,
        min_rating=min_rating,
        max_rating=max_rating,
        limit=count,
    )

    return {
        "cf_handle": cf_handle,
        "coach_mode": coach_mode,
        "problems": problems,
        "focus_tags": focus_tags,
        "rating_range": {"min": min_rating, "max": max_rating},
        "found": True,
    }


def _next_milestone(embedding: dict | None) -> dict | None:
    if not embedding:
        return None
    rating = embedding.get("current_rating") or 0
    for m in _milestone_targets():
        if rating < m:
            gap = m - rating
            return {"next_rating": m, "gap": gap, "label": f"Reach {m}"}
    return {"next_rating": rating, "gap": 0, "label": "Peak rating achieved"}
