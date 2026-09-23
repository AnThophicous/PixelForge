"""Local image upscaler with a quality pipeline and optional OpenCV AI backend."""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

try:
    from PIL import Image, ImageEnhance, ImageFilter
except ImportError as exc:  # pragma: no cover - exercised by the startup message
    raise SystemExit("Pillow não está instalado. Execute: python -m pip install -r requirements.txt") from exc


SUPPORTED = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
LAYA_URL = "https://wire.ia.br/v1/decide"
MODEL_MAX_EDGE = {"edsr": 2048, "fsrcnn": 4096, "espcn": 4096}
MODEL_PRIORITY = ("edsr", "fsrcnn", "espcn")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file, code, msg, headers, new_url):
        raise urllib.error.HTTPError(request.full_url, code, "redirecionamento recusado", headers, file)


@dataclass(frozen=True)
class UpscaleOptions:
    scale: int = 4
    mode: str = "auto"
    model_path: Path | None = None
    tile: int = 512
    overlap: int = 24
    sharpen: float = 0.35
    threads: int = max(1, (os.cpu_count() or 2) - 1)


def load_dotenv(path: Path) -> dict[str, str]:
    """Load only simple KEY=VALUE pairs; values never enter logs or output."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in {"LAYA_KEY"}:
            values[key] = value.strip().strip('"').strip("'")
    return values


def model_family(path: Path) -> str | None:
    name = path.stem.lower()
    return next((family for family in MODEL_PRIORITY if family in name), None)


def model_fits_output(path: Path, width: int, height: int, scale: int) -> bool:
    family = model_family(path)
    return family is not None and max(width * scale, height * scale) <= MODEL_MAX_EDGE[family]


def discover_model(explicit: Path | None, width: int | None = None, height: int | None = None, scale: int = 4) -> Path | None:
    if explicit:
        if not explicit.is_file():
            return None
        if width is not None and height is not None and not model_fits_output(explicit, width, height, scale):
            return None
        return explicit
    model_dir = Path(__file__).with_name("models")
    models = {model_family(path): path for path in model_dir.glob("*.pb") if model_family(path)}
    if width is None or height is None:
        return next((models.get(family) for family in MODEL_PRIORITY if models.get(family)), None)
    return next((models.get(family) for family in MODEL_PRIORITY if models.get(family) and model_fits_output(models[family], width, height, scale)), None)


def _ai_tile(image: Image.Image, model_path: Path, scale: int, tile: int, overlap: int, threads: int) -> Image.Image:
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("O backend de IA exige opencv-contrib-python e numpy.") from exc

    if not hasattr(cv2, "dnn_superres"):
        raise RuntimeError("Instale opencv-contrib-python para habilitar o backend de IA.")
    if not model_path.is_file():
        raise RuntimeError(f"Modelo não encontrado: {model_path}")

    if tile < 64 or overlap < 0 or overlap * 2 >= tile:
        raise ValueError("tile deve ser >= 64 e overlap deve ser menor que metade de tile.")
    cv2.setNumThreads(max(1, threads))
    model_name = model_path.stem.lower()
    algorithm = next((name for name in ("edsr", "lapsrn", "fsrcnn", "espcn") if name in model_name), "edsr")
    sr = cv2.dnn_superres.DnnSuperResImpl_create()
    sr.readModel(str(model_path))
    sr.setModel(algorithm, scale)

    rgb = np.asarray(image.convert("RGB"))
    height, width = rgb.shape[:2]
    output = np.zeros((height * scale, width * scale, 3), dtype=np.float32)
    weights = np.zeros((height * scale, width * scale, 1), dtype=np.float32)
    step = max(32, tile - overlap * 2)
    for top in range(0, height, step):
        for left in range(0, width, step):
            bottom = min(height, top + tile)
            right = min(width, left + tile)
            crop = cv2.cvtColor(rgb[top:bottom, left:right], cv2.COLOR_RGB2BGR)
            up = sr.upsample(crop)
            up = cv2.cvtColor(up, cv2.COLOR_BGR2RGB).astype(np.float32)
            y0, x0 = top * scale, left * scale
            y1, x1 = y0 + up.shape[0], x0 + up.shape[1]
            output[y0:y1, x0:x1] += up
            weights[y0:y1, x0:x1] += 1
    result = np.clip(output / np.maximum(weights, 1), 0, 255).astype(np.uint8)
    return Image.fromarray(result, "RGB")


def _quality_upscale(image: Image.Image, scale: int, sharpen: float) -> Image.Image:
    """High-quality non-AI path: Lanczos resize plus restrained edge recovery."""
    target = (image.width * scale, image.height * scale)
    result = image.convert("RGB").resize(target, Image.Resampling.LANCZOS)
    if sharpen <= 0:
        return result
    result = result.filter(ImageFilter.UnsharpMask(radius=1.2, percent=125, threshold=3))
    return ImageEnhance.Sharpness(result).enhance(1.0 + min(sharpen, 1.0))


def upscale_image(
    source: Path,
    destination: Path,
    options: UpscaleOptions,
    progress: Callable[[str], None] | None = None,
) -> str:
    if source.suffix.lower() not in SUPPORTED:
        raise ValueError(f"Formato não suportado: {source.suffix or '(sem extensão)'}")
    if options.scale not in {2, 3, 4, 8}:
        raise ValueError("A escala deve ser 2, 3, 4 ou 8.")
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.resolve() == destination.resolve():
        raise ValueError("A saída deve ser um arquivo diferente da entrada.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as opened:
        source_image = opened.copy()
        source_image.info.pop("exif", None)
    if progress:
        progress(f"Entrada: {source_image.width}x{source_image.height}")

    model = discover_model(options.model_path, source_image.width, source_image.height, options.scale)
    use_ai = options.mode == "ai" or (options.mode == "auto" and model is not None)
    if use_ai and model is not None:
        if progress:
            progress(f"Backend: IA ({model.name})")
        try:
            result = _ai_tile(source_image, model, options.scale, options.tile, options.overlap, options.threads)
            backend = "ai"
        except RuntimeError:
            if options.mode == "ai":
                raise
            if progress:
                progress("IA indisponível; usando pipeline de qualidade local")
            result = _quality_upscale(source_image, options.scale, options.sharpen)
            backend = "quality"
    else:
        if options.mode == "ai":
            raise RuntimeError("Nenhum modelo IA disponível para o tamanho solicitado. Limites: EDSR 2K; FSRCNN/ESPCN 4K.")
        if progress:
            progress("Backend: qualidade local (Lanczos + recuperação de bordas)")
        result = _quality_upscale(source_image, options.scale, options.sharpen)
        backend = "quality"

    suffix = destination.suffix.lower()
    save_kwargs = {"quality": 97, "subsampling": 0} if suffix in {".jpg", ".jpeg"} else {}
    result.save(destination, **save_kwargs)
    if progress:
        progress(f"Saída: {result.width}x{result.height} | {backend}")
    return backend


def ask_laya(source: Path, scale: int, api_key: str) -> str | None:
    """Ask Laya for a mode using metadata only; failures keep the local path usable."""
    if not api_key.strip():
        return None
    with Image.open(source) as image:
        width, height = image.size
    has_model = discover_model(None, width, height, scale) is not None
    payload = {"state": {"width": width, "height": height, "suffix": source.suffix.lower(), "scale": scale, "local_ai_model": has_model}, "questions": {"mode": {"type": "choice", "instructions": "Which local upscale mode should be used?", "criteria": {"quality": "no AI model available", "ai": "a local super-resolution model is available"}}}}
    request = urllib.request.Request(
        LAYA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        opener = urllib.request.build_opener(_NoRedirect)
        with opener.open(request, timeout=8) as response:
            body = json.loads(response.read(256_000).decode("utf-8"))
        choice = body.get("answers", {}).get("mode", {}).get("choice")
        if choice == "ai" and not has_model:
            return "quality"
        return choice if choice in {"quality", "ai"} else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Upscale local de imagens com fallback seguro.")
    parser.add_argument("input", nargs="?", type=Path, help="imagem de entrada")
    parser.add_argument("-o", "--output", type=Path, help="arquivo de saída")
    parser.add_argument("-s", "--scale", type=int, default=4, choices=(2, 3, 4, 8))
    parser.add_argument("--mode", choices=("auto", "quality", "ai"), default="auto")
    parser.add_argument("--model", type=Path, help="modelo OpenCV DNN .pb")
    parser.add_argument("--tile", type=int, default=512)
    parser.add_argument("--overlap", type=int, default=24)
    parser.add_argument("--laya", action="store_true", help="consultar Laya usando apenas metadados")
    parser.add_argument("--gui", action="store_true", help="abrir a interface gráfica")
    return parser


def run_cli(args: argparse.Namespace) -> int:
    if not args.input:
        raise SystemExit("Informe uma imagem ou use --gui.")
    output = args.output or args.input.with_name(f"{args.input.stem}_x{args.scale}.png")
    mode = args.mode
    env = load_dotenv(Path(__file__).with_name(".env"))
    if args.laya and env.get("LAYA_KEY"):
        mode = ask_laya(args.input, args.scale, env["LAYA_KEY"]) or mode
    options = UpscaleOptions(scale=args.scale, mode=mode, model_path=args.model, tile=args.tile, overlap=args.overlap)
    upscale_image(args.input, output, options, print)
    return 0


def launch_gui() -> None:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title("Upscale local")
    root.geometry("680x390")
    source = tk.StringVar()
    destination = tk.StringVar()
    scale = tk.StringVar(value="4")
    mode = tk.StringVar(value="auto")
    use_laya = tk.BooleanVar(value=bool(load_dotenv(Path(__file__).with_name(".env")).get("LAYA_KEY")))
    status = tk.StringVar(value="Escolha uma imagem.")

    def pick_source() -> None:
        path = filedialog.askopenfilename(filetypes=[("Imagens", "*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff")])
        if path:
            source.set(path)
            destination.set(str(Path(path).with_name(f"{Path(path).stem}_x{scale.get()}.png")))

    def pick_destination() -> None:
        path = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg")])
        if path:
            destination.set(path)

    def start() -> None:
        if not source.get() or not destination.get():
            messagebox.showerror("Entrada necessária", "Escolha a imagem e o arquivo de saída.")
            return
        options = UpscaleOptions(scale=int(scale.get()), mode=mode.get())
        laya_enabled = use_laya.get()
        start_button.config(state="disabled")

        def work() -> None:
            try:
                selected_mode = options.mode
                env = load_dotenv(Path(__file__).with_name(".env"))
                if laya_enabled:
                    if env.get("LAYA_KEY"):
                        root.after(0, status.set, "Laya está escolhendo o backend...")
                        selected_mode = ask_laya(Path(source.get()), options.scale, env["LAYA_KEY"]) or selected_mode
                        root.after(0, status.set, f"Laya escolheu: {selected_mode}")
                    else:
                        root.after(0, status.set, "LAYA_KEY não configurada; usando modo local")
                selected = UpscaleOptions(scale=options.scale, mode=selected_mode, model_path=options.model_path, tile=options.tile, overlap=options.overlap, sharpen=options.sharpen, threads=options.threads)
                upscale_image(Path(source.get()), Path(destination.get()), selected, lambda text: root.after(0, status.set, text))
                root.after(0, lambda: messagebox.showinfo("Concluído", f"Imagem salva em:\n{destination.get()}"))
            except (OSError, RuntimeError, ValueError) as exc:
                root.after(0, lambda: messagebox.showerror("Falha no upscale", str(exc)))
            finally:
                root.after(0, lambda: start_button.config(state="normal"))

        threading.Thread(target=work, daemon=True).start()

    frame = ttk.Frame(root, padding=20)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="Upscale local", font=("Segoe UI", 18, "bold")).pack(anchor="w")
    ttk.Label(frame, text="Lanczos + recuperação de bordas; use um modelo .pb em models/ para IA.").pack(anchor="w", pady=(0, 18))
    for label, variable, button, command in (("Entrada", source, "Abrir", pick_source), ("Saída", destination, "Salvar como", pick_destination)):
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=5)
        ttk.Label(row, text=label, width=10).pack(side="left")
        ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(row, text=button, command=command).pack(side="right")
    controls = ttk.Frame(frame)
    controls.pack(fill="x", pady=18)
    ttk.Label(controls, text="Escala").pack(side="left")
    ttk.Combobox(controls, textvariable=scale, values=("2", "3", "4", "8"), width=5, state="readonly").pack(side="left", padx=8)
    ttk.Label(controls, text="Modo").pack(side="left", padx=(18, 0))
    ttk.Combobox(controls, textvariable=mode, values=("auto", "quality", "ai"), width=10, state="readonly").pack(side="left", padx=8)
    ttk.Checkbutton(controls, text="Decidir com Laya", variable=use_laya).pack(side="left", padx=(18, 0))
    start_button = ttk.Button(frame, text="Ampliar imagem", command=start)
    start_button.pack(anchor="w")
    ttk.Label(frame, textvariable=status, wraplength=620).pack(anchor="w", pady=22)
    root.mainloop()


def main() -> int:
    args = build_parser().parse_args()
    if args.gui or not args.input:
        launch_gui()
        return 0
    return run_cli(args)


if __name__ == "__main__":
    sys.exit(main())
