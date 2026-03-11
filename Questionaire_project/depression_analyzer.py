"""
Beck's Depression Inventory (BDI) Analyzer
Scale: 21 items, each scored 0-3
Total range: 0-63
Integrated for Student Companion Django project
"""

from typing import Dict, List, Tuple, Any
from datetime import datetime


class DepressionAnalyzer:

    BDI_ITEMS = {
        1: {
            'dimension': 'Sadness',
            'responses': {
                0: 'I do not feel sad.',
                1: 'I feel sad.',
                2: "I am sad all the time and I can't snap out of it.",
                3: "I am so sad and unhappy that I can't stand it."
            }
        },
        2: {
            'dimension': 'Pessimism',
            'responses': {
                0: 'I am not particularly discouraged about the future.',
                1: 'I feel discouraged about the future.',
                2: 'I feel I have nothing to look forward to.',
                3: 'I feel the future is hopeless and that things cannot improve.'
            }
        },
        3: {
            'dimension': 'Past Failure',
            'responses': {
                0: 'I do not feel like a failure.',
                1: 'I feel I have failed more than the average person.',
                2: 'As I look back on my life, all I can see is a lot of failures.',
                3: 'I feel I am a complete failure as a person.'
            }
        },
        4: {
            'dimension': 'Loss of Pleasure',
            'responses': {
                0: 'I get as much satisfaction out of things as I used to.',
                1: "I don't enjoy things the way I used to.",
                2: "I don't get real satisfaction out of anything anymore.",
                3: 'I am dissatisfied or bored with everything.'
            }
        },
        5: {
            'dimension': 'Guilty Feelings',
            'responses': {
                0: "I don't feel particularly guilty.",
                1: 'I feel guilty a good part of the time.',
                2: 'I feel quite guilty most of the time.',
                3: 'I feel guilty all of the time.'
            }
        },
        6: {
            'dimension': 'Punishment Feelings',
            'responses': {
                0: "I don't feel I am being punished.",
                1: 'I feel I may be punished.',
                2: 'I expect to be punished.',
                3: 'I feel I am being punished.'
            }
        },
        7: {
            'dimension': 'Self-Dislike',
            'responses': {
                0: "I don't feel disappointed in myself.",
                1: 'I am disappointed in myself.',
                2: 'I am disgusted with myself.',
                3: 'I hate myself.'
            }
        },
        8: {
            'dimension': 'Self-Criticalness',
            'responses': {
                0: "I don't feel I am any worse than anybody else.",
                1: 'I am critical of myself for my weaknesses or mistakes.',
                2: 'I blame myself all the time for my faults.',
                3: 'I blame myself for everything bad that happens.'
            }
        },
        9: {
            'dimension': 'Suicidal Thoughts or Wishes',
            'responses': {
                0: "I don't have any thoughts of killing myself.",
                1: 'I have thoughts of killing myself, but I would not carry them out.',
                2: 'I would like to kill myself.',
                3: 'I would kill myself if I had the chance.'
            }
        },
        10: {
            'dimension': 'Crying',
            'responses': {
                0: "I don't cry any more than usual.",
                1: 'I cry more now than I used to.',
                2: 'I cry all the time now.',
                3: "I used to be able to cry, but now I can't cry even though I want to."
            }
        },
        11: {
            'dimension': 'Agitation',
            'responses': {
                0: 'I am no more irritated by things than I ever was.',
                1: 'I am slightly more irritated now than usual.',
                2: 'I am quite annoyed or irritated a good deal of the time.',
                3: 'I feel irritated all the time.'
            }
        },
        12: {
            'dimension': 'Loss of Interest',
            'responses': {
                0: 'I have not lost interest in other people.',
                1: 'I am less interested in other people than I used to be.',
                2: 'I have lost most of my interest in other people.',
                3: 'I have lost all of my interest in other people.'
            }
        },
        13: {
            'dimension': 'Indecisiveness',
            'responses': {
                0: 'I make decisions about as well as I ever could.',
                1: 'I put off making decisions more than I used to.',
                2: 'I have greater difficulty in making decisions more than I used to.',
                3: "I can't make decisions at all anymore."
            }
        },
        14: {
            'dimension': 'Worthlessness',
            'responses': {
                0: "I don't feel that I look any worse than I used to.",
                1: 'I am worried that I am looking old or unattractive.',
                2: 'I feel there are permanent changes in my appearance that make me look unattractive.',
                3: 'I believe that I look ugly.'
            }
        },
        15: {
            'dimension': 'Loss of Energy',
            'responses': {
                0: 'I can work about as well as before.',
                1: 'It takes an extra effort to get started at doing something.',
                2: 'I have to push myself very hard to do anything.',
                3: "I can't do any work at all."
            }
        },
        16: {
            'dimension': 'Changes in Sleep Pattern',
            'responses': {
                0: 'I can sleep as well as usual.',
                1: "I don't sleep as well as I used to.",
                2: 'I wake up 1-2 hours earlier than usual and find it hard to get back to sleep.',
                3: 'I wake up several hours earlier than I used to and cannot get back to sleep.'
            }
        },
        17: {
            'dimension': 'Irritability',
            'responses': {
                0: "I don't get more tired than usual.",
                1: 'I get tired more easily than I used to.',
                2: 'I get tired from doing almost anything.',
                3: 'I am too tired to do anything.'
            }
        },
        18: {
            'dimension': 'Changes in Appetite',
            'responses': {
                0: 'My appetite is no worse than usual.',
                1: 'My appetite is not as good as it used to be.',
                2: 'My appetite is much worse now.',
                3: 'I have no appetite at all anymore.'
            }
        },
        19: {
            'dimension': 'Concentration Difficulty / Weight Loss',
            'responses': {
                0: "I haven't lost much weight, if any, lately.",
                1: 'I have lost more than five pounds.',
                2: 'I have lost more than ten pounds.',
                3: 'I have lost more than fifteen pounds.'
            }
        },
        20: {
            'dimension': 'Tiredness or Fatigue',
            'responses': {
                0: 'I am no more worried about my health than usual.',
                1: 'I am worried about physical problems like aches, pains, upset stomach, or constipation.',
                2: "I am very worried about physical problems and it's hard to think of much else.",
                3: 'I am so worried about my physical problems that I cannot think of anything else.'
            }
        },
        21: {
            'dimension': 'Loss of Interest in Sex',
            'responses': {
                0: 'I have not noticed any recent change in my interest in sex.',
                1: 'I am less interested in sex than I used to be.',
                2: 'I have almost no interest in sex.',
                3: 'I have lost interest in sex completely.'
            }
        },
    }

    # BDI scoring thresholds (official Beck scoring)
    RISK_THRESHOLDS = [
        (0,  10,  'normal',     'Normal range — these ups and downs are considered normal.'),
        (11, 16,  'mild',       'Mild mood disturbance.'),
        (17, 20,  'borderline', 'Borderline clinical depression.'),
        (21, 30,  'moderate',   'Moderate depression.'),
        (31, 40,  'severe',     'Severe depression.'),
        (41, 63,  'extreme',    'Extreme depression.'),
    ]

    def __init__(self):
        self.timestamp = datetime.now().isoformat()

    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------

    def analyze(self, scores: Dict[int, int]) -> Dict[str, Any]:
        """
        Main entry point.

        Args:
            scores: {item_number (1-21): score (0-3)}

        Returns:
            Full depression assessment report dict.
        """
        validated = self._validate_scores(scores)
        total = sum(validated.values())
        risk_level, risk_label, interpretation = self._get_risk_level(total)
        critical = self._identify_critical_items(validated)

        report = {
            'timestamp': self.timestamp,
            'condition': 'Depression',
            'scale': "Beck's Depression Inventory (BDI)",
            'total_items': 21,
            'items_completed': len(validated),
            'total_score': total,
            'max_possible_score': 63,
            'score_percentage': round((total / 63) * 100, 1),
            'risk_level': risk_level,          # e.g. 'moderate'
            'risk_label': risk_label,           # e.g. 'Moderate depression.'
            'interpretation': interpretation,
            'item_details': self._build_item_details(validated),
            'critical_items': critical,
            'immediate_intervention_needed': risk_level in ('severe', 'extreme') or bool(critical['suicide_risk']),
            'confidence': self._confidence(validated),
            'clinical_summary': self._clinical_summary(total, risk_level),
            'recommendations': self._recommendations(risk_level, critical),
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
            if item not in self.BDI_ITEMS:
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

    def _build_item_details(self, scores: Dict[int, int]) -> List[Dict[str, Any]]:
        details = []
        for item_num in sorted(scores.keys()):
            score = scores[item_num]
            info = self.BDI_ITEMS[item_num]
            details.append({
                'item_number': item_num,
                'dimension': info['dimension'],
                'score': score,
                'max_score': 3,
                'selected_response': info['responses'][score],
                'item_severity': ['None', 'Mild', 'Moderate', 'Severe'][score],
            })
        return details

    def _identify_critical_items(self, scores: Dict[int, int]) -> Dict[str, List]:
        critical = {
            'suicide_risk': [],      # item 9 — always escalate if > 0
            'severe_items': [],      # score == 3
            'moderate_items': [],    # score == 2
        }

        for item_num, score in scores.items():
            info = self.BDI_ITEMS[item_num]
            entry = {
                'item': item_num,
                'dimension': info['dimension'],
                'score': score,
                'response': info['responses'][score],
            }

            # Item 9 — suicidal ideation: flag regardless of score level
            if item_num == 9 and score > 0:
                entry['urgency'] = 'CRITICAL' if score >= 2 else 'HIGH'
                critical['suicide_risk'].append(entry)
            elif score == 3:
                critical['severe_items'].append(entry)
            elif score == 2:
                critical['moderate_items'].append(entry)

        return critical

    def _confidence(self, scores: Dict[int, int]) -> float:
        n = len(scores)
        if n == 21:   return 0.97
        if n >= 19:   return 0.90
        if n >= 16:   return 0.80
        if n >= 10:   return 0.65
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

        # Always append suicide-specific recommendation if item 9 was flagged
        if critical['suicide_risk']:
            urgency = critical['suicide_risk'][0].get('urgency', 'HIGH')
            recs.insert(0, f"⚠️ SUICIDE RISK FLAGGED ({urgency}): Immediate safety assessment required regardless of total score.")

        return recs


# ------------------------------------------------------------------
# Convenience function — mirrors anxiety_analyzer.py pattern
# ------------------------------------------------------------------

def analyze_depression(scores: Dict[int, int]) -> Dict[str, Any]:
    """
    Convenience wrapper.

    Args:
        scores: {item_number: score} — e.g. {1: 2, 2: 0, 3: 1, ...}

    Returns:
        Full BDI depression assessment report.
    """
    return DepressionAnalyzer().analyze(scores)