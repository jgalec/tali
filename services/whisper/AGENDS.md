👉 Objetivo:

- Whisper corriendo como **servidor independiente (modelo en RAM)**
- MCP **solo hace requests**
- 100% local + CPU

------

# 🧠 Arquitectura final (lo que vas a construir)

```text
[ OpenCode Agent ]
        ↓
[ MCP (ligero) ]
        ↓ HTTP
[ Whisper Server (faster-whisper en RAM) ]
        ↓
[ Texto ]
```

👉 Esto es exactamente cómo se hace en producción.

------

# 🚀 PARTE 1 — Levantar el servidor Whisper (modelo en memoria)

## 🔹 Opción recomendada (la más fácil): usar server ya hecho

👉 Vamos a usar un server listo:

## 1. Clonar repo

```bash
git clone https://github.com/etalab-ia/faster-whisper-server.git
cd faster-whisper-server
```

------

## 2. Ejecutar con Docker (CPU)

```bash
docker run -p 8000:8000 \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  fedirz/faster-whisper-server:latest-cpu
```

👉 Esto hace:

- descarga el modelo
- lo carga en memoria
- levanta API en `http://localhost:8000`

✔️ Compatible con CPU
✔️ OpenAI-style API
✔️ streaming incluido
✔️ carga dinámica de modelos ([GitHub](https://github.com/etalab-ia/faster-whisper-server?utm_source=chatgpt.com))

------

## 🔥 Resultado

Ahora tienes:

```bash
http://localhost:8000/v1/audio/transcriptions
```

👉 ya corriendo con el modelo en RAM

------

# 🧪 Test rápido

```bash
curl http://localhost:8000/v1/audio/transcriptions \
  -F "file=@audio.wav" \
  -F "model=Systran/faster-distil-whisper-large-v3"
```

------

# 🧠 IMPORTANTE

Ese servidor:

- mantiene modelos en memoria
- puede cargar/descargar dinámicamente ([GitHub](https://github.com/etalab-ia/faster-whisper-server?utm_source=chatgpt.com))
- está optimizado con **faster-whisper (CTranslate2)** → más rápido y menos RAM ([GitHub](https://github.com/SYSTRAN/faster-whisper?utm_source=chatgpt.com))

------

# ⚙️ PARTE 2 — MCP (ligero, como tú quieres)

Tu MCP **NO carga modelo**
solo hace HTTP

------

## MCP minimal

```python
from mcp.server.fastmcp import FastMCP
import requests

mcp = FastMCP("whisper-client")

@mcp.tool()
def transcribe(file_path: str) -> str:
    with open(file_path, "rb") as f:
        response = requests.post(
            "http://localhost:8000/v1/audio/transcriptions",
            files={"file": f},
            data={"model": "Systran/faster-distil-whisper-large-v3"}
        )
    return response.json().get("text", "")

if __name__ == "__main__":
    mcp.run()
```

------

# 🔌 PARTE 3 — Configurar en OpenCode

```json
{
  "mcpServers": {
    "whisper": {
      "command": "python",
      "args": ["whisper_mcp.py"]
    }
  }
}
```

------

# ⚡ ALTERNATIVA (sin Docker, más control)

Si quieres que tu agente lo haga todo:

------

## 1. Instalar deps

```bash
pip install faster-whisper fastapi uvicorn python-multipart
```

------

## 2. Server propio (copy-paste)

```python
from fastapi import FastAPI, UploadFile
from faster_whisper import WhisperModel

app = FastAPI()

# 🔥 modelo en RAM
model = WhisperModel("base", compute_type="int8")

@app.post("/transcribe")
async def transcribe(file: UploadFile):
    audio = await file.read()

    with open("temp.wav", "wb") as f:
        f.write(audio)

    segments, _ = model.transcribe("temp.wav")

    text = " ".join([s.text for s in segments])

    return {"text": text}
```

------

## 3. Ejecutar

```bash
uvicorn server:app --host 0.0.0.0 --port 8000
```

------

👉 Esto hace exactamente lo mismo:

- modelo cargado una vez
- API local
- MCP lo consume