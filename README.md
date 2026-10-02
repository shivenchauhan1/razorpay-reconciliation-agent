# Streamlit deployment files

These files turn the existing Razorpay reconciliation backend into a Streamlit app without changing the reconciliation logic in `src/`.

## Files to add/replace

Copy these into the **root of the existing repository**:

- `app.py` — Streamlit entrypoint
- `requirements.txt` — Python dependencies including Streamlit
- `.streamlit/config.toml` — Streamlit runtime configuration

Keep the existing `src/`, `run_agent.py`, `README.md`, `DEMO.md`, and other project files.

## Streamlit Community Cloud settings

Repository:

`shivenchauhan1/razorpay-reconciliation-agent`

Branch:

`main`

Main file:

`app.py`

## Optional Gemini secret

In Streamlit Community Cloud, open:

`App settings → Secrets`

Add:

```toml
GEMINI_API_KEY = "your_key_here"
GEMINI_MODEL = "gemini-2.0-flash"
```

The app works without the key. In that case, deterministic fallback explanations are shown.

## Important

Do **not** upload `.env` or commit the real Gemini API key.

The synthetic data files do not need to be committed because `app.py` regenerates them each time the reconciliation button is pressed.
