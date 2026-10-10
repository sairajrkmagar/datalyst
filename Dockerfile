# Datalyst web app. The AI (Ollama) runs OUTSIDE this container.
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# where Ollama is. On Docker Desktop (Mac, Windows) the host computer is:
ENV OLLAMA_URL=http://host.docker.internal:11434
EXPOSE 8501

HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", "--browser.gatherUsageStats=false"]
