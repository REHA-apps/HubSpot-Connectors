FROM python:3.12-slim

WORKDIR /app

# Install uv for fast dependency management
RUN pip install uv

# Copy only dependency files first for caching
COPY pyproject.toml .
# Note: uv.lock is ignored in git, so we rely on pyproject.toml
RUN uv pip install . --system

# Copy application code
COPY app ./app

ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
