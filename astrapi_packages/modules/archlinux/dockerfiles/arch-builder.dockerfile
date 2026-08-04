FROM archlinux:latest

# Simpsons-Mirror: core/extra/multilib via $repo-Variable, SSL für interne CA deaktiviert
RUN echo 'Server = https://mirror.simpsons.lan/files/archlinux/$repo/os/$arch' \
        > /etc/pacman.d/mirrorlist && \
    sed -i '/^\[options\]/a XferCommand = /usr/bin/curl -k -L -C - -f -o %o %u' /etc/pacman.conf && \
    printf '\n[simpsons]\nSigLevel = Optional TrustAll\nServer = https://mirror.simpsons.lan/files/archlinux/simpsons/os/$arch\n' \
        >> /etc/pacman.conf

RUN pacman -Syu --noconfirm && \
    pacman -S --noconfirm base-devel git sudo namcap && \
    pacman -Scc --noconfirm

RUN sed -i "s/#MAKEFLAGS=\"-j2\"/MAKEFLAGS=\"-j\$(nproc)\"/" /etc/makepkg.conf && \
    sed -i '/^OPTIONS=/s/\bdebug\b/!debug/' /etc/makepkg.conf

RUN useradd -m -G wheel makepkg && \
    echo "makepkg ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers

COPY arch-build.sh /usr/local/bin/build.sh
RUN chmod +x /usr/local/bin/build.sh

USER makepkg
WORKDIR /home/makepkg

# yay-bin installieren (binäres Release, kein Go-Compiler nötig)
RUN cd /tmp && \
    git clone https://aur.archlinux.org/yay-bin.git && \
    cd yay-bin && \
    makepkg -si --noconfirm && \
    rm -rf /tmp/yay-bin

ENTRYPOINT ["/usr/local/bin/build.sh"]
