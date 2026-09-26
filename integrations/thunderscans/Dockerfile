FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml LICENSE ./
COPY thunderscans ./thunderscans
RUN pip install --no-cache-dir .

FROM base AS test
COPY tests ./tests
RUN pip install --no-cache-dir '.[test]' && python -m pytest -q && touch /tests-passed

FROM base AS runtime
COPY --from=test /tests-passed /tests-passed
USER 65534:65534
EXPOSE 3004
HEALTHCHECK --interval=15s --timeout=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:3004/api/health', timeout=3)"
CMD ["gunicorn", "--bind", "0.0.0.0:3004", "--workers", "1", "--threads", "4", "--timeout", "120", "thunderscans.app:create_app()"]
