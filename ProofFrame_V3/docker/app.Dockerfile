FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 app
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir -e ".[dev]"
COPY tests ./tests
COPY scripts ./scripts
COPY profiles ./profiles
COPY demo ./demo
RUN mkdir -p /data /dropbox && chown app:app /data /dropbox
USER app
ENV PYTHONUNBUFFERED=1
