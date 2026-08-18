"""astrapi_packages.api.status – Vokabular fuer `last_status`.

Die Zustaende lagen bisher als Zeichenketten verstreut in beiden Modulen. Wer
einen Vergleich anfasst, sieht dort nicht, welche anderen Werte es gibt und was
sie bedeuten -- genau daraus sind T-063, T-132 und T-134 entstanden.

Zustaende
---------
NEU       Eintrag angelegt, noch nie gebaut.
BUILDING  Bau laeuft.
PENDING   Fuer einen Bau eingeplant (Abhaengigkeits-Warteschlange, archlinux
          und debian).
OK        Bau erfolgreich abgeschlossen.
ERROR     Bau ausgefuehrt und fehlgeschlagen -- oder ein Lauf, der beim
          App-Neustart mitten in BUILDING/PENDING unterbrochen wurde
          (T-148-PACKAGES: der eigene ABORTED-Zustand aus T-132 wurde wieder
          entfernt, der seltene Fall ist manuelles Eingreifen wert).
"""

from __future__ import annotations

NEU = "neu"
BUILDING = "building"
PENDING = "pending"
OK = "ok"
ERROR = "error"

#: Ein Vorgang laeuft gerade. Beim Start kann das nicht zutreffen.
LAEUFT = (BUILDING, PENDING)

#: Noch nie gebaut. "" ist der historische Wert aus astrapi-packages (T-134);
#: bestehende Zeilen werden beim Start normalisiert, der Vergleich bleibt
#: trotzdem tolerant.
NIE_GEBAUT = (NEU, "")

#: Zustaende, die an der automatischen Aktualisierung teilnehmen.
#:
#: OK      -- gebaut, Version bekannt, Vergleich moeglich.
#:
#: Bewusst *nicht* enthalten:
#: NEU     -- G-017: der erste Bau wird von Hand angestossen und beobachtet.
#: ERROR   -- der Bau ist nachweislich fehlgeschlagen; ihn ungefragt zu
#:            wiederholen ist Endlos-Wiederholung ohne neue Erkenntnis. Das
#:            gilt seit T-148-PACKAGES bewusst auch fuer einen durch
#:            App-Neustart unterbrochenen Lauf (vorher eigener ABORTED-
#:            Zustand, T-132) -- der seltene Fall bleibt manuelles Eingreifen,
#:            statt dafuer ein eigenes Vokabular zu pflegen.
AUTO_UPDATE = (OK,)


def ist_nie_gebaut(status: str | None) -> bool:
    return (status or "") in NIE_GEBAUT
