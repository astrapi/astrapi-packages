// Dark Mode – Fallback: localStorage nur wenn JS-Toggle benötigt wird
// (Server setzt .light-mode per class-Attribut; diese Funktion bleibt
// für Rückwärtskompatibilität und sofortigen Effekt nach Settings-Save)
function applyLightMode(value) {
    document.documentElement.classList.toggle('light-mode', value === '1' || value === true);
}

// Active Nav
function updateActiveNav() {
    const path = window.location.pathname.replace(/^\/+/, "") || "overview";
    document.querySelectorAll(".nav-item").forEach(btn => {
        const key = btn.id.replace("nav-", "");
        if (key) {
            btn.classList.toggle("active", path === key);
        }
    });
}

document.addEventListener('DOMContentLoaded', function() {
    updateActiveNav();
});

document.body.addEventListener("htmx:afterSwap", (evt) => {
    if (evt.detail.target.id === "main-content") {
        updateActiveNav();
    }
});

document.body.addEventListener("htmx:pushedIntoHistory", () => {
    updateActiveNav();
});

// ── Spaltenbreiten-Resize ─────────────────────────────────────────────────────
function initColResize(table) {
    const module = table.dataset.module;
    if (!module) return;
    const saved = JSON.parse(table.dataset.colWidths || '{}');
    const headers = Array.from(table.querySelectorAll('thead th'));
    const last = headers.length - 1;

    headers.forEach((th, i) => {
        if (i === 0 || i === last || i === last - 1) return;
        if (saved[i] !== undefined) th.style.width = saved[i] + 'px';

        const handle = document.createElement('span');
        handle.className = 'col-resize-handle';
        th.appendChild(handle);

        handle.addEventListener('mousedown', e => {
            e.preventDefault();
            const startX = e.clientX;
            const startW = th.offsetWidth;
            handle.classList.add('resizing');

            const onMove = e => {
                th.style.width = Math.max(40, startW + e.clientX - startX) + 'px';
            };
            const onUp = () => {
                handle.classList.remove('resizing');
                document.removeEventListener('mousemove', onMove);
                document.removeEventListener('mouseup', onUp);
                const widths = {};
                headers.forEach((h, idx) => {
                    if (idx === 0 || idx === last || idx === last - 1) return;
                    widths[idx] = h.offsetWidth;
                });
                fetch(`/ui/preferences/col-widths/${module}`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({widths}),
                });
            };
            document.addEventListener('mousemove', onMove);
            document.addEventListener('mouseup', onUp);
        });
    });
}

function initAllColResize(root) {
    (root || document).querySelectorAll('.ds-list-table[data-module]').forEach(initColResize);
}

document.addEventListener('DOMContentLoaded', () => initAllColResize());
document.body.addEventListener('htmx:afterSwap', e => initAllColResize(e.detail.target));

// ── Tabellen-Sortierung ───────────────────────────────────────────────────────
function initTableSort(table) {
    const module = table.dataset.module;
    const storageKey = module ? `sort:${module}` : null;
    let saved = {};
    if (storageKey) {
        try { saved = JSON.parse(localStorage.getItem(storageKey) || '{}'); } catch {}
    }

    const headers = Array.from(table.querySelectorAll('thead th.sortable'));
    if (!headers.length) return;

    function applySort(th, dir, save) {
        headers.forEach(h => h.classList.remove('sort-asc', 'sort-desc'));
        th.classList.add(dir === 'asc' ? 'sort-asc' : 'sort-desc');

        const col = th.cellIndex;
        const tbody = table.querySelector('tbody');
        const rows = Array.from(tbody.querySelectorAll('tr'));
        rows.sort((a, b) => {
            const av = (a.cells[col]?.textContent || '').trim();
            const bv = (b.cells[col]?.textContent || '').trim();
            const cmp = av.localeCompare(bv, undefined, {numeric: true, sensitivity: 'base'});
            return dir === 'asc' ? cmp : -cmp;
        });
        rows.forEach(r => tbody.appendChild(r));
        if (save && storageKey) {
            localStorage.setItem(storageKey, JSON.stringify({col, dir}));
        }
    }

    if (saved.col !== undefined) {
        const th = headers.find(h => h.cellIndex === saved.col);
        if (th) applySort(th, saved.dir || 'asc', false);
    }

    headers.forEach(th => {
        th.addEventListener('click', () => {
            applySort(th, th.classList.contains('sort-asc') ? 'desc' : 'asc', true);
        });
    });
}

function initAllTableSort(root) {
    (root || document).querySelectorAll('.ds-list-table[data-module]').forEach(initTableSort);
}

document.addEventListener('DOMContentLoaded', () => initAllTableSort());
document.body.addEventListener('htmx:afterSwap', e => initAllTableSort(e.detail.target));

// ── Karten-/Listenansicht Toggle ─────────────────────────────────────────────
function viewToggle(_module) {
    const mq = window.matchMedia('(max-width: 767px)');
    return {
        view: mq.matches ? 'card' : 'list',
        _mq: mq,
        init() {
            this._mqHandler = (e) => { this.view = e.matches ? 'card' : 'list'; };
            this._mq.addEventListener('change', this._mqHandler);
        },
        destroy() {
            this._mq.removeEventListener('change', this._mqHandler);
        },
    };
}
