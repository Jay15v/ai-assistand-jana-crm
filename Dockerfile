# Ability CRM assistant (FastAPI), dev service on port 9995.
#
#   docker build -t crm-assistant .
#   docker run -d --name crm-assistant -p 9995:9995 --env-file .env crm-assistant
#
# Secrets (GEMINI_API_KEY, DATABASE_URL, LANGFUSE_*) are passed at run time, never baked in:
# .env is excluded by .dockerignore.

FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first, so code changes don't reinstall them.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Only what the app reads at run time: the code, the Chroma index + tab data, and the two manuals.
COPY app/ app/
COPY data/ data/
COPY Ability_CRM_User_Manual.md Ability_CRM_User_Manual_AR.md ./

# Run as a non-root user. Chroma writes to its sqlite file, so data/ must be writable by it.
RUN useradd --create-home --uid 1000 appuser && chown -R appuser:appuser /app/data
USER appuser

EXPOSE 9995

# One worker: without DATABASE_URL the chat memory is in-process, and the history writer is a
# per-process background thread.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9995"]
