# syntax=docker/dockerfile:1
#
# FaceOff with ANTs inside: run it on a folder of scans without installing anything else.
#
#   docker run --rm --init --user "$(id -u):$(id -g)" -v "$PWD":/data ghcr.io/srikash/faceoff -i scan.nii.gz
#
# The image is amd64 only, because the ANTs image it takes ANTs from is.

# Keep in step with ANTS_IMAGE in faceoff/ants.py (a test checks this).
ARG ANTS_IMAGE=antsx/ants:2.6.5

FROM ghcr.io/astral-sh/uv:0.13.7 AS uv

# Take only what FaceOff runs from the ANTs image: the four tools and the libraries they load
# (about 130 MB of the 340 MB in /opt/ants).
FROM ${ANTS_IMAGE} AS ants
RUN set -eu; \
    mkdir -p /ants/bin /ants/lib; \
    for tool in antsAI antsRegistration antsApplyTransforms ConvertTransformFile; do \
        cp "/opt/ants/bin/${tool}" /ants/bin/; \
        ldd "/opt/ants/bin/${tool}" | awk '/=> \/opt\/ants/ {print $3}' >> /tmp/libs.txt; \
    done; \
    test -s /tmp/libs.txt; \
    sort -u /tmp/libs.txt | xargs -I{} cp -L {} /ants/lib/; \
    test "$(ls /ants/lib | wc -l)" -gt 20

FROM python:3.13-slim-bookworm AS builder
COPY --from=uv /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /src
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
# A normal (not editable) install builds the wheel, which downloads the five template files
# from Zenodo and bundles them, so the image needs no download when it runs.
COPY README.md LICENCE bundle_template.py ./
COPY faceoff ./faceoff
RUN uv sync --locked --no-dev --no-editable

# Same Debian release as the ANTs image, so its libraries match.
FROM python:3.13-slim-bookworm
LABEL org.opencontainers.image.title="FaceOff" \
      org.opencontainers.image.description="Deface MRI scans with ANTs and a modified MNI152 template" \
      org.opencontainers.image.source="https://github.com/srikash/FaceOff" \
      org.opencontainers.image.licenses="MIT AND Apache-2.0"
COPY --from=ants /ants /opt/ants
COPY licences /usr/share/doc/faceoff/licences
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /src/faceoff/COPYING-MNI /usr/share/doc/faceoff/licences/MNI-COPYING.txt
# The copied libraries are all ITK's and ANTs' own (libitk*-5.4), none named like a system
# library, so putting their folder on the library path cannot shadow Python's.
ENV PATH="/opt/venv/bin:/opt/ants/bin:${PATH}" \
    LD_LIBRARY_PATH=/opt/ants/lib
WORKDIR /data
ENTRYPOINT ["faceoff"]
