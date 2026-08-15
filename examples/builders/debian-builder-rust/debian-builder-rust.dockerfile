FROM rust:1.95.0-slim-trixie

# Wie debian-builder.dockerfile, nur mit vorinstalliertem Rust (rustc/cargo
# 1.95.0) fuer Pakete, deren MSRV ueber dem liegt, was trixie selbst
# mitbringt (z.B. vaultwarden: rust-version >= 1.93.0). Separates Image
# statt debian-builder.dockerfile selbst umzustellen, damit alle anderen
# Debian-Pakete beim schlanken Standard-Image bleiben.
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

# pkg-config/libssl-dev/libsqlite3-dev sind vaultwardens deklarierte
# makedepends -- jobs.py::_build_cmd() wertet makedepends aber nie aus,
# darum hier fest im Image statt ueber die PKGBUILD.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        apt-utils \
        build-essential \
        devscripts \
        debhelper \
        git \
        curl \
        fakeroot \
        pkg-config \
        libssl-dev \
        libsqlite3-dev && \
    rm -rf /var/lib/apt/lists/*

RUN useradd -m builder && mkdir /build /repo && chown builder:builder /build /repo
USER builder
WORKDIR /build
