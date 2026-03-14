import json
import logging
import time
import requests
from django.conf import settings
import re

logger = logging.getLogger(__name__)

# ── HuggingFace Inference API — GoEmotions RoBERTa (28 labels) ───────────────
# Model: SamLowe/roberta-base-go_emotions
# Labels: 27 emotional concerns + "neutral" (neutral is filtered out on return)
# Full label list: admiration, amusement, anger, annoyance, approval, caring,
#   confusion, curiosity, desire, disappointment, disapproval, disgust,
#   embarrassment, excitement, fear, gratitude, grief, joy, love, nervousness,
#   optimism, pride, realization, relief, remorse, sadness, surprise, neutral
HF_INFERENCE_URL = (
    "https://router.huggingface.co/hf-inference/models/"
    "SamLowe/roberta-base-go_emotions"
)
# ── OpenRouter endpoint for LLaMA 4 ──────────────────────────────────────────
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
LLAMA4_MODEL   = "meta-llama/llama-4-maverick"

# ── Constants ─────────────────────────────────────────────────────────────────
EMOTION_SCORE_THRESHOLD = 0.01   # minimum score to include an emotion
MAX_TOP_EMOTIONS        = 10     # how many emotions to pass to LLaMA prompt
MAX_TEXT_FOR_ROBERTA    = 1000   # chars (safe ~512 token approximation)
MAX_TEXT_FOR_LLAMA      = 3000   # chars
ROBERTA_TIMEOUT_SEC     = 30
OPENROUTER_TIMEOUT_SEC  = 45
# FIX 1: Reduced retry count — original had MAX_RETRIES + 2 loop range
# which caused an off-by-one. Now MAX_RETRIES controls loop directly.
MAX_RETRIES             = 5      # number of retry attempts on transient errors
RETRY_BACKOFF_SEC       = 5.0    # seconds to wait between retries


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────
def check_for_emergency(text: str) -> list:
    text_lower = text.lower()
    detected_categories = []
    
    # This regex uses a negative lookbehind (?<!...) to ignore matches 
    # preceded by "don't", "not", "won't", or "never"
    risks = {
        "Suicidal Ideation": [
            r"(?<!don't )\bkill myself\b", 
            r"(?<!not )\bsuicide\b", 
            r"(?<!don't )\bend my life\b", 
            r"(?<!don't )\bwant to die\b"
        ],
        "Threat of Violence": [
            r"(?<!don't )\bkill others\b", 
            r"(?<!not )\bhurt others\b", 
            r"(?<!not )\bharm others\b"
        ],
        "Self-Harm": [
            r"(?<!don't )\bhurt myself\b", 
            r"(?<!don't )\bcut myself\b", 
            r"\bself-harm\b"
        ],
    }
    
    for category, patterns in risks.items():
        if any(re.search(pattern, text_lower) for pattern in patterns):
            detected_categories.append(category)
            
    return list(set(detected_categories))

def analyze_open_ended_text(text: str) -> dict:
    if not text or not text.strip():
        return _empty_result("No response provided.")

    # 1. INITIAL KEYWORD CHECK
    detected_risks = check_for_emergency(text)

    # 2. EMOTION ANALYSIS
    hf_token = getattr(settings, "HUGGING_FACE_TOKEN", "").strip()
    roberta_scores = _get_roberta_scores(text, hf_token) or {}
    concern_feeling_label = {
        label.capitalize(): round(score, 4)
        for label, score in roberta_scores.items()
        if label.lower() != "neutral" and score >= EMOTION_SCORE_THRESHOLD
    }

    # 3. LLAMA ANALYSIS (Now returns 3 values)
    openrouter_key = getattr(settings, "OPENROUTER_API_KEY", "").strip()
    summary, concerns, is_llama_confirmed = _get_llama_summary(
        text, concern_feeling_label, openrouter_key
    )

    # 4. FINAL EMERGENCY DECISION
    # We only trigger emergency if keywords found AND LLaMA agrees it's a real crisis
    if len(detected_risks) > 0 and is_llama_confirmed:
        is_emergency = True
        logger.critical(f"CONFIRMED EMERGENCY: {', '.join(detected_risks)}")
        
        for risk in detected_risks:
            label_text = f"EMERGENCY: {risk} Detected"
            if label_text not in concerns:
                concerns.insert(0, label_text)
            concern_feeling_label[risk] = 1.0
        
        risk_str = " and ".join(detected_risks)
        summary = f"⚠️ CRITICAL CONCERNS: {risk_str}. {summary}"
    else:
        # If LLaMA rejected the crisis or no keywords found, 
        # scrub any "Emergency" mentions that might have leaked
        is_emergency = False
        concerns = [c for c in concerns if "EMERGENCY" not in c.upper()]
        detected_risks = [] # Clear the risks list so it's not sent to frontend

    # Sort feelings
    concern_feeling_label = dict(
        sorted(concern_feeling_label.items(), key=lambda x: x[1], reverse=True)
    )

    return {
        "concern_feeling_label": concern_feeling_label,
        "summary": summary,
        "concerns": concerns,
        "available": True,
        "is_emergency": is_emergency,
        "emergency_types": detected_risks
    }
# ─────────────────────────────────────────────────────────────────────────────
# PRIVATE HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _get_roberta_scores(text: str, hf_token: str) -> dict | None:
    """
    Calls HuggingFace Inference API for SamLowe/roberta-base-go_emotions.
    Returns {emotion_label: score} dict or None on failure.
    Retries up to MAX_RETRIES times on transient (5xx) errors.

    Note: The model handles up to 512 tokens internally.
    We send the first MAX_TEXT_FOR_ROBERTA characters as a safe approximation.
    """
    headers = {"Authorization": f"Bearer {hf_token}"}
    payload = {"inputs": text[:MAX_TEXT_FOR_ROBERTA]}

    # FIX 3: Corrected loop range.
    # Original: range(1, MAX_RETRIES + 2) caused MAX_RETRIES+1 iterations
    # but the last attempt could still `continue` on 503 without returning.
    # Now: range(1, MAX_RETRIES + 1) = exactly MAX_RETRIES clean iterations.
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(
                HF_INFERENCE_URL,
                headers=headers,
                json=payload,
                timeout=ROBERTA_TIMEOUT_SEC,
            )

            # FIX 4: Handle model loading (HF returns 503 while warming up).
            # Original: resp.json().get(...) could raise if body is not JSON.
            # Now: wrapped in try/except so non-JSON 503 bodies don't crash.
            if resp.status_code == 503:
                try:
                    wait_time = float(
                        resp.json().get("estimated_time", RETRY_BACKOFF_SEC)
                    )
                except Exception:
                    wait_time = RETRY_BACKOFF_SEC

                logger.warning(
                    "RoBERTa model loading (attempt %d/%d). Waiting %.1fs...",
                    attempt, MAX_RETRIES, wait_time,
                )
                time.sleep(wait_time)
                continue  # retry

            # FIX 5: Log the full HTTP error body — previously swallowed silently.
            # This is the #1 debugging aid: you'll see 401 Unauthorized, etc.
            resp.raise_for_status()

            # HF pipeline returns [[{label, score}, ...]] for classifier.
            # FIX 6: Improved response parsing to handle all known HF formats:
            #   Format A: [[{label, score}, ...]]  — double-nested list
            #   Format B:  [{label, score}, ...]   — single-level list
            raw = resp.json()
            logger.debug("RoBERTa raw response type=%s len=%d", type(raw).__name__, len(raw) if raw else 0)

            if not raw or not isinstance(raw, list):
                logger.error("RoBERTa returned unexpected format (not a list): %s", str(raw)[:300])
                return None

            # Unwrap double-nesting if present
            results = raw[0] if isinstance(raw[0], list) else raw

            if not results or not isinstance(results, list):
                logger.error("RoBERTa results not a list after unwrap: %s", str(results)[:300])
                return None

            if not isinstance(results[0], dict):
                logger.error("RoBERTa first result item is not a dict: %s", str(results[0])[:200])
                return None

            # FIX 7: Validate expected keys exist before accessing them.
            if "label" not in results[0] or "score" not in results[0]:
                logger.error(
                    "RoBERTa result missing 'label'/'score' keys. Keys found: %s",
                    list(results[0].keys()),
                )
                return None

            scores = {item["label"]: item["score"] for item in results}
            logger.debug("RoBERTa returned %d emotion scores.", len(scores))
            return scores

        except requests.exceptions.Timeout:
            logger.warning(
                "RoBERTa request timed out (attempt %d/%d).", attempt, MAX_RETRIES
            )

        except requests.exceptions.ConnectionError as e:
            logger.warning(
                "RoBERTa connection error (attempt %d/%d): %s", attempt, MAX_RETRIES, e
            )

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else "unknown"
            # FIX 8: Log response body on HTTP errors so you can see 401/403 messages.
            body = ""
            if e.response is not None:
                try:
                    body = e.response.json()
                except Exception:
                    body = e.response.text[:300]
            logger.error(
                "RoBERTa HTTP %s error (attempt %d/%d): %s — body: %s",
                status, attempt, MAX_RETRIES, e, body,
            )
            # Don't retry on 4xx client errors (bad token, wrong URL, etc.)
            if e.response is not None and 400 <= e.response.status_code < 500:
                logger.error(
                    "RoBERTa 4xx error — not retrying. "
                    "Check your HUGGING_FACE_TOKEN and model URL."
                )
                return None

        except (KeyError, ValueError, json.JSONDecodeError) as e:
            logger.error("RoBERTa response parse error (attempt %d): %s", attempt, e)
            return None  # Parse errors are deterministic — no point retrying

        except Exception as e:
            logger.exception(
                "Unexpected RoBERTa error (attempt %d/%d): %s", attempt, MAX_RETRIES, e
            )

        # FIX 9: Only sleep if there are remaining attempts.
        if attempt < MAX_RETRIES:
            logger.info("Retrying RoBERTa in %.1fs...", RETRY_BACKOFF_SEC)
            time.sleep(RETRY_BACKOFF_SEC)

    logger.error("RoBERTa GoEmotions failed after %d attempts.", MAX_RETRIES)
    return None

def _get_llama_summary(
    text: str,
    emotion_scores: dict,
    openrouter_key: str,
) -> tuple[str, list, bool]:  # Added bool to return type
    """
    Sends student text + RoBERTa scores to LLaMA.
    Returns (summary_str, concerns_list, is_emergency_confirmed).
    """
    if not openrouter_key:
        logger.warning("_get_llama_summary: OPENROUTER_API_KEY missing.")
        return ("AI summary unavailable.", [], False)

    top_emotions = dict(list(emotion_scores.items())[:MAX_TOP_EMOTIONS])
    scores_formatted = ", ".join(f"{label}: {score}" for label, score in top_emotions.items()) or "none detected"

    prompt = f"""Act as a compassionate school counselor. A student has shared some very painful thoughts:

"{text[:MAX_TEXT_FOR_LLAMA]}"

Emotion analysis from RoBERTa GoEmotions model (scores 0-1, higher = stronger):
{scores_formatted}

Instructions:
- Identify the core concerns the student is expressing.
- Write a 2-3 sentence compassionate summary of their situation.
- Base your summary on both the text AND the emotion scores above.
write summary accoridng to the following instructions: 
1. Start by acknowledging the immense weight of their pain. 
2. Use natural transitions (e.g., "It sounds like this has led you ..." instead of "You have thoughts of...").
3. If they mentioned self-harm or violence, address the seriousness of those thoughts with deep compassion, not as a category.
4. Ensure the flow moves from the 'root' of the pain (comparison/inadequacy) to the 'result' (the crisis thoughts).
5. Return ONLY a JSON object.
- CRITICAL INSTRUCTION ON CRISIS:If the student explicitly denies wanting to harm themselves or others or denies suicidal thoughts (e.g., "I don't want to kill myself"), you MUST:
  1. Set "is_emergency_confirmed" to false.
  2. Do NOT mention "suicide", "killing", or "violence" in the summary or concerns.
  3. Instead, summarize their feeling as "intense emotional exhaustion" or "searching for an escape from pressure."
JSON format:
{{
  "identified_concerns": ["concern1", "concern2", "concern3"],
  "summary": "Your compassionate summary here."
  "is_emergency_confirmed": true/false
}}"""
    headers = {
        "Authorization": f"Bearer {openrouter_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": getattr(settings, "SITE_URL", "https://yourapp.example.com"),
        "X-Title": getattr(settings, "SITE_NAME", "School Counselor App"),
    }
    payload = {
        "model": LLAMA4_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 512,
        "response_format": {"type": "json_object"},
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=OPENROUTER_TIMEOUT_SEC)
            resp.raise_for_status()
            text_out = resp.json()['choices'][0]['message']['content']
            
            # Robust JSON cleaning
            clean = text_out.strip()
            if clean.startswith("```"):
                clean = clean[clean.find("\n") + 1:] if "\n" in clean else clean[3:]
            if clean.endswith("```"):
                clean = clean[:-3]
            
            parsed = json.loads(clean.strip())

            summary = parsed.get("summary", "").strip()
            concerns = parsed.get("identified_concerns", [])
            is_confirmed = parsed.get("is_emergency_confirmed", False) # Extract the boolean

            return summary, [str(c) for c in concerns], is_confirmed

        except Exception as e:
            logger.error(f"Attempt {attempt} failed: {e}")
            if attempt < MAX_RETRIES: time.sleep(RETRY_BACKOFF_SEC)

    return ("Summary generation failed.", [], False)

def _empty_result(reason: str = "") -> dict:
    """Returns a standardized empty/failure result."""
    return {
        "concern_feeling_label": {},
        "summary": reason,
        "concerns": [],
        "available": False,
        "error": reason,
    }


# ─────────────────────────────────────────────────────────────────────────────
# QUICK DIAGNOSTIC UTILITY
# Run from Django shell: python manage.py shell
#   >>> from <your_app>.emotion_analysis import diagnose
#   >>> diagnose()
# ─────────────────────────────────────────────────────────────────────────────

def diagnose() -> None:
    """
    Prints a quick diagnosis of configuration and connectivity.
    Run from Django shell to debug 'Emotion analysis failed' errors.
    """
    print("=" * 60)
    print("Emotion Analysis — Diagnostic Check")
    print("=" * 60)

    # 1. Check HuggingFace token
    hf_token = getattr(settings, "HUGGING_FACE_TOKEN", "").strip()
    if not hf_token:
        print("[FAIL] HUGGING_FACE_TOKEN is not set in Django settings.")
    else:
        masked = hf_token[:6] + "..." + hf_token[-4:]
        print(f"[ OK ] HUGGING_FACE_TOKEN found: {masked}")

    # 2. Check OpenRouter key
    or_key = getattr(settings, "OPENROUTER_API_KEY", "").strip()
    if not or_key:
        print("[WARN] OPENROUTER_API_KEY is not set — LLaMA summaries will be skipped.")
    else:
        masked = or_key[:6] + "..." + or_key[-4:]
        print(f"[ OK ] OPENROUTER_API_KEY found: {masked}")

    # 3. Test RoBERTa connectivity
    if hf_token:
        print("\nTesting RoBERTa API with sample text...")
        scores = _get_roberta_scores("I am feeling very stressed and anxious today.", hf_token)
        if scores:
            top = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
            print(f"[ OK ] RoBERTa responded. Top emotions: {top}")
        else:
            print("[FAIL] RoBERTa returned None — check logs above for the reason.")
    else:
        print("\n[SKIP] Skipping RoBERTa connectivity test (no token).")

    # 4. Test full pipeline
    if hf_token:
        print("\nTesting full pipeline...")
        result = analyze_open_ended_text("I am struggling with my coursework and feel hopeless.")
        if result.get("available"):
            print(f"[ OK ] Full pipeline succeeded.")
            print(f"       Emotions detected: {list(result['concern_feeling_label'].keys())[:5]}")
            print(f"       Summary: {result['summary'][:80]}...")
        else:
            print(f"[FAIL] Full pipeline failed: {result.get('error')}")

    print("=" * 60)