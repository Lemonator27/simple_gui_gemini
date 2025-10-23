import os
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
from PIL import Image, ImageTk
from .paths import ensure_all_dirs
from .conversations import conversation_manager
from .api import api_client
from .logger import log_json

# ---- Model list / defaults ----
try:
    from .constants import AVAILABLE_MODELS, DEFAULT_MODEL
except ImportError:
    DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gemini-2.5-flash")
    CHAT_MODELS = [
        {"name": "Gemini 2.5 Pro", "value": "gemini-2.5-pro"},
        {"name": "Gemini 2.5 Flash", "value": "gemini-2.5-flash"},
    ]
    IMAGE_MODELS = [
        {"name": "Imagen 4 (Google Vertex AI)", "value": "imagen-4"},
        {"name": "Gemini 2.5 Flash Image Preview", "value": "gemini-2.5-flash-image-preview"},
    ]
    VIDEO_MODELS = [
        {"name": "Veo 3.0 Generate", "value": "veo-3.0-generate-001"},
    ]
    AVAILABLE_MODELS = CHAT_MODELS + IMAGE_MODELS + VIDEO_MODELS
    if DEFAULT_MODEL not in [m["value"] for m in AVAILABLE_MODELS]:
        AVAILABLE_MODELS.insert(0, {"name": f"Custom default ({DEFAULT_MODEL})", "value": DEFAULT_MODEL})

class ChatGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Thực Chiến AI – Chat GUI")
        self.geometry("1120x740")
        self.minsize(1000, 640)
        ensure_all_dirs()
        self.current_conv = None
        self.current_conv_id = None
        self.uploaded_image_path = None
        self.uploaded_image_data = None
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._create_widgets()
        self.refresh_convs()
        if self.conv_list.size() > 0:
            self.conv_list.selection_set(0)
            self.on_open_conv()
        self.on_api_select()

    def _create_widgets(self):
        self._create_left_panel()
        self._create_right_panel()
        self._create_status_bar()

    def _create_left_panel(self):
        left = ttk.Frame(self, padding=10)
        left.grid(row=0, column=0, sticky="ns")
        ttk.Label(left, text="Conversations", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
        self.conv_list = tk.Listbox(left, height=28, activestyle="dotbox")
        self.conv_list.grid(row=1, column=0, columnspan=2, sticky="nswe")
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)
        btns = ttk.Frame(left)
        btns.grid(row=2, column=0, columnspan=2, sticky="we", pady=8)
        ttk.Button(btns, text="New", command=self.on_new_conv).pack(side="left")
        ttk.Button(btns, text="Refresh", command=self.refresh_convs).pack(side="left", padx=6)
        ttk.Button(btns, text="Open", command=self.on_open_conv).pack(side="left")

    def _create_right_panel(self):
        right = ttk.Frame(self, padding=10)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)
        self._create_top_bar(right)
        self._create_video_params_frame(right)
        self.history = ScrolledText(right, wrap="word", height=22, state="disabled")
        self.history.grid(row=1, column=0, sticky="nsew", pady=(0, 8))
        self._create_input_area(right)

    def _create_top_bar(self, parent):
        topbar = ttk.Frame(parent)
        topbar.grid(row=0, column=0, sticky="we", pady=(0, 6))
        ttk.Label(topbar, text="API:").pack(side="left")
        self.api_var = tk.StringVar(value="Chat Completions (/chat/completions)")
        self.api_combo = ttk.Combobox(topbar, textvariable=self.api_var, state="readonly", values=["Chat Completions (/chat/completions)", "Video Generation"], width=34)
        self.api_combo.pack(side="left", padx=(6, 12))
        self.api_combo.bind("<<ComboboxSelected>>", self.on_api_select)
        ttk.Label(topbar, text="Model:").pack(side="left")
        self.model_combo = ttk.Combobox(topbar, values=[m["value"] for m in AVAILABLE_MODELS], width=30)
        self.model_combo.set(DEFAULT_MODEL)
        self.model_combo.pack(side="left", padx=(6, 12))
        ttk.Label(topbar, text="Temp:").pack(side="left")
        self.temp_var = tk.DoubleVar(value=float(os.getenv("TEMPERATURE", "1.0")))
        self.temp_spin = ttk.Spinbox(topbar, from_=0.0, to=2.0, increment=0.1, textvariable=self.temp_var, width=5)
        self.temp_spin.pack(side="left", padx=(6, 12))
        self.ws_enabled = tk.BooleanVar(value=False)
        self.ws_check = ttk.Checkbutton(topbar, text="Use Web Search", variable=self.ws_enabled)
        self.ws_check.pack(side="left", padx=(12, 6))
        api_base = os.getenv("THUCCHIEN_API_BASE", "https://api.thucchien.ai")
        ttk.Label(topbar, text=f"@ {api_base}", foreground="#666").pack(side="right")

    def _create_video_params_frame(self, parent):
        self.video_params_frame = ttk.Frame(parent, padding=10)
        self.video_params_frame.grid_columnconfigure(1, weight=1)
        # Video Prompt
        ttk.Label(self.video_params_frame, text="Video Prompt:").grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.video_prompt_input = ScrolledText(self.video_params_frame, wrap="word", height=3)
        self.video_prompt_input.grid(row=0, column=1, sticky="we", padx=(6, 0), pady=(0, 6))
        # Video Model
        ttk.Label(self.video_params_frame, text="Video Model:").grid(row=1, column=0, sticky="w", pady=(0, 6))
        self.video_model_combo = ttk.Combobox(self.video_params_frame, values=[m["value"] for m in VIDEO_MODELS], width=30, state="readonly")
        self.video_model_combo.set(VIDEO_MODELS[0]["value"])
        self.video_model_combo.grid(row=1, column=1, sticky="w", padx=(6, 0), pady=(0, 6))
        # Aspect Ratio
        ttk.Label(self.video_params_frame, text="Aspect Ratio:").grid(row=2, column=0, sticky="w", pady=(0, 6))
        self.video_ratio_var = tk.StringVar(value="16:9")
        self.video_ratio_combo = ttk.Combobox(self.video_params_frame, textvariable=self.video_ratio_var, values=["16:9", "1:1", "9:16"], width=10, state="readonly")
        self.video_ratio_combo.grid(row=2, column=1, sticky="w", padx=(6, 0), pady=(0, 6))
        # Duration
        ttk.Label(self.video_params_frame, text="Duration (s):").grid(row=3, column=0, sticky="w", pady=(0, 6))
        self.video_duration_var = tk.IntVar(value=8)
        self.video_duration_spin = ttk.Spinbox(self.video_params_frame, from_=2, to=10, increment=1, textvariable=self.video_duration_var, width=5)
        self.video_duration_spin.grid(row=3, column=1, sticky="w", padx=(6, 0), pady=(0, 6))
        # Negative Prompt
        ttk.Label(self.video_params_frame, text="Negative Prompt:").grid(row=4, column=0, sticky="w", pady=(0, 6))
        self.video_negative_prompt_input = ScrolledText(self.video_params_frame, wrap="word", height=2)
        self.video_negative_prompt_input.grid(row=4, column=1, sticky="we", padx=(6, 0), pady=(0, 6))
        # Image Frames
        self.first_frame_image_data, self.last_frame_image_data, self.reference_images_data = None, None, []
        self.first_frame_image_status = tk.StringVar()
        self.last_frame_image_status = tk.StringVar()
        self.reference_images_status = tk.StringVar()
        self._create_image_upload_button(5, "Upload First Frame", self.on_upload_first_frame_image, self.first_frame_image_status)
        self._create_image_upload_button(6, "Upload Last Frame", self.on_upload_last_frame_image, self.last_frame_image_status)
        self._create_image_upload_button(7, "Upload Reference Images (max 3)", self.on_upload_reference_images, self.reference_images_status)

    def _create_image_upload_button(self, row, text, command, status_var):
        frame = ttk.Frame(self.video_params_frame)
        frame.grid(row=row, column=0, columnspan=2, sticky="we", pady=(6, 0))
        ttk.Button(frame, text=text, command=command).pack(side="left")
        ttk.Label(frame, textvariable=status_var).pack(side="left", padx=(8, 0))

    def _create_input_area(self, parent):
        bottom = ttk.Frame(parent)
        bottom.grid(row=2, column=0, sticky="we")
        bottom.grid_columnconfigure(0, weight=1)
        self.input_box = ScrolledText(bottom, wrap="word", height=5)
        self.input_box.grid(row=0, column=0, sticky="we")
        self.input_box.bind("<Control-Return>", self.on_send_event)
        actions = ttk.Frame(bottom)
        actions.grid(row=0, column=1, sticky="ns", padx=(8, 0))
        self.send_btn = ttk.Button(actions, text="Send (Ctrl+Enter)", command=self.on_send)
        self.send_btn.grid(row=0, column=0, sticky="we")
        img_buttons = ttk.Frame(actions)
        img_buttons.grid(row=1, column=0, sticky="we", pady=(8, 0))
        ttk.Button(img_buttons, text="Upload Image", command=self.on_upload_image).pack(side="left", padx=(0, 4))
        ttk.Button(img_buttons, text="Generate Image", command=self.open_image_generator).pack(side="left")
        self.image_status = tk.StringVar()
        ttk.Label(img_buttons, textvariable=self.image_status).pack(side="left", padx=(8, 0))

    def _create_status_bar(self):
        self.status = tk.StringVar(value="Ready.")
        statusbar = ttk.Label(self, textvariable=self.status, anchor="w", relief="sunken")
        statusbar.grid(row=1, column=0, columnspan=2, sticky="we")

    def on_api_select(self, _event=None):
        is_video = self.api_var.get() == "Video Generation"
        if is_video:
            self.video_params_frame.grid(row=0, column=0, sticky="we", pady=(0, 6))
            self.ws_check.pack_forget()
            self.temp_spin.pack_forget()
            self.model_combo.config(values=[m["value"] for m in VIDEO_MODELS])
            self.model_combo.set(VIDEO_MODELS[0]["value"])
        else:
            self.video_params_frame.grid_forget()
            self.ws_check.pack(side="left", padx=(12, 6))
            self.temp_spin.pack(side="left", padx=(6, 12))
            self.model_combo.config(values=[m["value"] for m in CHAT_MODELS + IMAGE_MODELS])
            self.model_combo.set(DEFAULT_MODEL)

    def refresh_convs(self):
        self.conv_list.delete(0, tk.END)
        for c in conversation_manager.list_conversations():
            self.conv_list.insert(tk.END, f"{c['name']} — {c.get('updatedAt', c['createdAt'])}")
        self.status.set(f"Loaded {self.conv_list.size()} conversation(s).")

    def on_new_conv(self):
        conv = conversation_manager.create_conversation()
        self.status.set(f"Created: {conv['name']}")
        self.refresh_convs()
        if self.conv_list.size() > 0:
            self.conv_list.selection_clear(0, tk.END)
            self.conv_list.selection_set(0)
            self.on_open_conv()

    def on_open_conv(self):
        if not self.conv_list.curselection():
            self.status.set("Select a conversation first.")
            return
        idx = self.conv_list.curselection()[0]
        conv_id = conversation_manager.list_conversations()[idx]["id"]
        self.current_conv = conversation_manager.load_conversation(conv_id)
        self.current_conv_id = conv_id
        self.render_history()
        self.status.set(f"Opened: {self.current_conv['name']}")

    def render_history(self):
        self.history.config(state="normal")
        self.history.delete("1.0", tk.END)
        if self.current_conv:
            for m in self.current_conv.get("messages", []):
                prefix = {"user": "You", "assistant": "Assistant"}.get(m["role"], m["role"])
                self.history.insert(tk.END, f"{prefix}:\n")
                if m.get("type") == "image" and "image_path" in m:
                    self._display_image_in_chat(m["image_path"], m["content"], m.get("filename", "image.png"))
                else:
                    self.history.insert(tk.END, f"{m['content']}\n\n")
        self.history.config(state="disabled")
        self.history.see(tk.END)

    def _display_image_in_chat(self, image_path, content, filename):
        try:
            self.history.insert(tk.END, f"{content}\n")
            img = Image.open(image_path)
            img.thumbnail((400, 300), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            label = tk.Label(self.history, image=photo, bd=2, relief="solid")
            label.image = photo
            self.history.window_create(tk.END, window=label)
            self.history.insert(tk.END, f"\n[Image: {filename}]\n\n")
        except Exception as e:
            self.history.insert(tk.END, f"{content}\n[📷 {filename} - Could not display: {e}]\n\n")

    def on_send_event(self, _evt):
        self.on_send()
        return "break"

    def on_send(self):
        if not self.current_conv:
            self.status.set("Create or open a conversation first.")
            return
        text = self.input_box.get("1.0", tk.END).strip()
        if not text and not self.uploaded_image_data:
            return
        self.input_box.delete("1.0", tk.END)
        if self.uploaded_image_data:
            filename = os.path.basename(self.uploaded_image_path) if self.uploaded_image_path else "uploaded.png"
            conversation_manager.append_image_message(self.current_conv, "user", text or "Uploaded image", self.uploaded_image_data, filename)
            self.uploaded_image_data = self.uploaded_image_path = None
            self.image_status.set("")
        else:
            conversation_manager.append_message(self.current_conv, "user", text)
        self.render_history()
        self.send_btn.config(state="disabled")
        if self.api_var.get() == "Video Generation":
            self.status.set("Generating video...")
            threading.Thread(target=self._call_video_api_threadsafe, daemon=True).start()
        else:
            self.status.set("Calling API...")
            threading.Thread(target=self._call_chat_api_threadsafe, daemon=True).start()

    def _call_chat_api_threadsafe(self):
        try:
            messages = [{"role": m["role"], "content": m["content"]} for m in self.current_conv["messages"]]
            result = api_client.chat_completions(
                messages=messages,
                model=self.model_combo.get() or DEFAULT_MODEL,
                temperature=self.temp_var.get(),
                use_web_search=self.ws_enabled.get(),
            )
            reply = result.get("content", "(empty response)")
            conversation_manager.append_message(self.current_conv, "assistant", reply)
            self._on_api_done(True, "API call successful.")
        except Exception as e:
            self._on_api_done(False, f"Error: {e}")

    def _call_video_api_threadsafe(self):
        try:
            prompt = self.video_prompt_input.get("1.0", tk.END).strip()
            if not any([prompt, self.first_frame_image_data, self.last_frame_image_data, self.reference_images_data]):
                self._on_api_done(False, "Error: Provide a prompt or at least one image.")
                return
            is_image_mode = any([self.first_frame_image_data, self.last_frame_image_data, self.reference_images_data])
            result = api_client.generate_video(
                prompt=prompt,
                model=self.video_model_combo.get(),
                aspect_ratio=self.video_ratio_var.get(),
                duration=self.video_duration_var.get(),
                negative_prompt=self.video_negative_prompt_input.get("1.0", tk.END).strip(),
                person_generation="allow_adult" if is_image_mode else "allow_all",
                reference_images=self.reference_images_data or None,
                first_frame_image_data=self.first_frame_image_data,
                last_frame_image_data=self.last_frame_image_data,
            )
            self._reset_video_inputs()
            if result.get("success"):
                filename = f"generated_video_{int(time.time())}.mp4"
                video_path = self._save_video(result["video_data"], filename)
                conversation_manager.append_message(self.current_conv, "assistant", f"Generated video saved to: {video_path}")
                self._on_api_done(True, f"Video generated: {filename}")
            else:
                self._on_api_done(False, f"Video generation failed: {result.get('error')}")
        except Exception as e:
            self._on_api_done(False, f"Error: {e}")

    def _reset_video_inputs(self):
        self.first_frame_image_data = self.last_frame_image_data = None
        self.reference_images_data.clear()
        self.first_frame_image_status.set("")
        self.last_frame_image_status.set("")
        self.reference_images_status.set("")
        self.video_negative_prompt_input.delete("1.0", tk.END)

    def _save_video(self, video_data, filename):
        path = os.path.join("generated_videos", filename)
        os.makedirs("generated_videos", exist_ok=True)
        with open(path, "wb") as f:
            f.write(video_data)
        return path

    def _on_api_done(self, success, msg):
        self.after(0, self._finalize_ui_update, success, msg)

    def _finalize_ui_update(self, success, msg):
        if self.current_conv_id:
            self.current_conv = conversation_manager.load_conversation(self.current_conv_id)
        self.render_history()
        self.send_btn.config(state="normal")
        self.status.set(msg)

    def on_upload_image(self):
        path = filedialog.askopenfilename(title="Select an image", filetypes=[("Image files", "*.png *.jpg *.jpeg"), ("All files", "*.*")])
        if path:
            try:
                with open(path, "rb") as f:
                    self.uploaded_image_data = f.read()
                self.uploaded_image_path = path
                self.image_status.set(f"Loaded: {os.path.basename(path)}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load image: {e}")

    def on_upload_first_frame_image(self):
        self.first_frame_image_data = self._upload_single_image("Select first frame", self.first_frame_image_status)

    def on_upload_last_frame_image(self):
        self.last_frame_image_data = self._upload_single_image("Select last frame", self.last_frame_image_status)

    def _upload_single_image(self, title, status_var):
        path = filedialog.askopenfilename(title=title, filetypes=[("Image files", "*.png *.jpg *.jpeg"), ("All files", "*.*")])
        if path:
            try:
                with open(path, "rb") as f:
                    status_var.set(f"Loaded: {os.path.basename(path)}")
                    return f.read()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load image: {e}")
        return None

    def on_upload_reference_images(self):
        paths = filedialog.askopenfilenames(title="Select up to 3 reference images", filetypes=[("Image files", "*.png *.jpg *.jpeg"), ("All files", "*.*")])
        if paths:
            try:
                self.reference_images_data.clear()
                for p in paths[:3]:
                    with open(p, "rb") as f:
                        self.reference_images_data.append(f.read())
                self.reference_images_status.set(f"{len(self.reference_images_data)} image(s) loaded")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load images: {e}")

    def open_image_generator(self):
        if not hasattr(self, "image_generator_window") or not self.image_generator_window.winfo_exists():
            self.image_generator_window = ImageGeneratorWindow(self)
        self.image_generator_window.lift()
        self.image_generator_window.focus()

class ImageGeneratorWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("Thực Chiến AI – Image Generator")
        self.geometry("1120x740")
        self.minsize(1000, 640)
        self.transient(parent)
        self.grab_set()
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (self.winfo_width() // 2)
        y = (self.winfo_screenheight() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")
        self.current_conv = parent.current_conv
        self.current_conv_id = parent.current_conv_id
        self.uploaded_image_path = None
        self.uploaded_image_data = None
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._create_widgets()
        self.refresh_convs()
        if self.conv_list.size() > 0 and self.current_conv_id:
            for i in range(self.conv_list.size()):
                if self.current_conv_id in self.conv_list.get(i):
                    self.conv_list.selection_set(i)
                    break
            self.render_history()
        self.current_image_data = None
        self.current_image_filename = None
        self.bind("<Escape>", lambda e: self.on_close())
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _create_widgets(self):
        self._create_left_panel()
        self._create_right_panel()
        self._create_status_bar()

    def _create_left_panel(self):
        left = ttk.Frame(self, padding=10)
        left.grid(row=0, column=0, sticky="ns")
        ttk.Label(left, text="Conversations", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
        self.conv_list = tk.Listbox(left, height=28, activestyle="dotbox")
        self.conv_list.grid(row=1, column=0, columnspan=2, sticky="nswe")
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)
        btns = ttk.Frame(left)
        btns.grid(row=2, column=0, columnspan=2, sticky="we", pady=8)
        ttk.Button(btns, text="New", command=self.on_new_conv).pack(side="left")
        ttk.Button(btns, text="Refresh", command=self.refresh_convs).pack(side="left", padx=6)
        ttk.Button(btns, text="Open", command=self.on_open_conv).pack(side="left")

    def _create_right_panel(self):
        right = ttk.Frame(self, padding=10)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)
        self._create_top_bar(right)
        self.history = ScrolledText(right, wrap="word", height=22, state="disabled")
        self.history.grid(row=1, column=0, sticky="nsew", pady=(0, 8))
        self._create_input_area(right)

    def _create_top_bar(self, parent):
        topbar = ttk.Frame(parent)
        topbar.grid(row=0, column=0, sticky="we", pady=(0, 6))
        ttk.Label(topbar, text="API:").pack(side="left")
        self.api_var = tk.StringVar(value="Image Generation")
        self.api_combo = ttk.Combobox(topbar, textvariable=self.api_var, state="readonly", values=["Image Generation"], width=34)
        self.api_combo.pack(side="left", padx=(6, 12))
        ttk.Label(topbar, text="Model:").pack(side="left")
        self.model_combo = ttk.Combobox(topbar, values=[m["value"] for m in IMAGE_MODELS], width=30)
        self.model_combo.set("imagen-4")
        self.model_combo.pack(side="left", padx=(6, 12))
        ttk.Label(topbar, text="Aspect Ratio:").pack(side="left")
        self.ratio_var = tk.StringVar(value="1:1")
        self.ratio_combo = ttk.Combobox(topbar, textvariable=self.ratio_var, width=10, values=["1:1", "16:9", "9:16", "4:3", "3:4"])
        self.ratio_combo.pack(side="left", padx=(6, 12))
        api_base = os.getenv("THUCCHIEN_API_BASE", "https://api.thucchien.ai")
        ttk.Label(topbar, text=f"@ {api_base}", foreground="#666").pack(side="right")

    def _create_input_area(self, parent):
        bottom = ttk.Frame(parent)
        bottom.grid(row=2, column=0, sticky="we")
        bottom.grid_columnconfigure(0, weight=1)
        self.input_box = ScrolledText(bottom, wrap="word", height=5)
        self.input_box.grid(row=0, column=0, sticky="we")
        self.input_box.bind("<Control-Return>", self.on_send_event)
        actions = ttk.Frame(bottom)
        actions.grid(row=0, column=1, sticky="ns", padx=(8, 0))
        self.send_btn = ttk.Button(actions, text="Generate (Ctrl+Enter)", command=self.on_send)
        self.send_btn.grid(row=0, column=0, sticky="we")
        img_buttons = ttk.Frame(actions)
        img_buttons.grid(row=1, column=0, sticky="we", pady=(8, 0))
        ttk.Button(img_buttons, text="Upload Image", command=self.on_upload_image).pack(side="left", padx=(0, 4))
        self.image_status = tk.StringVar()
        ttk.Label(img_buttons, textvariable=self.image_status).pack(side="left", padx=(8, 0))

    def _create_status_bar(self):
        self.status = tk.StringVar(value="Ready to generate images.")
        statusbar = ttk.Label(self, textvariable=self.status, anchor="w", relief="sunken")
        statusbar.grid(row=1, column=0, columnspan=2, sticky="we")

    def refresh_convs(self):
        self.conv_list.delete(0, tk.END)
        for c in conversation_manager.list_conversations():
            self.conv_list.insert(tk.END, f"{c['name']} — {c.get('updatedAt', c['createdAt'])}")
        self.status.set(f"Loaded {self.conv_list.size()} conversation(s).")

    def on_new_conv(self):
        conv = conversation_manager.create_conversation()
        self.status.set(f"Created: {conv['name']}")
        self.refresh_convs()
        if self.conv_list.size() > 0:
            self.conv_list.selection_clear(0, tk.END)
            self.conv_list.selection_set(0)
            self.on_open_conv()

    def on_open_conv(self):
        if not self.conv_list.curselection():
            self.status.set("Select a conversation first.")
            return
        idx = self.conv_list.curselection()[0]
        conv_id = conversation_manager.list_conversations()[idx]["id"]
        self.current_conv = conversation_manager.load_conversation(conv_id)
        self.current_conv_id = conv_id
        self.render_history()
        self.status.set(f"Opened: {self.current_conv['name']}")
        self.parent.current_conv = self.current_conv
        self.parent.current_conv_id = self.current_conv_id
        self.parent.render_history()

    def render_history(self):
        self.history.config(state="normal")
        self.history.delete("1.0", tk.END)
        if self.current_conv:
            for m in self.current_conv.get("messages", []):
                prefix = {"user": "You", "assistant": "Assistant"}.get(m["role"], m["role"])
                self.history.insert(tk.END, f"{prefix}:\n")
                if m.get("type") == "image" and "image_path" in m:
                    self._display_image_in_chat(m["image_path"], m["content"], m.get("filename", "image.png"))
                else:
                    self.history.insert(tk.END, f"{m['content']}\n\n")
        self.history.config(state="disabled")
        self.history.see(tk.END)

    def _display_image_in_chat(self, image_path, content, filename):
        try:
            self.history.insert(tk.END, f"{content}\n")
            img = Image.open(image_path)
            img.thumbnail((400, 300), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            label = tk.Label(self.history, image=photo, bd=2, relief="solid")
            label.image = photo
            self.history.window_create(tk.END, window=label)
            self.history.insert(tk.END, f"\n[Image: {filename}]\n\n")
        except Exception as e:
            self.history.insert(tk.END, f"{content}\n[📷 {filename} - Could not display: {e}]\n\n")

    def on_send_event(self, _evt):
        self.on_send()
        return "break"

    def on_send(self):
        if not self.current_conv:
            self.status.set("Create or open a conversation first.")
            return
        text = self.input_box.get("1.0", tk.END).strip()
        if not text and not self.uploaded_image_data:
            return
        self.input_box.delete("1.0", tk.END)
        if self.uploaded_image_data:
            filename = os.path.basename(self.uploaded_image_path) if self.uploaded_image_path else "uploaded.png"
            conversation_manager.append_image_message(self.current_conv, "user", text or "Uploaded image", self.uploaded_image_data, filename)
            self.uploaded_image_data = self.uploaded_image_path = None
            self.image_status.set("")
        else:
            conversation_manager.append_message(self.current_conv, "user", text)
        self.render_history()
        self.send_btn.config(state="disabled")
        self.status.set("Generating image...")
        threading.Thread(target=self._generate_image_threadsafe, daemon=True).start()

    def _generate_image_threadsafe(self):
        try:
            prompt = ""
            image_context = []
            if self.uploaded_image_data:
                image_context.append(self.uploaded_image_data)
            for m in reversed(self.current_conv["messages"]):
                if m.get("type") == "image" and "image_path" in m:
                    try:
                        with open(m["image_path"], "rb") as img_file:
                            img_data = img_file.read()
                            image_context.append(img_data)
                    except Exception:
                        pass
                elif m["role"] == "user" and not prompt:
                    prompt = m["content"]
            if not prompt:
                prompt = "Generate an image based on the uploaded context"

            result = api_client.generate_image(
                prompt=prompt,
                model=self.model_combo.get(),
                aspect_ratio=self.ratio_var.get(),
                image_context=image_context if image_context else None,
            )
            if result.get("success"):
                filename = f"generated_{int(time.time())}.png"
                saved_path = api_client.save_image(result["image_data"], filename)
                conversation_manager.append_image_message(
                    self.current_conv, "assistant", f"Generated image: '{prompt}'", result["image_data"], filename
                )
                self._on_image_done(True, f"Image generated and saved: {filename}", saved_path)
                self.parent.current_conv = conversation_manager.load_conversation(self.current_conv_id)
                self.parent.render_history()
            else:
                self._on_image_done(False, f"Image generation failed: {result.get('error')}", None)
        except Exception as e:
            self._on_image_done(False, f"Error generating image: {e}", None)

    def _on_image_done(self, success, msg, image_path=None):
        self.after(0, self._finalize_ui_update, success, msg, image_path)

    def _finalize_ui_update(self, success, msg, image_path=None):
        if self.current_conv_id:
            self.current_conv = conversation_manager.load_conversation(self.current_conv_id)
        self.render_history()
        self.send_btn.config(state="normal")
        self.status.set(msg)

    def on_upload_image(self):
        path = filedialog.askopenfilename(title="Select an image", filetypes=[("Image files", "*.png *.jpg *.jpeg"), ("All files", "*.*")])
        if path:
            try:
                with open(path, "rb") as f:
                    self.uploaded_image_data = f.read()
                self.uploaded_image_path = path
                self.image_status.set(f"Loaded: {os.path.basename(path)}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load image: {e}")

    def on_close(self):
        self.grab_release()
        self.parent.image_generator_window = None
        self.destroy()

def launch():
    app = ChatGUI()
    app.mainloop()
