FROM golang:1.24-alpine AS build

RUN apk add --no-cache git
RUN GOBIN=/out go install github.com/minio/minio@RELEASE.2025-04-22T22-12-26Z

FROM alpine:3.21
RUN apk add --no-cache ca-certificates
COPY --from=build /out/minio /usr/local/bin/minio
EXPOSE 9000 9001
ENTRYPOINT ["minio"]
