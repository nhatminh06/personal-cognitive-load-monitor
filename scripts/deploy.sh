#!/usr/bin/env bash
set -euo pipefail

NAMESPACE=${NAMESPACE:-cognitive-load}
RELEASE=${RELEASE:-cognitive-load-monitor}
IMAGE_REPOSITORY=${IMAGE_REPOSITORY:-ghcr.io/OWNER/REPO/cognitive-load-api}
IMAGE_TAG=${IMAGE_TAG:-latest}
KSERVE_STORAGE_URI=${KSERVE_STORAGE_URI:-gs://CHANGE_ME_BUCKET/models/cognitive-load-classifier}
HOST=${HOST:-cognitive-load.example.com}

helm upgrade --install "$RELEASE" ./helm/cognitive-load-monitor \
  --namespace "$NAMESPACE" \
  --create-namespace \
  --set image.repository="$IMAGE_REPOSITORY" \
  --set image.tag="$IMAGE_TAG" \
  --set ingress.hosts[0].host="$HOST" \
  --set kserve.storageUri="$KSERVE_STORAGE_URI"
