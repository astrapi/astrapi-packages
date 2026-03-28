FROM debian:stable-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        devscripts \
        debhelper \
        git \
        fakeroot && \
    rm -rf /var/lib/apt/lists/*

RUN useradd -m builder
USER builder
WORKDIR /build
