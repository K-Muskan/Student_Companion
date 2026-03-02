"""
Mental Status Exam (MSE) AI Analyzer
Analyzes patient responses using NLP, sentiment analysis, and pattern recognition
Based on standardized MSE assessment criteria
"""
import re
from datetime import datetime
from typing import Dict, List, Tuple, Any
import json

try:
    import spacy
except Exception:  # pragma: no cover - optional dependency
    spacy = None


class MSEAnalyzer:
    """AI-powered Mental Status Exam analyzer"""
    
    # Keywords for different MSE categories
    MOOD_KEYWORDS = {
        'depressed': ['sad', 'down', 'depressed', 'hopeless', 'empty', 'numb', 'worthless', 'miserable'],
        'anxious': ['anxious', 'nervous', 'worried', 'tense', 'scared', 'afraid', 'panic', 'fear'],
        'elevated': ['happy', 'great', 'excellent', 'energetic', 'high', 'ecstatic', 'euphoric'],
        'irritable': ['angry', 'irritated', 'annoyed', 'frustrated', 'mad', 'agitated'],
        'euthymic': ['okay', 'fine', 'normal', 'stable', 'alright', 'good']
    }
    
    SUICIDAL_INDICATORS = {
        'passive': ['wish i was dead', 'better off dead', 'wish i could sleep forever', 'go to sleep and not wake'],
        'active': ['kill myself', 'end my life', 'suicide', 'want to die', 'plan to die'],
        'self_harm': ['cut myself', 'cutting', 'burn myself', 'hurt myself', 'self harm', 'self-harm']
    }
    
    PSYCHOTIC_INDICATORS = {
        'hallucinations': {
            'auditory': ['hear voices', 'voices tell', 'voices say', 'hear things', 'hear people'],
            'visual': ['see things', 'see people', 'visions', 'seeing'],
            'tactile': ['feel bugs', 'crawling', 'tingling', 'feel things on'],
        },
        'delusions': {
            'paranoid': ['following me', 'watching me', 'spy', 'spying', 'out to get', 'conspir'],
            'reference': ['signs', 'messages for me', 'special meaning', 'meant for me'],
            'control': ['control my', 'controlling me', 'not my own', 'inserted', 'broadcasting'],
            'grandiose': ['special powers', 'chosen one', 'special mission', 'unique ability']
        }
    }
    
    THOUGHT_PROCESS_PATTERNS = {
        'organized': ['first', 'then', 'because', 'therefore', 'however', 'although'],
        'tangential': ['by the way', 'speaking of', 'that reminds me'],
        'circumstantial': ['detail', 'specifically', 'exactly'],
    }
    
    ANXIETY_INDICATORS = ['panic', 'heart racing', 'can\'t breathe', 'shaking', 'sweating', 
                         'trembling', 'dizzy', 'chest pain', 'afraid', 'scared']
    
    SLEEP_ISSUES = ['insomnia', 'can\'t sleep', 'trouble sleeping', 'wake up', 'nightmares', 
                    'too much sleep', 'sleeping all day']
    
    SUBSTANCE_USE = ['alcohol', 'drinking', 'beer', 'wine', 'drugs', 'marijuana', 'weed', 
                     'cocaine', 'pills', 'prescription']

    # Advanced rule-based NLP lexicons and cues (DSM-5 / ICD-11 aligned heuristics)
    NEGATION_CUES = [
        'no', 'not', 'never', 'none', 'without', 'denies', 'deny', 'denied',
        "don't", "dont", "didn't", "didnt", "isn't", "isnt", "wasn't", "wasnt",
        "can't", "cant", "won't", "wont", "cannot", "neither", "nor"
    ]

    BENIGN_IDIOM_EXCLUSIONS = [
        "kill time",
        "dead tired",
        "suicide squad",
        "this assignment is killing me",
        "killed it",
    ]

    INTENSIFIERS = [
        'very', 'extremely', 'severely', 'constantly', 'always', 'overwhelming',
        'intense', 'terribly', 'so', 'really', 'highly'
    ]

    DURATION_HINTS = [
        'for weeks', 'for months', 'for years', 'for a long time', 'long time',
        'since last year', 'since last month', 'since last week', 'for years',
        'for months', 'for weeks'
    ]

    IMPAIRMENT_PHRASES = [
        "can't study", "cannot study", "can't focus", "cannot focus", "failing classes",
        "failed classes", "missed classes", "can't work", "cannot work", "quit my hobbies",
        "stopped my hobbies", "stopped hobbies", "can't function", "cannot function",
        "affecting school", "affecting my school", "affecting my life", "interfering with school",
        "interfering with life", "unable to study", "unable to work"
    ]

    DEPRESSIVE_LEXICON = [
        'sad', 'down', 'depressed', 'hopeless', 'empty', 'numb', 'worthless',
        'miserable', 'low energy', 'anhedonia', 'no interest', 'loss of interest',
        'crying', 'tearful', 'guilty'
    ]

    ANXIETY_LEXICON = [
        'anxious', 'nervous', 'worried', 'tense', 'scared', 'afraid', 'panic',
        'on edge', 'restless', 'racing heart', 'trembling', 'shaking'
    ]

    SLEEP_LEXICON = [
        'insomnia', "can't sleep", 'trouble sleeping', 'wake up', 'nightmares',
        'too much sleep', 'sleeping all day', 'sleep all day'
    ]
    
    def __init__(self):
        """Initialize the analyzer"""
        self.assessment = {}
        self._nlp = None
        if spacy is not None:
            try:
                self._nlp = spacy.load("en_core_web_sm")
            except Exception:
                self._nlp = None
        
    def analyze_all_responses(self, answers: Dict[str, str]) -> Dict[str, Any]:
        """
        Main analysis function - analyzes all responses and generates MSE report
        
        Args:
            answers: Dictionary of {question_id: answer_text}
            
        Returns:
            Complete MSE assessment report
        """
        standardized_scales = self._analyze_standardized_scales(answers)
        report = {
            'timestamp': datetime.now().isoformat(),
            'mood_affect': self._analyze_mood_affect(answers),
            'thought_content': self._analyze_thought_content(answers),
            'thought_process': self._analyze_thought_process(answers),
            'cognition': self._analyze_cognition(answers),
            'insight_judgment': self._analyze_insight_judgment(answers),
            'risk_assessment': self._analyze_risk(answers),
            'standardized_scales': standardized_scales,
            'clinical_impressions': self._generate_clinical_impressions(answers, standardized_scales),
            'recommendations': self._generate_recommendations(answers),
            'rules_applied': [
                'DSM-5 2-week duration heuristic for depressive symptoms',
                'Impairment rule for functional impact',
                'Negation handling to reduce false positives',
                'PHQ-9 and GAD-7 style severity mapping (rule-based)',
                'ICD-11 psychosis priority referral heuristic',
                'C-SSRS-inspired critical safety flagging'
            ],
            'full_responses': answers
        }
        
        return report

    def _normalize(self, text: str) -> str:
        return re.sub(r'\s+', ' ', text.lower()).strip()

    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r"[a-zA-Z']+|\d+", text.lower())

    def _find_phrase_matches(self, tokens: List[str], phrase_tokens: List[str]) -> List[Tuple[int, int]]:
        matches = []
        if not phrase_tokens:
            return matches
        n = len(phrase_tokens)
        for i in range(0, len(tokens) - n + 1):
            if tokens[i:i + n] == phrase_tokens:
                matches.append((i, i + n))
        return matches

    def _is_negated(self, tokens: List[str], start: int, end: int, window: int = 4) -> bool:
        pre = tokens[max(0, start - window):start]
        post = tokens[end:end + window]
        if any(t in self.NEGATION_CUES for t in pre):
            return True
        if any(t in self.NEGATION_CUES for t in post):
            return True
        return False

    def _is_negated_spacy(self, doc, start: int, end: int) -> bool:
        span = doc[start:end]
        for token in span:
            if token.dep_ == "neg":
                return True
            if any(child.dep_ == "neg" for child in token.children):
                return True
            if any(t.lower_ in self.NEGATION_CUES for t in token.lefts):
                return True
        return False

    def _has_intensifier(self, tokens: List[str], start: int, end: int, window: int = 2) -> bool:
        pre = tokens[max(0, start - window):start]
        post = tokens[end:end + window]
        return any(t in self.INTENSIFIERS for t in pre + post)

    def _match_lexicon(self, text: str, lexicon: List[str]) -> Dict[str, Any]:
        if self._nlp is not None:
            doc = self._nlp(text)
            tokens = [t.text.lower() for t in doc]
        else:
            doc = None
            tokens = self._tokenize(text)
        present = []
        negated = []
        intensity_hits = 0

        for phrase in lexicon:
            phrase_tokens = self._tokenize(phrase)
            for start, end in self._find_phrase_matches(tokens, phrase_tokens):
                if doc is not None:
                    negated_hit = self._is_negated_spacy(doc, start, end)
                else:
                    negated_hit = self._is_negated(tokens, start, end)

                if negated_hit:
                    negated.append(phrase)
                else:
                    present.append(phrase)
                    if self._has_intensifier(tokens, start, end):
                        intensity_hits += 1

        return {
            'present': list(dict.fromkeys(present)),
            'negated': list(dict.fromkeys(negated)),
            'intensity_hits': intensity_hits
        }

    def _edit_distance(self, a: str, b: str) -> int:
        if a == b:
            return 0
        if not a:
            return len(b)
        if not b:
            return len(a)
        prev = list(range(len(b) + 1))
        for i, ca in enumerate(a, start=1):
            cur = [i]
            for j, cb in enumerate(b, start=1):
                insert = cur[j - 1] + 1
                delete = prev[j] + 1
                replace = prev[j - 1] + (ca != cb)
                cur.append(min(insert, delete, replace))
            prev = cur
        return prev[-1]

    def _contains_benign_idiom(self, text: str) -> bool:
        text_norm = self._normalize(text)
        return any(phrase in text_norm for phrase in self.BENIGN_IDIOM_EXCLUSIONS)

    def _fuzzy_phrase_present(self, text: str, phrase: str, max_ratio: float = 0.22) -> bool:
        text_tokens = self._tokenize(text)
        phrase_tokens = self._tokenize(phrase)
        n = len(phrase_tokens)
        if n == 0 or len(text_tokens) < n:
            return False
        phrase_joined = " ".join(phrase_tokens)
        max_edits = max(1, int(len(phrase_joined) * max_ratio))
        for i in range(len(text_tokens) - n + 1):
            candidate = " ".join(text_tokens[i:i + n])
            if self._edit_distance(candidate, phrase_joined) <= max_edits:
                return True
        return False

    def _detect_plan_like(self, text: str) -> bool:
        text_norm = self._normalize(text)
        benign = ["plan my day", "plan my week", "study plan", "project plan"]
        if any(b in text_norm for b in benign):
            return False
        patterns = [
            r"\b(i|im|i am)\s+(going to|gonna|will)\s+(use|take|do)\b",
            r"\b(method|means|dose|rope|knife|gun|pills|bridge)\b",
            r"\b(tonight|tomorrow|this week|at \d{1,2}(:\d{2})?\s?(am|pm)?)\b",
            r"\bwhen everyone is asleep\b",
            r"\bno one will find me\b",
        ]
        return any(re.search(pattern, text_norm) for pattern in patterns)

    def _first_person_intent(self, text: str) -> bool:
        text_norm = self._normalize(text)
        third_person_prefix = re.match(
            r"^\s*(he|she|they|someone|my friend|a friend|friend)\b",
            text_norm,
        )
        if third_person_prefix:
            return False

        # Guard against quoted/reported speech (e.g., "he said i want to die")
        # so third-person context is not escalated as direct first-person intent.
        reported_speech_cues = [
            r"\b(he|she|they|friend|someone|teacher|mother|father|brother|sister)\s+(said|says|told|mentioned|wrote)\b",
            r"\b(my friend|a friend|someone)\s+(said|says|told|mentioned|wrote)\b",
            r"\b(i heard|i read|i saw)\b",
        ]
        if any(re.search(pattern, text_norm) for pattern in reported_speech_cues):
            # Keep this conservative to avoid false High risk from quoted content.
            if " but i " not in f" {text_norm} " and " and i " not in f" {text_norm} ":
                return False
        first_person = [" i ", " i'm ", " im ", " my ", " myself "]
        if any(fp in f" {text_norm} " for fp in first_person):
            return True
        return text_norm.startswith("i ")

    def _build_domain_meta(self, evidence: List[str], negated: List[str]) -> Dict[str, Any]:
        ev = list(dict.fromkeys(evidence))
        confidence = min(0.95, 0.35 + (0.15 * len(ev)))
        if not ev:
            confidence = 0.25
        return {
            "confidence": round(confidence, 3),
            "evidence": ev[:10],
            "negated_evidence": list(dict.fromkeys(negated))[:10],
            "uncertainty": "high" if confidence < 0.45 else ("medium" if confidence < 0.7 else "low"),
        }

    def _estimate_duration_days(self, text: str) -> Tuple[int, bool]:
        """
        Returns (estimated_days, duration_2_weeks_or_more)
        """
        text_norm = self._normalize(text)
        if not text_norm:
            return 0, False

        number_words = {
            'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6,
            'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10, 'eleven': 11, 'twelve': 12
        }

        for word, value in number_words.items():
            text_norm = re.sub(rf'\b{word}\b', str(value), text_norm)

        match = re.search(r'(\d+)\s*(day|week|month|year)s?', text_norm)
        if match:
            num = int(match.group(1))
            unit = match.group(2)
            if unit == 'day':
                days = num
            elif unit == 'week':
                days = num * 7
            elif unit == 'month':
                days = num * 30
            else:
                days = num * 365
            return days, days >= 14

        if any(hint in text_norm for hint in self.DURATION_HINTS):
            return 14, True

        return 0, False

    def _detect_impairment(self, answers: Dict[str, str]) -> bool:
        all_text = self._normalize(' '.join(answers.values()))
        return any(phrase in all_text for phrase in self.IMPAIRMENT_PHRASES)
    
    def _analyze_mood_affect(self, answers: Dict[str, str]) -> Dict[str, Any]:
        """Analyze mood and affect from responses"""
        # Question 1: Mood description
        # Question 2: Congruence of internal/external emotions
        
        q1 = answers.get('1', '').lower()
        q2 = answers.get('2', '').lower()
        
        mood_analysis = {
            'stated_mood': 'Not provided',
            'mood_category': 'Unknown',
            'affect_quality': [],
            'affect_range': 'Unable to assess from text',
            'congruence': 'Unknown',
            'sentiment_score': 0.0
        }
        
        # Detect mood from Q1 with negation handling
        if q1:
            mood_analysis['stated_mood'] = q1[:200]  # First 200 chars
            
            # Categorize mood
            mood_scores = {}
            for category, keywords in self.MOOD_KEYWORDS.items():
                matches = self._match_lexicon(q1, keywords)
                score = len(matches['present'])
                if score > 0:
                    mood_scores[category] = score
            
            if mood_scores:
                dominant_mood = max(mood_scores.items(), key=lambda x: x[1])
                mood_analysis['mood_category'] = dominant_mood[0]
            
            # Sentiment analysis (simple)
            mood_analysis['sentiment_score'] = self._calculate_sentiment(q1)
        
        # Analyze congruence from Q2
        if q2:
            if any(word in q2 for word in ['no', 'not', "don't", "doesn't", 'different', 'incongruent']):
                mood_analysis['congruence'] = 'Incongruent - discrepancy between internal feelings and external presentation'
            elif any(word in q2 for word in ['yes', 'match', 'same', 'consistent']):
                mood_analysis['congruence'] = 'Congruent - internal feelings match external presentation'
            else:
                mood_analysis['congruence'] = 'Partially congruent or variable'
        
        # Check for lability
        if any(word in q2 for word in ['change', 'vary', 'fluctuate', 'up and down', 'different throughout']):
            mood_analysis['affect_quality'].append('labile')
        
        return mood_analysis
    
    def _analyze_thought_content(self, answers: Dict[str, str]) -> Dict[str, Any]:
        """Analyze thought content for concerning themes"""
        
        content_analysis = {
            'suicidal_ideation': self._assess_suicide_risk(answers),
            'homicidal_ideation': self._assess_homicidal_ideation(answers),
            'hallucinations': self._assess_hallucinations(answers),
            'delusions': self._assess_delusions(answers),
            'obsessions_compulsions': self._assess_ocd(answers)
        }
        
        return content_analysis
    
    def _assess_suicide_risk(self, answers: Dict[str, str]) -> Dict[str, Any]:
        """Assess suicidal ideation - Question 7"""
        q7 = answers.get('7', '').lower()
        
        risk = {
            'present': False,
            'type': 'None',
            'severity': 'None',
            'plan': False,
            'intent': False,
            'protective_factors': [],
            'risk_level': 'Low',
            'triggered_phrases': [],
            'negated_phrases': [],
            'confidence': 0.25,
            'evidence': []
        }
        
        if not q7 or q7 in ['no', 'none', 'n/a']:
            return risk
        if self._contains_benign_idiom(q7):
            return risk
        
        # Check for passive ideation with negation handling
        passive_matches = self._match_lexicon(q7, self.SUICIDAL_INDICATORS['passive'])
        for phrase in passive_matches['present']:
            risk['present'] = True
            risk['type'] = 'Passive ideation'
            risk['severity'] = 'Moderate'
            risk['risk_level'] = 'Moderate'
            risk['triggered_phrases'].append(phrase)
            risk['evidence'].append(phrase)
        for phrase in passive_matches['negated']:
            risk['negated_phrases'].append(phrase)
        
        # Check for active ideation
        active_matches = self._match_lexicon(q7, self.SUICIDAL_INDICATORS['active'])
        for phrase in active_matches['present']:
            is_first_person = self._first_person_intent(q7)
            risk['present'] = True
            risk['type'] = 'Active ideation' if is_first_person else 'Possible third-person/quoted suicidal content'
            risk['severity'] = 'Severe' if is_first_person else 'Moderate'
            risk['risk_level'] = 'High' if is_first_person else 'Moderate'
            risk['triggered_phrases'].append(phrase)
            risk['evidence'].append(phrase)
        for phrase in active_matches['negated']:
            risk['negated_phrases'].append(phrase)
        
        # Check for self-harm
        self_harm_matches = self._match_lexicon(q7, self.SUICIDAL_INDICATORS['self_harm'])
        for phrase in self_harm_matches['present']:
            is_first_person = self._first_person_intent(q7)
            risk['present'] = True
            if 'self_harm' not in risk['type']:
                risk['type'] += ' with self-harm behaviors'
            risk['risk_level'] = 'High' if is_first_person else 'Moderate'
            risk['triggered_phrases'].append(phrase)
            risk['evidence'].append(phrase)

        # Fuzzy matching for typos in critical self-harm phrases
        for phrase in self.SUICIDAL_INDICATORS['active'] + self.SUICIDAL_INDICATORS['self_harm']:
            if phrase in risk["triggered_phrases"]:
                continue
            if self._fuzzy_phrase_present(q7, phrase) and not self._contains_benign_idiom(q7):
                is_first_person = self._first_person_intent(q7)
                risk['present'] = True
                risk['risk_level'] = 'High' if is_first_person else 'Moderate'
                risk['severity'] = 'Severe' if is_first_person else 'Moderate'
                if 'self harm' in phrase or 'cut' in phrase or 'burn' in phrase:
                    risk['type'] = 'Active ideation with self-harm behaviors'
                else:
                    risk['type'] = 'Active ideation'
                risk['triggered_phrases'].append(f"fuzzy:{phrase}")
                risk['evidence'].append(f"fuzzy:{phrase}")
        for phrase in self_harm_matches['negated']:
            risk['negated_phrases'].append(phrase)
        
        # Check for plan
        plan_words = ['plan', 'method', 'how i would', 'going to', 'will use']
        if (any(word in q7 for word in plan_words) and not any(b in q7 for b in ['plan my day', 'study plan'])) or self._detect_plan_like(q7):
            risk['plan'] = True
            risk['risk_level'] = 'High'
        
        # Check for protective factors
        protective = ['but i won\'t', 'never would', 'couldn\'t do', 'family', 'children', 'religion']
        for factor in protective:
            if factor in q7:
                risk['protective_factors'].append(factor)

        meta = self._build_domain_meta(risk['evidence'], risk['negated_phrases'])
        risk['confidence'] = meta['confidence']
        risk['evidence'] = meta['evidence']

        return risk
    
    def _assess_homicidal_ideation(self, answers: Dict[str, str]) -> Dict[str, Any]:
        """Assess homicidal ideation - Question 8"""
        q8 = answers.get('8', '').lower()
        
        risk = {
            'present': False,
            'specific_target': False,
            'plan': False,
            'risk_level': 'Low',
            'triggered_phrases': [],
            'negated_phrases': [],
            'confidence': 0.25,
            'evidence': []
        }
        
        if not q8 or q8 in ['no', 'none', 'n/a']:
            return risk
        
        harm_words = ['hurt', 'harm', 'kill', 'attack', 'hit', 'punch']
        harm_matches = self._match_lexicon(q8, harm_words)
        if harm_matches['present']:
            risk['present'] = True
            risk['risk_level'] = 'Moderate'
            risk['triggered_phrases'].extend(harm_matches['present'])
            risk['evidence'].extend(harm_matches['present'])
        if harm_matches['negated']:
            risk['negated_phrases'].extend(harm_matches['negated'])
        
        if any(word in q8 for word in ['specific person', 'my', 'them', 'him', 'her', 'name']):
            risk['specific_target'] = True
            risk['risk_level'] = 'High'
        
        if any(word in q8 for word in ['plan', 'going to', 'will', 'method']):
            risk['plan'] = True
            risk['risk_level'] = 'High'

        meta = self._build_domain_meta(risk['evidence'], risk['negated_phrases'])
        risk['confidence'] = meta['confidence']
        risk['evidence'] = meta['evidence']

        return risk
    
    def _assess_hallucinations(self, answers: Dict[str, str]) -> Dict[str, Any]:
        """Assess for hallucinations - Question 9"""
        q9 = answers.get('9', '').lower()
        
        hallucinations = {
            'present': False,
            'types': [],
            'frequency': 'Unknown',
            'distressing': False,
            'confidence': 0.25,
            'evidence': [],
        }
        
        if not q9 or q9 in ['no', 'none', 'n/a']:
            return hallucinations
        
        # Check each type with negation handling
        for h_type, keywords in self.PSYCHOTIC_INDICATORS['hallucinations'].items():
            matches = self._match_lexicon(q9, keywords)
            if matches['present']:
                hallucinations['present'] = True
                if h_type not in hallucinations['types']:
                    hallucinations['types'].append(h_type)
                hallucinations['evidence'].extend(matches['present'])
        
        # Check frequency
        if any(word in q9 for word in ['often', 'frequently', 'always', 'constantly', 'daily']):
            hallucinations['frequency'] = 'Frequent'
        elif any(word in q9 for word in ['sometimes', 'occasionally', 'rarely']):
            hallucinations['frequency'] = 'Occasional'
        
        # Check if distressing
        if any(word in q9 for word in ['scared', 'afraid', 'frightening', 'disturbing', 'distressing']):
            hallucinations['distressing'] = True
        hallucinations['confidence'] = self._build_domain_meta(hallucinations['evidence'], [])['confidence']

        return hallucinations
    
    def _assess_delusions(self, answers: Dict[str, str]) -> Dict[str, Any]:
        """Assess for delusional thinking - Question 10"""
        q10 = answers.get('10', '').lower()
        
        delusions = {
            'present': False,
            'types': [],
            'fixed': False,
            'confidence': 0.25,
            'evidence': [],
        }
        
        if not q10 or q10 in ['no', 'none', 'n/a']:
            return delusions
        
        for d_type, keywords in self.PSYCHOTIC_INDICATORS['delusions'].items():
            matches = self._match_lexicon(q10, keywords)
            if matches['present']:
                delusions['present'] = True
                if d_type not in delusions['types']:
                    delusions['types'].append(d_type)
                delusions['evidence'].extend(matches['present'])
        
        # Check if beliefs are fixed
        if any(word in q10 for word in ['know it\'s true', 'definitely', 'certain', 'sure']):
            delusions['fixed'] = True
        delusions['confidence'] = self._build_domain_meta(delusions['evidence'], [])['confidence']
        
        return delusions
    
    def _assess_ocd(self, answers: Dict[str, str]) -> Dict[str, Any]:
        """Assess for obsessive-compulsive symptoms"""
        # Look across all responses for OCD patterns
        all_text = ' '.join(answers.values()).lower()
        
        ocd = {
            'obsessions_present': False,
            'compulsions_present': False,
            'themes': []
        }
        
        obsession_words = ['can\'t stop thinking', 'intrusive', 'obsess', 'constantly think']
        compulsion_words = ['have to', 'must', 'ritual', 'repeatedly', 'checking', 'washing', 'counting']
        
        if any(word in all_text for word in obsession_words):
            ocd['obsessions_present'] = True
        
        if any(word in all_text for word in compulsion_words):
            ocd['compulsions_present'] = True
        
        # Identify themes
        if 'clean' in all_text or 'contamination' in all_text or 'germs' in all_text:
            ocd['themes'].append('contamination/cleaning')
        if 'check' in all_text or 'lock' in all_text:
            ocd['themes'].append('checking')
        if 'order' in all_text or 'symmetry' in all_text:
            ocd['themes'].append('ordering/symmetry')
        
        return ocd
    
    def _analyze_thought_process(self, answers: Dict[str, str]) -> Dict[str, Any]:
        """Analyze thought process and organization"""
        
        process = {
            'organization': 'Unknown',
            'coherence': 'Unknown',
            'observations': []
        }
        
        # Analyze all responses for patterns
        all_responses = [v for v in answers.values() if v]
        
        if not all_responses:
            return process
        
        # Check for organized thinking
        organized_count = 0
        for response in all_responses:
            if len(response.split('.')) > 2:  # Multiple sentences
                # Check for logical connectors
                organized_count += sum(1 for word in self.THOUGHT_PROCESS_PATTERNS['organized'] 
                                      if word in response.lower())
        
        if organized_count > len(all_responses):
            process['organization'] = 'Logical and sequential'
            process['coherence'] = 'Coherent'
        else:
            process['organization'] = 'Variable organization'
            process['coherence'] = 'Mostly coherent'
        
        # Check for tangentiality
        tangential_markers = sum(1 for response in all_responses 
                                for marker in self.THOUGHT_PROCESS_PATTERNS['tangential']
                                if marker in response.lower())
        if tangential_markers > 2:
            process['observations'].append('Some tangential responses')
        
        # Check response length (circumstantiality)
        avg_length = sum(len(r.split()) for r in all_responses) / len(all_responses)
        if avg_length > 100:
            process['observations'].append('Verbose responses - possible circumstantiality')
        elif avg_length < 10:
            process['observations'].append('Brief responses - possible poverty of speech')
        
        return process
    
    def _analyze_cognition(self, answers: Dict[str, str]) -> Dict[str, Any]:
        """Analyze cognitive functioning from responses"""
        
        cognition = {
            'orientation': 'Appears oriented (based on coherent responses)',
            'memory': 'Unable to formally assess from interview',
            'concentration': 'Unknown',
            'observations': []
        }
        
        # Check response coherence as proxy for orientation
        all_text = ' '.join(answers.values())
        if not all_text or len(all_text) < 50:
            cognition['orientation'] = 'Unable to assess - minimal responses'
            return cognition
        
        # Check for memory complaints
        q5 = answers.get('5', '').lower()  # Sleep question may mention memory
        memory_words = ['forget', 'memory', 'remember', 'recall']
        if any(word in all_text.lower() for word in memory_words):
            cognition['observations'].append('Patient mentions memory concerns')
        
        # Check for concentration issues
        q3 = answers.get('3', '').lower()  # Anxiety question
        q4 = answers.get('4', '').lower()  # Panic question
        if any(word in q3 + q4 for word in ['can\'t focus', 'concentrate', 'distracted']):
            cognition['concentration'] = 'Patient reports difficulty concentrating'
        
        return cognition
    
    def _analyze_insight_judgment(self, answers: Dict[str, str]) -> Dict[str, Any]:
        """Analyze insight and judgment - Questions 12 and 13"""
        
        q12 = answers.get('12', '').lower()  # Impulsivity/decision making
        q13 = answers.get('13', '').lower()  # Awareness of difficulties/willingness for help
        
        analysis = {
            'insight': 'Unknown',
            'judgment': 'Unknown',
            'awareness': False,
            'treatment_acceptance': False
        }
        
        # Analyze insight (Q13)
        if q13:
            # Check awareness
            if any(word in q13 for word in ['yes', 'i have', 'struggling', 'difficult', 'problems']):
                analysis['awareness'] = True
                analysis['insight'] = 'Good - patient acknowledges difficulties'
            elif any(word in q13 for word in ['no', 'nothing wrong', 'fine', "don't need", 'no problems']):
                analysis['insight'] = 'Poor - limited awareness of difficulties'
            else:
                analysis['insight'] = 'Partial - some awareness present'
            
            # Check treatment acceptance
            if any(word in q13 for word in ['willing', 'want help', 'need help', 'accept', 'yes']):
                analysis['treatment_acceptance'] = True
            elif any(word in q13 for word in ['refuse', 'won\'t', 'don\'t want', 'no']):
                analysis['treatment_acceptance'] = False
        
        # Analyze judgment (Q12)
        if q12:
            if any(word in q12 for word in ['impulsive', 'without thinking', 'regret', 'poor choices']):
                analysis['judgment'] = 'Impaired - patient acknowledges impulsive decision-making'
            elif any(word in q12 for word in ['reasonable', 'appropriate', 'think through', 'consider']):
                analysis['judgment'] = 'Good - thoughtful decision-making reported'
            else:
                analysis['judgment'] = 'Fair - mixed decision-making patterns'
        
        return analysis
    
    def _analyze_risk(self, answers: Dict[str, str]) -> Dict[str, Any]:
        """Comprehensive risk assessment"""
        
        suicide_risk = self._assess_suicide_risk(answers)
        homicide_risk = self._assess_homicidal_ideation(answers)

        # Tier 1: C-SSRS inspired critical safety flag (non-negated triggers)
        if suicide_risk['triggered_phrases'] or homicide_risk['triggered_phrases']:
            return {
                'suicide_risk_level': suicide_risk['risk_level'],
                'homicide_risk_level': homicide_risk['risk_level'],
                'substance_use_concern': False,
                'acute_anxiety': False,
                'sleep_disturbance': False,
                'overall_risk': 'Critical',
                'immediate_intervention_needed': True,
                'risk_factors': ['Non-negated suicidal/homicidal content detected (C-SSRS rule)'],
                'protective_factors': suicide_risk.get('protective_factors', []),
                'critical_flag': True,
                'confidence': max(suicide_risk.get('confidence', 0.25), homicide_risk.get('confidence', 0.25)),
                'evidence': suicide_risk.get('evidence', []) + homicide_risk.get('evidence', []),
            }
        
        # Assess other risk factors
        q3 = answers.get('3', '').lower()
        q4 = answers.get('4', '').lower()
        q5 = answers.get('5', '').lower()
        q11 = answers.get('11', '').lower()
        scales = self._analyze_standardized_scales(answers)
        thought_content = self._analyze_thought_content(answers)
        
        risk_assessment = {
            'suicide_risk_level': suicide_risk['risk_level'],
            'homicide_risk_level': homicide_risk['risk_level'],
            'substance_use_concern': False,
            'acute_anxiety': False,
            'sleep_disturbance': False,
            'overall_risk': 'Low',
            'immediate_intervention_needed': False,
            'risk_factors': [],
            'protective_factors': [],
            'critical_flag': False,
            'confidence': 0.3,
            'evidence': [],
        }
        
        # Substance use
        if q11 and any(word in q11 for word in self.SUBSTANCE_USE):
            if any(word in q11 for word in ['daily', 'often', 'a lot', 'problem', 'can\'t stop']):
                risk_assessment['substance_use_concern'] = True
                risk_assessment['risk_factors'].append('Significant substance use')
            else:
                risk_assessment['risk_factors'].append('Substance use reported')
        
        # Anxiety
        if any(word in q3 + q4 for word in self.ANXIETY_INDICATORS):
            risk_assessment['acute_anxiety'] = True
            risk_assessment['risk_factors'].append('Significant anxiety symptoms')

        # Depression/Anxiety severity from standardized scales
        phq = scales.get('phq9', {})
        gad = scales.get('gad7', {})
        if phq.get('severity_label') in ['Moderate', 'Severe']:
            risk_assessment['risk_factors'].append(f"Depression severity (PHQ-style): {phq.get('severity_label')}")
        if gad.get('severity_label') in ['Moderate', 'Severe']:
            risk_assessment['risk_factors'].append(f"Anxiety severity (GAD-style): {gad.get('severity_label')}")
        
        # Sleep disturbance
        if any(word in q5 for word in self.SLEEP_ISSUES):
            risk_assessment['sleep_disturbance'] = True
            risk_assessment['risk_factors'].append('Sleep disturbance')

        # Psychosis increases risk priority
        if thought_content['hallucinations']['present'] or thought_content['delusions']['present']:
            risk_assessment['risk_factors'].append('Psychosis features present (ICD-11 priority)')

        # Overall risk calculation
        if thought_content['hallucinations']['present'] or thought_content['delusions']['present']:
            risk_assessment['overall_risk'] = 'High'
            risk_assessment['immediate_intervention_needed'] = True
        elif suicide_risk['risk_level'] == 'High' or homicide_risk['risk_level'] == 'High':
            risk_assessment['overall_risk'] = 'High'
            risk_assessment['immediate_intervention_needed'] = True
        elif suicide_risk['risk_level'] == 'Moderate' or homicide_risk['risk_level'] == 'Moderate':
            risk_assessment['overall_risk'] = 'Moderate'
        elif phq.get('probable_depressive_episode') or phq.get('severity_label') in ['Moderate', 'Severe']:
            risk_assessment['overall_risk'] = 'Moderate'
        elif gad.get('severity_label') in ['Moderate', 'Severe']:
            risk_assessment['overall_risk'] = 'Moderate'
        elif len(risk_assessment['risk_factors']) >= 3:
            risk_assessment['overall_risk'] = 'Moderate'
        
        # Protective factors
        q14 = answers.get('14', '').lower()
        if any(word in ' '.join(answers.values()).lower() for word in 
               ['family', 'support', 'friends', 'hope', 'faith', 'religion', 'children']):
            risk_assessment['protective_factors'].append('Social support mentioned')
        
        if suicide_risk.get('protective_factors'):
            risk_assessment['protective_factors'].extend(suicide_risk['protective_factors'])

        # Contradiction detection: denied in Q7 but self-harm/suicide-like content elsewhere.
        q7 = answers.get('7', '').lower()
        if any(deny in q7 for deny in ['no', 'none', "don't", "do not"]) and (
            self._match_lexicon(' '.join(answers.values()).lower(), self.SUICIDAL_INDICATORS['active'])['present']
            or self._match_lexicon(' '.join(answers.values()).lower(), self.SUICIDAL_INDICATORS['self_harm'])['present']
        ):
            risk_assessment['risk_factors'].append('Contradiction detected: denied suicidality in Q7 but concerning content appears elsewhere')
            risk_assessment['needs_clinician_review'] = True
            risk_assessment['overall_risk'] = 'Moderate' if risk_assessment['overall_risk'] == 'Low' else risk_assessment['overall_risk']

        meta = self._build_domain_meta(risk_assessment['risk_factors'], [])
        risk_assessment['confidence'] = meta['confidence']
        risk_assessment['evidence'] = meta['evidence']

        return risk_assessment
    
    def _generate_clinical_impressions(self, answers: Dict[str, str], scales: Dict[str, Any]) -> List[str]:
        """Generate clinical impressions based on analysis"""
        
        impressions = []
        
        # Analyze each domain
        mood_affect = self._analyze_mood_affect(answers)
        thought_content = self._analyze_thought_content(answers)
        risk = self._analyze_risk(answers)
        insight = self._analyze_insight_judgment(answers)

        # Tier 1: Critical safety
        if risk.get('critical_flag'):
            impressions.append('CRITICAL RISK: Non-negated suicidal/homicidal content detected - immediate clinical action required')

        # Mood/Affect impressions
        if mood_affect['mood_category'] == 'depressed':
            impressions.append('Depressive symptoms present - low mood, possible anhedonia')
        elif mood_affect['mood_category'] == 'anxious':
            impressions.append('Significant anxiety symptoms reported')
        elif mood_affect['mood_category'] == 'elevated':
            impressions.append('Elevated mood - assess for manic/hypomanic symptoms')
        
        # Psychotic symptoms
        if thought_content['hallucinations']['present']:
            types = ', '.join(thought_content['hallucinations']['types'])
            impressions.append(f'Psychotic symptoms present - {types} hallucinations')
        
        if thought_content['delusions']['present']:
            types = ', '.join(thought_content['delusions']['types'])
            impressions.append(f'Delusional thinking present - {types} themes')

        # Tier 3: ICD-11 psychosis priority referral heuristic
        if thought_content['hallucinations']['present'] or thought_content['delusions']['present']:
            impressions.append('Clinical Priority 1: Psychosis features detected - refer to clinician for full assessment (ICD-11 heuristic)')
        
        # Safety concerns
        if risk['suicide_risk_level'] in ['Moderate', 'High']:
            impressions.append(f'SAFETY CONCERN: {risk["suicide_risk_level"]} suicide risk - requires immediate attention')
        
        if risk['homicide_risk_level'] in ['Moderate', 'High']:
            impressions.append(f'SAFETY CONCERN: {risk["homicide_risk_level"]} homicide risk - duty to warn may apply')
        
        # Substance use
        if risk['substance_use_concern']:
            impressions.append('Substance use disorder - assess severity and readiness for treatment')
        
        # Insight/Judgment
        if not insight['awareness']:
            impressions.append('Limited insight into mental health difficulties')
        if not insight['treatment_acceptance']:
            impressions.append('Ambivalence or resistance to treatment')

        # Tier 2: PHQ-9 mapping (DSM-5 duration + impairment rule)
        phq = scales.get('phq9', {})
        if phq.get('probable_depressive_episode'):
            impressions.append('Probable Depressive Episode (rule-based) - DSM-5 2-week duration + impairment criteria met')
        elif phq.get('severity_label') in ['Moderate', 'Severe']:
            impressions.append('Depressive symptoms with moderate/severe intensity (PHQ-9-style mapping)')

        # Insight rule: denies problems but other tiers flagged
        if insight['insight'].startswith('Poor') and (risk.get('critical_flag') or phq.get('probable_depressive_episode')):
            impressions.append('Poor Insight: Denies difficulties despite clinically significant findings')
        
        if not impressions:
            impressions.append('No acute psychiatric symptoms identified - further assessment recommended')
        if risk.get('needs_clinician_review'):
            impressions.append('Needs clinician review due to internal response contradiction.')
        
        return impressions
    
    def _generate_recommendations(self, answers: Dict[str, str]) -> List[str]:
        """Generate treatment recommendations"""
        
        recommendations = []
        risk = self._analyze_risk(answers)
        thought_content = self._analyze_thought_content(answers)
        mood_affect = self._analyze_mood_affect(answers)
        insight = self._analyze_insight_judgment(answers)
        
        # Safety first
        if risk['immediate_intervention_needed']:
            recommendations.append('IMMEDIATE: Safety assessment and crisis intervention required')
            recommendations.append('Consider psychiatric hospitalization or intensive outpatient program')
            recommendations.append('Remove access to lethal means')
            recommendations.append('Establish 24/7 supervision until acute risk subsides')
        
        # Psychiatric evaluation
        if thought_content['hallucinations']['present'] or thought_content['delusions']['present']:
            recommendations.append('Psychiatric evaluation for antipsychotic medication')
            recommendations.append('Rule out organic causes (medical workup, drug screen)')
        
        # Mood treatment
        if mood_affect['mood_category'] == 'depressed':
            recommendations.append('Consider antidepressant medication evaluation')
            recommendations.append('Cognitive Behavioral Therapy (CBT) for depression')
        elif mood_affect['mood_category'] == 'anxious':
            recommendations.append('Anxiety-focused psychotherapy (CBT, exposure therapy)')
            recommendations.append('Consider anxiolytic medication if symptoms severe')
        
        # Substance use
        if risk['substance_use_concern']:
            recommendations.append('Substance use assessment and referral to addiction treatment')
            recommendations.append('Consider 12-step program or other peer support')
        
        # Sleep
        if risk['sleep_disturbance']:
            recommendations.append('Sleep hygiene education')
            recommendations.append('Consider sleep study if indicated')
        
        # General recommendations
        recommendations.append('Regular psychiatric follow-up appointments')
        recommendations.append('Psychoeducation about diagnosed conditions')
        
        if insight['treatment_acceptance']:
            recommendations.append('Patient appears motivated for treatment - good prognostic sign')
        else:
            recommendations.append('Motivational interviewing to enhance treatment engagement')
        
        return recommendations
    
    def _calculate_sentiment(self, text: str) -> float:
        """
        Simple sentiment analysis
        Returns score from -1 (very negative) to +1 (very positive)
        """
        positive_words = ['good', 'happy', 'great', 'better', 'fine', 'well', 'okay', 'positive']
        negative_words = ['bad', 'sad', 'depressed', 'anxious', 'worried', 'terrible', 'awful', 
                         'horrible', 'miserable', 'hopeless', 'worthless']
        
        tokens = self._tokenize(text)
        pos_count = 0
        neg_count = 0
        for i, token in enumerate(tokens):
            if token in positive_words:
                if any(t in self.NEGATION_CUES for t in tokens[max(0, i - 2):i]):
                    neg_count += 1
                else:
                    pos_count += 1
            if token in negative_words:
                if any(t in self.NEGATION_CUES for t in tokens[max(0, i - 2):i]):
                    pos_count += 1
                else:
                    neg_count += 1
        
        total = pos_count + neg_count
        if total == 0:
            return 0.0
        
        return (pos_count - neg_count) / total

    def _analyze_standardized_scales(self, answers: Dict[str, str]) -> Dict[str, Any]:
        """
        Rule-based severity mapping inspired by PHQ-9 / GAD-7 using open-ended answers.
        """
        q1 = answers.get('1', '').lower()
        q2 = answers.get('2', '').lower()
        q3 = answers.get('3', '').lower()
        q4 = answers.get('4', '').lower()
        q5 = answers.get('5', '').lower()

        impairment_present = self._detect_impairment(answers)
        duration_days, duration_meets_2_weeks = self._estimate_duration_days(' '.join([q1, q2, q5]))

        depressive_matches = self._match_lexicon(' '.join([q1, q2]), self.DEPRESSIVE_LEXICON)
        sleep_matches = self._match_lexicon(q5, self.SLEEP_LEXICON)
        depressive_symptoms = len(depressive_matches['present']) + len(sleep_matches['present'])
        depressive_intensity = depressive_matches['intensity_hits'] + sleep_matches['intensity_hits']

        depression_score = 0
        if depressive_symptoms > 0:
            depression_score += 1
        if depressive_symptoms >= 2 or depressive_intensity > 0:
            depression_score += 1
        if duration_meets_2_weeks or impairment_present:
            depression_score += 1
        depression_score = min(depression_score, 3)

        depression_label = ['None', 'Mild', 'Moderate', 'Severe'][depression_score]

        anxiety_matches = self._match_lexicon(' '.join([q3, q4]), self.ANXIETY_LEXICON)
        anxiety_symptoms = len(anxiety_matches['present'])
        anxiety_intensity = anxiety_matches['intensity_hits']

        anxiety_score = 0
        if anxiety_symptoms > 0:
            anxiety_score += 1
        if anxiety_symptoms >= 2 or anxiety_intensity > 0:
            anxiety_score += 1
        if duration_meets_2_weeks:
            anxiety_score += 1
        anxiety_score = min(anxiety_score, 3)

        anxiety_label = ['None', 'Mild', 'Moderate', 'Severe'][anxiety_score]

        probable_depressive_episode = (
            depression_score >= 2 and duration_meets_2_weeks and impairment_present
        )

        return {
            'phq9': {
                'score_0_3': depression_score,
                'severity_label': depression_label,
                'duration_days_estimate': duration_days,
                'duration_2_weeks_or_more': duration_meets_2_weeks,
                'impairment_present': impairment_present,
                'probable_depressive_episode': probable_depressive_episode
            },
            'gad7': {
                'score_0_3': anxiety_score,
                'severity_label': anxiety_label,
                'duration_2_weeks_or_more': duration_meets_2_weeks
            }
        }
    
    def generate_formatted_report(self, analysis: Dict[str, Any]) -> str:
        """Generate human-readable MSE report"""
        
        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append("MENTAL STATUS EXAMINATION REPORT")
        report_lines.append("AI-Assisted Analysis")
        report_lines.append("Heuristic Confidence: Medium (rule-based, non-diagnostic)")
        report_lines.append("=" * 80)
        report_lines.append(f"Assessment Date: {analysis['timestamp']}")
        report_lines.append("")
        
        # MOOD AND AFFECT
        report_lines.append("MOOD AND AFFECT")
        report_lines.append("-" * 80)
        mood = analysis['mood_affect']
        report_lines.append(f"Stated Mood: {mood['stated_mood']}")
        report_lines.append(f"Mood Category: {mood['mood_category']}")
        report_lines.append(f"Sentiment Analysis Score: {mood['sentiment_score']:.2f} (-1 to +1 scale)")
        report_lines.append(f"Affect Range: {mood['affect_range']}")
        report_lines.append(f"Congruence: {mood['congruence']}")
        if mood['affect_quality']:
            report_lines.append(f"Affect Quality: {', '.join(mood['affect_quality'])}")
        report_lines.append("")
        
        # THOUGHT CONTENT
        report_lines.append("THOUGHT CONTENT")
        report_lines.append("-" * 80)
        
        # Suicidal ideation
        si = analysis['thought_content']['suicidal_ideation']
        report_lines.append(f"Suicidal Ideation: {'Present' if si['present'] else 'Denied'}")
        if si['present']:
            report_lines.append(f"  Type: {si['type']}")
            report_lines.append(f"  Severity: {si['severity']}")
            report_lines.append(f"  Plan: {'Yes' if si['plan'] else 'No'}")
            report_lines.append(f"  Risk Level: {si['risk_level']}")
            if si['protective_factors']:
                report_lines.append(f"  Protective Factors: {', '.join(si['protective_factors'])}")
        
        # Homicidal ideation
        hi = analysis['thought_content']['homicidal_ideation']
        report_lines.append(f"Homicidal Ideation: {'Present' if hi['present'] else 'Denied'}")
        if hi['present']:
            report_lines.append(f"  Specific Target: {'Yes' if hi['specific_target'] else 'No'}")
            report_lines.append(f"  Plan: {'Yes' if hi['plan'] else 'No'}")
            report_lines.append(f"  Risk Level: {hi['risk_level']}")
        
        # Hallucinations
        hall = analysis['thought_content']['hallucinations']
        report_lines.append(f"Hallucinations: {'Present' if hall['present'] else 'Denied'}")
        if hall['present']:
            report_lines.append(f"  Types: {', '.join(hall['types'])}")
            report_lines.append(f"  Frequency: {hall['frequency']}")
            report_lines.append(f"  Distressing: {'Yes' if hall['distressing'] else 'No'}")
        
        # Delusions
        delusions = analysis['thought_content']['delusions']
        report_lines.append(f"Delusions: {'Present' if delusions['present'] else 'Denied'}")
        if delusions['present']:
            report_lines.append(f"  Types: {', '.join(delusions['types'])}")
            report_lines.append(f"  Fixed Beliefs: {'Yes' if delusions['fixed'] else 'Uncertain'}")
        
        # OCD
        ocd = analysis['thought_content']['obsessions_compulsions']
        if ocd['obsessions_present'] or ocd['compulsions_present']:
            report_lines.append(f"Obsessive-Compulsive Symptoms:")
            report_lines.append(f"  Obsessions: {'Present' if ocd['obsessions_present'] else 'None'}")
            report_lines.append(f"  Compulsions: {'Present' if ocd['compulsions_present'] else 'None'}")
            if ocd['themes']:
                report_lines.append(f"  Themes: {', '.join(ocd['themes'])}")
        
        report_lines.append("")
        
        # THOUGHT PROCESS
        report_lines.append("THOUGHT PROCESS")
        report_lines.append("-" * 80)
        tp = analysis['thought_process']
        report_lines.append(f"Organization: {tp['organization']}")
        report_lines.append(f"Coherence: {tp['coherence']}")
        if tp['observations']:
            report_lines.append(f"Observations: {'; '.join(tp['observations'])}")
        report_lines.append("")
        
        # COGNITION
        report_lines.append("COGNITION")
        report_lines.append("-" * 80)
        cog = analysis['cognition']
        report_lines.append(f"Orientation: {cog['orientation']}")
        report_lines.append(f"Memory: {cog['memory']}")
        report_lines.append(f"Concentration: {cog['concentration']}")
        if cog['observations']:
            for obs in cog['observations']:
                report_lines.append(f"  - {obs}")
        report_lines.append("")
        
        # INSIGHT AND JUDGMENT
        report_lines.append("INSIGHT AND JUDGMENT")
        report_lines.append("-" * 80)
        ij = analysis['insight_judgment']
        report_lines.append(f"Insight: {ij['insight']}")
        report_lines.append(f"Judgment: {ij['judgment']}")
        report_lines.append(f"Awareness of Difficulties: {'Yes' if ij['awareness'] else 'No'}")
        report_lines.append(f"Treatment Acceptance: {'Yes' if ij['treatment_acceptance'] else 'No'}")
        report_lines.append("")
        
        # RISK ASSESSMENT
        report_lines.append("RISK ASSESSMENT")
        report_lines.append("-" * 80)
        risk = analysis['risk_assessment']
        report_lines.append(f"OVERALL RISK LEVEL: {risk['overall_risk']}")
        report_lines.append(f"Risk Confidence: {risk.get('confidence', 0.0):.2f}")
        report_lines.append(f"Immediate Intervention Needed: {'YES' if risk['immediate_intervention_needed'] else 'No'}")
        report_lines.append(f"Suicide Risk: {risk['suicide_risk_level']}")
        report_lines.append(f"Homicide Risk: {risk['homicide_risk_level']}")
        report_lines.append(f"Substance Use Concern: {'Yes' if risk['substance_use_concern'] else 'No'}")
        report_lines.append(f"Acute Anxiety: {'Yes' if risk['acute_anxiety'] else 'No'}")
        report_lines.append(f"Sleep Disturbance: {'Yes' if risk['sleep_disturbance'] else 'No'}")
        
        if risk['risk_factors']:
            report_lines.append("\nRisk Factors:")
            for factor in risk['risk_factors']:
                report_lines.append(f"  - {factor}")
        
        if risk['protective_factors']:
            report_lines.append("\nProtective Factors:")
            for factor in risk['protective_factors']:
                report_lines.append(f"  - {factor}")
        report_lines.append("")

        # STANDARDIZED SCALES (RULE-BASED)
        if 'standardized_scales' in analysis:
            scales = analysis['standardized_scales']
            report_lines.append("STANDARDIZED SCALES (RULE-BASED)")
            report_lines.append("-" * 80)
            phq = scales.get('phq9', {})
            gad = scales.get('gad7', {})
            report_lines.append(f"PHQ-9 Style Severity (0-3): {phq.get('score_0_3', 'N/A')} - {phq.get('severity_label', 'N/A')}")
            report_lines.append(f"Depression Duration ≥ 2 Weeks: {'Yes' if phq.get('duration_2_weeks_or_more') else 'No'}")
            report_lines.append(f"Functional Impairment Present: {'Yes' if phq.get('impairment_present') else 'No'}")
            report_lines.append(f"Probable Depressive Episode (Rule-Based): {'Yes' if phq.get('probable_depressive_episode') else 'No'}")
            report_lines.append(f"GAD-7 Style Severity (0-3): {gad.get('score_0_3', 'N/A')} - {gad.get('severity_label', 'N/A')}")
            report_lines.append("")
        
        # CLINICAL IMPRESSIONS
        report_lines.append("CLINICAL IMPRESSIONS")
        report_lines.append("-" * 80)
        for i, impression in enumerate(analysis['clinical_impressions'], 1):
            report_lines.append(f"{i}. {impression}")
        report_lines.append("")

        # RULES APPLIED
        if 'rules_applied' in analysis:
            report_lines.append("RULES APPLIED")
            report_lines.append("-" * 80)
            for i, rule in enumerate(analysis['rules_applied'], 1):
                report_lines.append(f"{i}. {rule}")
            report_lines.append("")
        
        # RECOMMENDATIONS
        report_lines.append("RECOMMENDATIONS")
        report_lines.append("-" * 80)
        for i, rec in enumerate(analysis['recommendations'], 1):
            report_lines.append(f"{i}. {rec}")
        report_lines.append("")
        
        report_lines.append("=" * 80)
        report_lines.append("END OF REPORT")
        report_lines.append("=" * 80)
        report_lines.append("")
        report_lines.append("NOTE: This is an AI-assisted analysis and should be reviewed by a")
        report_lines.append("qualified mental health professional. This report does not constitute")
        report_lines.append("a formal diagnosis or treatment plan.")
        report_lines.append("Uncertainty notice: Outputs are heuristic and may contain false positives/negatives.")
        
        return '\n'.join(report_lines)


# Example usage function
def analyze_patient_responses(answers_dict: Dict[str, str]) -> Tuple[Dict, str]:
    """
    Convenience function to analyze responses and get both structured and formatted output
    
    Args:
        answers_dict: Dictionary of {question_id: answer_text}
        
    Returns:
        Tuple of (structured_analysis_dict, formatted_report_text)
    """
    analyzer = MSEAnalyzer()
    analysis = analyzer.analyze_all_responses(answers_dict)
    formatted_report = analyzer.generate_formatted_report(analysis)
    
    return analysis, formatted_report


def append_emotion_summary_to_report(formatted_report: str, emotion_summary: Dict[str, Any]) -> str:
    lines = [formatted_report, "", "=" * 80, "EMOTION STREAM SUMMARY", "-" * 80]

    if not emotion_summary.get("available"):
        lines.append("No emotion data available for this assessment.")
        return "\n".join(lines)

    lines.append(f"Sample Size: {emotion_summary.get('sample_size', 0)}")
    lines.append(f"Total Records: {emotion_summary.get('total_records', emotion_summary.get('sample_size', 0))}")
    lines.append(f"Overall Dominant Emotion: {emotion_summary.get('overall_dominant_emotion')}")
    lines.append("")

    lines.append("Distribution Counts:")
    distribution = emotion_summary.get("distribution_counts", {})
    if distribution:
        for emotion, count in distribution.items():
            lines.append(f"  - {emotion}: {count}")
    else:
        lines.append("  - None")

    lines.append("")
    lines.append("Average Emotion Scores:")
    avg_scores = emotion_summary.get("average_emotion_scores", {})
    if avg_scores:
        for emotion, score in avg_scores.items():
            lines.append(f"  - {emotion}: {score:.4f}")
    else:
        lines.append("  - None")

    lines.append("")
    lines.append("Per-Question Dominant Emotion:")
    per_q = emotion_summary.get("per_question_dominant", {})
    if per_q:
        for qid, emotion in per_q.items():
            lines.append(f"  - Q{qid}: {emotion}")
    else:
        lines.append("  - None")

    distress = emotion_summary.get("distress_proxy", {})
    lines.append("")
    lines.append(
        f"Distress Proxy: flag={distress.get('flag')} ratio={distress.get('ratio')} threshold={distress.get('threshold')}"
    )
    lines.append(f"Distress Proxy Lower Bound: {distress.get('ratio_lower_bound')}")
    lines.append(f"Note: {distress.get('note', 'Soft indicator only; not a diagnosis.')}" )

    return "\n".join(lines)
