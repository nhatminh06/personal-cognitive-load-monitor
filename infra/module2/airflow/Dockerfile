FROM python:3.11.18-alpine3.24@sha256:7fbad8e4652eae0186429a6f26cf5b23e27e8c6fd7ac4d0cfd7a6988cdeea1e1 AS builder

ADD --checksum=sha256:9dcbdb5f9b36433b961a03aeb718cf5045005edbe558eeb5ff4a70d99eb50c71 \
    https://raw.githubusercontent.com/apache/airflow/constraints-3.4.0/constraints-no-providers-3.11.txt \
    /constraints.txt
RUN sed -i 's/^dnspython==2.9.1$/dnspython==2.9.2/' /constraints.txt \
    && python -m venv /opt/airflow \
    && /opt/airflow/bin/pip install --no-cache-dir \
        --constraint /constraints.txt \
        apache-airflow==3.4.0 \
        dnspython==2.9.2 \
    && /opt/airflow/bin/pip check \
    && /opt/airflow/bin/python -m pip uninstall -y pip setuptools wheel uv

FROM python:3.11.18-alpine3.24@sha256:7fbad8e4652eae0186429a6f26cf5b23e27e8c6fd7ac4d0cfd7a6988cdeea1e1

RUN apk add --no-cache \
        krb5-libs=1.22.3-r0 \
        zlib=1.4-r0 \
    && rm -rf \
        /usr/local/lib/python3.11/site-packages/pip* \
        /usr/local/lib/python3.11/site-packages/setuptools* \
        /usr/local/lib/python3.11/site-packages/wheel* \
        /usr/local/bin/pip* \
        /usr/local/bin/wheel \
    && addgroup -g 50000 airflow \
    && adduser -D -u 50000 -G airflow -h /opt/airflow-home airflow

COPY --from=builder --chown=50000:50000 /opt/airflow /opt/airflow

ENV AIRFLOW_HOME=/opt/airflow-home \
    PATH=/opt/airflow/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin

USER 50000:50000
WORKDIR /opt/airflow-home
ENTRYPOINT ["airflow"]
