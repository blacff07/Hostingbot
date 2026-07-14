FROM python:3.11-slim-bookworm

WORKDIR /app
ENV PYTHONUNBUFFERED=1

# Install system packages with retry strategies
RUN apt-get update -oAcquire::AllowInsecureRepositories=true -oAcquire::AllowDowngradeToInsecureRepositories=true || \
    (sed -i 's/deb.debian.org/archive.debian.org/g' /etc/apt/sources.list && apt-get update) || true

# Install ONLY essential tools (git, curl, wget, build tools)
RUN apt-get install -y --no-install-recommends \
    git curl wget build-essential ca-certificates 2>/dev/null || true

# Install ONLY core Python packages - others installed on demand
RUN pip install --upgrade pip && pip install --no-cache-dir \
    pyTelegramBotAPI \
    python-dotenv \
    psutil \
    requests \
    flask

# Clean everything
RUN pip cache purge && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* /var/cache/apt/* 2>/dev/null || true

COPY . .
CMD ["python", "src/main.py"]
