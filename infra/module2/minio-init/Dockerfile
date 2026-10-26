FROM python:3.11-slim
RUN pip install --no-cache-dir boto3==1.43.0 \
    && python -m pip uninstall -y pip setuptools
COPY init.py /init.py
RUN useradd --create-home --uid 10001 minio-init
USER minio-init
ENTRYPOINT ["python", "/init.py"]
