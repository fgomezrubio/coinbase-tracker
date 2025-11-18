# 📈 Coinbase Tracker (Flask + MongoDB)

Coinbase Tracker is a lightweight dashboard built with **Flask**, **MongoDB**, and the **Coinbase Public API**.  
It allows you to quickly visualize the **Top Movers (24h)** for any selected `quote_currency` (USD, USDT, EUR, etc.).

This project is ideal for:
- Learning how to use Flask for real-world APIs  
- Building a crypto monitoring tool  
- Practicing MongoDB + Python integrations  
- Expanding into algo-trading or data pipelines later  

---

## 🚀 Features

### 🔍 Product Data
- Fetches all available trading pairs from Coinbase Exchange API  
- Stores them locally in MongoDB (`CoinBase.products`)  
- Updates automatically with `upsert`  

### 📊 Top Movers Dashboard
- Filter by **quote_currency**
- Select how many results to show (Top N)
- Shows:
  - Open price (24h)
  - Last price
  - % Change (24h)
  - Positive/negative highlight  
  - **Direct link to Coinbase Advanced Trade** for each coin  

### 🎨 UI / UX
- Modern responsive design  
- Styling separated into external CSS (`static/css/styles.css`)
- Button navigation for each trading pair  
- Ready for theme switch, auto-
