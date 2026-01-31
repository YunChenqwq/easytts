"""
DO NOT COMMIT REAL TOKENS.

Usage:
1) Copy this file to `easytts_secrets.py`
2) Fill in your own values

`easytts_tokens.load_remote_config()` will read from `easytts_secrets.py` first,
then fall back to environment variables.
"""

# Base URL of your deployed Gradio app (ModelScope / ms.show, etc.)
EASYTTS_BASE_URL = "https://yunchenqwq-easytts.ms.show"

# Treat as secret. Never commit this to git.
EASYTTS_STUDIO_TOKEN = ""

# These may change if you update the Gradio UI wiring.
EASYTTS_FN_INDEX = 3
EASYTTS_TRIGGER_ID = 19

