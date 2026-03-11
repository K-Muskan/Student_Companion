"""
Beck Anxiety Inventory (BAI) Analyzer
21 items scored 0-3, total range 0-63
Scoring:
  0–21  → Low Anxiety
  22–35 → Moderate Anxiety
  36–63 → Potentially Concerning Anxiety

Reference:
Beck, A. T., Epstein, N., Brown, G., & Steer, R. A. (1988).
Journal of Consulting and Clinical Psychology, 56(6), 893-897.
"""

from typing import Dict, List, Any
from datetime import datetime


class AnxietyAnalyzer:

    BAI_ITEMS = {
        1:  {'description': 'Numbness or tingling',      'category': 'physical'},
        2:  {'description': 'Feeling hot',               'category': 'physical'},
        3:  {'description': 'Wobbliness in legs',        'category': 'physical'},
        4:  {'description': 'Unable to relax',           'category': 'cognitive'},
        5:  {'description': 'Fear of worst happening',   'category': 'cognitive'},
        6:  {'description': 'Dizzy or lightheaded',      'category': 'physical'},
        7:  {'description': 'Heart pounding or racing',  'category': 'physical'},
        8:  {'description': 'Unsteady',                  'category': 'physical'},
        9:  {'description': 'Terrified or afraid',       'category': 'emotional'},
        10: {'description': 'Nervous',                   'category': 'emotional'},
        11: {'description': 'Feeling of choking',        'category': 'physical'},
        12: {'description': 'Hands trembling',           'category': 'physical'},
        13: {'description': 'Shaky or unsteady',         'category': 'physical'},
        14: {'description': 'Fear of losing control',    'category': 'cognitive'},
        15: {'description': 'Difficulty in breathing',   'category': 'physical'},
        16: {'description': 'Fear of dying',             'category': 'cognitive'},
        17: {'description': 'Scared',                    'category': 'emotional'},
        18: {'description': 'Indigestion',               'category': 'physical'},
        19: {'description': 'Faint or lightheaded',      'category': 'physical'},
        20: {'description': 'Face flushed',              'category': 'physical'},
        21: {'description': 'Hot or cold sweats',        'category': 'physical'},
    }

    SCORE_LABELS = {
        0: 'Not at all',
        1: "Mildly — it didn't bother me much",
        2: "Moderately — it wasn't pleasant at times",
        3: 'Severely — it bothered me a lot',
    }

    # Category max scores for reference
    CATEGORY_ITEMS = {
        'physical':  [1, 2, 3, 6, 7, 8, 11, 12, 13, 15, 18, 19, 20, 21],  # 14 items → max 42
        'cognitive': [4, 5, 14, 16],                                         # 4 items  → max 12
        'emotional': [9, 10, 17],                                            # 3 items  → max 9
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
        Main entry point.

        Args:
            scores: {str(item_id): score (0-3)}
                    e.g. {'1': 2, '2': 0, ...}

        Returns:
            Complete BAI anxiety assessment report.
        """
        validated = self._validate_scores(scores)
        total = sum(v['score'] for v in validated.values())
        risk_level, risk_label = self._get_risk_level(total)
        category_breakdown = self._category_breakdown(validated)
        top_symptoms = self._get_highest_symptoms(validated)

        report = {
            'timestamp': self.timestamp,
            # --- consistent keys across all four analyzers ---
            'condition': 'Anxiety',
            'scale': 'Beck Anxiety Inventory (BAI)',
            'total_items': 21,
            'items_completed': len(validated),
            'total_score': total,
            'max_possible_score': 63,
            'score_percentage': round((total / 63) * 100, 1),
            'risk_level': risk_level,           # 'low' | 'moderate' | 'high'
            'risk_label': risk_label,           # human-readable label
            'interpretation': self._interpretation_text(risk_level, total),
            'clinical_significance': risk_level in ('moderate', 'high'),
            'immediate_intervention_needed': risk_level == 'high',
            'confidence': self._confidence(validated),
            # --- detail ---
            'item_scores': validated,
            'evidence': {
                'highest_symptoms': top_symptoms,
                'category_breakdown': category_breakdown,
            },
            'critical_items': self._identify_critical_items(validated),
            'clinical_summary': self._clinical_summary(total, risk_level, category_breakdown),
            'recommendations': self._generate_recommendations(total, top_symptoms),
        }

        return report

    # ------------------------------------------------------------------
    # INTERNAL HELPERS
    # ------------------------------------------------------------------

    def _validate_scores(self, scores: Dict) -> Dict[int, Dict]:
        """Validate and structure item scores."""
        validated = {}
        for item_id in range(1, 22):
            raw = scores.get(str(item_id), scores.get(item_id, 0))
            try:
                score = int(raw)
            except (TypeError, ValueError):
                score = 0
            score = max(0, min(3, score))   # clamp to 0-3

            info = self.BAI_ITEMS[item_id]
            validated[item_id] = {
                'description': info['description'],
                'category': info['category'],
                'score': score,
                'label': self.SCORE_LABELS[score],
                'item_severity': ['None', 'Mild', 'Moderate', 'Severe'][score],
            }
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

    def _category_breakdown(self, validated: Dict[int, Dict]) -> Dict[str, Any]:
        breakdown = {}
        for cat, items in self.CATEGORY_ITEMS.items():
            cat_score = sum(validated[i]['score'] for i in items if i in validated)
            cat_max = len(items) * 3
            breakdown[f'{cat}_symptoms'] = {
                'score': cat_score,
                'max': cat_max,
                'percentage': round((cat_score / cat_max) * 100, 1) if cat_max else 0,
            }
        return breakdown

    def _get_highest_symptoms(self, validated: Dict[int, Dict]) -> List[Dict]:
        sorted_items = sorted(validated.items(), key=lambda x: x[1]['score'], reverse=True)
        return [
            {
                'item_id': item_id,
                'description': data['description'],
                'score': data['score'],
                'label': data['label'],
                'category': data['category'],
            }
            for item_id, data in sorted_items[:5]
            if data['score'] > 0
        ]

    def _identify_critical_items(self, validated: Dict[int, Dict]) -> Dict[str, List]:
        return {
            'severe_items':   [
                {'item': i, 'description': d['description'], 'score': d['score']}
                for i, d in validated.items() if d['score'] == 3
            ],
            'moderate_items': [
                {'item': i, 'description': d['description'], 'score': d['score']}
                for i, d in validated.items() if d['score'] == 2
            ],
        }

    def _confidence(self, validated: Dict[int, Dict]) -> float:
        answered = sum(1 for d in validated.values() if d['score'] > 0)
        if len(validated) == 21: return 0.97
        if answered >= 19:       return 0.90
        if answered >= 15:       return 0.80
        return 0.65

    def _clinical_summary(self, total: int, level: str, breakdown: Dict) -> str:
        ph = breakdown.get('physical_symptoms', {})
        cog = breakdown.get('cognitive_symptoms', {})
        em = breakdown.get('emotional_symptoms', {})
        return (
            f"BAI Total: {total}/63 ({level.upper()}). "
            f"Physical: {ph.get('score', 0)}/{ph.get('max', 42)} | "
            f"Cognitive: {cog.get('score', 0)}/{cog.get('max', 12)} | "
            f"Emotional: {em.get('score', 0)}/{em.get('max', 9)}."
        )

    def _generate_recommendations(self, total: int, top_symptoms: List[Dict]) -> List[str]:
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

        # Symptom-specific additions
        for symptom in top_symptoms:
            desc = symptom['description'].lower()
            if symptom['score'] >= 2:
                if any(w in desc for w in ['breathing', 'choking']):
                    recs.append('Practice diaphragmatic (belly) breathing exercises daily.')
                elif any(w in desc for w in ['heart', 'pounding', 'racing']):
                    recs.append('Rule out cardiac causes with your doctor if not done recently.')
                elif any(w in desc for w in ['trembling', 'shaky']):
                    recs.append('Limit caffeine intake and try grounding techniques (5-4-3-2-1 method).')
                elif any(w in desc for w in ['dizzy', 'faint']):
                    recs.append('Ensure adequate hydration, nutrition, and sleep.')
                elif 'relax' in desc:
                    recs.append('Try progressive muscle relaxation or guided yoga.')

        # Deduplicate
        seen, unique = set(), []
        for r in recs:
            if r not in seen:
                seen.add(r)
                unique.append(r)
        return unique


# ------------------------------------------------------------------
# Convenience function — consistent with other analyzer modules
# ------------------------------------------------------------------

def analyze_anxiety(scores: Dict[str, int]) -> Dict[str, Any]:
    """
    Convenience wrapper.

    Args:
        scores: {str(item_id): score (0-3)}

    Returns:
        Full BAI anxiety assessment report.
    """
    return AnxietyAnalyzer().analyze_responses(scores)