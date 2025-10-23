import json
import time
import uuid
from pathlib import Path
from .paths import CONV_DIR, CONV_INDEX, ensure_all_dirs

ensure_all_dirs()

class ConversationManager:
    def __init__(self):
        self.conv_dir = CONV_DIR
        self.conv_index = CONV_INDEX

    def _read_index(self):
        try:
            return json.loads(self.conv_index.read_text(encoding="utf-8"))
        except Exception:
            return {"conversations": []}

    def _write_index(self, idx):
        self.conv_index.write_text(json.dumps(idx, indent=2, ensure_ascii=False), encoding="utf-8")

    def list_conversations(self):
        idx = self._read_index()
        idx["conversations"].sort(key=lambda c: c.get("updatedAt", 0), reverse=True)
        return idx["conversations"]

    def create_conversation(self, name: str | None = None):
        ts = int(time.time() * 1000)
        conv_id = str(uuid.uuid4())
        conv = {
            "id": conv_id,
            "name": name or f"Conversation {time.strftime('%Y-%m-%d %H:%M:%S')}",
            "createdAt": ts,
            "updatedAt": ts,
            "messages": []
        }
        (self.conv_dir / f"{conv_id}.json").write_text(json.dumps(conv, indent=2, ensure_ascii=False), encoding="utf-8")
        idx = self._read_index()
        idx["conversations"].append({"id": conv_id, "name": conv["name"], "createdAt": ts, "updatedAt": ts})
        self._write_index(idx)
        return conv

    def load_conversation(self, conv_id: str):
        p = self.conv_dir / f"{conv_id}.json"
        return json.loads(p.read_text(encoding="utf-8"))

    def save_conversation(self, conv: dict):
        conv["updatedAt"] = int(time.time() * 1000)
        (self.conv_dir / f"{conv['id']}.json").write_text(json.dumps(conv, indent=2, ensure_ascii=False), encoding="utf-8")
        idx = self._read_index()
        for it in idx["conversations"]:
            if it["id"] == conv["id"]:
                it["name"] = conv["name"]
                it["updatedAt"] = conv["updatedAt"]
                break
        self._write_index(idx)

    def append_message(self, conv: dict, role: str, content: str, message_type: str = "text"):
        message = {
            "role": role,
            "content": content,
            "at": int(time.time() * 1000),
            "type": message_type
        }
        conv["messages"].append(message)
        self.save_conversation(conv)

    def append_image_message(self, conv: dict, role: str, content: str, image_data: bytes, filename: str = None):
        conv_images_dir = self.conv_dir / conv["id"] / "images"
        conv_images_dir.mkdir(parents=True, exist_ok=True)
        if not filename:
            timestamp = int(time.time())
            filename = f"image_{timestamp}.png"
        image_path = conv_images_dir / filename
        with open(image_path, "wb") as f:
            f.write(image_data)
        message = {
            "role": role,
            "content": content,
            "at": int(time.time() * 1000),
            "type": "image",
            "image_path": str(image_path.relative_to(self.conv_dir.parent.parent)),
            "filename": filename
        }
        conv["messages"].append(message)
        self.save_conversation(conv)
        return str(image_path)

conversation_manager = ConversationManager()

def list_conversations():
    return conversation_manager.list_conversations()

def create_conversation(name: str | None = None):
    return conversation_manager.create_conversation(name)

def load_conversation(conv_id: str):
    return conversation_manager.load_conversation(conv_id)

def save_conversation(conv: dict):
    conversation_manager.save_conversation(conv)

def append_message(conv: dict, role: str, content: str, message_type: str = "text"):
    conversation_manager.append_message(conv, role, content, message_type)

def append_image_message(conv: dict, role: str, content: str, image_data: bytes, filename: str = None):
    return conversation_manager.append_image_message(conv, role, content, image_data, filename)
