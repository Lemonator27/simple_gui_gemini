import os
from InquirerPy import inquirer
from InquirerPy.separator import Separator
from src.conversations import conversation_manager
from src.api import api_client
from src.logger import log_json
from src.gui import launch
from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gpt-4o-mini")

AVAILABLE_MODELS = [
    {"name": "Gemini 2.5 Pro", "value": "gemini-2.5-pro"},
    {"name": "Gemini 2.5 Flash", "value": "gemini-2.5-flash"},
    {"name": "Veo 3", "value": "veo 3"},
    {"name": "Imagen 4 (Google Vertex AI)", "value": "imagen-4"},
    {"name": "Gemini 2.5 Flash Image Preview", "value": "gemini-2.5-flash-image-preview"},
    {"name": "Gemini 2.5 Flash Preview TTS", "value": "gemini-2.5-flash-preview-tts"},
    {"name": "Gemini 2.5 Pro Preview TTS", "value": "gemini-2.5-pro-preview-tts"},
]

def pick_model():
    return inquirer.select(
        message="Choose AI model:",
        choices=[(m["name"], m["value"]) for m in AVAILABLE_MODELS],
        default=DEFAULT_MODEL,
    ).execute()

def chat_loop(conv: dict, selected_model: str):
    print(f"\n💬 Using: {conv['name']} (id: {conv['id']}) with model: {selected_model}")
    print("Type /exit to return to menu.\n")
    while True:
        prompt = inquirer.text(message="You:").execute()
        if not prompt or prompt.strip() == "/exit":
            break
        conversation_manager.append_message(conv, "user", prompt)
        try:
            start = __import__("time").time()
            messages = [{"role": m["role"], "content": m["content"]} for m in conv["messages"]]
            result = api_client.chat_completions(messages, model=selected_model)
            content = result["content"]
            conversation_manager.append_message(conv, "assistant", content)
            log_path = log_json({
                "type": "chat.completions",
                "conversationId": conv["id"],
                "request": {"messages": messages[:-1]},
                "response": result["raw"],
                "latency_ms": int((__import__("time").time() - start) * 1000),
            })
            print(f"\n🤖 Assistant:\n{content}\n")
            print(f"🗒  Log: {log_path}\n")
        except Exception as e:
            log_path = log_json({
                "type": "chat.completions.error",
                "conversationId": conv["id"],
                "error": {"message": str(e)},
            })
            print(f"❌ Error calling API. Details logged at: {log_path}\n")

def main():
    launch()

if __name__ == "__main__":
    main()
