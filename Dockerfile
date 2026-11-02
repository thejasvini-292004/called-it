# Called It: container image.
# Default build is small and uses the Hugging Face API for the model (set HF_TOKEN at run time).
# To run the open-source model inside the container instead:
#   docker build --build-arg LOCAL_MODEL=1 -t called-it .
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

COPY requirements.txt requirements-local.txt ./
ARG LOCAL_MODEL=0
RUN pip install --no-cache-dir -r requirements.txt && \
    if [ "$LOCAL_MODEL" = "1" ]; then \
      pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r requirements-local.txt; \
    fi

COPY . .

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT}"]
