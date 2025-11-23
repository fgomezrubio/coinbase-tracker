// main.js
console.log("Coinbase Top Movers dashboard loaded ✅");

// Aquí puedes agregar lógica JS futura, por ejemplo:
// - Auto-refresh cada X segundos
// - Ordenar columnas en el frontend
// - Mostrar tooltips, etc.

// Global watchlist
let watchlist = {};  
// estructura: 
// watchlist[product_id] = { initialPrice, addedAt, rowElement }

function addToWatchlist(productId, initialPrice) {
    if (watchlist[productId]) return; // ya está agregado

    const addedAt = new Date();

    // Crear fila en tabla
    const tbody = document.getElementById("watchlist-body");
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
        rowElement: row
    };
}

function removeFromWatchlist(productId) {
    const row = document.getElementById(`row-${productId}`);
    if (row) row.remove();
    delete watchlist[productId];
}

async function refreshWatchlist() {
    for (let productId in watchlist) {
        try {
            const res = await fetch(`/api/price/${productId}`);
            const data = await res.json();

            if (!data.last_price) continue;

            const obj = watchlist[productId];
            const row = obj.rowElement;

            const lastPriceCell = row.querySelector(".last-price");
            const changeCell = row.querySelector(".change");
            const elapsedCell = row.querySelector(".elapsed");

            const last = data.last_price;
            const change = ((last - obj.initialPrice) / obj.initialPrice) * 100;

            // actualizar precio
            lastPriceCell.textContent = last.toFixed(6);

            // actualizar cambio
            changeCell.textContent = change.toFixed(2) + "%";

            // colores:
            if (change > 0.0001) {
                changeCell.style.color = "green";
            } else if (change < -0.0001) {
                changeCell.style.color = "red";
            } else {
                changeCell.style.color = "black";
            }

            // calcular tiempo transcurrido
            const elapsedSec = Math.floor((new Date() - obj.addedAt) / 1000);
            elapsedCell.textContent = elapsedSec + "s";

        } catch (err) {
            console.error("Error refreshing: ", productId);
        }
    }
}

// refrescar cada 5s
setInterval(refreshWatchlist, 5000);

