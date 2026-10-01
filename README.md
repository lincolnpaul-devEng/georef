# GeoRef.ai &bull; AI-Powered Map Georeferencing & Transformation Platform

An intelligent, full-stack geospatial application designed to process scanned historical, topographic, and cadastral maps (PDF & Raster), extract neatlines and ground control points (GCPs) with Vision AI, convert local/regional datums to GPS WGS84 coordinates, and render interactive 3D satellite overlays using Mapbox GL JS.

---

## 🌟 Key Features

- **Multimodal AI Vision Extraction:** Utilizes OpenRouter (`google/gemini-2.5-flash`) for automated neatline tick mark OCR, grid coordinate identification, and scale detection.
- **Smart Cadastral & Regional Georeferencing:** Location-aware heuristics for regional survey diagrams (e.g. Arc 1960 UTM Zone 36S vs 37S for East African cadastral sheets).
- **High-Resolution PDF Rasterization:** Renders vector and scanned multi-layer map PDFs into crisp image textures via `pypdfium2`.
- **Geodetic Coordinate Transformation:** Real-time datum conversions via `pyproj` (WGS 84, Arc 1960, ED50, NAD83/27, Clarke 1880, Cassini-Soldner).
- **Interactive Mapbox GL JS v3 Studio:** High-res satellite imagery, 3D terrain pitch and relief, glowing neon radar GCP markers, and camera fly-to animations.
- **Early Access Verification Gate:** Access control powered by Supabase `access_requests` table with instant user verification on the landing page.
- **Enterprise Security Hardening:** Comprehensive XSS mitigation, secure headers middleware (`nosniff`, `DENY` frames, `mode=block`), MIME-type & magic byte validation, and CSRF protection.

---

## 🛠️ Tech Stack

- **Backend:** Python 3.11, Django 5.x
- **AI & OCR:** OpenRouter API (Gemini 2.5 Flash Multimodal)
- **Geodesy & GIS:** PyProj, Pillow, PyPDFium2
- **Frontend & Mapping:** Mapbox GL JS v3, Bootstrap 5, HTML5/CSS3 Neon Theme
- **Database & Auth:** SQLite (local mirror) & Supabase REST API (access requests)

---

## 🚀 Quickstart & Setup

### 1. Clone & Setup Virtual Environment
```bash
git clone https://github.com/lincolnpaul-devEng/georef.git
cd georef

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Environment Configuration
Copy `.env.example` to `.env` and fill in your keys:
```bash
cp .env.example .env
```

Edit `.env`:
```env
DJANGO_SECRET_KEY=your-secret-key
DEBUG=True

# OpenRouter AI Key
OPENROUTER_API_KEY=your-openrouter-key
OPENROUTER_MODEL=google/gemini-2.5-flash

# Mapbox Token
MAPBOX_ACCESS_TOKEN=pk.your-mapbox-token

# Supabase Access Verification
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-anon-or-service-key
```

### 3. Database Migrations
```bash
python manage.py migrate
```

### 4. Run Development Server
```bash
python manage.py runserver
```
Visit `http://127.0.0.1:8000/` in your browser.

---

## 📄 License
MIT License &copy; 2026 GeoRef.ai
