FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml LICENSE ./
COPY demonicscans ./demonicscans
# Git checkouts made with umask 077 may contain 600 files and 700 directories.
# Normalize only application code inside the image, before building its wheel.
RUN chmod -R a+rX /app/demonicscans && pip install --no-cache-dir .

FROM base AS test
COPY tests ./tests
RUN pip install --no-cache-dir '.[test]' && python -m pytest -q && touch /tests-passed

FROM base AS runtime
COPY --from=test /tests-passed /tests-passed
USER 65534:65534
# Verify imports and health as the runtime user, not only as root in the test stage.
RUN python -c 'from demonicscans.app import create_app; r = create_app().test_client().get("/api/health"); assert r.status_code == 200'
EXPOSE 3003
HEALTHCHECK --interval=15s --timeout=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:3003/api/health', timeout=3)"
CMD ["gunicorn", "--bind", "0.0.0.0:3003", "--workers", "1", "--threads", "4", "--timeout", "120", "demonicscans.app:create_app()"]
