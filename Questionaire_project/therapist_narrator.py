import logging
import time
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# Groq uses the OpenAI-compatible chat completions endpoint
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# ---------------------------------------------------------------------------
# Internal: HTTP call to Groq REST API
# ---------------------------------------------------------------------------

def _call_groq(prompt: str, max_tokens: int = 1024) -> str:
    api_key = getattr(settings, "GROQ_API_KEY", None)
    if not api_key:
        logger.error("[Therapist] GROQ_API_KEY is not set in Django settings.")
        return ""

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "llama-3.3-70b-versatile",  # High quality, fast model
        "messages": [
            {
                "role": "system", 
                "content": "You are a warm, empathetic virtual therapist for university students."
            },
            {
                "role": "user", 
                "content": prompt
            }
        ],
        "temperature": 0.7,
        "max_tokens": max_tokens,
    }

    for attempt in range(3):
        try:
            response = requests.post(GROQ_URL, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 429:
                logger.warning("[Therapist] Groq Rate limit hit. Retrying...")
                time.sleep(2)
                continue
                
            response.raise_for_status()
            data = response.json()
            text = data["choices"][0]["message"]["content"].strip()
            logger.info("[Therapist] Groq response received — %d chars", len(text))
            return text

        except Exception as e:
            logger.error("[Therapist] Error calling Groq: %s", e)
            if attempt < 2:
                time.sleep(1)
            else:
                return ""
    return ""

# ---------------------------------------------------------------------------
# Internal: Build context block (Keeping your existing logic)
# ---------------------------------------------------------------------------

def _build_minimal_context(analysis_result) -> dict:
    return {
        "emotional_summary": analysis_result.emotional_summary or "No reflection provided.",
        "comparison_results": [
            comp.get("comparison_result", "") if isinstance(comp, dict) else str(comp)
            for comp in (analysis_result.comparison_results or [])
        ],
        "recommendations": analysis_result.recommendations_json or {},
        "levels": {
            "depression": analysis_result.depression_level or "unknown",
            "anxiety": analysis_result.anxiety_level or "unknown",
            "stress": analysis_result.stress_level or "unknown",
        }
    }

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def generate_therapist_script(analysis_result) -> str:
    logger.info("[Therapist] Generating Groq script for assessment_id=%s", analysis_result.assessment_id)

    context = _build_minimal_context(analysis_result)
    
    # Prompt construction remains largely the same as your high-quality version
    prompt = f"""
    You are a warm, empathetic virtual therapist speaking directly to a university student after reviewing their mental health assessment. Speak in first person as a therapist — calm, unhurried, and human.

    ASSESSMENT DATA:
    - Depression: {context['levels']['depression']}
    - Anxiety: {context['levels']['anxiety']}
    - Stress: {context['levels']['stress']}
    - Previous Session Trends: {", ".join(context['comparison_results']) if context['comparison_results'] else "No previous sessions available."}
    - Recommendations to weave in naturally: {context['recommendations']}
    - What the student shared with you: "{context['emotional_summary']}"

    YOUR TASK:
    Write a single flowing therapist monologue of exactly 280–350 words. Follow this structure naturally — do not use headers or bullet points, just warm continuous speech:

    1. OPEN WITH THE REPORT FINDINGS (2–3 sentences)
    Start by gently telling the student what the assessment has found. Lead with the most concerning finding first (highest severity). Use phrases like "According to your responses, it seems like you may be experiencing signs of..." — never diagnose, always say "signs of".

    2. ACKNOWLEDGE WHAT THEY SHARED (2–3 sentences)
    Reference their emotional reflection directly. Use phrases like "Based on what you have shared with me..." or "I hear that you have been feeling...". 
    and provide consoling according to that like if it's insecurity then mention you are different from others everyone is unique etc
    If they mentioned anything that suggests suicidal ideation, self-harm, or threat of violence — explicitly and compassionately tell them to contact a mental health professional or crisis helpline immediately, and make this the priority above all else.

    3. SPEAK TO THE TREND (2–3 sentences)
    Address the previous session comparison specifically. Name which dimension improved, which worsened, and which showed no improvement. If things are worsening or showing no improvement, use extra warmth and tell them they deserve additional care and support right now. If improving, offer gentle encouragement without being dismissive of remaining struggles.

    4. WEAVE IN RECOMMENDATIONS (3–4 sentences)
    Naturally suggest the provided recommendations as if you are personally advising them gently introducing each one, provide list of recommendations in bullet points. Use phrases like "The few things I would gently encourage you to try..." or "I wonder if it might help to...".

    5. CLOSING (1–2 sentences)
    End with a warm, reassuring statement that reminds them they are not alone and that small steps matter.

    TONE RULES:
    - Use "it seems like", "I wonder if", "I hear that", "it sounds like" throughout
    - Never use clinical bullet points or numbered steps in the output
    - Never diagnose — always "signs of" or "may be experiencing"
    - Write as if you are sitting across from this person and speaking slowly and kindly
    """


    # Use the new Groq caller
    response_text = _call_groq(prompt)
    
    # Emergency Fallback if API fails
    if not response_text:
        return ("I'm here with you. It sounds like things have been quite difficult lately. "
                "I want to help you navigate these feelings—please take a moment to breathe, "
                "and remember that your well-being is the most important thing right now.")

    return response_text


    