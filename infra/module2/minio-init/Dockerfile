FROM python:3.11-slim
RUN pip install --no-cache-dir boto3==1.43.0
COPY init.py /init.py
ENTRYPOINT ["python", "/init.py"]
