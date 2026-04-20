# Whisper MCP

Lightweight MCP client for a Whisper HTTP server.

Architecture:

```text
[ OpenCode Agent ]
        ->
[ MCP client ]
        -> HTTP
[ Whisper server ]
        ->
[ transcription text ]
```

This MCP does not load models. It only sends HTTP requests to a running Whisper server, local or remote.

## Files

- `services/whisper/whisper_mcp.py`: MCP server with transcription tools
- `services/whisper/modal_whisper_app.py`: small Modal deployment for Whisper
- `services/whisper/requirements.txt`: Python dependencies
- `services/whisper/requirements-modal.txt`: local dependency for Modal deploys
- `services/whisper/output/`: generated transcription files

## Tools

- `whisper_server_status`: checks if the local Whisper server is reachable
- `transcribe_audio`: transcribes one local audio file
- `transcribe_manifest`: transcribes every audio listed in a manifest file and writes results to disk

## Defaults

- Whisper URL: `http://localhost:8000`
- Model: `large-v3`
- Auth: `WHISPER_AUTH_TOKEN` bearer token when set
- Status timeout: `WHISPER_STATUS_TIMEOUT=30`
- Default manifest: `me2_game_files_durations.txt`
- Default audio root: `me2_game_files`

## Install

```bash
pip install -r services/whisper/requirements.txt
```

## MVP with Modal

This repo now includes a small Modal app that exposes the same transcription route expected by the MCP:

```text
POST /v1/audio/transcriptions
GET  /health
```

### 1. Install local deploy dependency

```bash
pip install -r services/whisper/requirements-modal.txt
```

### 2. Configure the model for the MVP

Optional environment variables:

```bash
set WHISPER_MODEL_NAME=large-v3
set WHISPER_COMPUTE_TYPE=float16
set WHISPER_DEVICE=cuda
```

The current deployed MVP uses `large-v3` on GPU. If you want to override the client-side default, set `WHISPER_MODEL` before running the MCP.

### 3. Test locally on Modal

```bash
modal serve services/whisper/modal_whisper_app.py
```

### 4. Deploy

```bash
modal deploy services/whisper/modal_whisper_app.py
```

After deploy, Modal will print the public URL for the FastAPI app.

### 5. Point the MCP to Modal

```bash
set WHISPER_SERVER_URL=https://your-modal-url.modal.run
set WHISPER_AUTH_TOKEN=your-bearer-token
python services/whisper/whisper_mcp.py
```

The deployed Modal app can require a bearer token. When `WHISPER_AUTH_TOKEN` is set locally, the MCP sends `Authorization: Bearer ...` automatically.

### Modal URL notes

- Modal always gives the endpoint a `.modal.run` URL automatically.
- The auto-generated URL has the shape `https://<workspace-or-env>--<label>.modal.run`.
- You can customize the `label` portion of the URL for the web endpoint.
- You cannot freely customize the full `.modal.run` hostname on standard plans.
- Fully custom domains require Modal custom domain support on Team/Enterprise plans.
- Adding a custom domain does not disable the original `.modal.run` URL; both keep working.

## Current Modal profile

- GPU: `T4`
- CPU: `4`
- Memory: `16384` MiB
- Model: `large-v3`
- Compute type: `float16`
- Max concurrent inputs per container: `1`

## Output directories

- Smoke tests: `services/whisper/output_modal_smoke`
- Auth smoke tests: `services/whisper/output_modal_smoke_auth`
- 25-file benchmark: `services/whisper/output_modal_benchmark_25`
- Final full run: `services/whisper/output_modal_final`

## Local server option

Recommended Docker option:

```bash
docker run -p 8000:8000 -v ~/.cache/huggingface:/root/.cache/huggingface fedirz/faster-whisper-server:latest-cpu
```

Once running, the transcription endpoint will be available at:

```text
http://localhost:8000/v1/audio/transcriptions
```

## Run the MCP

```bash
set WHISPER_SERVER_URL=http://localhost:8000
python services/whisper/whisper_mcp.py
```

## OpenCode MCP config

```json
{
  "mcpServers": {
    "whisper": {
      "command": "python",
      "args": ["services/whisper/whisper_mcp.py"]
    }
  }
}
```

## Suggested first call

Call `whisper_server_status` first. If the server is healthy, call `transcribe_manifest`.

Example parameters for the filtered Tali batch:

```json
{
  "manifest_path": "me2_game_files_durations.txt",
  "audio_root": "me2_game_files",
  "output_dir": "services/whisper/output",
  "language": "en",
  "max_workers": 1,
  "resume": true
}
```

## Output files

- `services/whisper/output/transcriptions.jsonl`: structured per-audio result, including errors
- `services/whisper/output/transcriptions.txt`: grouped text output by folder

`resume=true` will reuse existing `transcriptions.jsonl` entries and skip already transcribed files.
