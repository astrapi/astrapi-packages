FROM debian:stable-slim

# Wie debian-builder.dockerfile, nur mit den zusaetzlichen apt-Paketen, die
# paperless-ngx zum Bau seines vendorten venvs braucht: python3-venv (fuer
# "python3 -m venv"), python3-dev + libpq-dev + pkg-config (damit pip
# "psycopg-c" aus Quelltext kompilieren kann -- PyPI hat fuer die von
# paperless-ngx gepinnte Version 3.2.12 nur fuer cp312+x86_64/aarch64 ein
# eigenes, von paperless-ngx selbst gehostetes Wheel, sonst kein Wheel, siehe
# E-003). Kein exotisches Basis-Image wie bei debian-builder-rust.dockerfile
# noetig: Debian trixies eigenes python3 (3.13.5) erfuellt paperless-ngx'
# "requires-python = >=3.10" ohne Weiteres.
#
# Simpsons-Mirror konfigurieren, SSL für interne CA deaktivieren.
#
# debian.sources muss weg: das Basis-Image bringt seine Quellen im
# DEB822-Format unter sources.list.d/ mit. Bleibt die Datei liegen, zieht apt
# zusätzlich von deb.debian.org und der interne Mirror wird umgangen.
#
# Das simpsons-Repo ist ein FLACHES Repo (Release-Datei schreibt "Suite: ./"),
# wird also als "URL/ ./" adressiert – nicht als Suite plus Komponente. Sonst
# sucht apt unter dists/simpsons/ und bekommt 404.
RUN rm -f /etc/apt/sources.list.d/debian.sources && \
    printf 'deb https://mirror.simpsons.lan/files/debian/debian-trixie/ trixie main contrib non-free non-free-firmware\n\
deb https://mirror.simpsons.lan/files/debian/debian-trixie-security/ trixie-security main\n\
deb [trusted=yes] https://mirror.simpsons.lan/files/debian/simpsons/ ./\n' > /etc/apt/sources.list && \
    echo 'Acquire::https::Verify-Peer "false";' > /etc/apt/apt.conf.d/99simpsons-mirror

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        apt-utils \
        build-essential \
        devscripts \
        debhelper \
        git \
        curl \
        fakeroot \
        python3 \
        python3-venv \
        python3-dev \
        libpq-dev \
        pkg-config && \
    rm -rf /var/lib/apt/lists/*

RUN useradd -m builder && mkdir /build /repo && chown builder:builder /build /repo
USER builder
WORKDIR /build
