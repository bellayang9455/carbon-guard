FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home appuser
COPY --chown=appuser:appuser . .
RUN mkdir -p /app/data && chown appuser:appuser /app/data
USER appuser
ENV CARBON_DATA_DIR=/app/data CARBON_HOST=0.0.0.0
EXPOSE 8000
CMD ["python", "run.py"]
