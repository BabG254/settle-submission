FROM python:3.12-slim

WORKDIR /app
# The slim Python base does not bundle GNU make.
RUN apt-get update && apt-get install -y --no-install-recommends make \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY settle/ ./settle/
COPY skills/ ./skills/
COPY Makefile README.md REPRODUCE.md CHANGELOG.md WINDOWS.md .env.example run.ps1 ./

# Offline evaluation must complete before the image can be published.
RUN make offline

CMD ["make", "help"]
