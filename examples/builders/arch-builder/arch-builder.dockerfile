FROM archlinux:latest

# Simpsons-Mirror: core/extra/multilib via $repo-Variable, SSL für interne CA deaktiviert
RUN echo 'Server = https://mirror.simpsons.lan/files/archlinux/$repo/os/$arch' \
        > /etc/pacman.d/mirrorlist && \
    sed -i '/^\[options\]/a XferCommand = /usr/bin/curl -k -L -C - -f --no-progress-meter -o %o %u' /etc/pacman.conf && \
    printf '\n[simpsons]\nSigLevel = Optional TrustAll\nServer = https://mirror.simpsons.lan/files/archlinux/simpsons/os/$arch\n' \
        >> /etc/pacman.conf

RUN pacman -Syu --noconfirm && \
    pacman -S --noconfirm base-devel git sudo namcap && \
    pacman -Scc --noconfirm

RUN sed -i "s/#MAKEFLAGS=\"-j2\"/MAKEFLAGS=\"-j\$(nproc)\"/" /etc/makepkg.conf && \
    sed -i '/^OPTIONS=/s/\bdebug\b/!debug/' /etc/makepkg.conf

RUN useradd -m -G wheel makepkg && \
    echo "makepkg ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers

# Kein COPY/ENTRYPOINT mehr fuer build.sh: seit dem generischen Build-Runner
# (astrapi_packages/utils/build_runner.py, siehe
# projects/packages/planung-datei-editor.md, "Virtuelles OS-Modul") wird
# build.sh/publish.sh als Datei des Builder-Image-Eintrags zur Laufzeit
# gemountet und explizit aufgerufen (`bash /build/scripts/build.sh`), nicht
# mehr ins Image gebacken -- siehe examples/os-types/archlinux/build.sh.

USER makepkg
WORKDIR /home/makepkg

# yay-bin installieren (binäres Release, kein Go-Compiler nötig)
RUN cd /tmp && \
    git clone https://aur.archlinux.org/yay-bin.git && \
    cd yay-bin && \
    makepkg -si --noconfirm && \
    rm -rf /tmp/yay-bin
