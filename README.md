**To reproduce a minimal working setup, we recommend testing the browser extention + Gnosis server.**

**Of course you can setup other components if you wish to.**

**If you need assistance, feel free to reach out to @catalypso on Discord or at contact@faroukfaiz.com**

## High level architecture

[Excalidraw](https://excalidraw.com/#json=lfeB-kNoAjqHpXqX_ISz8,wX2xbci-nkG_hAH6_tKBpQ)
![diagram](/assets/diagram.png)

The Gnosis POC is a combination of multiple components:

- Recording and OCR: OpenRecall
- Scrapping browser content: Chrome extention + open-webui for embedded chat interface
- Chat app: An electron wrapper around Open WebUI
- Proxy server and memory management: Gnosis server


## How to run

### 1. Load the extension

Run a docker container with our custom open-webui image

```
 docker run -d -p 3003:8080 -e WEBUI_AUTH=False -e OLLAMA_BASE_URL="http://localhost:9000/proxy" -e DEFAULT_MODELS="llama3.2:3b" -v open-webui:/app/backend/data --name open-webui-custom ghcr.io/raise-your-hack-qasten/open-webui-custom:latest
```

1. On your browser, open Extensions -> Manage Extensions -> Load unpacked (make sure Developer mode is enabled).
2. Point to the `extension` directory.
3. Start a docker container with our custom image of open-webui

### 2. Run the memory server

1. Install [Ollama](https://ollama.com/download).
2. Run the server

```bash
cd server
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements
## Obviously this is bad, but we're sharing the key regardless for you to be able to test
## Hope the scrappers don't find this first
GROQ_API_KEY="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"
# OR ANYTHING_LLM_API_KEY="YOUR_ANYTHING_LLM_API_KEY" for local inference
python3 app.py
```

## Optional components:

### 3. Run the Chatbot UI

1. Install [docker](https://docs.docker.com/engine/install/)
2. Run the Chatbot UI

```bash
docker run -d -p 3000:8080 -e WEBUI_AUTH=False -e OLLAMA_BASE_URL="http://localhost:9000/proxy"  -e OFFLINE_MODE=true -v open-webui:/app/backend/data --add-host=host.docker.internal:host-gateway --name open-webui ghcr.io/open-webui/open-webui:main
```

### 4. Run OpenRecall

```bash
pipx install . --python 3.11 --include-deps --force -e
source ~/.local/share/pipx/venvs/openrecall/bin/activate
python3 -m openrecall.app
```
