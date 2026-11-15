"""Optional Gemini integration for free-text questions.

The rule-based assistant always works; Gemini only adds plain-language answers
when GEMINI_API_KEY is configured. The model never sees emails, care codes or
passcodes, and is instructed never to change doses or diagnose.
"""

import logging
from typing import Protocol

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTION = """You are CareSync's care assistant for an elderly person, their caretakers and family.
Rules:
- Answer in plain, warm, simple English in at most 120 words. Use short sentences.
- Use only the care context provided plus general, well-established health information.
- Never diagnose, never change or suggest new doses, never tell anyone to stop a medicine.
- For anything about doses, side effects, interactions or symptoms,
  advise confirming with a doctor or pharmacist.
- If the question describes an emergency (chest pain, breathing trouble, fainting, stroke signs, overdose),
  tell them to call emergency services (112 in India) immediately, first.
- Respect the elderly person's independence: speak to them, not about them, when they are asking.
- If the question is unrelated to the person's care, politely say you can only help with their care."""

DISCLAIMER = (
    "CareSync's assistant gives general information, not medical advice. Check with a doctor or pharmacist."
)


class AssistantModel(Protocol):
    def answer(self, question: str, context: str) -> str: ...


class AIUnavailableError(RuntimeError):
    """The AI service could not produce an answer."""


class GeminiAssistant:
    def __init__(self, api_key: str, model: str) -> None:
        from google import genai  # Imported lazily so the app starts fast without AI.

        self._client = genai.Client(api_key=api_key)
        self._model = model

    def answer(self, question: str, context: str) -> str:
        from google.genai import errors, types

        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=f"Care context:\n{context}\n\nQuestion:\n{question}",
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    temperature=0.3,
                    max_output_tokens=600,
                ),
            )
        except errors.APIError as exc:
            logger.warning("Gemini request failed: %s", exc)
            raise AIUnavailableError("The assistant is unavailable right now.") from exc
        text = (response.text or "").strip()
        if not text:
            raise AIUnavailableError("The assistant could not answer that. Please rephrase.")
        return text


def build_assistant(api_key: str | None, model: str) -> AssistantModel | None:
    return GeminiAssistant(api_key, model) if api_key else None
