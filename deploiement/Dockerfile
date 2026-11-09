# Image de la page web « Assistant Sûreté ».
# Construction (depuis la racine du projet) : docker compose -f deploiement/docker-compose.yml build
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY deploiement/requirements-serveur.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

COPY safety_agent/ safety_agent/
COPY examples/ examples/
COPY .streamlit/config.toml .streamlit/config.toml

# Utilisateur sans droits d'administration ; /data reçoit le journal et le journal d'audit.
RUN useradd --create-home --uid 1000 assistant && mkdir -p /data && chown assistant /data
USER assistant

ENV SAFETY_AGENT_SERVEUR=1 \
    SAFETY_AGENT_JOURNAL=/data/journal_validations.csv \
    SAFETY_AGENT_AUDIT_LOG=/data/safety_agent_audit.jsonl

EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health', timeout=4)"

CMD ["python", "-m", "safety_agent", "web", "--partage", "--port", "8501"]
