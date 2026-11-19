FROM gcr.io/tfx-oss-public/ml_metadata_store_server@sha256:51404ef4419c1426da80f3e14a83dcb55f65bb5a971371d36d14cec1e50af830 AS upstream

FROM ubuntu@sha256:73b999393d07f2bf65a40373778a44dc9a6d54ad7718d29247d8ff9413c4d6a8

RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends ca-certificates libstdc++6 tzdata \
    && groupadd --gid 10001 mlmd \
    && useradd --no-create-home --uid 10001 --gid 10001 --shell /usr/sbin/nologin mlmd \
    && rm -rf /var/lib/apt/lists/*

COPY --from=upstream --chown=10001:10001 /bin/metadata_store_server /bin/metadata_store_server

USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["/bin/metadata_store_server"]
