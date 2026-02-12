FROM python:3.10-slim

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8080

# Cloud Run richiede che l'app ascolti sulla porta 8080
ENTRYPOINT ["streamlit", "run", "app_local.py", "--server.port=8080", "--server.address=0.0.0.0"]