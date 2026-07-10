FROM debian:stable-slim

# Simpsons-Mirror konfigurieren, SSL für interne CA deaktivieren
RUN printf 'deb https://mirror.simpsons.lan/files/debian/debian-trixie/ trixie main contrib non-free non-free-firmware\n\
deb https://mirror.simpsons.lan/files/debian/debian-trixie-security/ trixie-security main\n\
deb https://mirror.simpsons.lan/files/debian/simpsons/ simpsons main\n' > /etc/apt/sources.list && \
    echo 'Acquire::https::Verify-Peer "false";' > /etc/apt/apt.conf.d/99simpsons-mirror

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        apt-utils \
        build-essential \
        devscripts \
        debhelper \
        git \
        curl \
        fakeroot && \
    rm -rf /var/lib/apt/lists/*

RUN useradd -m builder && mkdir /build /repo && chown builder:builder /build /repo
USER builder
WORKDIR /build
