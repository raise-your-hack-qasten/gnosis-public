import logging
from flask import Flask, request, jsonify, send_file, Request, Response
import requests
import json
import time

import os
from mem0 import Memory

OLLAMA_URL = "http://localhost:11434"
ANYTHING_LLM_URL = "http://localhost:3001"
MEM0_USER_ID = "default_user"

mem0_base_config = {
    "vector_store": {
        "config": {
            "embedding_model_dims": 1024,  # https://docs.mem0.ai/components/vectordbs/overview#using-model-with-different-dimensions
        },
    },
    "embedder": {
        "provider": "ollama",
        "config": {"model": "mxbai-embed-large:latest"},
    },
}
mem0_ollama_config = {
    **mem0_base_config,
    "llm": {
        "provider": "ollama",
        "config": {
            "model": "llama3.2:3b",
            "temperature": 0,
            "max_tokens": 20000,
        },
    },
}
mem0_groq_config = {
    **mem0_base_config,
    "llm": {
        "provider": "groq",
        "config": {
            "model": "llama-3.3-70b-versatile",
            "temperature": 0,
            "max_tokens": 20000,
        },
    },
}
mem0_snapdragon_config = {
    **mem0_base_config,
    "llm": {
        "provider": "ollama",
        "config": {
            "model": "llama3.2:3b",
            "temperature": 0,
            "max_tokens": 20000,
            "ollama_base_url": ANYTHING_LLM_URL,
        },
    },
}

MEM0_CUSTOM_INSTRUCTIONS_TO_EXTRACT_OCR = """
You are processing raw OCR of a user’s screen. 
1. CLEANING  
   • Normalize whitespace and punctuation; remove obvious OCR artifacts (e.g., “ﬁ”→“fi”, extraneous “—‑_”, repeated characters).  
   • Merge words broken by hard line‑breaks; correct common OCR confusions (1↔l, 0↔O, rn↔m).  
   • Drop UI chrome such as window titles, toolbar labels, time/‑battery readouts, and any line shorter than 3 characters.

2. EXTRACTION  
   Identify and keep only *actionable* or *contextual* nuggets. Tag each line with one of:  
   • **Task:** An instruction, to‑do, or reminder containing a verb (“send”, “finish”, “call”).  
   • **Event:** A meeting, appointment, or date/time reference.  
   • **Decision:** A conclusion or choice that has been agreed upon.  
   • **Note:** Factual info likely to matter later (numbers, IDs, contact info, credentials).  
   • **Link:** Any URL.

3. OUTPUT FORMAT  
   Return a concise bulleted list, one nugget per line, in the form  
   “• <Tag> <cleaned content>”.  
   Preserve original capitalization only when necessary (proper nouns, acronyms). If nothing meaningful is found, return an empty list.
"""


app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
file_handler = logging.FileHandler("server.log")
file_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
file_handler.setFormatter(formatter)
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.DEBUG)

mem0_provider = "Ollama"
mem0_config = mem0_ollama_config
if os.environ.get("ANYTHING_LLM_API_KEY"):
    active_model_name = "llama3.2:3b"
    mem0_provider = "Anything LLM with models running on the NPU"
    mem0_config = mem0_snapdragon_config
elif os.environ.get("GROQ_API_KEY"):
    active_model_name = "llama3-70b-8192"
    mem0_provider = "Groq"
    mem0_config = mem0_groq_config

app.logger.info(f"Will use {mem0_provider} for Mem0 operations.")


memory = Memory.from_config(mem0_config)


@app.route("/add_page", methods=["POST"])
def add_page():
    """Endpoint to add a page's content to the Mem0 memory store."""
    try:
        data = request.get_json(force=True)
        title = data.get("title")
        url = data.get("url")
        content = data.get("content")
        if content is None or url is None:
            return (
                jsonify(
                    {"success": False, "error": "Missing 'url' or 'content' in request"}
                ),
                400,
            )

        app.logger.info(
            f"Received /add_page request: title='{title}', url='{url}', content_length={len(content) if content else 0}"
        )

        memory.add(
            content,
            user_id=MEM0_USER_ID,
            metadata={"url": url, "source": "browser_dom", "title": title},
        )
        app.logger.info(f"Content from {url} added to memory.")
        return jsonify({"success": True, "message": "Content added to memory"}), 200

    except Exception as e:
        app.logger.error(f"Error in /add_page: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/add_ocr", methods=["POST"])
def add_ocr():
    """Endpoint to OCR content to the Mem0 memory store."""
    try:
        data = request.get_json(force=True)
        app_name = data.get("app_name")
        window_name = data.get("window_name")
        ocr_data = data.get("text")
        if ocr_data is None:
            return (
                jsonify(
                    {"success": False, "error": "Missing OCR content from OpenRecall"}
                ),
                400,
            )

        app.logger.info(
            f"Received /add_ocr request: Application name='{app_name}', Windows name'{window_name}', content_length={len(ocr_data) if ocr_data else 0}"
        )
        # Maybe, set infer=False if this spoils the consitancy of the memory/personal interests
        memory.add(
            ocr_data,
            user_id=MEM0_USER_ID,
            metadata={
                "Application name": app_name,
                "Window name": window_name,
                "source": "OCR from screenshot of user screen",
            },
            prompt=MEM0_CUSTOM_INSTRUCTIONS_TO_EXTRACT_OCR,
        )
        app.logger.info(f"Content from OCR of {app_name} added to memory.")
        return jsonify({"success": True, "message": "Content added to memory"}), 200

    except Exception as e:
        app.logger.error(f"Error in /add_page: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


def generate(prompt: str) -> str:
    """Generate a response from the local LLM using a single prompt."""

    url = f"{OLLAMA_URL}/api/generate"
    payload = {
        "model": "llama3.2:3b",
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0, "max_tokens": 20000},
    }
    try:
        response = requests.post(url, json=payload)
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Failed to connect to Ollama at {url}: {e}")
    if response.status_code != 200:
        raise RuntimeError(f"Ollama API error {response.status_code}: {response.text}")
    result_json = response.text.strip()
    data = json.loads(result_json)
    return data.get("response", "")


@app.route("/get_interests", methods=["GET"])
def get_interests():
    try:
        data = memory.get_all(user_id=MEM0_USER_ID)
        memories = [entry["memory"] for entry in data.get("results", [])]
    except Exception as e:
        app.logger.error(f"Error retrieving memories for user': {e}")
        return jsonify({"error": "Failed to retrieve memories"}), 500

    if not memories:
        return jsonify({"summary": "No memories found for user.", "topics": []}), 200

    summary_prompt = (
        "Analyze the following user memories and identify the user's main interests.\n"
        "Provide a concise narrative summary of these interests, then list the top recurring topics or themes, "
        "with each topic's name and how many times it appears.\n\n"
        "Memories:\n"
    )
    for mem in memories:
        summary_prompt += f"- {mem}\n"
    summary_prompt += (
        "\nRespond in JSON format with the following structure:\n"
        '{ "summary": "<narrative_summary>", "topics": [ {"name": "<topic>", "count": <count>, "memories": [<related_memories>] }, ... ] }\n'
    )

    try:
        llm_output = generate(summary_prompt)
        print(llm_output)
    except Exception as e:
        app.logger.error(f"LLM generation failed: {e}")
        return jsonify({"error": "LLM processing error"}), 500

    result = {}
    try:
        result = json.loads(llm_output)
    except Exception as e:
        app.logger.warning(f"Failed to parse LLM output as JSON: {e}")
        result = {"summary": str(llm_output).strip(), "topics": []}

    summary_text = result.get("summary", "")
    topics_info = result.get("topics", [])
    if not summary_text:
        summary_text = "No summary available."
    if topics_info is None or not isinstance(topics_info, list):
        topics_info = []

    clustered_topics = []
    for topic in topics_info:
        name = topic.get("name")
        count = topic.get("count", 0)
        related_mems = []
        if name:
            try:
                search_res = memory.search(query=name, user_id=MEM0_USER_ID)
                for entry in search_res.get("results", []):
                    related_mems.append(entry["memory"])
            except Exception as se:
                app.logger.error(f"Memory search failed for topic '{name}': {se}")
                related_mems = [m for m in memories if name.lower() in m.lower()]
        clustered_topics.append(
            {"name": name or "Unnamed", "count": count, "memories": related_mems}
        )

    response_data = {"summary": summary_text, "topics": clustered_topics}
    return jsonify(response_data), 200


@app.route("/")
def index():
    return send_file("index.html")


@app.route("/memories", methods=["GET"])
def get_memories():
    user_id = request.args.get("user_id", MEM0_USER_ID)
    memories = memory.get_all(user_id=user_id)
    return jsonify(memories)


@app.route("/memories", methods=["POST"])
def add_memory():
    data = request.get_json()
    if not data or "content" not in data:
        return jsonify({"error": "Content is required"}), 400
    content = data["content"]
    user_id = data.get("user_id", MEM0_USER_ID)
    messages = [
        {"role": "user", "content": content},
        {"role": "assistant", "content": "Noted."},
    ]
    result = memory.add(messages, user_id=user_id)
    return jsonify(result), 201


@app.route("/memories/<memory_id>", methods=["PUT"])
def update_memory(memory_id):
    data = request.get_json()
    if not data or "content" not in data:
        return jsonify({"error": "Content is required"}), 400
    new_content = data["content"]
    result = memory.update(memory_id=memory_id, text=new_content)
    if result is None:
        return jsonify({"status": "updated"})
    return jsonify(result)


@app.route("/memories/<memory_id>", methods=["DELETE"])
def delete_memory(memory_id):
    memory.delete(memory_id=memory_id)
    return jsonify({"status": "deleted"})

@app.route("/active_model", methods=["GET"])
def get_active_model():
    return jsonify({"model": active_model_name})

@app.route("/proxy/chat/completions", methods=["POST"], provide_automatic_options=False)
def proxy_chat_completion():
    try:
        proxied_request = request
        memory_augmentation_duration = 0
        memory_start_time = time.perf_counter()
        data = json.loads(request.get_data().decode())
        last_message = data["messages"][-1]

        memories = memory.search(last_message["content"], user_id=MEM0_USER_ID)[
            "results"
        ]

        if len(memories):
            memories_str = "\n".join(f"- {entry['memory']}" for entry in memories)

            last_message["content"] = (
                f"Here are some memories about me that can help answer.\n Memories: {memories_str}. \n {last_message['content']}"
            )

        app.logger.debug(
            f"⌛ Memory augmentation took {time.perf_counter() - memory_start_time:.2f}s"
        )

        proxied_request = Request.from_values(
            data=json.dumps(data).encode(),
            method=request.method,
            headers=dict(request.headers),
        )
        
        response = proxy_request(proxied_request, "chat/completions", True)
        
        def generate():
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    yield chunk

        filtered_headers = {
            name: value
            for name, value in response.headers.items()
            if name.lower() != "transfer-encoding"
        }

        return Response(
            generate(),
            status=response.status_code,
            headers=filtered_headers,
        )

    except Exception as e:
        app.logger.error(f"Error proxying streamed chat completions: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/proxy/<path:subpath>", methods=["POST", "OPTIONS", "GET"])
def proxy(subpath):
    try:

        response = proxy_request(request, subpath)

        filtered_headers = {
            name: value
            for name, value in response.headers.items()
            if name.lower() != "transfer-encoding"
        }

        return response.content, response.status_code, filtered_headers

    except Exception as e:
        app.logger.error(f"Error proxying {request.method} to {subpath}: {e}")
        return jsonify({"error": str(e)}), 500


def proxy_request(request, subpath, stream=False):
    grok_api_key = os.environ.get("GROQ_API_KEY")
    anything_llm_api_key = os.environ.get("ANYTHING_LLM_API_KEY")
    if anything_llm_api_key:
        return proxy_snapdragon_llm(request, subpath, anything_llm_api_key, stream)
    elif grok_api_key:
        return proxy_groq(request, subpath, grok_api_key, stream)

    return proxy_ollama(request, subpath, stream)


def proxy_groq(request, subpath, api_key, stream):
    headers = dict(request.headers)
    del headers["Host"]
    headers["Authorization"] = f"Bearer {api_key}"
    stream_arg = {"stream": True} if stream else {}

    res = requests.request(
        method=request.method,
        url=f"https://api.groq.com/openai/v1/{subpath}",
        headers=headers,
        data=request.get_data(),
        **stream_arg,
    )

    res.headers.pop("Connection", None)

    return res


def proxy_ollama(request, subpath, stream):
    stream_arg = {"stream": True} if stream else {}

    return requests.request(
        method=request.method,
        url=f"{OLLAMA_URL}/v1/{subpath}",
        headers=request.headers,
        data=request.get_data(),
        **stream_arg,
    )


def proxy_snapdragon_llm(request, subpath, anything_llm_api_key, stream):
    headers = dict(request.headers)
    headers["Authorization"] = f"Bearer {anything_llm_api_key}"

    kwargs = (
        {"json": json.loads(request.get_data().decode())}
        if request.method == "POST"
        else {"data": request.get_data()}
    )
    if stream:
        kwargs["stream"] = True

    res = requests.request(
        method=request.method,
        url=f"{ANYTHING_LLM_URL}/api/v1/openai/{subpath}",
        headers=headers,
        **kwargs,
    )

    res.headers.pop("Connection", None)

    if subpath == "models" and request.method == "GET":
        data = res.json()
        data["data"][0]["id"] = data["data"][0]["model"]
        res._content = json.dumps(data).encode()
    return res


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9000)
