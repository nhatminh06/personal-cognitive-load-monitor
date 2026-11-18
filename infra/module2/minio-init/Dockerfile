FROM python:3.11.18-alpine3.24@sha256:7fbad8e4652eae0186429a6f26cf5b23e27e8c6fd7ac4d0cfd7a6988cdeea1e1
RUN apk upgrade --no-cache \
    && pip install --no-cache-dir boto3==1.43.0 \
    && python -m pip uninstall -y pip setuptools
COPY init.py /init.py
RUN adduser -D -u 10001 minio-init
USER minio-init
ENTRYPOINT ["python", "/init.py"]
