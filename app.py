from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from PIL import Image
import io
import zipfile
import os

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

GAM_SIZES = [
    {"name": "Billboard",        "w": 970, "h": 250, "gam": "970x250"},
    {"name": "Filmstrip",        "w": 560, "h": 320, "gam": "560x320"},
    {"name": "Mobile Banner",    "w": 320, "h": 100, "gam": "320x100"},
    {"name": "Leaderboard",      "w": 970, "h": 90,  "gam": "970x90"},
    {"name": "Medium Rectangle", "w": 300, "h": 250, "gam": "300x250"},
    {"name": "Half Page",        "w": 360, "h": 600, "gam": "360x600"},
    {"name": "Wide Skyscraper",  "w": 300, "h": 600, "gam": "300x600"},
]

def fit_to_width(img, target_w, target_h, output_format):
    """
    Scale image to fit target width, maintain aspect ratio.
    Canvas is exactly target_w x target_h.
    Transparent bg for PNG, white bg for JPG.
    Image is centered horizontally; anchored to top vertically.
    """
    orig_w, orig_h = img.size
    scale = target_w / orig_w
    new_w = target_w
    new_h = round(orig_h * scale)

    # Resize the image
    resized = img.resize((new_w, new_h), Image.LANCZOS)

    # Create canvas
    is_jpg = output_format == "jpg"
    mode = "RGB" if is_jpg else "RGBA"
    bg_color = (255, 255, 255, 255) if not is_jpg else (255, 255, 255)
    canvas = Image.new(mode, (target_w, target_h), bg_color)

    # Convert resized to match canvas mode
    if mode == "RGBA":
        if resized.mode != "RGBA":
            resized = resized.convert("RGBA")
        canvas.paste(resized, (0, 0), resized)
    else:
        if resized.mode in ("RGBA", "P"):
            resized = resized.convert("RGB")
        canvas.paste(resized, (0, 0))

    buf = io.BytesIO()
    if is_jpg:
        canvas.save(buf, format="JPEG", quality=92, optimize=True)
    else:
        canvas.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf

def fit_animated_gif(img_bytes, target_w, target_h):
    """
    Resize animated GIF: scale to fit width, preserve frames and timing.
    """
    img = Image.open(io.BytesIO(img_bytes))
    frames = []
    durations = []

    try:
        while True:
            frame = img.copy().convert("RGBA")
            orig_w, orig_h = frame.size
            scale = target_w / orig_w
            new_w = target_w
            new_h = round(orig_h * scale)
            resized = frame.resize((new_w, new_h), Image.LANCZOS)

            # Place on canvas
            canvas = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
            canvas.paste(resized, (0, 0), resized)
            frames.append(canvas)
            durations.append(img.info.get("duration", 100))
            img.seek(img.tell() + 1)
    except EOFError:
        pass

    if not frames:
        return None

    buf = io.BytesIO()
    frames[0].save(
        buf,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        loop=img.info.get("loop", 0),
        duration=durations,
        optimize=False,
        disposal=2,
    )
    buf.seek(0)
    return buf

@app.route("/")
def index():
    with open(os.path.join(app.template_folder, "index.html"), "r") as f:
        return f.read()

@app.route("/api/process", methods=["POST"])
def process():
    """
    Accepts multipart/form-data:
      - file: image file
      - sizes: comma-separated GAM codes e.g. "970x250,300x250"
      - format: "png" | "jpg"
      - single_size: if set, returns single file instead of ZIP
    Returns: ZIP of all sizes, or single file if single_size is set
    """
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    output_format = request.form.get("format", "png").lower()
    sizes_param = request.form.get("sizes", "")
    single_size = request.form.get("single_size", "")

    # Determine sizes
    if sizes_param:
        selected = set(sizes_param.split(","))
        active_sizes = [s for s in GAM_SIZES if s["gam"] in selected]
    else:
        active_sizes = GAM_SIZES

    try:
        img_bytes = file.read()
        img = Image.open(io.BytesIO(img_bytes))
        is_gif = file.filename.lower().endswith(".gif") or img.format == "GIF"
        is_animated = is_gif and hasattr(img, "n_frames") and img.n_frames > 1
        base_name = os.path.splitext(file.filename)[0]
    except Exception as e:
        return jsonify({"error": f"Could not open image: {str(e)}"}), 400

    # Single size download
    if single_size and len(active_sizes) == 1:
        s = active_sizes[0]
        if is_animated:
            buf = fit_animated_gif(img_bytes, s["w"], s["h"])
            ext = "gif"
            mime = "image/gif"
        else:
            img_copy = Image.open(io.BytesIO(img_bytes))
            buf = fit_to_width(img_copy, s["w"], s["h"], output_format)
            ext = output_format
            mime = "image/jpeg" if ext == "jpg" else "image/png"
        fname = f"{base_name}_{s['w']}x{s['h']}.{ext}"
        return send_file(buf, mimetype=mime, as_attachment=True, download_name=fname)

    # ZIP of all sizes
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for size in active_sizes:
            w, h = size["w"], size["h"]
            img_copy = Image.open(io.BytesIO(img_bytes))
            if is_animated:
                resized_buf = fit_animated_gif(img_bytes, w, h)
                ext = "gif"
            else:
                resized_buf = fit_to_width(img_copy, w, h, output_format)
                ext = output_format
            fname = f"{base_name}_{w}x{h}.{ext}"
            zf.writestr(fname, resized_buf.read())

    zip_buf.seek(0)
    return send_file(zip_buf, mimetype="application/zip",
                     as_attachment=True,
                     download_name=f"{base_name}_all-sizes.zip")

@app.route("/api/sizes")
def get_sizes():
    return jsonify(GAM_SIZES)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
