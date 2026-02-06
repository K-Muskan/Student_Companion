"""
Mental Status Exam (MSE) AI Analyzer
Analyzes patient responses using NLP, sentiment analysis, and pattern recognition
Based on standardized MSE assessment criteria
"""

import re
from datetime import datetime
from typing import Dict, List, Tuple, Any
import json


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
    
    def __init__(self):
        """Initialize the analyzer"""
        self.assessment = {}
        
    def analyze_all_responses(self, answers: Dict[str, str]) -> Dict[str, Any]:
        """
        Main analysis function - analyzes all responses and generates MSE report
        
        Args:
            answers: Dictionary of {question_id: answer_text}
            
        Returns:
            Complete MSE assessment report
        """
        report = {
            'timestamp': datetime.now().isoformat(),
            'mood_affect': self._analyze_mood_affect(answers),
            'thought_content': self._analyze_thought_content(answers),
            'thought_process': self._analyze_thought_process(answers),
            'cognition': self._analyze_cognition(answers),
            'insight_judgment': self._analyze_insight_judgment(answers),
            'risk_assessment': self._analyze_risk(answers),
            'clinical_impressions': self._generate_clinical_impressions(answers),
            'recommendations': self._generate_recommendations(answers),
            'full_responses': answers
        }
        
        return report
    
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
        
        # Detect mood from Q1
        if q1:
            mood_analysis['stated_mood'] = q1[:200]  # First 200 chars
            
            # Categorize mood
            mood_scores = {}
            for category, keywords in self.MOOD_KEYWORDS.items():
                score = sum(1 for kw in keywords if kw in q1)
                if score > 0:
                    mood_scores[category] = score
            
            if mood_scores:
                dominant_mood = max(mood_scores.items(), key=lambda x: x[1])
                mood_analysis['mood_category'] = dominant_mood[0]
            
            # Sentiment analysis (simple)
            mood_analysis['sentiment_score'] = self._calculate_sentiment(q1)
        
        # Analyze congruence from Q2
        if q2:
            if any(word in q2 for word in ['no', 'not', 'don\'t', 'doesn\'t', 'different']):
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
            'risk_level': 'Low'
        }
        
        if not q7 or q7 in ['no', 'none', 'n/a']:
            return risk
        
        # Check for passive ideation
        for phrase in self.SUICIDAL_INDICATORS['passive']:
            if phrase in q7:
                risk['present'] = True
                risk['type'] = 'Passive ideation'
                risk['severity'] = 'Moderate'
                risk['risk_level'] = 'Moderate'
        
        # Check for active ideation
        for phrase in self.SUICIDAL_INDICATORS['active']:
            if phrase in q7:
                risk['present'] = True
                risk['type'] = 'Active ideation'
                risk['severity'] = 'Severe'
                risk['risk_level'] = 'High'
        
        # Check for self-harm
        for phrase in self.SUICIDAL_INDICATORS['self_harm']:
            if phrase in q7:
                risk['present'] = True
                if 'self_harm' not in risk['type']:
                    risk['type'] += ' with self-harm behaviors'
                risk['risk_level'] = 'High'
        
        # Check for plan
        plan_words = ['plan', 'method', 'how i would', 'going to', 'will use']
        if any(word in q7 for word in plan_words):
            risk['plan'] = True
            risk['risk_level'] = 'High'
        
        # Check for protective factors
        protective = ['but i won\'t', 'never would', 'couldn\'t do', 'family', 'children', 'religion']
        for factor in protective:
            if factor in q7:
                risk['protective_factors'].append(factor)
        
        return risk
    
    def _assess_homicidal_ideation(self, answers: Dict[str, str]) -> Dict[str, Any]:
        """Assess homicidal ideation - Question 8"""
        q8 = answers.get('8', '').lower()
        
        risk = {
            'present': False,
            'specific_target': False,
            'plan': False,
            'risk_level': 'Low'
        }
        
        if not q8 or q8 in ['no', 'none', 'n/a']:
            return risk
        
        harm_words = ['hurt', 'harm', 'kill', 'attack', 'hit', 'punch']
        if any(word in q8 for word in harm_words):
            risk['present'] = True
            risk['risk_level'] = 'Moderate'
        
        if any(word in q8 for word in ['specific person', 'my', 'them', 'him', 'her', 'name']):
            risk['specific_target'] = True
            risk['risk_level'] = 'High'
        
        if any(word in q8 for word in ['plan', 'going to', 'will', 'method']):
            risk['plan'] = True
            risk['risk_level'] = 'High'
        
        return risk
    
    def _assess_hallucinations(self, answers: Dict[str, str]) -> Dict[str, Any]:
        """Assess for hallucinations - Question 9"""
        q9 = answers.get('9', '').lower()
        
        hallucinations = {
            'present': False,
            'types': [],
            'frequency': 'Unknown',
            'distressing': False
        }
        
        if not q9 or q9 in ['no', 'none', 'n/a']:
            return hallucinations
        
        # Check each type
        for h_type, keywords in self.PSYCHOTIC_INDICATORS['hallucinations'].items():
            for keyword in keywords:
                if keyword in q9:
                    hallucinations['present'] = True
                    if h_type not in hallucinations['types']:
                        hallucinations['types'].append(h_type)
        
        # Check frequency
        if any(word in q9 for word in ['often', 'frequently', 'always', 'constantly', 'daily']):
            hallucinations['frequency'] = 'Frequent'
        elif any(word in q9 for word in ['sometimes', 'occasionally', 'rarely']):
            hallucinations['frequency'] = 'Occasional'
        
        # Check if distressing
        if any(word in q9 for word in ['scared', 'afraid', 'frightening', 'disturbing', 'distressing']):
            hallucinations['distressing'] = True
        
        return hallucinations
    
    def _assess_delusions(self, answers: Dict[str, str]) -> Dict[str, Any]:
        """Assess for delusional thinking - Question 10"""
        q10 = answers.get('10', '').lower()
        
        delusions = {
            'present': False,
            'types': [],
            'fixed': False
        }
        
        if not q10 or q10 in ['no', 'none', 'n/a']:
            return delusions
        
        for d_type, keywords in self.PSYCHOTIC_INDICATORS['delusions'].items():
            for keyword in keywords:
                if keyword in q10:
                    delusions['present'] = True
                    if d_type not in delusions['types']:
                        delusions['types'].append(d_type)
        
        # Check if beliefs are fixed
        if any(word in q10 for word in ['know it\'s true', 'definitely', 'certain', 'sure']):
            delusions['fixed'] = True
        
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
            elif any(word in q13 for word in ['no', 'nothing wrong', 'fine', 'don\'t need']):
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
        
        # Assess other risk factors
        q3 = answers.get('3', '').lower()
        q4 = answers.get('4', '').lower()
        q5 = answers.get('5', '').lower()
        q11 = answers.get('11', '').lower()
        
        risk_assessment = {
            'suicide_risk_level': suicide_risk['risk_level'],
            'homicide_risk_level': homicide_risk['risk_level'],
            'substance_use_concern': False,
            'acute_anxiety': False,
            'sleep_disturbance': False,
            'overall_risk': 'Low',
            'immediate_intervention_needed': False,
            'risk_factors': [],
            'protective_factors': []
        }
        
        # Substance use
        if q11 and any(word in q11 for word in self.SUBSTANCE_USE):
            if any(word in q11 for word in ['daily', 'often', 'a lot', 'problem', 'can\'t stop']):
                risk_assessment['substance_use_concern'] = True
                risk_assessment['risk_factors'].append('Significant substance use')
        
        # Anxiety
        if any(word in q3 + q4 for word in self.ANXIETY_INDICATORS):
            risk_assessment['acute_anxiety'] = True
            risk_assessment['risk_factors'].append('Significant anxiety symptoms')
        
        # Sleep disturbance
        if any(word in q5 for word in self.SLEEP_ISSUES):
            risk_assessment['sleep_disturbance'] = True
            risk_assessment['risk_factors'].append('Sleep disturbance')
        
        # Overall risk calculation
        if suicide_risk['risk_level'] == 'High' or homicide_risk['risk_level'] == 'High':
            risk_assessment['overall_risk'] = 'High'
            risk_assessment['immediate_intervention_needed'] = True
        elif suicide_risk['risk_level'] == 'Moderate' or homicide_risk['risk_level'] == 'Moderate':
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
        
        return risk_assessment
    
    def _generate_clinical_impressions(self, answers: Dict[str, str]) -> List[str]:
        """Generate clinical impressions based on analysis"""
        
        impressions = []
        
        # Analyze each domain
        mood_affect = self._analyze_mood_affect(answers)
        thought_content = self._analyze_thought_content(answers)
        risk = self._analyze_risk(answers)
        insight = self._analyze_insight_judgment(answers)
        
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
        
        if not impressions:
            impressions.append('No acute psychiatric symptoms identified - further assessment recommended')
        
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
        
        text_lower = text.lower()
        pos_count = sum(1 for word in positive_words if word in text_lower)
        neg_count = sum(1 for word in negative_words if word in text_lower)
        
        total = pos_count + neg_count
        if total == 0:
            return 0.0
        
        return (pos_count - neg_count) / total
    
    def generate_formatted_report(self, analysis: Dict[str, Any]) -> str:
        """Generate human-readable MSE report"""
        
        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append("MENTAL STATUS EXAMINATION REPORT")
        report_lines.append("AI-Assisted Analysis")
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
        
        # CLINICAL IMPRESSIONS
        report_lines.append("CLINICAL IMPRESSIONS")
        report_lines.append("-" * 80)
        for i, impression in enumerate(analysis['clinical_impressions'], 1):
            report_lines.append(f"{i}. {impression}")
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