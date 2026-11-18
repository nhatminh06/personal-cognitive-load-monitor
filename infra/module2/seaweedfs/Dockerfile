FROM golang:1.26.10-alpine AS build

RUN apk add --no-cache git
RUN git clone --branch 4.50 --depth 1 https://github.com/seaweedfs/seaweedfs.git /src \
    && test "$(git -C /src rev-parse HEAD)" = "ec8f9793502c59ce3381cc4151bfc0806afd92e8" \
    && cd /src \
    && go get github.com/go-jose/go-jose/v4@v4.1.6 golang.org/x/net@v0.62.0 \
    && GOMAXPROCS=2 GOFLAGS=-p=2 CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/weed ./weed

FROM alpine:3.24
RUN apk upgrade --no-cache \
    && apk add --no-cache ca-certificates \
    && adduser -D -u 10001 seaweedfs \
    && mkdir /data \
    && chown seaweedfs:seaweedfs /data
COPY --from=build /out/weed /usr/local/bin/weed
USER seaweedfs
EXPOSE 9000
ENTRYPOINT ["weed"]
