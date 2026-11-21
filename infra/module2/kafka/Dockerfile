FROM alpine:3.24@sha256:be2656061b536c1883c4034790e21d0a09c5aaaf51968b89368a3c0371ea2c9a AS dependencies

ADD --checksum=sha256:58c8e0b813960d2a248e050c353baea73139b48a2ffc55382d42c69707e17325 \
    https://repo.maven.apache.org/maven2/at/yawk/lz4/lz4-java/1.11.4/lz4-java-1.11.4.jar /lz4-java.jar
ADD --checksum=sha256:35228628442e4b9797681c7cbd3b26594f6da3379159dbd0cb07094ed3aece0d \
    https://repo.maven.apache.org/maven2/org/xerial/snappy/snappy-java/1.1.10.9/snappy-java-1.1.10.9.jar /snappy-java.jar

FROM apache/kafka:4.4.0@sha256:833b867a9585a141da455dc2b57431c65cbccb27f11c91f694444cca9f777e0f

USER root
RUN apk add --no-cache \
        alpine-release=3.24.4-r0 \
        apk-tools=3.0.9-r0 \
        brotli-libs=1.2.1-r0 \
        libfontenc=1.1.10-r0 \
        ca-certificates=20261020-r0 \
        ca-certificates-bundle=20261020-r0 \
        libapk=3.0.9-r0 \
        libexpat=2.10.0-r0 \
        musl=1.2.6-r3 \
        musl-utils=1.2.6-r3 \
        tzdata=2026f-r0 \
        zlib=1.4-r0 \
    && rm /opt/kafka/libs/lz4-java-1.11.2.jar /opt/kafka/libs/snappy-java-1.1.10.7.jar
COPY --from=dependencies --chown=appuser:appuser /lz4-java.jar /opt/kafka/libs/lz4-java-1.11.4.jar
COPY --from=dependencies --chown=appuser:appuser /snappy-java.jar /opt/kafka/libs/snappy-java-1.1.10.9.jar
USER appuser
