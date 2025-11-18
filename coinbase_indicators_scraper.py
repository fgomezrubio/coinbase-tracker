from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException
import time

# URL de cualquier par en Advanced Trade (ajusta si quieres otro)
ADVANCED_URL = "https://www.coinbase.com/advanced-trade/spot/BTC-USD"

# ====== SELECTORES XPATH (puedes ajustarlos si cambia la UI) ======
# Botón "Indicators" arriba del gráfico
XPATH_INDICATORS_BUTTON = "//button[contains(., 'Indicators')]"

# Contenedor del popup de indicadores (panel que se abre)
XPATH_INDICATORS_DIALOG = "//div[contains(., 'Indicators') and @role='dialog']"

# Contenedor con scroll donde están listados los indicadores
# (ajusta si es necesario inspeccionando el DOM)
XPATH_SCROLL_CONTAINER = (
    XPATH_INDICATORS_DIALOG
    + "//div[contains(@class,'overflow-y-auto') or contains(@class,'Scroll') or contains(@class,'scroll')]"
)

# Cada fila/indicador en la lista (normalmente son botones clicables)
XPATH_INDICATOR_ROW = XPATH_SCROLL_CONTAINER + "//div[@role='button']"


def main():
    # Configurar Chrome
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options,
    )

    wait = WebDriverWait(driver, 60)

    try:
        print("[*] Abriendo Coinbase Advanced...")
        driver.get(ADVANCED_URL)

        print("[*] Haz login si es necesario. El script esperará a que aparezca el botón 'Indicators'.")

        # Esperar a que aparezca el botón Indicators (hasta 2 minutos)
        indicators_btn = WebDriverWait(driver, 120).until(
            EC.element_to_be_clickable((By.XPATH, XPATH_INDICATORS_BUTTON))
        )
        print("[+] Botón 'Indicators' encontrado, haciendo clic...")
        indicators_btn.click()

        # Esperar a que aparezca el diálogo de indicadores
        dialog = wait.until(
            EC.visibility_of_element_located((By.XPATH, XPATH_INDICATORS_DIALOG))
        )
        print("[+] Panel de indicadores visible.")

        # Encontrar el contenedor con scroll
        scroll_container = driver.find_element(By.XPATH, XPATH_SCROLL_CONTAINER)

        indicator_names = set()
        last_seen_count = -1
        stable_scrolls = 0

        print("[*] Recorriendo la lista de indicadores (scroll)...")

        while True:
            rows = driver.find_elements(By.XPATH, XPATH_INDICATOR_ROW)

            for row in rows:
                try:
                    text = row.text.strip()
                    # Normalmente la primera línea es el nombre del indicador
                    if "\n" in text:
                        text = text.split("\n", 1)[0].strip()
                    if text and text not in indicator_names:
                        indicator_names.add(text)
                        print(f"  [+] Nuevo indicador: {text}")
                except StaleElementReferenceException:
                    # Si el elemento desaparece al hacer scroll, lo ignoramos
                    continue

            # Hacer scroll hasta abajo del contenedor
            driver.execute_script(
                "arguments[0].scrollTop = arguments[0].scrollHeight;", scroll_container
            )
            time.sleep(1)

            # Condición de parada: si ya no aumentan los elementos encontrados
            if len(indicator_names) == last_seen_count:
                stable_scrolls += 1
                if stable_scrolls >= 3:
                    break
            else:
                stable_scrolls = 0
                last_seen_count = len(indicator_names)

        print("\n==============================")
        print(f"Total de indicadores encontrados: {len(indicator_names)}")
        print("==============================")

        # Guardar en archivo
        with open("coinbase_indicators.txt", "w", encoding="utf-8") as f:
            for name in sorted(indicator_names):
                f.write(name + "\n")

        print("[+] Lista guardada en 'coinbase_indicators.txt'")

    finally:
        # Cierra el navegador al final (si quieres dejarlo abierto, comenta esto)
        time.sleep(3)
        driver.quit()


if __name__ == "__main__":
    main()

