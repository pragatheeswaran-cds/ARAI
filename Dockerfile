# ARAI API and worker (final-spec component 15). The image holds code, the specification and the lock file.
# Data is mounted at run time: the artifact root only. The private truth root is never mounted into serving.
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 ARTIFACT_ROOT=/data/artifacts ARAI_SPEC_ROOT=/app/final-spec
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY final-spec ./final-spec
COPY src ./src
RUN uv sync --frozen --no-dev
RUN useradd --create-home arai && mkdir -p /data/artifacts && chown -R arai /data
USER arai
EXPOSE 8000
CMD ["uv", "run", "--no-sync", "arai", "serve", "--host", "0.0.0.0", "--port", "8000"]
