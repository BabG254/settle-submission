FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY settle/ ./settle/
COPY skills/ ./skills/
COPY Makefile README.md REPRODUCE.md CHANGELOG.md WINDOWS.md .env.example run.ps1 ./

# The offline half of the evaluation runs at build time, so a broken image
# fails here rather than in front of a judge.
RUN make offline

CMD ["make", "help"]
