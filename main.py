#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MetaClean - Remoção de Metadados (Imagem/Vídeo) para Windows
- UI Tkinter centralizada (50% da tela), sem redimensionamento.
- Seleção de arquivo com validação (imagem/vídeo).
- Remoção de metadados: Pillow (imagens) e FFmpeg (vídeos).
- Renomeia o arquivo limpo com HASH6_nomeoriginal.ext (sanitizado).
- Salva em pasta "cleaned/" ao lado do executável/script.
- Busca por ffmpeg.exe local (./ffmpeg/ffmpeg.exe ou ./ffmpeg.exe) antes do PATH.
"""
import os
import re
import sys
import secrets
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import filetype

# ---------------------- Config ----------------------
APP_NAME = "MetaClean - Remoção de Metadados"
OUTPUT_DIR = "cleaned"
LOGO_FILE = "logo.png"  # coloque seu logo aqui (na mesma pasta do executável)

VALID_IMAGE_MIME_PREFIX = "image/"
VALID_VIDEO_MIME_PREFIX = "video/"

# ---------------------- Helpers ----------------------
def ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

def hash6():
    # 6 dígitos hex aleatórios (ex.: a3f91b)
    return secrets.token_hex(3)

def sanitize_filename(name: str) -> str:
    """
    - trim()
    - troca espaços por underscore
    - remove caracteres especiais perigosos (mantém letras, números, ., _, -)
    """
    name = name.strip()
    base, ext = os.path.splitext(name)
    base = re.sub(r"\s+", "_", base)
    base = re.sub(r"[^A-Za-z0-9._-]", "", base)
    base = base.strip("._-")
    if not base:
        base = "arquivo"
    return f"{base}{ext}"

def get_base_dir():
    # Quando empacotado com PyInstaller --onefile, os assets ficam em _MEIPASS
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    # Execução normal (dev)
    return os.path.dirname(os.path.abspath(sys.argv[0]))

def get_ffmpeg_cmd():
    """
    Retorna o caminho do ffmpeg empacotado (se existir) ou 'ffmpeg' (PATH).
    Procura em:
      - ./ffmpeg.exe
      - ./ffmpeg/ffmpeg.exe
      - PATH
    """
    base = get_base_dir()
    local_ffmpeg_root = os.path.join(base, 'ffmpeg.exe')
    if os.path.exists(local_ffmpeg_root):
        return local_ffmpeg_root

    local_ffmpeg_folder = os.path.join(base, 'ffmpeg', 'ffmpeg.exe')
    if os.path.exists(local_ffmpeg_folder):
        return local_ffmpeg_folder

    return 'ffmpeg'  # tenta pelo PATH

def ffmpeg_available() -> bool:
    try:
        proc = _run_hidden([get_ffmpeg_cmd(), "-version"])
        # Se o binário existe, retorna 0 ou >0 mas sem erro de "file not found"
        return proc is not None and ("ffmpeg version" in (proc.stdout or "") or "ffmpeg version" in (proc.stderr or ""))
    except Exception:
        return False

def is_media_supported(filepath: str):
    """
    Usa filetype para detectar o mimetype.
    Retorna ('image'|'video'|None, ext_sugerida_ou_existente)
    """
    kind = None
    try:
        kind = filetype.guess(filepath)
    except Exception:
        kind = None

    if kind is None or not getattr(kind, "mime", None):
        ext = os.path.splitext(filepath)[1].lower()
        if ext in [".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"]:
            return "image", ext
        if ext in [".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm"]:
            return "video", ext
        return None, None

    mime = kind.mime.lower()
    ext = os.path.splitext(filepath)[1].lower()
    if mime.startswith(VALID_IMAGE_MIME_PREFIX):
        return "image", ext
    if mime.startswith(VALID_VIDEO_MIME_PREFIX):
        return "video", ext
    return None, None

def clean_image(input_path: str, output_path: str):
    """
    Remove metadados salvando a imagem novamente sem EXIF.
    Para JPEG/PNG/WEBP, regrava o conteúdo sem informações extras.
    """
    with Image.open(input_path) as im:
        if im.mode in ("P", "RGBA"):
            im = im.convert("RGB")
        im.save(output_path)

def clean_video(input_path: str, output_path: str):
    cmd = [
        get_ffmpeg_cmd(),
        "-y",
        "-nostdin",        # evita esperar teclado
        "-hide_banner",    # esconde banner
        "-loglevel", "error",  # só erros
        "-i", input_path,
        "-map_metadata", "-1",
        "-map_chapters", "-1",  # (extra) remove chapters também
        "-c", "copy",
        output_path
    ]
    proc = _run_hidden(cmd)
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg falhou:\n{proc.stderr}")

def _run_hidden(cmd: list[str]):
    """
    Executa um subprocesso sem abrir janela no Windows.
    Em outros SOs, apenas executa normalmente.
    """
    kwargs = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "shell": False,
    }

    if os.name == "nt":
        # Esconde a janela de console do processo filho
        CREATE_NO_WINDOW = 0x08000000
        kwargs["creationflags"] = CREATE_NO_WINDOW

        # startupinfo extra por garantia
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        kwargs["startupinfo"] = si

    return subprocess.run(cmd, **kwargs)

# ---------------------- UI ----------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.configure(bg="#111111")
        self.resizable(False, False)
        self.selected_file = None
        self.media_kind = None
        self.logo_image = None

        # Centraliza janela em 50% da tela
        self.center_half_screen()

        # Layout
        self.build_ui()

    def center_half_screen(self):
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        width = max(640, sw // 2)
        height = max(420, sh // 2)
        x = (sw - width) // 2
        y = (sh - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")

    def build_ui(self):
        # Logo
        logo_frame = tk.Frame(self, bg="#111111")
        logo_frame.pack(pady=16)

        logo_path = os.path.join(get_base_dir(), LOGO_FILE)
        try:
            img = Image.open(logo_path)
            max_w, max_h = 480, 200
            w, h = img.size
            scale = min(max_w / w, max_h / h, 1.0)
            img = img.resize((int(w*scale), int(h*scale)))
            self.logo_image = ImageTk.PhotoImage(img)
            logo_label = tk.Label(logo_frame, image=self.logo_image, bg="#111111")
        except Exception:
            logo_label = tk.Label(logo_frame, text="MetaClean", fg="#FFA500", bg="#111111", font=("Segoe UI", 32, "bold"))
        logo_label.pack()

        # Subtitle
        subtitle = tk.Label(self, text="Remoção de Metadados", fg="#FFA500", bg="#111111", font=("Segoe UI", 12, "bold"))
        subtitle.pack(pady=(0, 10))

        # Arquivo selector
        picker_frame = tk.Frame(self, bg="#111111")
        picker_frame.pack(pady=8)

        self.file_entry_var = tk.StringVar(value="Selecione um arquivo de mídia")
        self.file_entry = tk.Entry(picker_frame, textvariable=self.file_entry_var, width=48, state="readonly",
                                   readonlybackground="#222222", fg="#FFFFFF", relief="flat", justify="center")
        self.file_entry.grid(row=0, column=0, padx=(8, 8), ipady=6)

        self.pick_btn = tk.Button(picker_frame, text="Procurar arquivo", command=self.on_pick_file, bg="#444444", fg="#FFFFFF",
                                  activebackground="#555555", relief="raised", cursor="hand2")
        self.pick_btn.grid(row=0, column=1, padx=(0, 8), ipadx=10, ipady=4)

        # Status
        self.status_var = tk.StringVar(value="")
        self.status_lbl = tk.Label(self, textvariable=self.status_var, fg="#AAAAAA", bg="#111111", font=("Segoe UI", 10))
        self.status_lbl.pack(pady=(2, 8))

        # Botão limpar (verde) - começa desativado
        self.clean_btn = tk.Button(
            self,
            text="LIMPAR METADADOS",
            command=self.on_clean,
            bg="#0FA34A",
            fg="#FFFFFF",
            activebackground="#0C8B3E",
            disabledforeground="#8BE4B4",  # 👈 cor mais clara quando desativado
            state="disabled",
            relief="raised",
            cursor="arrow",
            font=("Segoe UI", 10, "bold")
        )
        self.clean_btn.pack(pady=12, ipadx=12, ipady=6)

        # Rodapé
        footer_frame = tk.Frame(self, bg="#111111")
        footer_frame.pack(side="bottom", pady=8)

        footer = tk.Label(
            footer_frame,
            text="O Arquivo só poderá ser gerado depois de selecionado e permitido pelo MetaClean.",
            fg="#666666", bg="#111111", font=("Segoe UI", 9)
        )
        footer.pack()

        # Link "Desenvolvido por Diego R Ribeiro"
        def open_link(event=None):
            import webbrowser
            webbrowser.open("https://github.com/diegorribeiro")  # substitua pelo seu link real

        link = tk.Label(
            footer_frame,
            text="Desenvolvido por # Diego Ribeiro",
            fg="#1E90FF",  # azul
            bg="#111111",
            font=("Segoe UI", 9, "underline"),
            cursor="hand2"
        )
        link.pack()
        link.bind("<Button-1>", open_link)

    def reset_clean_button(self):
        self.clean_btn.configure(state="disabled", cursor="arrow")
        self.status_var.set("")

    def enable_clean_button(self):
        self.clean_btn.configure(state="normal", cursor="hand2")

    def on_pick_file(self):
        # Ao escolher novo arquivo, o botão deve sumir/desabilitar até nova validação
        self.reset_clean_button()

        path = filedialog.askopenfilename(
            title="Selecione uma imagem ou vídeo",
            filetypes=[
                ("Mídia", "*.jpg *.jpeg *.png *.webp *.bmp *.tiff *.mp4 *.mov *.m4v *.mkv *.avi *.webm"),
                ("Todos os arquivos", "*.*"),
            ]
        )
        if not path:
            return

        kind, _ = is_media_supported(path)
        if kind is None:
            self.selected_file = None
            self.file_entry_var.set("Arquivo inválido. Selecione imagem ou vídeo compatível.")
            self.status_var.set("")
            return

        # Validado
        self.selected_file = path
        self.media_kind = kind

        display_name = os.path.basename(path).strip()
        display_name = re.sub(r"\s+", " ", display_name)
        self.file_entry_var.set(display_name)
        self.status_var.set(f"Tipo detectado: {kind.upper()} — pronto para limpar.")
        self.enable_clean_button()

    def on_clean(self):
        if not self.selected_file or not self.media_kind:
            messagebox.showwarning("Aviso", "Nenhum arquivo válido selecionado.")
            return

        ensure_output_dir()

        # Pega pasta do arquivo original
        original_dir = os.path.dirname(self.selected_file)

        original = os.path.basename(self.selected_file)
        original = sanitize_filename(original)
        base, ext = os.path.splitext(original)

        h = hash6()
        new_name = f"[CLEANED]{h}_{base}{ext}"
        
        # Salva na pasta original do arquivo com nome sanitizado + HASH6
        out_path = os.path.join(original_dir, new_name)
        
        # Salva na pasta /cleaned
        # out_path = os.path.join(OUTPUT_DIR, new_name)

        try:
            if self.media_kind == "image":
                clean_image(self.selected_file, out_path)
            elif self.media_kind == "video":
                if not ffmpeg_available():
                    raise RuntimeError("FFmpeg não encontrado. Garanta 'ffmpeg.exe' em ./ffmpeg/ ou ./ e/ou no PATH.")
                clean_video(self.selected_file, out_path)
            else:
                raise RuntimeError("Tipo de mídia não suportado.")

            messagebox.showinfo("Sucesso", f"Metadados limpo e salvo em:\n{os.path.abspath(out_path)}")
            # Após processar, reseta o botão
            self.reset_clean_button()
            self.file_entry_var.set("Selecione um arquivo de mídia")
            self.selected_file = None
            self.media_kind = None
        except Exception as e:
            messagebox.showerror("Erro", str(e))

def main():
    app = App()
    app.mainloop()

if __name__ == "__main__":
    main()
