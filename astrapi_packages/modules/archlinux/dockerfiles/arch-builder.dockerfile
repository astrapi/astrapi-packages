FROM archlinux:latest

# Simpsons-Mirror: core/extra/multilib via $repo-Variable, SSL für interne CA deaktiviert
#
# DatabaseNever statt des Standard-DatabaseOptional: astrapi-mirror synct
# .db.sig bewusst nur best-effort (viele Upstream-Mirrors bieten sie gar
# nicht an, siehe astrapi-mirror/.../downloader.py::_check_completeness()) --
# core.db.sig/extra.db.sig fehlen auf mirror.simpsons.lan deshalb, und
# simpsons.db.sig gibt es nie (unser eigenes lokales Repo signiert nie).
# Jeder Build brach das (folgenlos, aber als 404 sichtbare) Sync-Rauschen vor
# dem eigentlichen Bauen. "Optional" heißt für pacman weiterhin "versuchen,
# Fehlen tolerieren" -- erst "Never" verzichtet ganz auf den Versuch.
# Paket-Signaturen (Required) für core/extra bleiben davon unberührt; das
# eigene [simpsons]-Repo bekommt komplett SigLevel=Never (wie bisher
# TrustAll schon faktisch keine Paketsignaturen verlangte).
RUN echo 'Server = https://mirror.simpsons.lan/files/archlinux/$repo/os/$arch' \
        > /etc/pacman.d/mirrorlist && \
    sed -i '/^\[options\]/a XferCommand = /usr/bin/curl -k -L -C - -f --no-progress-meter -o %o %u' /etc/pacman.conf && \
    sed -i 's/^SigLevel[[:space:]]*=.*/SigLevel = Required DatabaseNever/' /etc/pacman.conf && \
    printf '\n[simpsons]\nSigLevel = Never\nServer = https://mirror.simpsons.lan/files/archlinux/simpsons/os/$arch\n' \
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
