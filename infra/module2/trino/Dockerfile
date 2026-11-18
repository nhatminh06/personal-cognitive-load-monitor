FROM golang:1.27.3-alpine3.23@sha256:5d5113301ffcac84e2bfb20c42648803fecaea6789c89bb9b66884e18cbb30a7 AS launcher

ADD --checksum=sha256:53102119b3aaf09f74c8c1078ed41a0c22742f62dae0fef9d4c1f61231cb8c92 \
    https://github.com/airlift/launcher/archive/refs/tags/321.tar.gz /tmp/launcher.tar.gz
RUN tar -xzf /tmp/launcher.tar.gz -C /tmp \
    && cd /tmp/launcher-321/src/main/go \
    && go mod edit -go=1.27.3 \
    && go get golang.org/x/text@v0.41.0 \
    && CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build \
        -ldflags='-s -w -extldflags=-static -X launcher/args.Version=321' \
        -o /launcher .

FROM trinodb/trino:484@sha256:2704eb53935af5e582d63d6033e9bf99d20c325e9b0e30b1016ef59a4773979f AS trino

USER root
RUN rm -rf \
        /usr/lib/trino/plugin/iceberg \
        /usr/lib/trino/plugin/lakehouse \
        /usr/lib/trino/plugin/ranger \
        /usr/lib/trino/secrets-plugin/keystore-secrets-plugin

FROM registry.access.redhat.com/ubi10/ubi-minimal:10.1@sha256:5af8e51abe2a81b4247f05219284a627d37fb9ccf1055b90528a246fac11bc4d

ENV JAVA_HOME=/usr/lib/jvm/jdk-25.0.4+7 \
    PATH=/usr/lib/jvm/jdk-25.0.4+7/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    HOME=/tmp \
    LANG=C.UTF-8 \
    CATALOG_MANAGEMENT=static

RUN printf 'trino:x:1000:1000::/home/trino:/bin/bash\n' >> /etc/passwd \
    && printf 'trino:x:1000:\n' >> /etc/group \
    && mkdir -p /home/trino /data/trino \
    && chown -R 1000:1000 /home/trino /data/trino

COPY --from=trino --chown=1000:1000 /usr/lib/jvm /usr/lib/jvm
COPY --from=trino --chown=1000:1000 /usr/lib/trino /usr/lib/trino
COPY --from=trino --chown=1000:1000 /usr/bin/trino /usr/bin/trino
COPY --from=launcher --chown=1000:1000 /launcher /usr/lib/trino/bin/linux-amd64/launcher

USER 1000:1000
WORKDIR /tmp
EXPOSE 8080
CMD ["/usr/lib/trino/bin/launcher", "run", "--etc-dir", "/etc/trino"]
