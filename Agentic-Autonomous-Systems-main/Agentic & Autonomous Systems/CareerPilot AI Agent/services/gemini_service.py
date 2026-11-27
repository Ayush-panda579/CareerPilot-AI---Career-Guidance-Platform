import os
from pathlib import Path

from dotenv import dotenv_values, load_dotenv
import google.generativeai as genai
from google.api_core.exceptions import DeadlineExceeded, GoogleAPIError
from requests.exceptions import RequestException, Timeout

APP_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(APP_ROOT / ".env")

_LOCAL_CONFIG = dotenv_values(APP_ROOT / ".env")


class GeminiConfigurationError(RuntimeError):
    pass


class GeminiServiceError(RuntimeError):
    pass


def _get_api_key():
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if api_key:
        return api_key

    return (
        _LOCAL_CONFIG.get("GEMINI_API_KEY")
        or _LOCAL_CONFIG.get("GOOGLE_API_KEY")
    )


def _get_model_name():
    return (
        os.getenv("GEMINI_MODEL")
        or _LOCAL_CONFIG.get("GEMINI_MODEL")
        or "gemini-3.5-flash-lite"
    )


def generate_ai_response(prompt):
    api_key = _get_api_key()
    if not api_key:
        raise GeminiConfigurationError(
            "Gemini is not configured. Set GEMINI_API_KEY in the environment "
            "or in a local .env file."
        )

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(_get_model_name())
        response = model.generate_content(
            prompt,
            generation_config={
                "max_output_tokens": 320,
                "temperature": 0.4,
            },
            request_options={"timeout": 10},
        )
    except (DeadlineExceeded, Timeout) as error:
        raise GeminiServiceError(
            "Gemini did not respond within 10 seconds. Please retry with a "
            "shorter question."
        ) from error
    except GoogleAPIError as error:
        error_text = str(error).lower()
        status_code = getattr(error, "code", None)
        if (
            status_code in (400, 401, 403)
            and ("api key" in error_text or "api_key" in error_text
                 or status_code in (401, 403))
        ):
            raise GeminiConfigurationError(
                "Gemini rejected the configured API key or access. Add a valid "
                "Gemini API key with API access in the local .env file."
            ) from error
        if status_code == 404:
            raise GeminiConfigurationError(
                "The configured Gemini model is unavailable. Check GEMINI_MODEL "
                "and ensure the model is available to your API key."
            ) from error
        raise GeminiServiceError(
            "The Gemini API request failed. Check API access and network "
            "connection, then retry."
        ) from error
    except RequestException as error:
        raise GeminiServiceError(
            "Could not reach Gemini. Check the network connection and retry."
        ) from error

    try:
        text = response.text
    except ValueError as error:
        raise GeminiServiceError(
            "Gemini returned no text for this request. Please try rephrasing it."
        ) from error

    if not text or not text.strip():
        raise GeminiServiceError(
            "Gemini returned an empty response. Please try again."
        )

    return text.strip()