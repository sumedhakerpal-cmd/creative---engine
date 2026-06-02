from flask import Flask, request, jsonify, send_file, render_template_string
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

def resize_static(img, w, h, output_format):
    """Resize a static image (PNG/JPG) to exact dimensions."""
    resized = img.resize((w, h), Image.LANCZOS)
    buf = io.BytesIO()
    fmt = "JPEG" if output_format == "jpg" else "PNG"
    if fmt == "JPEG" and resized.mode in ("RGBA", "P"):
        resized = resized.convert("RGB")
    resized.save(buf, format=fmt, quality=92, optimize=True)
    buf.seek(0)
    return buf

def resize_animated_gif(img, w, h):
    """Resize an animated GIF preserving all frames and timing."""
    frames = []
    durations = []

    try:
        while True:
            frame = img.copy().convert("RGBA")
            frame = frame.resize((w, h), Image.LANCZOS)
            frames.append(frame)
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
    Accepts: multipart/form-data
      - file: the uploaded image
      - sizes: comma-separated list of "WxH" to include (optional, defaults to all)
      - format: "png" | "jpg" (for non-GIF outputs)
    Returns: ZIP file with resized creatives
    """
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    output_format = request.form.get("format", "png").lower()
    sizes_param = request.form.get("sizes", "")

    # Determine which sizes to include
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

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for size in active_sizes:
            w, h = size["w"], size["h"]
            try:
                img.seek(0)
            except Exception:
                pass
            img_copy = Image.open(io.BytesIO(img_bytes))

            if is_animated:
                resized_buf = resize_animated_gif(img_copy, w, h)
                ext = "gif"
            else:
                resized_buf = resize_static(img_copy, w, h, output_format)
                ext = output_format

            fname = f"{base_name}_{w}x{h}.{ext}"
            zf.writestr(fname, resized_buf.read())

    zip_buf.seek(0)
    zip_name = f"{base_name}_all-sizes.zip"
    return send_file(zip_buf, mimetype="application/zip",
                     as_attachment=True, download_name=zip_name)

@app.route("/api/sizes")
def get_sizes():
    return jsonify(GAM_SIZES)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
