# ============================================================
#  HostingBot Sandbox Image
#  Isolated runtime environment for user scripts & shells
# ============================================================

FROM ubuntu:22.04

LABEL maintainer="Blac (@blcqt)"
LABEL description="Secure sandbox container for HostingBot users"

# Prevent interactive prompts during build
ENV DEBIAN_FRONTEND=noninteractive

# Install global tools & runtimes available to all users
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        wget \
        git \
        nano \
        vim \
        python3 \
        python3-pip \
        python3-venv \
        nodejs \
        npm \
        build-essential \
        g++ \
        gcc \
        default-jdk \
        php \
        ruby \
        lua5.3 \
        perl \
        r-base \
        unzip \
        zip \
    && rm -rf /var/lib/apt/lists/*

# Pre‑install commonly used Python packages
RUN pip3 install --no-cache-dir \
    requests \
    flask \
    numpy \
    pandas \
    matplotlib \
    beautifulsoup4 \
    Pillow \
    python-dotenv \
    cryptography \
    pyyaml

# Pre‑install commonly used Node.js packages
RUN npm install -g --silent \
    express \
    axios \
    lodash \
    moment \
    dotenv

# Create non‑root sandbox user
RUN useradd --create-home --shell /bin/bash sandbox \
    && echo 'sandbox ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/sandbox

# Set working directory
WORKDIR /home/sandbox

# Switch to sandbox user
USER sandbox

# Default command
CMD ["/bin/bash"]