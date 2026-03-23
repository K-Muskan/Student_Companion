"""
Beck Anxiety Inventory (BAI) Analyzer
Scale: 21 items, scored 0-3
Total range: 0-63

Risk thresholds:
    0–21  → Low
   22–35  → Moderate
   36–63  → High (Potentially Concerning)

Symptom categories:
    Physical  : items 1,2,3,6,7,8,11,12,13,15,18,19,20,21  (14 items, max 42)
    Cognitive : items 4,5,14,16                              ( 4 items, max 12)
    Emotional : items 9,10,17                                ( 3 items, max  9)

Reference: Beck et al. (1988), Journal of Consulting and Clinical Psychology, 56(6), 893-897.

NOTE: Question text and response labels live in views.py QUESTIONS list.
      This module handles scoring logic only.
"""

from typing import Dict, List, Any
from datetime import datetime


class AnxietyAnalyzer:

    VALID_ITEMS = set(range(1, 22))  # items 1–21

    CATEGORY_ITEMS = {
        'physical':  [1, 2, 3, 6, 7, 8, 11, 12, 13, 15, 18, 19, 20, 21],
        'cognitive': [4, 5, 14, 16],
        'emotional': [9, 10, 17],
    }

    RISK_THRESHOLDS = [
        (0,  21, 'low',      'Low Anxiety'),
        (22, 35, 'moderate', 'Moderate Anxiety'),
        (36, 63, 'high',     'Potentially Concerning Anxiety'),
    ]

    def __init__(self):
        self.timestamp = datetime.now().isoformat()

    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------

    def analyze_responses(self, scores: Dict[str, int]) -> Dict[str, Any]:
        """
        Args:
            scores: {str(item_id): score (0-3)}  e.g. {'1': 2, '2': 0, ...}
        Returns:
            Complete BAI anxiety assessment report.
        """
        validated          = self._validate_scores(scores)
        total              = sum(validated.values())
        risk_level, risk_label = self._get_risk_level(total)
        category_breakdown = self._category_breakdown(validated)
        top_items          = self._get_highest_items(validated)

        return {
            'timestamp':                    self.timestamp,
            'condition':                    'Anxiety',
            'scale':                        'Beck Anxiety Inventory (BAI)',
            'total_items':                  21,
            'items_completed':              len(validated),
            'total_score':                  total,
            'max_possible_score':           63,
            'score_percentage':             round((total / 63) * 100, 1),
            'risk_level':                   risk_level,
            'risk_label':                   risk_label,
            'interpretation':               self._interpretation_text(risk_level, total),
            'clinical_significance':        risk_level in ('moderate', 'high'),
            'immediate_intervention_needed': risk_level == 'high',
            'confidence':                   self._confidence(validated),
            'evidence': {
                'highest_items':        top_items,
                'category_breakdown':   category_breakdown,
            },
            'critical_items':               self._identify_critical_items(validated),
            'clinical_summary':             self._clinical_summary(total, risk_level, category_breakdown),
            'recommendations':              self._recommendations(total, top_items),
        }

    # ------------------------------------------------------------------
    # INTERNAL HELPERS
    # ------------------------------------------------------------------

    def _validate_scores(self, scores: Dict) -> Dict[int, int]:
        """Returns {item_id: clamped_score} for all 21 items (defaults to 0)."""
        validated = {}
        for item_id in range(1, 22):
            raw = scores.get(str(item_id), scores.get(item_id, 0))
            try:
                score = int(raw)
            except (TypeError, ValueError):
                score = 0
            validated[item_id] = max(0, min(3, score))
        return validated

    def _get_risk_level(self, total: int):
        for lo, hi, level, label in self.RISK_THRESHOLDS:
            if lo <= total <= hi:
                return level, label
        return 'high', 'Potentially Concerning Anxiety'

    def _interpretation_text(self, level: str, total: int) -> str:
        texts = {
            'low': (
                f'Score {total}/63 — Minimal anxiety symptoms. '
                'Continue with healthy coping strategies and self-care.'
            ),
            'moderate': (
                f'Score {total}/63 — Moderate anxiety present. '
                'Consider seeking support from a mental health professional. '
                'Therapy and stress management techniques can be helpful.'
            ),
            'high': (
                f'Score {total}/63 — Potentially concerning anxiety levels. '
                'Professional evaluation and intervention are strongly recommended. '
                'Please reach out to a mental health professional promptly.'
            ),
        }
        return texts.get(level, f'Score {total}/63.')

    def _category_breakdown(self, validated: Dict[int, int]) -> Dict[str, Any]:
        breakdown = {}
        for cat, items in self.CATEGORY_ITEMS.items():
            cat_score = sum(validated.get(i, 0) for i in items)
            cat_max   = len(items) * 3
            breakdown[f'{cat}_symptoms'] = {
                'score':      cat_score,
                'max':        cat_max,
                'percentage': round((cat_score / cat_max) * 100, 1) if cat_max else 0,
            }
        return breakdown

    def _get_highest_items(self, validated: Dict[int, int]) -> List[Dict]:
        """Top 5 highest-scoring items (score > 0 only)."""
        sorted_items = sorted(validated.items(), key=lambda x: x[1], reverse=True)
        return [
            {'item_id': item_id, 'score': score}
            for item_id, score in sorted_items[:5]
            if score > 0
        ]

    def _identify_critical_items(self, validated: Dict[int, int]) -> Dict[str, List]:
        return {
            'severe_items':   [
                {'item': i, 'score': s}
                for i, s in validated.items() if s == 3
            ],
            'moderate_items': [
                {'item': i, 'score': s}
                for i, s in validated.items() if s == 2
            ],
        }

    def _confidence(self, validated: Dict[int, int]) -> float:
        answered = sum(1 for s in validated.values() if s > 0)
        if len(validated) == 21: return 0.97
        if answered >= 19:       return 0.90
        if answered >= 15:       return 0.80
        return 0.65

    def _clinical_summary(self, total: int, level: str, breakdown: Dict) -> str:
        ph  = breakdown.get('physical_symptoms',  {})
        cog = breakdown.get('cognitive_symptoms', {})
        em  = breakdown.get('emotional_symptoms', {})
        return (
            f"BAI Total: {total}/63 ({level.upper()}). "
            f"Physical: {ph.get('score', 0)}/{ph.get('max', 42)} | "
            f"Cognitive: {cog.get('score', 0)}/{cog.get('max', 12)} | "
            f"Emotional: {em.get('score', 0)}/{em.get('max', 9)}."
        )

    def _recommendations(self, total: int, top_items: List[Dict]) -> List[str]:
        if total <= 21:
            recs = [
                'Maintain current healthy lifestyle and coping strategies.',
                'Continue regular exercise and adequate sleep.',
                'Annual mental health check-in recommended.',
            ]
        elif total <= 35:
            recs = [
                'Consider seeking counselling or therapy (CBT is evidence-based for anxiety).',
                'Practice relaxation techniques: deep breathing, progressive muscle relaxation, or mindfulness.',
                'Evaluate and reduce potential triggers (caffeine, workload, sleep deficit).',
                'Maintain regular physical activity and a consistent sleep schedule.',
            ]
        else:
            recs = [
                'URGENT: Schedule an appointment with a mental health professional promptly.',
                'Consider psychiatric evaluation for assessment and possible treatment.',
                'Explore evidence-based treatments: CBT, medication, or a combination.',
                'Use crisis resources if you feel overwhelmed.',
            ]

        # Item-specific additions based on highest scoring items
        # Maps item IDs to symptom keywords and their recommendation
        ITEM_RECS = {
            frozenset([15, 11]): 'Practice diaphragmatic (belly) breathing exercises daily.',
            frozenset([7, 41]):  'Rule out cardiac causes with your doctor if not done recently.',
            frozenset([12, 13]): 'Limit caffeine intake and try grounding techniques (5-4-3-2-1 method).',
            frozenset([6, 19]):  'Ensure adequate hydration, nutrition, and sleep.',
            frozenset([4]):      'Try progressive muscle relaxation or guided yoga.',
        }

        high_items = {item['item_id'] for item in top_items if item['score'] >= 2}
        seen = set(recs)
        for item_set, rec in ITEM_RECS.items():
            if high_items & item_set and rec not in seen:
                recs.append(rec)
                seen.add(rec)

        return recs


# ------------------------------------------------------------------
# Convenience wrapper
# ------------------------------------------------------------------

def analyze_anxiety(scores: Dict[str, int]) -> Dict[str, Any]:
    """
    Args:
        scores: {str(item_id): score (0-3)}
    Returns:
        Full BAI anxiety assessment report.
    """
    return AnxietyAnalyzer().analyze_responses(scores)