# The public demo. The web app uses only Python's standard library, so there's nothing to install.
FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MOCK_QUIET=1 CONNECT_ENV_FILE=/dev/null CONNECT_VAR_DIR=/tmp/connect
WORKDIR /app
COPY connect ./connect
COPY demo_web ./demo_web
COPY run.py ./run.py
COPY fonecta_data/FONECTA_CONNECT_SUGGESTS_2026 ./fonecta_data/FONECTA_CONNECT_SUGGESTS_2026
RUN useradd --create-home connect
USER connect
CMD ["python3", "demo_web/server.py"]
