"""astrapi_packages.api.status – Vokabular fuer `last_status`.

Die Zustaende lagen bisher als Zeichenketten verstreut in beiden Modulen. Wer
einen Vergleich anfasst, sieht dort nicht, welche anderen Werte es gibt und was
sie bedeuten -- genau daraus sind T-063, T-132 und T-134 entstanden.

Zustaende
---------
NEU       Eintrag angelegt, noch nie gebaut.
BUILDING  Bau laeuft.
PENDING   Fuer einen Bau eingeplant (nur archlinux, als Abhaengigkeit).
OK        Bau erfolgreich abgeschlossen.
ERROR     Bau ausgefuehrt und fehlgeschlagen.
ABORTED   Bau kam nicht zu Ende -- Neustart, Absturz, Update. **Kein**
          Fehlschlag: ueber das Paket ist damit nichts Schlechtes bekannt.
"""

from __future__ import annotations

NEU = "neu"
BUILDING = "building"
PENDING = "pending"
OK = "ok"
ERROR = "error"
ABORTED = "aborted"

#: Ein Vorgang laeuft gerade. Beim Start kann das nicht zutreffen.
LAEUFT = (BUILDING, PENDING)

#: Noch nie gebaut. "" ist der historische Wert aus astrapi-packages (T-134);
#: bestehende Zeilen werden beim Start normalisiert, der Vergleich bleibt
#: trotzdem tolerant.
NIE_GEBAUT = (NEU, "")

#: Zustaende, die an der automatischen Aktualisierung teilnehmen.
#:
#: OK      -- gebaut, Version bekannt, Vergleich moeglich.
#: ABORTED -- der letzte Lauf kam nicht zu Ende, das Paket war davor aber in
#:            Ordnung. Es hier auszuschliessen wuerde bedeuten, dass ein
#:            Neustart zur falschen Zeit ein Paket dauerhaft aus der Automatik
#:            wirft (T-132).
#:
#: Bewusst *nicht* enthalten:
#: NEU     -- G-017: der erste Bau wird von Hand angestossen und beobachtet.
#: ERROR   -- der Bau ist nachweislich fehlgeschlagen; ihn ungefragt zu
#:            wiederholen ist Endlos-Wiederholung ohne neue Erkenntnis.
AUTO_UPDATE = (OK, ABORTED)


def ist_nie_gebaut(status: str | None) -> bool:
    return (status or "") in NIE_GEBAUT
