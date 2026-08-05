FROM python:3.12-slim

WORKDIR /app

# Install system deps for datahub CLI
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ && \
    rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml requirements.txt ./
COPY src/ ./src/
COPY config/ ./config/
COPY tests/ ./tests/

# Install
RUN pip install --no-cache-dir -e ".[test]"

# Default env (overridden at runtime)
ENV DATAHUB_SERVER_URL=http://localhost:8080 \
    DATAHUB_FRONTEND_URL=http://localhost:9002 \
    TOOLS_IS_MUTATION_ENABLED=true

ENTRYPOINT ["python", "src/main.py"]
