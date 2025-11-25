// static/js/main.js

const STORAGE_KEY = "coinbase_watchlist";

// watchlist en memoria
// estructura: watchlist[productId] = { initialPrice, addedAt: Date, rowElement }
let watchlist = {};

async function addToWatchlistFromMarkets(productId) {
    // Evitar duplicados
    if (watchlist[productId]) {
        console.log("Already in watchlist:", productId);
        return;
    }

    try {
        const res = await fetch(`/api/price/${productId}`);
        if (!res.ok) {
            console.error("Failed to fetch price for", productId);
            return;
        }
        const data = await res.json();
        if (!data.last_price) {
            console.error("Invalid price data for", productId, data);
            return;
        }

        const initialPrice = Number(data.last_price);
        addToWatchlist(productId, initialPrice);
    } catch (err) {
        console.error("Error adding from markets:", productId, err);
    }
}

function toggleCard(cardId) {
    const card = document.getElementById(cardId);
    if (!card) return;

    card.classList.toggle("collapsed");

    const btn = card.querySelector(".btn-toggle");
    if (!btn) return;

    if (card.classList.contains("collapsed")) {
        btn.textContent = "+";
    } else {
        btn.textContent = "−";
    }
}

function formatElapsed(totalSeconds) {
    let seconds = totalSeconds;

    const days = Math.floor(seconds / 86400);
    seconds -= days * 86400;

    const hours = Math.floor(seconds / 3600);
    seconds -= hours * 3600;

    const minutes = Math.floor(seconds / 60);
    seconds -= minutes * 60;

    // Helper para formatear en 2 dígitos
    const pad = (num) => num.toString().padStart(2, '0');

    // Construcción del texto final
    if (days > 0) {
        // Si hay días → mostramos formato: 2d 03h 15m
        return `${days}d ${pad(hours)}h ${pad(minutes)}m`;
    } 
    
    if (hours > 0) {
        // Si hay horas → 1h 05m 10s
        return `${hours}h ${pad(minutes)}m ${pad(seconds)}s`;
    }

    if (minutes > 0) {
        // Si hay minutos → 3m 42s
        return `${minutes}m ${pad(seconds)}s`;
    }

    // Solo segundos
    return `${seconds}s`;
}

function saveWatchlistToStorage() {
    const list = Object.entries(watchlist).map(([productId, obj]) => ({
        productId,
        initialPrice: obj.initialPrice,
        addedAt: obj.addedAt.toISOString(),
    }));
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
    } catch (e) {
        console.error("Error saving watchlist to localStorage", e);
    }
}

function loadWatchlistFromStorage() {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return;

    try {
        const list = JSON.parse(raw);
        if (!Array.isArray(list)) return;

        list.forEach(item => {
            const { productId, initialPrice, addedAt } = item;
            // recreamos cada fila
            createWatchlistRow(productId, Number(initialPrice), new Date(addedAt), false);
        });
    } catch (e) {
        console.error("Error loading watchlist from localStorage", e);
    }
}

/**
 * Crea la fila visual y actualiza el objeto watchlist
 * @param {string} productId
 * @param {number} initialPrice
 * @param {Date} addedAt
 * @param {boolean} persist si true, también guarda en localStorage
 */
function createWatchlistRow(productId, initialPrice, addedAt, persist = true) {
    if (watchlist[productId]) return; // ya existe

    const tbody = document.getElementById("watchlist-body");
    if (!tbody) return;

    const row = document.createElement("tr");
    row.id = `row-${productId}`;

    row.innerHTML = `
        <td>${productId}</td>
        <td>${initialPrice.toFixed(6)}</td>
        <td class="last-price">-</td>
        <td class="change">-</td>
        <td>${addedAt.toLocaleString()}</td>
        <td class="elapsed">0s</td>
        <td>
            <a class="trade-btn" target="_blank"
               href="https://www.coinbase.com/advanced-trade/spot/${productId}">
               Open ↗
            </a>
        </td>
        <td>
            <button class="btn-remove" onclick="removeFromWatchlist('${productId}')">
                ✖
            </button>
        </td>
    `;

    tbody.appendChild(row);

    watchlist[productId] = {
        initialPrice,
        addedAt,
        rowElement: row,
    };

    if (persist) {
        saveWatchlistToStorage();
    }
}

/**
 * Llamado desde el botón Monitor en la tabla superior
 */
function addToWatchlist(productId, initialPrice) {
    // initialPrice viene de Jinja como número ({{ r.last }})
    createWatchlistRow(productId, Number(initialPrice), new Date(), true);
}

/**
 * Elimina una fila del watchlist y actualiza storage
 */
function removeFromWatchlist(productId) {
    const row = document.getElementById(`row-${productId}`);
    if (row) row.remove();
    delete watchlist[productId];
    saveWatchlistToStorage();
}

/**
 * Refresca precios para todos los elementos del watchlist
 */
async function refreshWatchlist() {
    const entries = Object.entries(watchlist);
    for (const [productId, obj] of entries) {
        try {
            const res = await fetch(`/api/price/${productId}`);
            if (!res.ok) continue;
            const data = await res.json();
            if (!data.last_price) continue;

            const row = obj.rowElement;
            if (!row) continue;

            const lastPriceCell = row.querySelector(".last-price");
            const changeCell = row.querySelector(".change");
            const elapsedCell = row.querySelector(".elapsed");

            const last = Number(data.last_price);
            const change = ((last - obj.initialPrice) / obj.initialPrice) * 100;

            // actualizar precio
            lastPriceCell.textContent = last.toFixed(6);

            // actualizar cambio
            changeCell.textContent = change.toFixed(2) + "%";

            // colores (verde, rojo, negro)
            if (change > 0.0001) {
                changeCell.style.color = "green";
            } else if (change < -0.0001) {
                changeCell.style.color = "red";
            } else {
                changeCell.style.color = "black";
            }

            // tiempo transcurrido
            // const elapsedSec = Math.floor((new Date() - obj.addedAt) / 1000);
            // elapsedCell.textContent = elapsedSec + "s";

	    const elapsedSec = Math.floor((new Date() - obj.addedAt) / 1000);
	    elapsedCell.textContent = formatElapsed(elapsedSec);


        } catch (err) {
            console.error("Error refreshing price for", productId, err);
        }
    }
}

// Inicializar cuando cargue la página
window.addEventListener("DOMContentLoaded", () => {
    loadWatchlistFromStorage();
    // empieza el refresco cada 5s
    setInterval(refreshWatchlist, 5000);
    console.log("Realtime watchlist initialized ✅");
});

