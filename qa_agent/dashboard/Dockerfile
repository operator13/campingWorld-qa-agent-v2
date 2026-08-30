FROM python:3.11-slim
WORKDIR /app
COPY qa_agent/dashboard/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY qa_agent/dashboard/ ./qa_agent/dashboard/
EXPOSE 8080
CMD ["uvicorn", "qa_agent.dashboard.server:app", "--host", "0.0.0.0", "--port", "8080"]
