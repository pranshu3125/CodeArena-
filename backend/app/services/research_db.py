import json
import logging
import os
from contextlib import contextmanager
from typing import Any, Optional

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)

_REQUIRED_ENV_VARS = [
    "RESEARCH_DB_HOST",
    "RESEARCH_DB_USER",
    "RESEARCH_DB_PASSWORD",
    "RESEARCH_DB_NAME",
]


def _port() -> int:
    raw = os.getenv("RESEARCH_DB_PORT", "5432")
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise RuntimeError("RESEARCH_DB_PORT must be an integer")


def _config() -> dict[str, Any]:
    return {
        "host": os.getenv("RESEARCH_DB_HOST"),
        "port": _port(),
        "user": os.getenv("RESEARCH_DB_USER"),
        "password": os.getenv("RESEARCH_DB_PASSWORD"),
        "dbname": os.getenv("RESEARCH_DB_NAME"),
    }


def check_config() -> dict:
    missing = [v for v in _REQUIRED_ENV_VARS if not os.getenv(v)]
    invalid = []
    try:
        _port()
    except RuntimeError:
        invalid.append("RESEARCH_DB_PORT")
    if missing:
        return {"configured": False, "missing": missing, "invalid": invalid}
    if invalid:
        return {"configured": False, "missing": [], "invalid": invalid}
    return {"configured": True, "missing": [], "invalid": []}


def is_available() -> bool:
    try:
        with research_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            return True
    except (psycopg2.Error, RuntimeError):
        return False


@contextmanager
def research_db():
    cfg = check_config()
    if not cfg["configured"]:
        missing = ", ".join(cfg.get("missing", []))
        invalid = ", ".join(cfg.get("invalid", []))
        reason = ", ".join(x for x in (missing, invalid) if x)
        raise RuntimeError(f"Research DB is not configured: {reason}")
    try:
        conn = psycopg2.connect(**_config())
    except psycopg2.Error as e:
        logger.error("Research DB connection failed: %s", e)
        raise
    try:
        yield conn
        conn.commit()
    except psycopg2.Error as e:
        conn.rollback()
        logger.error("Research DB query failed: %s", e)
        raise
    finally:
        conn.close()


def fetch_user_id(cf_handle: str) -> Optional[int]:
    with research_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM public.users WHERE LOWER(cf_handle) = LOWER(%s)", (cf_handle,))
        row = cur.fetchone()
        return row[0] if row else None


def fetch_skill_vector(cf_handle: str) -> Optional[dict[str, float]]:
    user_id = fetch_user_id(cf_handle)
    if not user_id:
        return None
    with research_db() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT skills, sample_size FROM public.skill_vectors WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        if not row:
            return None
        skills = row["skills"]
        if isinstance(skills, str):
            skills = json.loads(skills)
        return {
            "skills": skills,
            "sample_size": row["sample_size"],
        }


def fetch_skill_graph(limit: int = 50) -> list[dict[str, Any]]:
    with research_db() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT source_tag, target_tag, transition_count, user_count, avg_rating_gain,
                   avg_source_rating, avg_target_rating
            FROM public.tag_transitions
            WHERE source_tag != target_tag
            ORDER BY transition_count DESC
            LIMIT %s
        """, (limit,))
        return [dict(row) for row in cur.fetchall()]


def fetch_user_embedding(cf_handle: str) -> Optional[dict[str, Any]]:
    user_id = fetch_user_id(cf_handle)
    if not user_id:
        return None
    with research_db() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT handle, current_rating, max_rating, cluster_label, cluster_name, embedding
            FROM public.user_embeddings WHERE user_id = %s
        """, (user_id,))
        row = cur.fetchone()
        if not row:
            return None
        emb = row["embedding"]
        if isinstance(emb, str):
            emb = json.loads(emb)
        return dict(row) | {"embedding": emb}


def fetch_plateau_predictors() -> list[dict[str, Any]]:
    with research_db() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT feature_importance, failure_analysis
            FROM public.prediction_runs
            WHERE task_name = 'plateau_risk'
            ORDER BY id DESC LIMIT 1
        """)
        row = cur.fetchone()
        if not row:
            return []
        fi = row["feature_importance"]
        if isinstance(fi, str):
            fi = json.loads(fi)
        fa = row["failure_analysis"]
        if isinstance(fa, str):
            fa = json.loads(fa)
        return {"feature_importance": fi, "failure_analysis": fa}


def fetch_prediction_models() -> list[dict[str, Any]]:
    with research_db() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT id, task_name, task_type, model_type, accuracy, f1_score, roc_auc,
                   mae, rmse, r2, sample_size, feature_importance
            FROM public.prediction_runs
            ORDER BY id
        """)
        rows = []
        for row in cur.fetchall():
            r = dict(row)
            if r.get("feature_importance") and isinstance(r["feature_importance"], str):
                r["feature_importance"] = json.loads(r["feature_importance"])
            rows.append(r)
        return rows


def fetch_findings(category: Optional[str] = None, limit: int = 20) -> list[dict[str, Any]]:
    with research_db() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if category:
            cur.execute("""
                SELECT id, title, description, metric, category, confidence_score, supporting_data, source_loop
                FROM public.research_findings
                WHERE category = %s
                ORDER BY id DESC LIMIT %s
            """, (category, limit))
        else:
            cur.execute("""
                SELECT id, title, description, metric, category, confidence_score, supporting_data, source_loop
                FROM public.research_findings
                ORDER BY id DESC LIMIT %s
            """, (limit,))
        rows = []
        for row in cur.fetchall():
            r = dict(row)
            if r.get("supporting_data") and isinstance(r["supporting_data"], str):
                r["supporting_data"] = json.loads(r["supporting_data"])
            rows.append(r)
        return rows


def fetch_hypotheses(limit: int = 20) -> list[dict[str, Any]]:
    with research_db() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT id, question, status, priority, category, source_finding_id,
                   evidence, test_result, confidence, tested_at
            FROM public.research_hypotheses
            ORDER BY priority DESC, id DESC
            LIMIT %s
        """, (limit,))
        rows = []
        for row in cur.fetchall():
            r = dict(row)
            if r.get("evidence") and isinstance(r["evidence"], str):
                r["evidence"] = json.loads(r["evidence"])
            rows.append(r)
        return rows


def fetch_trajectory_milestones(cf_handle: str) -> list[dict[str, Any]]:
    with research_db() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT milestone, achieved_at_rating, days_to_achieve, contests_to_achieve,
                   start_rating, first_6mo, pre_breakthrough_6mo
            FROM public.trajectory_milestones
            WHERE LOWER(handle) = LOWER(%s)
            ORDER BY achieved_at_rating ASC
        """, (cf_handle,))
        rows = []
        for row in cur.fetchall():
            r = dict(row)
            for field in ("first_6mo", "pre_breakthrough_6mo"):
                if r.get(field) and isinstance(r[field], str):
                    r[field] = json.loads(r[field])
            rows.append(r)
        return rows


def fetch_user_rating_history(cf_handle: str) -> list[dict[str, Any]]:
    user_id = fetch_user_id(cf_handle)
    if not user_id:
        return []
    with research_db() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT contest_name, old_rating, new_rating, rating_change, rank, contest_time
            FROM public.rating_history
            WHERE user_id = %s
            ORDER BY contest_time ASC
        """, (user_id,))
        return [dict(row) for row in cur.fetchall()]


def fetch_closest_users(cf_handle: str, n: int = 5) -> list[dict[str, Any]]:
    user_id = fetch_user_id(cf_handle)
    if not user_id:
        return []
    with research_db() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT ue2.handle, ue2.current_rating, ue2.cluster_name
            FROM public.user_embeddings ue1
            JOIN public.user_embeddings ue2 ON ue1.cluster_label = ue2.cluster_label
            WHERE ue1.user_id = %s AND ue2.user_id != %s
            ORDER BY ue2.current_rating DESC
            LIMIT %s
        """, (user_id, user_id, n))
        return [dict(row) for row in cur.fetchall()]


def fetch_closest_users_by_rating(current_rating: int, n: int = 5) -> list[dict[str, Any]]:
    with research_db() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            """
            SELECT handle, current_rating, cluster_name
            FROM public.user_embeddings
            WHERE current_rating IS NOT NULL
            ORDER BY ABS(current_rating - %s), current_rating DESC
            LIMIT %s
            """,
            (current_rating, n),
        )
        return [dict(row) for row in cur.fetchall()]


def fetch_top_user_skill_benchmarks(limit: int = 100) -> list[dict[str, Any]]:
    with research_db() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            """
            SELECT ue.handle, ue.current_rating, ue.cluster_name, sv.skills, sv.sample_size
            FROM public.user_embeddings ue
            JOIN public.skill_vectors sv ON sv.user_id = ue.user_id
            WHERE ue.current_rating IS NOT NULL
            ORDER BY ue.current_rating DESC
            LIMIT %s
            """,
            (limit,),
        )
        rows = []
        for row in cur.fetchall():
            record = dict(row)
            skills = record.get("skills")
            if isinstance(skills, str):
                record["skills"] = json.loads(skills)
            rows.append(record)
        return rows


def fetch_findings_categories() -> list[dict[str, int]]:
    with research_db() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT category, COUNT(*) as count
            FROM public.research_findings
            GROUP BY category
            ORDER BY count DESC
        """)
        return [dict(row) for row in cur.fetchall()]


def fetch_practice_problems(
    tags: list[str],
    min_rating: int = 800,
    max_rating: int = 3500,
    limit: int = 10,
) -> list[dict[str, Any]]:
    with research_db() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if tags:
            cur.execute("""
                SELECT contest_id, index, name, rating, tags, solved_count
                FROM public.problems
                WHERE tags && %s
                  AND rating BETWEEN %s AND %s
                ORDER BY solved_count DESC
                LIMIT %s
            """, (tags, min_rating, max_rating, limit))
        else:
            cur.execute("""
                SELECT contest_id, index, name, rating, tags, solved_count
                FROM public.problems
                WHERE rating BETWEEN %s AND %s
                ORDER BY solved_count DESC
                LIMIT %s
            """, (min_rating, max_rating, limit))
        rows = []
        for row in cur.fetchall():
            r = dict(row)
            if r["rating"] is None:
                continue
            cf_url = f"https://codeforces.com/problemset/problem/{r['contest_id']}/{r['index']}"
            r["url"] = cf_url
            rows.append(r)
        return rows


def fetch_findings_count() -> dict[str, int]:
    with research_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM public.research_findings")
        total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM public.research_hypotheses WHERE status = 'validated'")
        validated = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM public.research_hypotheses WHERE status = 'tested'")
        tested = cur.fetchone()[0]
        return {"total_findings": total, "tested_hypotheses": tested, "validated_hypotheses": validated}
