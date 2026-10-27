# Includes the GCP command runtime used by deterministic containment actions.
FROM ghcr.io/astral-sh/uv:0.9.5 AS uv
FROM registry.gitlab.com/gitlab-org/cli:latest AS glab
FROM gcr.io/google.com/cloudsdktool/google-cloud-cli:stable
COPY --from=uv /uv /usr/local/bin/uv
COPY --from=glab /usr/bin/glab /usr/local/bin/glab
ENV UV_PYTHON_INSTALL_DIR=/opt/python UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY defuse ./defuse
RUN uv sync --frozen --no-dev --python 3.12 --no-editable \
    && useradd --create-home defuse && mkdir /data && chown defuse:defuse /data
ENV PATH="/app/.venv/bin:$PATH" DEFUSE_DATABASE_URL=sqlite+aiosqlite:////data/defuse.db DEFUSE_RECORDS_DIR=/data/records
USER defuse
EXPOSE 8000
CMD ["defuse", "serve", "--host", "0.0.0.0", "--port", "8000"]
