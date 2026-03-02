# VULNERABILIDAD-KICK

Proof of Concept — Vulnerabilidad en el sistema de viewers de Kick.com

## Requisitos

- **Node.js** v18+
- **Python** 3.10+
- **npm**

## Instalación

### 1. Clonar el repositorio

```bash
git clone https://github.com/JhonRamirez22/VULNERABILIDAD-KICK.git
cd VULNERABILIDAD-KICK
```

### 2. Instalar dependencias de Node.js

```bash
npm install
```

Esto instala:
- `ws` — cliente WebSocket
- `playwright` — automatización de navegador

### 3. Instalar dependencias de Python

```bash
pip3 install curl_cffi
```

> **Nota (macOS con Homebrew):** Si recibes el error `externally-managed-environment`, usa:
> ```bash
> pip3 install --break-system-packages curl_cffi
> ```
> O crea un entorno virtual:
> ```bash
> python3 -m venv .venv
> source .venv/bin/activate
> pip install curl_cffi
> ```

### 4. Verificar instalación

```bash
node -v          # debe ser v18+
python3 --version # debe ser 3.10+
python3 -c "from curl_cffi import requests; print('curl_cffi OK')"
```

## Uso

```bash
node kick-websocket.js https://kick.com/<canal> <cantidad_viewers>
```

**Ejemplo:**
```bash
node kick-websocket.js https://kick.com/coscu 800
```

## ⚠️ Disclaimer

Este proyecto es una **prueba de concepto (PoC)** con fines educativos y de investigación en seguridad. El uso indebido de esta herramienta es responsabilidad exclusiva del usuario.
