# --- Active provider: "ollama", "groq", or "omniroute" ---
# NOTE: This is a last-resort fallback only. Provider is dynamically resolved
# from Job Search AI Settings (via SettingsService) at runtime. Change the
# provider there, not here.
LLM_PROVIDER = "ollama"

# --- Ollama config ---
OLLAMA_MODEL_NAME = "qwen3:8b"
OLLAMA_BASE_URL = "http://135.181.6.215:11434"

# --- Groq config ---
GROQ_MODEL_NAME = "groq/compound"
GROQ_API_KEY = ""  # Set via environment variable GROQ_API_KEY or Frappe site config
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# --- OmniRoute config ---
OMNIROUTE_MODEL_NAME = "career-agent"
OMNIROUTE_BASE_URL = "http://localhost:20128/v1"
OMNIROUTE_API_KEY = "my_test_omniroute_key"

# --- Shared config ---
QUESTION_COUNT = 5
QUESTION_GENERATION_ATTEMPTS = 3
QUESTION_MAX_TOKENS = 2200
PASS_SCORE = 60
REQUEST_TIMEOUT_SECONDS = 60   # Groq is fast; Ollama may need more

# Convenience alias — whichever provider is active
if LLM_PROVIDER == "omniroute":
    MODEL_NAME = OMNIROUTE_MODEL_NAME
elif LLM_PROVIDER == "groq":
    MODEL_NAME = GROQ_MODEL_NAME
else:
    MODEL_NAME = OLLAMA_MODEL_NAME
