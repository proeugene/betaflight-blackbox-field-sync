FROM python:3.11-slim
WORKDIR /app
COPY . .
# Install only pyserial; skip RPi.GPIO (not available/needed on x86/Docker)
RUN pip install --no-cache-dir pyserial && \
    pip install --no-cache-dir --no-deps -e .
EXPOSE 8080
CMD ["python", "-c", \
     "from bbsyncer.web.server import run_server; run_server(storage_path='/data', port=8080)"]
