"""
Perceived Stress Scale - 10 Item (PSS-10) Analyzer
Scale: 10 items, scored 0-4
Total range: 0-40 (higher = more stress)
Items 4, 5, 7, 8 are REVERSE scored
Two subscales:
  - Perceived Helplessness: items 1, 2, 3, 6, 9, 10
  - Lack of Self-Efficacy:  items 4, 5, 7, 8
Integrated for Student Companion Django project
"""

from typing import Dict, List, Tuple, Any
from datetime import datetime


class StressAnalyzer:

    PSS_ITEMS = {
        1: {
            'dimension': 'Upset by unexpected events',
            'question': 'been upset because of something that happened unexpectedly?',
            'reverse_scored': False,
            'subscale': 'perceived_helplessness',
            'responses': {
                0: 'Never',
                1: 'Almost Never',
                2: 'Sometimes',
                3: 'Fairly Often',
                4: 'Very Often',
            }
        },
        2: {
            'dimension': 'Unable to control important things',
            'question': 'felt that you were unable to control the important things in your life?',
            'reverse_scored': False,
            'subscale': 'perceived_helplessness',
            'responses': {
                0: 'Never',
                1: 'Almost Never',
                2: 'Sometimes',
                3: 'Fairly Often',
                4: 'Very Often',
            }
        },
        3: {
            'dimension': 'Feeling nervous and stressed',
            'question': 'felt nervous and "stressed"?',
            'reverse_scored': False,
            'subscale': 'perceived_helplessness',
            'responses': {
                0: 'Never',
                1: 'Almost Never',
                2: 'Sometimes',
                3: 'Fairly Often',
                4: 'Very Often',
            }
        },
        4: {
            'dimension': 'Confidence in handling problems',
            'question': 'felt confident about your ability to handle your personal problems?',
            'reverse_scored': True,   # Never=4, Almost Never=3, Sometimes=2, Fairly Often=1, Very Often=0
            'subscale': 'lack_of_self_efficacy',
            'responses': {
                0: 'Very Often',
                1: 'Fairly Often',
                2: 'Sometimes',
                3: 'Almost Never',
                4: 'Never',
            }
        },
        5: {
            'dimension': 'Things going your way',
            'question': 'felt that things were going your way?',
            'reverse_scored': True,
            'subscale': 'lack_of_self_efficacy',
            'responses': {
                0: 'Very Often',
                1: 'Fairly Often',
                2: 'Sometimes',
                3: 'Almost Never',
                4: 'Never',
            }
        },
        6: {
            'dimension': 'Unable to cope with demands',
            'question': 'found that you could not cope with all the things that you had to do?',
            'reverse_scored': False,
            'subscale': 'perceived_helplessness',
            'responses': {
                0: 'Never',
                1: 'Almost Never',
                2: 'Sometimes',
                3: 'Fairly Often',
                4: 'Very Often',
            }
        },
        7: {
            'dimension': 'Able to control irritations',
            'question': 'been able to control irritations in your life?',
            'reverse_scored': True,
            'subscale': 'lack_of_self_efficacy',
            'responses': {
                0: 'Very Often',
                1: 'Fairly Often',
                2: 'Sometimes',
                3: 'Almost Never',
                4: 'Never',
            }
        },
        8: {
            'dimension': 'On top of things',
            'question': 'felt that you were on top of things?',
            'reverse_scored': True,
            'subscale': 'lack_of_self_efficacy',
            'responses': {
                0: 'Very Often',
                1: 'Fairly Often',
                2: 'Sometimes',
                3: 'Almost Never',
                4: 'Never',
            }
        },
        9: {
            'dimension': 'Angered by things outside control',
            'question': 'been angered because of things that were outside of your control?',
            'reverse_scored': False,
            'subscale': 'perceived_helplessness',
            'responses': {
                0: 'Never',
                1: 'Almost Never',
                2: 'Sometimes',
                3: 'Fairly Often',
                4: 'Very Often',
            }
        },
        10: {
            'dimension': 'Difficulties piling up uncontrollably',
            'question': 'felt difficulties were piling up so high that you could not overcome them?',
            'reverse_scored': False,
            'subscale': 'perceived_helplessness',
            'responses': {
                0: 'Never',
                1: 'Almost Never',
                2: 'Sometimes',
                3: 'Fairly Often',
                4: 'Very Often',
            }
        },
    }

    # PSS-10 risk thresholds
    # Based on Cohen & Janicki-Deverts (2012) population norms
    RISK_THRESHOLDS = [
        (0,  13, 'low',      'Low stress.'),
        (14, 26, 'moderate', 'Moderate stress.'),
        (27, 40, 'high',     'High perceived stress.'),
    ]

    # Reverse-scored items (user selects 0-4 on screen, we flip before summing)
    REVERSE_ITEMS = {4, 5, 7, 8}

    # Subscale item groupings
    SUBSCALES = {
        'perceived_helplessness': [1, 2, 3, 6, 9, 10],
        'lack_of_self_efficacy':  [4, 5, 7, 8],
    }

    def __init__(self):
        self.timestamp = datetime.now().isoformat()

    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------

    def analyze(self, raw_scores: Dict[int, int]) -> Dict[str, Any]:
        """
        Main entry point.

        Args:
            raw_scores: {item_number (1-10): raw_response (0-4)}
                        Raw responses as the user selected them on screen.
                        Reverse scoring is handled internally.

        Returns:
            Full PSS-10 stress assessment report dict.
        """
        validated_raw = self._validate_scores(raw_scores)
        adjusted = self._apply_reverse_scoring(validated_raw)
        total = sum(adjusted.values())

        risk_level, risk_label, interpretation = self._get_risk_level(total)
        subscale_scores = self._calculate_subscales(adjusted)
        critical = self._identify_critical_items(adjusted, validated_raw)

        report = {
            'timestamp': self.timestamp,
            'condition': 'Stress',
            'scale': 'Perceived Stress Scale — 10 Item (PSS-10)',
            'total_items': 10,
            'items_completed': len(adjusted),
            'total_score': total,
            'max_possible_score': 40,
            'score_percentage': round((total / 40) * 100, 1),
            'average_item_score': round(total / len(adjusted), 2) if adjusted else 0,
            'risk_level': risk_level,
            'risk_label': risk_label,
            'interpretation': interpretation,
            'subscales': subscale_scores,
            'item_details': self._build_item_details(validated_raw, adjusted),
            'critical_items': critical,
            'immediate_intervention_needed': risk_level == 'high',
            'confidence': self._confidence(adjusted),
            'clinical_summary': self._clinical_summary(total, risk_level, subscale_scores),
            'recommendations': self._recommendations(risk_level, subscale_scores),
        }
        return report

    # ------------------------------------------------------------------
    # INTERNAL HELPERS
    # ------------------------------------------------------------------

    def _validate_scores(self, scores: Dict) -> Dict[int, int]:
        validated = {}
        for k, v in scores.items():
            try:
                item = int(k)
                score = int(v)
            except (TypeError, ValueError):
                continue
            if item not in self.PSS_ITEMS:
                continue
            if not (0 <= score <= 4):
                continue
            validated[item] = score
        return validated

    def _apply_reverse_scoring(self, raw: Dict[int, int]) -> Dict[int, int]:
        """
        For reverse-scored items, convert: adjusted = 4 - raw
        """
        adjusted = {}
        for item, score in raw.items():
            if item in self.REVERSE_ITEMS:
                adjusted[item] = 4 - score
            else:
                adjusted[item] = score
        return adjusted

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
            item_scores = {i: adjusted[i] for i in items if i in adjusted}
            total = sum(item_scores.values())
            max_score = len(items) * 4
            avg = round(total / len(item_scores), 2) if item_scores else 0
            subscales[name] = {
                'items': items,
                'score': total,
                'max_score': max_score,
                'average': avg,
                'items_answered': len(item_scores),
                'label': name.replace('_', ' ').title(),
            }
        return subscales

    def _build_item_details(
        self,
        raw: Dict[int, int],
        adjusted: Dict[int, int]
    ) -> List[Dict[str, Any]]:
        details = []
        for item_num in sorted(adjusted.keys()):
            info = self.PSS_ITEMS[item_num]
            raw_score = raw[item_num]
            adj_score = adjusted[item_num]
            details.append({
                'item_number': item_num,
                'dimension': info['dimension'],
                'question': info['question'],
                'subscale': info['subscale'],
                'reverse_scored': info['reverse_scored'],
                'raw_response': raw_score,
                'raw_label': ['Never', 'Almost Never', 'Sometimes', 'Fairly Often', 'Very Often'][raw_score],
                'adjusted_score': adj_score,    # score after reverse-scoring
                'item_severity': self._item_severity(adj_score),
            })
        return details

    def _item_severity(self, adjusted_score: int) -> str:
        if adjusted_score <= 1:   return 'Low'
        if adjusted_score == 2:   return 'Moderate'
        return 'High'

    def _identify_critical_items(
        self,
        adjusted: Dict[int, int],
        raw: Dict[int, int]
    ) -> Dict[str, List]:
        critical = {
            'high_stress_items': [],    # adjusted score == 4
            'moderate_stress_items': [], # adjusted score == 3
        }
        for item_num, adj_score in adjusted.items():
            info = self.PSS_ITEMS[item_num]
            entry = {
                'item': item_num,
                'dimension': info['dimension'],
                'question': info['question'],
                'adjusted_score': adj_score,
                'raw_response_label': ['Never', 'Almost Never', 'Sometimes', 'Fairly Often', 'Very Often'][raw[item_num]],
            }
            if adj_score == 4:
                critical['high_stress_items'].append(entry)
            elif adj_score == 3:
                critical['moderate_stress_items'].append(entry)
        return critical

    def _confidence(self, scores: Dict[int, int]) -> float:
        n = len(scores)
        if n == 10:   return 0.97
        if n >= 9:    return 0.90
        if n >= 7:    return 0.75
        if n >= 5:    return 0.60
        return 0.40

    def _clinical_summary(
        self,
        total: int,
        level: str,
        subscales: Dict[str, Any]
    ) -> str:
        ph = subscales.get('perceived_helplessness', {})
        se = subscales.get('lack_of_self_efficacy', {})

        summary = f"PSS-10 Total: {total}/40 ({level.upper()}). "
        summary += (
            f"Perceived Helplessness subscale: {ph.get('score', 'N/A')}/24 | "
            f"Lack of Self-Efficacy subscale: {se.get('score', 'N/A')}/16. "
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

        # Subscale-specific additions
        ph = subscales.get('perceived_helplessness', {})
        se = subscales.get('lack_of_self_efficacy', {})

        if ph.get('average', 0) >= 3:
            recs.append('Perceived Helplessness is elevated — explore sense of control and coping strategies.')
        if se.get('average', 0) >= 3:
            recs.append('Low Self-Efficacy detected — consider confidence-building and problem-solving support.')

        return recs


# ------------------------------------------------------------------
# Convenience function — mirrors depression_analyzer.py pattern
# ------------------------------------------------------------------

def analyze_stress(raw_scores: Dict[int, int]) -> Dict[str, Any]:
    """
    Convenience wrapper.

    Args:
        raw_scores: {item_number (1-10): raw_response (0-4)}
                    Raw values as user selected — reverse scoring handled internally.

    Returns:
        Full PSS-10 stress assessment report.
    """
    return StressAnalyzer().analyze(raw_scores)