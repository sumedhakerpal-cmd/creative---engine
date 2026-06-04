from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from PIL import Image
import io
import zipfile
import os
import requests as req_lib
import anthropic
import json
import base64

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

ALL_SIZES = [
    {"name": "Billboard",        "w": 970,  "h": 250,  "gam": "970x250",   "type": "gam"},
    {"name": "Filmstrip",        "w": 560,  "h": 320,  "gam": "560x320",   "type": "gam"},
    {"name": "Mobile Banner",    "w": 320,  "h": 100,  "gam": "320x100",   "type": "gam"},
    {"name": "Leaderboard",      "w": 970,  "h": 90,   "gam": "970x90",    "type": "gam"},
    {"name": "Medium Rectangle", "w": 300,  "h": 250,  "gam": "300x250",   "type": "gam"},
    {"name": "Half Page",        "w": 360,  "h": 600,  "gam": "360x600",   "type": "gam"},
    {"name": "Wide Skyscraper",  "w": 300,  "h": 600,  "gam": "300x600",   "type": "gam"},
    {"name": "Meta Square",      "w": 1080, "h": 1080, "gam": "1080x1080", "type": "meta"},
    {"name": "Meta Story",       "w": 1080, "h": 1920, "gam": "1080x1920", "type": "meta"},
    {"name": "Meta Landscape",   "w": 1200, "h": 628,  "gam": "1200x628",  "type": "meta"},
]

def smart_crop_resize(img, target_w, target_h, output_format):
    """
    High quality resize using Pillow LANCZOS.
    Strategy: scale so the image FILLS the canvas (cover), 
    then crop from centre. No white space, no distortion.
    For very wide targets (billboard/leaderboard), 
    shift crop upward slightly to favour the car over sky.
    """
    orig_w, orig_h = img.size
    target_ratio = target_w / target_h
    orig_ratio = orig_w / orig_h

    # Scale to fill (cover), then crop
    if orig_ratio > target_ratio:
        # image is wider than target — scale by height, crop sides
        scale = target_h / orig_h
        new_w = round(orig_w * scale)
        new_h = target_h
    else:
        # image is taller than target — scale by width, crop top/bottom
        scale = target_w / orig_w
        new_w = target_w
        new_h = round(orig_h * scale)

    resized = img.resize((new_w, new_h), Image.LANCZOS)

    # Crop from centre, but shift up by 10% for landscape formats
    # so we favour the car/subject over sky
    cx = (new_w - target_w) // 2
    cy = (new_h - target_h) // 2

    # For wide landscape formats, shift crop up (favour lower half of image)
    if target_w > target_h * 2:  # very wide (billboard, leaderboard)
        cy = max(0, cy + round((new_h - target_h) * 0.15))
    elif target_w > target_h:    # moderately wide
        cy = max(0, cy + round((new_h - target_h) * 0.05))

    cropped = resized.crop((cx, cy, cx + target_w, cy + target_h))

    buf = io.BytesIO()
    if output_format == "jpg":
        if cropped.mode in ("RGBA", "P"):
            cropped = cropped.convert("RGB")
        cropped.save(buf, format="JPEG", quality=95, optimize=True, subsampling=0)
    else:
        cropped.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf

def resize_animated_gif(img_bytes, target_w, target_h):
    img = Image.open(io.BytesIO(img_bytes))
    frames, durations = [], []
    try:
        while True:
            frame = img.copy().convert("RGBA")
            orig_w, orig_h = frame.size
            scale = max(target_w / orig_w, target_h / orig_h)
            new_w, new_h = round(orig_w * scale), round(orig_h * scale)
            resized = frame.resize((new_w, new_h), Image.LANCZOS)
            cx = (new_w - target_w) // 2
            cy = (new_h - target_h) // 2
            canvas = Image.new("RGBA", (target_w, target_h), (0,0,0,0))
            canvas.paste(resized.crop((cx, cy, cx+target_w, cy+target_h)), (0,0))
            frames.append(canvas)
            durations.append(img.info.get("duration", 100))
            img.seek(img.tell() + 1)
    except EOFError:
        pass
    if not frames:
        return None
    buf = io.BytesIO()
    frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:],
                   loop=img.info.get("loop",0), duration=durations, optimize=False, disposal=2)
    buf.seek(0)
    return buf

@app.route("/")
def index():
    with open(os.path.join(app.template_folder, "index.html"), "r") as f:
        return f.read()

@app.route("/api/process", methods=["POST"])
def process():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files["file"]
    output_format = request.form.get("format", "png").lower()
    sizes_param = request.form.get("sizes", "")
    single_size = request.form.get("single_size", "")

    if sizes_param:
        selected = set(sizes_param.split(","))
        active_sizes = [s for s in ALL_SIZES if s["gam"] in selected]
    else:
        active_sizes = ALL_SIZES

    try:
        img_bytes = file.read()
        img = Image.open(io.BytesIO(img_bytes))
        is_gif = file.filename.lower().endswith(".gif") or img.format == "GIF"
        is_animated = is_gif and hasattr(img, "n_frames") and img.n_frames > 1
        base_name = os.path.splitext(file.filename)[0]
    except Exception as e:
        return jsonify({"error": f"Could not open image: {str(e)}"}), 400

    if single_size and len(active_sizes) == 1:
        s = active_sizes[0]
        if is_animated:
            buf = resize_animated_gif(img_bytes, s["w"], s["h"])
            ext, mime = "gif", "image/gif"
        else:
            img_copy = Image.open(io.BytesIO(img_bytes))
            buf = smart_crop_resize(img_copy, s["w"], s["h"], output_format)
            ext = output_format
            mime = "image/jpeg" if ext == "jpg" else "image/png"
        return send_file(buf, mimetype=mime, as_attachment=True,
                        download_name=f"{base_name}_{s['w']}x{s['h']}.{ext}")

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for size in active_sizes:
            w, h = size["w"], size["h"]
            img_copy = Image.open(io.BytesIO(img_bytes))
            if is_animated:
                resized_buf = resize_animated_gif(img_bytes, w, h)
                ext = "gif"
            else:
                resized_buf = smart_crop_resize(img_copy, w, h, output_format)
                ext = output_format
            zf.writestr(f"{base_name}_{w}x{h}.{ext}", resized_buf.read())
    zip_buf.seek(0)
    return send_file(zip_buf, mimetype="application/zip", as_attachment=True,
                    download_name=f"{base_name}_all-sizes.zip")

@app.route("/api/analyse-kv", methods=["POST"])
def analyse_kv():
    if not ANTHROPIC_API_KEY:
        return jsonify({"error": "ANTHROPIC_API_KEY not set"}), 500
    data = request.get_json()
    if not data or "image_b64" not in data:
        return jsonify({"error": "Missing image_b64"}), 400
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=350,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": data.get("mime","image/jpeg"), "data": data["image_b64"]}},
                {"type": "text", "text": f"Analyse this automotive KV for {data.get('car_model','the car')}. Describe: dominant colours (hex if obvious), background style, car position/angle, logo placement, visual mood. Be specific about layout zones. 2-3 sentences max."}
            ]}]
        )
        return jsonify({"analysis": msg.content[0].text.strip()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/write-copy", methods=["POST"])
def write_copy():
    if not ANTHROPIC_API_KEY:
        return jsonify({"error": "ANTHROPIC_API_KEY not set"}), 500
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing data"}), 400
    brief = data.get("brief", {})
    analysis = data.get("analysis", "")
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=400,
            messages=[{"role": "user", "content": f"""Expert automotive copywriter for Cars24 New Cars. Return ONLY valid JSON, no markdown:
{{"headline":"max 7 words","subheadline":"max 12 words","body":"max 18 words","cta":"{brief.get('cta','Learn More')}"}}
Car: {brief.get('model','the car')} | Audience: {brief.get('aud','urban buyers')} | Offer: {brief.get('offer','competitive pricing')} | Theme: {brief.get('theme','modern')} | KV style: {analysis} | Notes: {brief.get('style','none')}"""}]
        )
        raw = msg.content[0].text.strip().replace("```json","").replace("```","").strip()
        return jsonify(json.loads(raw))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/generate-image", methods=["POST"])
def generate_image():
    if not OPENAI_API_KEY:
        return jsonify({"error": "OPENAI_API_KEY not set"}), 500
    data = request.get_json()
    if not data or "prompt" not in data:
        return jsonify({"error": "Missing prompt"}), 400
    try:
        resp = req_lib.post(
            "https://api.openai.com/v1/images/generations",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
            json={"model": "gpt-image-1", "prompt": data["prompt"], "n": 1, "size": "1024x1024", "output_format": "png"},
            timeout=120
        )
        result = resp.json()
        if not resp.ok:
            return jsonify({"error": result.get("error", {}).get("message", "OpenAI error")}), resp.status_code
        return jsonify({"b64_json": result["data"][0]["b64_json"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/sizes")
def get_sizes():
    return jsonify(ALL_SIZES)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
