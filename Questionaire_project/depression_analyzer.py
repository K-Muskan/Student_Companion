"""
Beck's Depression Inventory (BDI) Analyzer
Scale: 21 items, each scored 0-3
Total range: 0-63

Scoring thresholds (official Beck):
    0–10  → Normal
   11–16  → Mild
   17–20  → Borderline
   21–30  → Moderate
   31–40  → Severe
   41–63  → Extreme

NOTE: Question text and response labels live in views.py QUESTIONS list.
      This module handles scoring logic only.
"""

from typing import Dict, List, Tuple, Any
from datetime import datetime


class DepressionAnalyzer:

    VALID_ITEMS = set(range(1, 22))  # items 1–21

    RISK_THRESHOLDS = [
        (0,  10, 'normal',     'Normal range — these ups and downs are considered normal.'),
        (11, 16, 'mild',       'Mild mood disturbance.'),
        (17, 20, 'borderline', 'Borderline clinical depression.'),
        (21, 30, 'moderate',   'Moderate depression.'),
        (31, 40, 'severe',     'Severe depression.'),
        (41, 63, 'extreme',    'Extreme depression.'),
    ]

    def __init__(self):
        self.timestamp = datetime.now().isoformat()

    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------

    def analyze(self, scores: Dict[int, int]) -> Dict[str, Any]:
        """
        Args:
            scores: {item_number (1-21): score (0-3)}
        Returns:
            Full BDI depression assessment report dict.
        """
        validated = self._validate_scores(scores)
        total = sum(validated.values())
        risk_level, risk_label, interpretation = self._get_risk_level(total)
        critical = self._identify_critical_items(validated)

        return {
            'timestamp':                    self.timestamp,
            'condition':                    'Depression',
            'scale':                        "Beck's Depression Inventory (BDI)",
            'total_items':                  21,
            'items_completed':              len(validated),
            'total_score':                  total,
            'max_possible_score':           63,
            'score_percentage':             round((total / 63) * 100, 1),
            'risk_level':                   risk_level,
            'risk_label':                   risk_label,
            'interpretation':               interpretation,
            'critical_items':               critical,
            'immediate_intervention_needed': (
                risk_level in ('severe', 'extreme') or bool(critical['suicide_risk'])
            ),
            'confidence':                   self._confidence(len(validated)),
            'clinical_summary':             self._clinical_summary(total, risk_level),
            'recommendations':              self._recommendations(risk_level, critical),
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
            if not (0 <= score <= 3):
                continue
            validated[item] = score
        return validated

    def _get_risk_level(self, total: int) -> Tuple[str, str, str]:
        for lo, hi, level, label in self.RISK_THRESHOLDS:
            if lo <= total <= hi:
                return level, label, self._interpretation_text(level, total)
        return 'extreme', 'Extreme depression.', self._interpretation_text('extreme', total)

    def _interpretation_text(self, level: str, total: int) -> str:
        texts = {
            'normal':     f'Score {total}/63 — Minimal depressive symptoms. Normal range.',
            'mild':       f'Score {total}/63 — Mild mood disturbance present. Monitoring recommended.',
            'borderline': f'Score {total}/63 — Borderline clinical depression. Professional evaluation advised.',
            'moderate':   f'Score {total}/63 — Moderate depression identified. Mental health support recommended.',
            'severe':     f'Score {total}/63 — Severe depression. Urgent professional intervention required.',
            'extreme':    f'Score {total}/63 — Extreme depression. Immediate professional intervention required.',
        }
        return texts.get(level, f'Score {total}/63.')

    def _identify_critical_items(self, scores: Dict[int, int]) -> Dict[str, List]:
        """
        Flags item 9 (suicidal ideation) regardless of score level.
        Also collects severe (score=3) and moderate (score=2) items.
        """
        critical = {
            'suicide_risk':   [],
            'severe_items':   [],
            'moderate_items': [],
        }
        for item_num, score in scores.items():
            entry = {'item': item_num, 'score': score}
            if item_num == 9 and score > 0:
                entry['urgency'] = 'CRITICAL' if score >= 2 else 'HIGH'
                critical['suicide_risk'].append(entry)
            elif score == 3:
                critical['severe_items'].append(entry)
            elif score == 2:
                critical['moderate_items'].append(entry)
        return critical

    def _confidence(self, n_answered: int) -> float:
        if n_answered == 21: return 0.97
        if n_answered >= 19: return 0.90
        if n_answered >= 16: return 0.80
        if n_answered >= 10: return 0.65
        return 0.40

    def _clinical_summary(self, total: int, level: str) -> str:
        summaries = {
            'normal':     'Student shows minimal depressive symptoms. No clinical concern at this time.',
            'mild':       'Student shows mild depressive features. Mood monitoring and lifestyle support advised.',
            'borderline': 'Student presents with borderline clinical depression. A professional evaluation is recommended.',
            'moderate':   'Student presents with moderate depression. Professional mental health support is warranted.',
            'severe':     'Student presents with severe depression. Urgent referral to mental health services is required.',
            'extreme':    'Student presents with extreme depression. Immediate clinical intervention is required.',
        }
        return f"BDI Total: {total}/63 — " + summaries.get(level, '')

    def _recommendations(self, level: str, critical: Dict) -> List[str]:
        base = {
            'normal': [
                'Maintain healthy sleep, exercise and social routines.',
                'Annual mental health check-in recommended.',
                'Seek support promptly if mood deteriorates.',
            ],
            'mild': [
                'Monitor mood over the next 2–4 weeks.',
                'Encourage regular physical activity and social engagement.',
                'Provide psychoeducation on mood management.',
                'Re-assess if symptoms persist or worsen.',
            ],
            'borderline': [
                'Schedule a professional mental health evaluation.',
                'Implement structured lifestyle modifications.',
                'Consider brief counselling or peer support.',
                'Follow-up assessment in 2 weeks.',
            ],
            'moderate': [
                'Refer to mental health professional for assessment.',
                'Discuss psychotherapy options (e.g. CBT).',
                'Evaluate whether medication consultation is appropriate.',
                'Establish a regular support and monitoring plan.',
            ],
            'severe': [
                'URGENT: Refer to mental health professional immediately.',
                'Assess suicide risk and activate safety planning.',
                'Consider psychiatric evaluation for medication management.',
                'Involve student support services and family/guardian if appropriate.',
            ],
            'extreme': [
                'IMMEDIATE ACTION REQUIRED: Contact mental health crisis services.',
                'Do not leave student unsupported — arrange immediate supervision.',
                'Initiate emergency psychiatric evaluation.',
                'Activate institution safeguarding protocol.',
            ],
        }

        recs = list(base.get(level, []))

        if critical['suicide_risk']:
            urgency = critical['suicide_risk'][0].get('urgency', 'HIGH')
            recs.insert(
                0,
                f"⚠️ SUICIDE RISK FLAGGED ({urgency}): "
                f"Immediate safety assessment required regardless of total score."
            )
        return recs


# ------------------------------------------------------------------
# Convenience wrapper
# ------------------------------------------------------------------

def analyze_depression(scores: Dict[int, int]) -> Dict[str, Any]:
    """
    Args:
        scores: {item_number: score}  e.g. {1: 2, 2: 0, 3: 1, ...}
    Returns:
        Full BDI depression assessment report.
    """
    return DepressionAnalyzer().analyze(scores)