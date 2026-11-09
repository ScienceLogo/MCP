FROM python:3.15-slim AS runtime

ARG VERSION=0.2.0
ARG RACKET_VERSION=9.3
ARG RACKET_SHA256=8f469b7e93645fc876594470d884775aafff7688f530fd38be873fb44c71ca6a
ARG SCIENCELOGO_RELEASE=v0.2
ARG SCIENCELOGO_CHECKSUM=6376e1556db72cac720792545b2302a5a6f5a8c2

LABEL org.opencontainers.image.title="ScienceLogo MCP Server"
LABEL org.opencontainers.image.description="Model Context Protocol server for writing and validating ScienceLogo workflows."
LABEL org.opencontainers.image.source="https://github.com/ScienceLogo/MCP"
LABEL org.opencontainers.image.version="${VERSION}"
LABEL io.modelcontextprotocol.server.name="io.github.ScienceLogo/sciencelogo-mcp"

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Racket and the ScienceLogo language release, each checked against its pinned checksum.
RUN python -c "import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], '/tmp/racket.tgz')" \
      "https://mirror.racket-lang.org/installers/${RACKET_VERSION}/racket-minimal-${RACKET_VERSION}-x86_64-linux-buster-cs.tgz" \
 && echo "${RACKET_SHA256}  /tmp/racket.tgz" | sha256sum -c - \
 && tar -xzf /tmp/racket.tgz -C /opt \
 && rm /tmp/racket.tgz \
 && /opt/racket/bin/raco pkg install --auto --batch --no-docs --scope installation \
      --checksum "${SCIENCELOGO_CHECKSUM}" \
      "https://github.com/ScienceLogo/Language/releases/download/${SCIENCELOGO_RELEASE}/sciencelogo.zip"
ENV PATH="/opt/racket/bin:${PATH}"

WORKDIR /app

COPY pyproject.toml README.md LICENSE /app/
COPY src /app/src

RUN python -m pip install --no-cache-dir .

ENTRYPOINT ["sciencelogo-mcp"]

# The tests run inside the image, against its Racket and language release.
FROM runtime AS test

RUN python -m pip install --no-cache-dir pytest
COPY tests /app/tests
RUN python -m pytest /app/tests
