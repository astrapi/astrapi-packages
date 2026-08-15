FROM debian:stable-slim

# Wie debian-builder.dockerfile, nur mit den zusaetzlichen apt-Paketen, die
# BookStack zum Bau braucht: php8.4-cli (composer/artisan brauchen einen
# echten PHP-Interpreter), composer selbst, sowie die von BookStacks
# composer.json verlangten ext-*-Erweiterungen (curl, dom, gd, mbstring,
# zip -- dom kommt ueber php8.4-xml, siehe Provides-Feld) und php8.4-mysql
# fuer den pdo_mysql-Treiber (MariaDB). fileinfo/json/tokenizer/pdo/
# openssl/iconv sind in Debians PHP-Paketierung fest in php8.4-common/-cli
# einkompiliert, brauchen kein eigenes Paket. Kein exotisches Basis-Image
# noetig wie bei debian-builder-rust.dockerfile: Debian trixies php 8.4
# erfuellt BookStacks "php": "^8.2.0" ohne Weiteres, siehe E-004.
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
        php8.4-cli \
        php8.4-curl \
        php8.4-xml \
        php8.4-mbstring \
        php8.4-gd \
        php8.4-zip \
        php8.4-mysql \
        composer && \
    rm -rf /var/lib/apt/lists/*

RUN useradd -m builder && mkdir /build /repo && chown builder:builder /build /repo
USER builder
WORKDIR /build
