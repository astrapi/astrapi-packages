#!/usr/bin/env python3
"""scripts/seed.py – Initialbefüllung der Datenbank.

Legt den arch-builder Docker-Eintrag und das yay-bin Testpaket an,
falls sie noch nicht existieren. Einstellungen werden nur gesetzt,
wenn der jeweilige Schlüssel noch nicht vorhanden ist.

Aufruf:  python3 scripts/seed.py
"""
import json
import sqlite3
from pathlib import Path

DB = Path(__file__).parent.parent / "app" / "data" / "app.db"

DOCKERFILE = """\
# ── Stage 1: Bootstrap herunterladen und entpacken ────────────────────────
FROM alpine AS bootstrap
RUN apk add --no-cache zstd
ADD https://geo.mirror.pkgbuild.com/iso/latest/archlinux-bootstrap-x86_64.tar.zst /tmp/
RUN mkdir /archroot && \\
    zstd -d /tmp/archlinux-bootstrap-x86_64.tar.zst --stdout | \\
    tar -x -C /archroot --strip-components=1

# ── Stage 2: Arch Linux from Scratch ──────────────────────────────────────
FROM scratch
COPY --from=bootstrap /archroot /

ARG LOCAL_MIRROR=https://geo.mirror.pkgbuild.com
RUN sed -i '/^\\[options\\]/a DisableSandbox' /etc/pacman.conf && \\
    echo "Server = ${LOCAL_MIRROR}/\\$repo/os/\\$arch" > /etc/pacman.d/mirrorlist && \\
    pacman-key --init && \\
    pacman-key --populate archlinux && \\
    pacman -Syu --noconfirm && \\
    rm -rf /var/cache/pacman/pkg/*

RUN pacman -S --needed --noconfirm base-devel git wget zsh && \\
    rm -rf /var/cache/pacman/pkg/*

RUN sed -i "s/^#MAKEFLAGS=.*/MAKEFLAGS=\\"-j$(nproc)\\"/" /etc/makepkg.conf
RUN wget -q -O /etc/zsh/zshrc https://git.grml.org/f/grml-etc-core/etc/zsh/zshrc

ARG user=makepkg
RUN useradd --system --create-home $user && \\
    echo "$user ALL=(ALL:ALL) NOPASSWD:ALL" > /etc/sudoers.d/$user

# run.sh als base64 einbetten (Legacy-Builder-kompatibel, kein BuildKit nötig)
# Dekodiert: #!/bin/bash – nimmt $1=Paketname, $2=Git-URL (optional für custom-Builds)
RUN echo 'IyEvYmluL2Jhc2gKCmlmIHRlc3QgLXogIiQxIjsgdGhlbgogICAgZWNobyAiRVJST1I6IHBscyBzcGVjaWZ5IGEgc29mdHdhcmUgdG8gYnVpbGQhIgogICAgZXhpdCAxCmZpCgojICQyIG9wdGlvbmFsOiB3ZW5uIGFuZ2VnZWJlbiAtPiBnaXQgY2xvbmUgKEFVUiksIHNvbnN0IHZvci1nZW1vdW50ZXRlIFNvdXJjZSBudXR6ZW4gKGN1c3RvbSkKaWYgdGVzdCAtbiAiJDIiOyB0aGVuCiAgICBnaXQgY2xvbmUgIiQyIiB+L3NvdXJjZQpmaQoKY2Qgfi9zb3VyY2UKCmVjaG8gIklORk86IGluc3RhbGxpbmcgYWxsIG1pc3NpbmcgZGVwZW5kZW5jaWVzLi4uIgptYWtlcGtnIC0tcHJpbnRzcmNpbmZvID4gU0lORk8KCnN1ZG8gcGFjbWFuIC1TeXVxIC0tbm9jb25maXJtCgp3aGlsZSByZWFkIC1yIC11IDkga2V5IHZhbHVlOyBkbwogICAgaWYgWyAiJGtleSIgPT0gImRlcGVuZHMiIF07IHRoZW4KICAgICAgICBkZXA9JChlY2hvICIkdmFsdWUiIHwgY3V0IC1kICcgJyAtZjIgfCBjdXQgLWQgJz4nIC1mMSkKICAgICAgICBlY2hvICJpbnN0YWxsaW5nICRkZXAuLi4iCiAgICAgICAgeWF5IC0tbm9jb25maXJtIC0tbm9lZGl0IC0tcmVtb3ZlbWFrZSAtUyAiJGRlcCIKICAgIGZpCmRvbmUgOTwgIlNJTkZPIgoKZWNobyAiZm91bmQgJChucHJvYykgY29yZXMiCm1ha2Vwa2cgLXMgLWMgLUMgLS1ub2NvbmZpcm0gLS1ub3Byb2dyZXNzYmFyIHwgdGVlIH4vJDEtYnVpbGQubG9nCnN1ZG8gY2hvd24gbWFrZXBrZyAvaG9tZS9tYWtlcGtnL3BrZwpta2RpciAtcCAvaG9tZS9tYWtlcGtnL3BrZwpjcCAuLyoucGtnLnRhci4qIC9ob21lL21ha2Vwa2cvcGtnCg==' \\
    | base64 -d > /usr/bin/run.sh && chmod +x /usr/bin/run.sh

USER makepkg
WORKDIR /home/makepkg

RUN git clone https://aur.archlinux.org/yay-bin.git && \\
    cd yay-bin && \\
    makepkg -sri --needed --noconfirm && \\
    cd && \\
    rm -rf .cache yay-bin

ENTRYPOINT ["run.sh"]
"""

ENTRIES = [
    ("docker", "arch-builder", {
        "tag": "latest",
        "enabled": True,
        "dockerfile_content": DOCKERFILE,
    }),
    ("pakete", "yay-bin", {
        "typ": "aur",
        "source_url": "https://aur.archlinux.org/yay-bin.git",
        "enabled": True,
    }),
]

SETTINGS = [
    ("_settings", "module.pakete.default_image", "ctl/arch-builder:latest"),
    ("_settings", "module.pakete.repo_path",     "/srv/pacman-repo"),
    ("_settings", "module.pakete.repo_name",     "local"),
]


def main():
    DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS kvstore "
        "(collection TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, "
        "PRIMARY KEY (collection, key))"
    )

    for collection, key, data in ENTRIES:
        cur.execute(
            "SELECT 1 FROM kvstore WHERE collection=? AND key=?", (collection, key)
        )
        if cur.fetchone():
            print(f"  skip  {collection}/{key} (bereits vorhanden)")
        else:
            cur.execute(
                "INSERT INTO kvstore (collection, key, value) VALUES (?, ?, ?)",
                (collection, key, json.dumps(data, ensure_ascii=False)),
            )
            print(f"  created {collection}/{key}")

    for collection, key, value in SETTINGS:
        cur.execute(
            "SELECT 1 FROM kvstore WHERE collection=? AND key=?", (collection, key)
        )
        if cur.fetchone():
            print(f"  skip  {collection}/{key} (bereits vorhanden)")
        else:
            cur.execute(
                "INSERT INTO kvstore (collection, key, value) VALUES (?, ?, ?)",
                (collection, key, json.dumps(value, ensure_ascii=False)),
            )
            print(f"  created {collection}/{key}")

    conn.commit()
    conn.close()
    print("Seed abgeschlossen.")


if __name__ == "__main__":
    main()
