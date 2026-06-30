FROM python:3.11-slim

# Install dependencies including Docker CLI
RUN apt-get update && apt-get install -y \
    curl wget git docker.io \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages
RUN pip install --upgrade pip && \
    pip install --no-cache-dir \
    pyTelegramBotAPI \
    python-dotenv==1.0.0 \
    psutil==5.9.8 \
    requests==2.31.0 \
    flask==3.0.0 \
    pyrogram \
    tgcrypto \
    phonenumbers

WORKDIR /app
ENV PYTHONUNBUFFERED=1

COPY . .

CMD ["python", "src/main.py"]
