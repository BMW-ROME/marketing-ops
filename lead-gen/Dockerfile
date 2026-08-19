FROM python:3.13-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x docker-entrypoint.sh

USER appuser

EXPOSE 8501

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["streamlit", "run", "lead_generator.py", "--server.port=8501", "--server.address=0.0.0.0"]