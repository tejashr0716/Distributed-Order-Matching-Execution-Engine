FROM python:3.11-slim as builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    clang \
    cmake \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY cpp /app/cpp
WORKDIR /app/cpp
RUN make clean && make

FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libstdc++6 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY --from=builder /app/cpp/liborder_matching.so /app/cpp/liborder_matching.dylib /app/cpp/
COPY backend /app/backend
COPY schema.sql /app/
COPY pytest.ini /app/

ENV PYTHONPATH=/app
ENV CPP_LIB_PATH=/app/cpp/liborder_matching.dylib

EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
