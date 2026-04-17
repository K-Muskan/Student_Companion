from django.db import connection
from django.utils import timezone


def _fetchall_as_dicts(cursor):
    columns = [col[0] for col in cursor.description]
    rows = cursor.fetchall()
    result = []
    for row in rows:
        d = {}
        for col, val in zip(columns, row):
            if hasattr(val, 'isoformat'):
                d[col] = val.isoformat()
            else:
                d[col] = val
        result.append(d)
    return result


def get_score_trend(user_id):
    """Line chart: depression/anxiety/stress over time."""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT assessment_id, session_date, depression_score, anxiety_score,
                   stress_score, depression_risk_level, anxiety_risk_level,
                   stress_risk_level, overall_trend, dominant_emotion, comparison_summary
            FROM analytics_score_trend
            WHERE user_id = %s
            ORDER BY session_date ASC
        """, [user_id])
        return _fetchall_as_dicts(cursor)


def get_facial_emotion_history(user_id):
    """Donut chart: dominant facial emotion per scale per session."""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT assessment_id, session_date, scale,
                   overall_dominant_emotion, distress_ratio, total_frames
            FROM analytics_facial_emotion
            WHERE user_id = %s AND overall_dominant_emotion IS NOT NULL
                  AND overall_dominant_emotion != ''
            ORDER BY session_date ASC
        """, [user_id])
        return _fetchall_as_dicts(cursor)


import json # Ensure this is at the top of analytics.py

def get_feeling_scores(user_id):
    """
    Bar chart: NLP feeling scores from latest session.
    """
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT questionnaire_project_final_score
            FROM analytics_feeling_scores
            WHERE user_id = %s
            ORDER BY session_date DESC
            LIMIT 1
        """, [user_id])
        row = cursor.fetchone()
        
    if not row or not row[0]:
        return {}

    # If your database returns a string, parse it. If it's already a dict, use it directly.
    scores = row[0]
    if isinstance(scores, str):
        try:
            scores = json.loads(scores)
        except:
            return {}

    # Sort scores descending so the highest feeling is at the top
    sorted_scores = dict(sorted(scores.items(), key=lambda item: item[1], reverse=True))

    return {
        "labels": list(sorted_scores.keys()),
        "values": list(sorted_scores.values())
    }

def get_latest_recommendations(user_id):
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT 
                ar.assessment_id,
                a.finalized_at AS session_date,
                ar.recommendations_json,
                ar.comparison_summary,
                ar.overall_trend,
                ar.dominant_emotion
            FROM "Questionaire_project_analysisresult" ar
            JOIN "Questionaire_project_assessment" a ON a.id = ar.assessment_id
            WHERE a.user_id = %s 
              AND a.is_completed = true
              AND a.finalized_at IS NOT NULL
            ORDER BY a.finalized_at DESC
            LIMIT 1
        """, [user_id])
        rows = _fetchall_as_dicts(cursor)
        return rows[0] if rows else {}


def get_dashboard_summary(user_id):
    """
    Metric cards: risk level, current mood, wellness scores from latest session.
    """
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT user_id, assessment_id, last_session_date,
                   depression_score, anxiety_score, stress_score,
                   depression_risk_level, anxiety_risk_level, stress_risk_level,
                   dominant_emotion, overall_trend, comparison_summary,
                   recommendations_json, scale_emotions
            FROM analytics_dashboard_summary
            WHERE user_id = %s
        """, [user_id])
        rows = _fetchall_as_dicts(cursor)
        return rows[0] if rows else {}


def get_session_list(user_id):
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT
                a.id AS assessment_id,
                a.finalized_at,
                a.depression_score,
                a.anxiety_score,
                a.stress_score,
                ar.dominant_emotion,
                ar.overall_trend,
                mr.report_html,  -- Add this line
                CASE WHEN mr.id IS NOT NULL THEN true ELSE false END AS has_report
            FROM "Questionaire_project_assessment" a
            LEFT JOIN "Questionaire_project_analysisresult" ar ON ar.assessment_id = a.id
            LEFT JOIN "Questionaire_project_msereport" mr ON mr.assessment_id = a.id
            WHERE a.user_id = %s AND a.is_completed = true
            ORDER BY a.finalized_at DESC
        """, [user_id])
        return _fetchall_as_dicts(cursor)

def get_stats(user_id):
    """
    Quick stat cards: sessions completed, downloads, days active, streak.
    """
    with connection.cursor() as cursor:
        # Sessions completed
        cursor.execute("""
            SELECT COUNT(*) AS total_sessions,
                   MIN(finalized_at) AS first_session,
                   MAX(finalized_at) AS latest_session
            FROM "Questionaire_project_assessment"
            WHERE user_id = %s AND is_completed = true
                  AND finalized_at IS NOT NULL
        """, [user_id])
        session_stats = _fetchall_as_dicts(cursor)[0]

    with connection.cursor() as cursor:
        # Downloads count
        cursor.execute("""
            SELECT COUNT(*) AS total_downloads
            FROM "Login_downloadlog"
            WHERE user_id = %s
        """, [user_id])
        download_row = cursor.fetchone()
        total_downloads = download_row[0] if download_row else 0

    with connection.cursor() as cursor:
        # Days active
        cursor.execute("""
            SELECT COUNT(DISTINCT activity_date) AS days_active
            FROM "Login_useractivitylog"
            WHERE user_id = %s
        """, [user_id])
        days_row = cursor.fetchone()
        days_active = days_row[0] if days_row else 0

    with connection.cursor() as cursor:
        # Session streak: consecutive days with a completed assessment
        cursor.execute("""
            WITH session_days AS (
                SELECT DISTINCT DATE(finalized_at) AS session_day
                FROM "Questionaire_project_assessment"
                WHERE user_id = %s AND is_completed = true
                      AND finalized_at IS NOT NULL
                ORDER BY session_day DESC
            ),
            numbered AS (
                SELECT session_day,
                       ROW_NUMBER() OVER (ORDER BY session_day DESC) AS rn
                FROM session_days
            ),
            streak AS (
                SELECT session_day, rn,
                       session_day + (rn - 1) * INTERVAL '1 day' AS grp
                FROM numbered
            )
            SELECT COUNT(*) AS streak_days
            FROM streak
            WHERE grp = (SELECT grp FROM streak WHERE rn = 1)
        """, [user_id])
        streak_row = cursor.fetchone()
        streak_days = streak_row[0] if streak_row else 0

    return {
        'total_sessions': session_stats.get('total_sessions', 0),
        'first_session': session_stats.get('first_session'),
        'latest_session': session_stats.get('latest_session'),
        'total_downloads': total_downloads,
        'days_active': days_active,
        'streak_days': streak_days,
    }


def get_wellness_factors(user_id):
    """
    Wellness Factors bars: convert raw scores to percentages.
    Depression max = 63, Anxiety max = 63, Stress max = 40
    Lower score = better wellness, so we invert: wellness = 100 - (score/max * 100)
    """
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT depression_score, anxiety_score, stress_score
            FROM analytics_dashboard_summary
            WHERE user_id = %s
        """, [user_id])
        row = cursor.fetchone()

    if not row or row[0] is None:
        return {
            'depression_wellness': None,
            'anxiety_wellness': None,
            'stress_wellness': None,
        }

    depression_score, anxiety_score, stress_score = row

    def to_wellness(score, max_score):
        if score is None:
            return None
        return round(100 - (score / max_score * 100), 1)

    return {
        'depression_wellness': to_wellness(depression_score, 63),
        'anxiety_wellness': to_wellness(anxiety_score, 63),
        'stress_wellness': to_wellness(stress_score, 40),
        'depression_score': depression_score,
        'anxiety_score': anxiety_score,
        'stress_score': stress_score,
    }

