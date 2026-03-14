import json
import requests
from django.conf import settings

# Use the v1beta endpoint for modern structured output capabilities
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent?key={key}"
)

def analyze_open_ended_text(text: str) -> dict:
    """
    Analyzes student input using Gemini API.
    Optimized to dynamically identify concerns and feelings based on the text 
    without a predefined list, returning only relevant data.
    """
    if not text or not text.strip():
        return _empty_result("No response provided.")

    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        return _empty_result("Gemini API key not configured.")

    # OPTIMIZED PROMPT:
    # 1. Removes the fixed list of emotions.
    # 2. Asks the model to identify the most relevant feelings based on context.
    # 3. Ensures only present concerns/feelings are returned.
    prompt = f"""
    Act as a compassionate school counselor. Analyze the following student response:
    "{text[:3000]}"
    
    Instructions:
    - Identify the core concerns expressed by the student.
    - Identify the specific emotions or feelings present in the text. 
    - Provide a score (0.1 to 1.0) for each identified feeling based on its intensity.
    - Do NOT return a list of feelings with 0.0 scores; only include what is actually present.
    - Provide a 2-3 sentence compassionate summary of the student's situation.

    Return a JSON object with this structure:
    {{
      "identified_concerns": ["list", "of", "top", "concerns"],
      "relevant_feelings": {{
        "FeelingName": float_score
      }},
      "summary": "Your compassionate summary here."
    }}
    """

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.2
        }
    }

    try:
        resp = requests.post(
            GEMINI_URL.format(key=api_key),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()

        data = resp.json()
        text_out = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(text_out)

        # Mapping to your existing application structure
        return {
            "concern_feeling_label": parsed.get("relevant_feelings", {}),
            "summary": parsed.get("summary", ""),
            "concerns": parsed.get("identified_concerns", []),
            "available": True
        }

    except Exception as e:
        return _empty_result(f"Analysis failed: {str(e)}")
def _empty_result(reason: str = "") -> dict:
    return {
        "concern_feeling_label": {},
        "summary": reason,
        "available": False,
    }