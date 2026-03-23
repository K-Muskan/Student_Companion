"""
Perceived Stress Scale — 10 Item (PSS-10) Analyzer
Scale: 10 items, scored 0-4
Total range: 0-40 (higher = more stress)

Reverse-scored items: 4, 5, 7, 8
    Formula: adjusted = 4 - raw_response

Subscales:
    Perceived Helplessness : items 1, 2, 3, 6, 9, 10  (max 24)
    Lack of Self-Efficacy  : items 4, 5, 7, 8          (max 16)

Risk thresholds (Cohen & Janicki-Deverts, 2012):
    0–13  → Low
   14–26  → Moderate
   27–40  → High

NOTE: Question text and response labels live in views.py QUESTIONS list.
      This module handles scoring logic only.
"""

from typing import Dict, List, Tuple, Any
from datetime import datetime


class StressAnalyzer:

    VALID_ITEMS  = set(range(1, 11))   # items 1–10
    REVERSE_ITEMS = {4, 5, 7, 8}

    SUBSCALES = {
        'perceived_helplessness': [1, 2, 3, 6, 9, 10],
        'lack_of_self_efficacy':  [4, 5, 7, 8],
    }

    RISK_THRESHOLDS = [
        (0,  13, 'low',      'Low stress.'),
        (14, 26, 'moderate', 'Moderate stress.'),
        (27, 40, 'high',     'High perceived stress.'),
    ]

    def __init__(self):
        self.timestamp = datetime.now().isoformat()

    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------

    def analyze(self, raw_scores: Dict[int, int]) -> Dict[str, Any]:
        """
        Args:
            raw_scores: {item_number (1-10): raw_response (0-4)}
                        Raw responses as selected on screen.
                        Reverse scoring is applied internally.
        Returns:
            Full PSS-10 stress assessment report dict.
        """
        validated_raw = self._validate_scores(raw_scores)
        adjusted      = self._apply_reverse_scoring(validated_raw)
        total         = sum(adjusted.values())

        risk_level, risk_label, interpretation = self._get_risk_level(total)
        subscale_scores = self._calculate_subscales(adjusted)
        critical        = self._identify_critical_items(adjusted)

        return {
            'timestamp':                    self.timestamp,
            'condition':                    'Stress',
            'scale':                        'Perceived Stress Scale — 10 Item (PSS-10)',
            'total_items':                  10,
            'items_completed':              len(adjusted),
            'total_score':                  total,
            'max_possible_score':           40,
            'score_percentage':             round((total / 40) * 100, 1),
            'average_item_score':           round(total / len(adjusted), 2) if adjusted else 0,
            'risk_level':                   risk_level,
            'risk_label':                   risk_label,
            'interpretation':               interpretation,
            'subscales':                    subscale_scores,
            'critical_items':               critical,
            'immediate_intervention_needed': risk_level == 'high',
            'confidence':                   self._confidence(len(adjusted)),
            'clinical_summary':             self._clinical_summary(total, risk_level, subscale_scores),
            'recommendations':              self._recommendations(risk_level, subscale_scores),
        }

    # ------------------------------------------------------------------
    # INTERNAL HELPERS
    # ------------------------------------------------------------------

    def _validate_scores(self, scores: Dict) -> Dict[int, int]:
        validated = {}
        for k, v in scores.items():
            try:
                item  = int(k)
                score = int(v)
            except (TypeError, ValueError):
                continue
            if item not in self.VALID_ITEMS:
                continue
            if not (0 <= score <= 4):
                continue
            validated[item] = score
        return validated

    def _apply_reverse_scoring(self, raw: Dict[int, int]) -> Dict[int, int]:
        """Items 4,5,7,8: adjusted = 4 - raw"""
        return {
            item: (4 - score if item in self.REVERSE_ITEMS else score)
            for item, score in raw.items()
        }

    def _get_risk_level(self, total: int) -> Tuple[str, str, str]:
        for lo, hi, level, label in self.RISK_THRESHOLDS:
            if lo <= total <= hi:
                return level, label, self._interpretation_text(level, total)
        return 'high', 'High perceived stress.', self._interpretation_text('high', total)

    def _interpretation_text(self, level: str, total: int) -> str:
        texts = {
            'low':      f'Score {total}/40 — Low perceived stress. Student is managing demands well.',
            'moderate': f'Score {total}/40 — Moderate perceived stress. Some stressors are affecting the student.',
            'high':     f'Score {total}/40 — High perceived stress. Student is struggling significantly with life demands.',
        }
        return texts.get(level, f'Score {total}/40.')

    def _calculate_subscales(self, adjusted: Dict[int, int]) -> Dict[str, Any]:
        subscales = {}
        for name, items in self.SUBSCALES.items():
            item_scores   = {i: adjusted[i] for i in items if i in adjusted}
            total         = sum(item_scores.values())
            max_score     = len(items) * 4
            avg           = round(total / len(item_scores), 2) if item_scores else 0
            subscales[name] = {
                'items':          items,
                'score':          total,
                'max_score':      max_score,
                'average':        avg,
                'items_answered': len(item_scores),
                'label':          name.replace('_', ' ').title(),
            }
        return subscales

    def _identify_critical_items(self, adjusted: Dict[int, int]) -> Dict[str, List]:
        """Items with adjusted score 4 = high stress, 3 = moderate stress."""
        critical = {
            'high_stress_items':     [],
            'moderate_stress_items': [],
        }
        for item_num, adj_score in adjusted.items():
            entry = {'item': item_num, 'adjusted_score': adj_score}
            if adj_score == 4:
                critical['high_stress_items'].append(entry)
            elif adj_score == 3:
                critical['moderate_stress_items'].append(entry)
        return critical

    def _confidence(self, n_answered: int) -> float:
        if n_answered == 10: return 0.97
        if n_answered >= 9:  return 0.90
        if n_answered >= 7:  return 0.75
        if n_answered >= 5:  return 0.60
        return 0.40

    def _clinical_summary(self, total: int, level: str, subscales: Dict[str, Any]) -> str:
        ph = subscales.get('perceived_helplessness', {})
        se = subscales.get('lack_of_self_efficacy', {})

        summary = (
            f"PSS-10 Total: {total}/40 ({level.upper()}). "
            f"Perceived Helplessness: {ph.get('score', 'N/A')}/24 | "
            f"Lack of Self-Efficacy: {se.get('score', 'N/A')}/16. "
        )
        if level == 'high':
            summary += "Student is experiencing high perceived stress with significant difficulty managing life demands."
        elif level == 'moderate':
            summary += "Student is experiencing moderate stress. Some areas of life demand are challenging."
        else:
            summary += "Student appears to be managing stress within a healthy range."
        return summary

    def _recommendations(self, level: str, subscales: Dict[str, Any]) -> List[str]:
        base = {
            'low': [
                'Continue current stress management strategies.',
                'Maintain healthy sleep, exercise, and social routines.',
                'Annual well-being check-in recommended.',
            ],
            'moderate': [
                'Introduce structured stress management techniques (e.g. mindfulness, time management).',
                'Encourage regular physical activity and adequate sleep.',
                'Explore peer support or brief counselling if needed.',
                'Re-assess in 4 weeks.',
            ],
            'high': [
                'URGENT: Refer student to counselling or mental health support services.',
                'Assess for co-occurring depression or anxiety.',
                'Implement a structured stress reduction programme.',
                'Review academic workload and personal demands with student.',
                'Follow-up within 1–2 weeks.',
            ],
        }

        recs = list(base.get(level, []))

        ph = subscales.get('perceived_helplessness', {})
        se = subscales.get('lack_of_self_efficacy', {})
        if ph.get('average', 0) >= 3:
            recs.append('Perceived Helplessness is elevated — explore sense of control and coping strategies.')
        if se.get('average', 0) >= 3:
            recs.append('Low Self-Efficacy detected — consider confidence-building and problem-solving support.')

        return recs


# ------------------------------------------------------------------
# Convenience wrapper
# ------------------------------------------------------------------

def analyze_stress(raw_scores: Dict[int, int]) -> Dict[str, Any]:
    """
    Args:
        raw_scores: {item_number (1-10): raw_response (0-4)}
                    Raw values as user selected — reverse scoring handled internally.
    Returns:
        Full PSS-10 stress assessment report.
    """
    return StressAnalyzer().analyze(raw_scores)