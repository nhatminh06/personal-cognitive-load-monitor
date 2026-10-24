FROM apache/spark:3.5.5-python3
USER root
RUN pip install --no-cache-dir boto3==1.37.38 importlib-metadata==8.5.0 \
    && pip install --no-cache-dir --no-deps delta-spark==3.3.2
USER spark
