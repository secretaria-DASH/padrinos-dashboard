"""
Compartir el dashboard con un link público usando ngrok.

ANTES DE CORRER:
  1. Crear cuenta gratis en https://ngrok.com  (solo email, no tarjeta)
  2. Copiar el Authtoken desde https://dashboard.ngrok.com/get-started/your-authtoken
  3. Pegarlo abajo donde dice TU_TOKEN_AQUI
  4. Correr:  python3 share.py
"""

from pyngrok import ngrok, conf
import subprocess, sys, time, webbrowser

# ── 1. Pegá tu token de ngrok.com/dashboard aquí ──────────────────────────────
NGROK_TOKEN = "TU_TOKEN_AQUI"
# ──────────────────────────────────────────────────────────────────────────────

if NGROK_TOKEN == "TU_TOKEN_AQUI":
    print("\n❌  Falta el token de ngrok.")
    print("    1. Creá cuenta gratis en https://ngrok.com")
    print("    2. Copiá tu Authtoken en https://dashboard.ngrok.com/get-started/your-authtoken")
    print("    3. Pegalo en este archivo donde dice TU_TOKEN_AQUI")
    sys.exit(1)

# Configura el token
conf.get_default().auth_token = NGROK_TOKEN

# Levanta el servidor Flask en background
print("🚀 Iniciando servidor...")
server = subprocess.Popen(
    [sys.executable, "app.py"],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL
)
time.sleep(2)

# Crea el túnel público
print("🌐 Creando link público...")
tunnel = ngrok.connect(5050, bind_tls=True)
url = tunnel.public_url

print("\n" + "="*55)
print(f"  ✅  Dashboard público:")
print(f"\n  👉  {url}\n")
print("  Compartí este link con quien quieras.")
print("  Funciona mientras esta ventana esté abierta.")
print("="*55)
print("\n  Presioná Ctrl+C para cerrar.\n")

webbrowser.open(url)

try:
    ngrok.get_ngrok_process().proc.wait()
except KeyboardInterrupt:
    print("\n\n🔴 Cerrando túnel...")
    ngrok.kill()
    server.terminate()
    print("Listo. El link ya no funciona.")
