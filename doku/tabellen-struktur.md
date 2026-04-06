# Tabellen-Struktur – astrapi-packages

Stand: 2026-04-06  
CSS: `table-layout: fixed` — explizite Breiten sind garantiert, flexible Spalten teilen den Rest.  
Kein horizontaler Scroll (`overflow-x: hidden`), die rechten Festspalten sind immer sichtbar.

---

## Kern-Struktur (alle Module)

| Klasse         | Min-Breite | Max-Breite | Verhalten                     |
|----------------|------------|------------|-------------------------------|
| `col-name`     | 250px      | 250px      | truncate + fett (core: Name)  |
| *(modul-spez.)* | —         | flex       | je nach Modul                 |
| `col-type`     | 60px       | 60px       | Typ-Badge                     |
| `col-version`  | 150px      | 150px      | Version, mono, truncate       |
| `col-last-run` | 150px      | 150px      | kein Wrap, truncate           |
| `col-status`   | 60px       | 60px       | Status-Badge (immer)          |
| `col-actions`  | 60px       | 60px       | ⋮-Menü (immer)               |

---

## Docker

| # | Spalte       | Klasse         | Min   | Max   | Inhalt              |
|---|--------------|----------------|-------|-------|---------------------|
| 1 | Name         | `col-name`     | 250px | 250px | Image-ID            |
| 2 | Image        | `col-trunc`    | —     | flex  | `ctl/<name>:<tag>`  |
| 3 | Letzter Lauf | `col-last-run` | 150px | 150px | `last_run`          |
| 4 | Status       | `col-status`   | 60px  | 60px  | Status-Badge        |
| 5 | ⋮            | `col-actions`  | 60px  | 60px  | Ctx-Menü            |

---

## Pakete

| # | Spalte       | Klasse         | Min   | Max   | Inhalt                             |
|---|--------------|----------------|-------|-------|------------------------------------|
| 1 | Name         | `col-name`     | 250px | 250px | Paket-ID                           |
| 2 | Typ          | `col-type`     | 60px  | 60px  | Badge: Paket / Dep / Verwaist      |
| 3 | Quelle       | `col-trunc`    | —     | flex  | Source-URL (Link)                  |
| 4 | Version      | `col-version`  | 150px | 150px | `last_version` + ggf. `→ upstream` |
| 5 | Letzter Lauf | `col-last-run` | 150px | 150px | `last_run`                         |
| 6 | Status       | `col-status`   | 60px  | 60px  | Status-Badge                       |
| 7 | ⋮            | `col-actions`  | 60px  | 60px  | Ctx-Menü                           |

---

## CSS-Regeln (Core — `app.css`)

```css
/* Feste Spalten */
.ds-list-table .col-type     { width:  60px; min-width:  60px; }
.ds-list-table .col-version  { width: 150px; min-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: var(--mono); font-size: .85em; }
.ds-list-table .col-last-run { width: 150px; min-width: 150px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ds-list-table .col-status   { width:  60px; min-width:  60px; }
.ds-list-table .col-actions  { width:  60px; min-width:  60px; }

/* col-name: 250px fix, flex nur für proxmox_hosts (keine anderen flex-Spalten) */
.ds-list-table .col-name     { width: 250px; min-width: 250px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 600; }

/* Flexible Spalten – truncaten wenn zu wenig Platz */
.ds-list-table .col-trunc    { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* Kein horizontaler Scroll */
.ds-list-table-wrap-scroll   { overflow-x: hidden; }
.ds-list-table               { width: 100%; table-layout: fixed; }
```
