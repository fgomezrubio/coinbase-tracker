import requests
import time

URL = "https://api.exchange.coinbase.com/products"

def probar_conectividad():
    print("🔍 Probando conectividad con la API pública de Coinbase...\n")

    try:
        inicio = time.time()
        respuesta = requests.get(URL, timeout=10)
        fin = time.time()

        print(f"✔ Código HTTP: {respuesta.status_code}")

        if respuesta.status_code == 200:
            print("✔ Conexión exitosa con la API pública.")
            print(f"⏱ Tiempo de respuesta: {fin - inicio:.3f} segundos")

            data = respuesta.json()

            print("\n📌 Primeros 3 productos:")
            for p in data[:3]:
                print(f" • {p['id']}  (base: {p['base_currency']}, quote: {p['quote_currency']})")

        else:
            print("❌ La API respondió un código diferente a 200.")
            print("Respuesta:", respuesta.text)

    except requests.exceptions.Timeout:
        print("❌ Timeout.")

    except requests.exceptions.ConnectionError:
        print("❌ Error de conexión (revisa VPN / red).")

    except Exception as e:
        print("❌ Error inesperado:", e)


if __name__ == "__main__":
    probar_conectividad()

