/**
 * SkedyClass - JavaScript Principal
 */

const PREFS_TTL_MS = 7 * 24 * 60 * 60 * 1000; // 7 días

function prefGet(key, fallback) {
    try {
        const raw = localStorage.getItem(key);
        if (!raw) return fallback;
        const parsed = JSON.parse(raw);
        if (Date.now() - parsed.ts > PREFS_TTL_MS) {
            localStorage.removeItem(key);
            return fallback;
        }
        return parsed.val;
    } catch (_) {
        return fallback;
    }
}

function prefSet(key, val) {
    localStorage.setItem(key, JSON.stringify({ val: val, ts: Date.now() }));
}

document.addEventListener('DOMContentLoaded', function() {
    initTheme();
    initColor();

    setTimeout(function() {
        const alerts = document.querySelectorAll('.alert');
        alerts.forEach(function(alert) {
            alert.style.transition = 'opacity 0.5s';
            alert.style.opacity = '0';
            setTimeout(function() { alert.remove(); }, 500);
        });
    }, 5000);
});

function initTheme() {
    const savedTheme = prefGet('skedyclass-theme', 'light');
    document.documentElement.setAttribute('data-theme', savedTheme);
    document.body.setAttribute('data-theme', savedTheme);

    document.querySelectorAll('.theme-btn').forEach(function(btn) {
        btn.classList.toggle('active', btn.getAttribute('data-theme') === savedTheme);
    });
}

function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    document.body.setAttribute('data-theme', theme);
    prefSet('skedyclass-theme', theme);

    document.querySelectorAll('.theme-btn').forEach(function(btn) {
        btn.classList.toggle('active', btn.getAttribute('data-theme') === theme);
    });

    // #20 — persistir en BD
    _savePreferencia({ tema: theme });
}

function initColor() {
    const savedColor = prefGet('skedyclass-color', 'default');
    document.documentElement.setAttribute('data-color', savedColor);
    document.body.setAttribute('data-color', savedColor);

    document.querySelectorAll('.color-btn').forEach(function(btn) {
        btn.classList.toggle('active', btn.getAttribute('data-color') === savedColor);
    });
}

function setColor(color) {
    document.documentElement.setAttribute('data-color', color);
    document.body.setAttribute('data-color', color);
    prefSet('skedyclass-color', color);

    document.querySelectorAll('.color-btn').forEach(function(btn) {
        btn.classList.toggle('active', btn.getAttribute('data-color') === color);
    });

    // #20 — persistir en BD
    _savePreferencia({ color: color });
}

function _getCsrf() {
    var m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? m[1] : '';
}

function _savePreferencia(data) {
    var body = new URLSearchParams(data);
    fetch('/api/preferencia/', {
        method: 'POST',
        headers: {
            'X-CSRFToken': _getCsrf(),
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: body.toString(),
    }).catch(function() { /* silencioso: localStorage ya tiene el valor */ });
}

/**
 * Confirmar eliminación
 */
function confirmDelete(message) {
    return confirm(message || '¿Estás seguro de que deseas eliminar este elemento?');
}

/**
 * Imprimir página
 */
function printPage() {
    window.print();
}

/**
 * Mostrar/ocultar elemento
 */
function toggleElement(elementId) {
    const element = document.getElementById(elementId);
    if (element) {
        element.classList.toggle('hidden');
    }
}

/**
 * Formatear fecha
 */
function formatDate(dateString) {
    const options = { year: 'numeric', month: 'long', day: 'numeric' };
    return new Date(dateString).toLocaleDateString('es-CO', options);
}

/**
 * Manejar drag and drop en el Kanban (básico)
 */
function initKanban() {
    const cards = document.querySelectorAll('.kanban-card');
    const columns = document.querySelectorAll('.kanban-column');
    
    cards.forEach(function(card) {
        card.setAttribute('draggable', 'true');
        
        card.addEventListener('dragstart', function(e) {
            e.dataTransfer.setData('text/plain', card.getAttribute('data-id'));
            card.classList.add('dragging');
        });
        
        card.addEventListener('dragend', function() {
            card.classList.remove('dragging');
        });
    });
    
    columns.forEach(function(column) {
        column.addEventListener('dragover', function(e) {
            e.preventDefault();
            column.classList.add('drag-over');
        });
        
        column.addEventListener('dragleave', function() {
            column.classList.remove('drag-over');
        });
        
        column.addEventListener('drop', function(e) {
            e.preventDefault();
            column.classList.remove('drag-over');

            const cardId = e.dataTransfer.getData('text/plain');
            const newStatus = column.getAttribute('data-status');
            if (!cardId || !newStatus) return;

            // #24 — usar fetch para validar respuesta antes de mover la carta
            fetch('/clases/estado/' + cardId + '/' + newStatus + '/', {
                method: 'POST',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': _getCsrf(),
                },
            })
            .then(function(res) {
                if (!res.ok) throw new Error('Error ' + res.status);
                return res.json();
            })
            .then(function(data) {
                if (data.ok) {
                    var card = document.querySelector('.kanban-card[data-id="' + cardId + '"]');
                    var cardsEl = column.querySelector('.kanban-cards');
                    if (card && cardsEl) cardsEl.appendChild(card);
                } else {
                    alert('No se pudo cambiar el estado: ' + (data.error || 'error desconocido'));
                }
            })
            .catch(function(err) {
                alert('Error al cambiar el estado. Recarga la página e inténtalo de nuevo.');
            });
        });
    });
}

// Inicializar Kanban si existe en la página
if (document.querySelector('.kanban-board')) {
    initKanban();
}
