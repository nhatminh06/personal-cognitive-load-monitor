FROM apache/airflow:slim-3.3.2-python3.11

USER root
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get purge -y docker-ce-cli \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

USER airflow
RUN pip install --no-cache-dir --upgrade \
        certifi==2026.10.19 \
        jaraco.context==6.1.0 \
        msgpack==1.2.1 \
        urllib3==2.8.0 \
    && pip uninstall -y setuptools wheel uv \
    && rm -rf /home/airflow/.local/share/uv \
    && pip check \
    && python -m pip uninstall -y pip

USER root
RUN rm -rf /usr/python/lib/python3.11/site-packages/setuptools

USER airflow
