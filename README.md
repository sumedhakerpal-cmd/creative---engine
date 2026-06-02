# Creative Preview Engine

Preview and download ad creatives in all 7 Google Ad Manager sizes.

**Supported formats:** JPG, PNG, animated GIF  
**Output formats:** PNG, JPG (GIFs always export as animated GIF)

---

## Deploy to Render (recommended — free, no server management)

### Step 1 — Push to GitHub
```bash
# In this folder, run:
git init
git add .
git commit -m "Creative preview engine"
```
Then create a new repo on github.com and push:
```bash
git remote add origin https://github.com/YOUR_USERNAME/creative-engine.git
git push -u origin main
```

### Step 2 — Deploy on Render
1. Go to [render.com](https://render.com) and sign up (free)
2. Click **New → Web Service**
3. Connect your GitHub repo
4. Render auto-detects the config from `render.yaml`
5. Click **Deploy** — takes ~2 minutes
6. You'll get a URL like `https://creative-preview-engine.onrender.com`
7. Share that URL with your team — done ✓

---

## Run locally (optional)

```bash
pip install -r requirements.txt
python app.py
```
Open http://localhost:5000

---

## Ad sizes included

| Name             | Width | Height | GAM Code |
|------------------|-------|--------|----------|
| Billboard        | 970   | 250    | 970x250  |
| Filmstrip        | 560   | 320    | 560x320  |
| Mobile Banner    | 320   | 100    | 320x100  |
| Leaderboard      | 970   | 90     | 970x90   |
| Medium Rectangle | 300   | 250    | 300x250  |
| Half Page        | 360   | 600    | 360x600  |
| Wide Skyscraper  | 300   | 600    | 300x600  |
