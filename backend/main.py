"""
BirdNET Audio Analysis API
Run with: uvicorn main:app --reload --port 8000
"""

import os
import shutil
import tempfile
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── BirdNET ────────────────────────────────────────────────────────────────────
from birdnetlib import Recording
from birdnetlib.analyzer import Analyzer

# ── Audio conversion ───────────────────────────────────────────────────────────
from pydub import AudioSegment  # requires ffmpeg on PATH


# ─────────────────────────────────────────────────────────────────────────────
# Region lookup (mocked; swap for live eBird API when you have a key)
# ─────────────────────────────────────────────────────────────────────────────
REGION_MAP: dict[str, List[str]] = {
    # North American species
    "American Robin":           ["Eastern North America", "Canada", "Mexico (winter)"],
    "Northern Cardinal":        ["Eastern & Central North America"],
    "House Sparrow":            ["Worldwide (introduced)", "North America", "Europe"],
    "European Starling":        ["North America (introduced)", "Europe", "Asia"],
    "Black-capped Chickadee":   ["Northern North America", "Canada"],
    "Mourning Dove":            ["North America", "Central America"],
    "American Crow":            ["North America"],
    "Blue Jay":                 ["Eastern North America", "Southern Canada"],
    "Song Sparrow":             ["North America"],
    "Red-winged Blackbird":     ["North America", "Central America"],
    "Common Yellowthroat":      ["North & Central America"],
    "Wood Thrush":              ["Eastern North America", "Central America (winter)"],
    "Hermit Thrush":            ["North America"],
    "Swainson's Thrush":        ["North America", "South America (winter)"],
    "White-throated Sparrow":   ["North America"],
    "Dark-eyed Junco":          ["North America"],
    "Cedar Waxwing":            ["North America"],
    "Baltimore Oriole":         ["Eastern North America", "Central America (winter)"],
    "Rose-breasted Grosbeak":   ["Eastern North America", "South America (winter)"],
    "Indigo Bunting":           ["Eastern North America", "Caribbean (winter)"],
    # European species
    "Common Chaffinch":         ["Europe", "Western Asia", "North Africa"],
    "Eurasian Blackbird":       ["Europe", "Asia", "North Africa"],
    "Common Wood Pigeon":       ["Europe", "Central Asia"],
    "Barn Swallow":             ["Worldwide"],
    "Common Swift":             ["Europe", "Africa (winter)"],
    "Great Tit":                ["Europe", "Asia"],
    "Blue Tit":                 ["Europe", "Western Asia"],
    "European Robin":           ["Europe", "North Africa", "Western Asia"],
    "Common Cuckoo":            ["Europe", "Africa (winter)", "Asia"],
    # Tropical / global
    "Common Myna":              ["South Asia", "Southeast Asia", "Introduced globally"],
    "Rose-ringed Parakeet":     ["South Asia", "Sub-Saharan Africa", "Introduced Europe"],
    "Zebra Finch":              ["Australia"],
    "Superb Fairywren":         ["Australia"],
}

FALLBACK_REGIONS = ["Widespread across multiple continents"]


def get_regions(common_name: str) -> List[str]:
    """Return known regions for a species, falling back to a generic message."""
    # Exact match first
    if common_name in REGION_MAP:
        return REGION_MAP[common_name]
    # Partial match (handles e.g. subspecies names like "American Robin (migratorius)")
    for key, regions in REGION_MAP.items():
        if key.lower() in common_name.lower() or common_name.lower() in key.lower():
            return regions
    return FALLBACK_REGIONS


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic response models
# ─────────────────────────────────────────────────────────────────────────────
class Detection(BaseModel):
    common_name: str
    scientific_name: str
    confidence: float
    start_time: float
    end_time: float
    regions: List[str]


class AnalysisResponse(BaseModel):
    detections: List[Detection]
    total: int


# ─────────────────────────────────────────────────────────────────────────────
# App setup
# ─────────────────────────────────────────────────────────────────────────────
app = FastAPI(title="BirdNET API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load the BirdNET model once at startup (slow first load, fast thereafter)
print("Loading BirdNET model …")
analyzer = Analyzer()
print("BirdNET model ready.")


# ─────────────────────────────────────────────────────────────────────────────
# Helper: convert any audio file → 48 kHz mono WAV (BirdNET requirement)
# ─────────────────────────────────────────────────────────────────────────────
def to_birdnet_wav(src_path: str, dest_path: str) -> None:
    """
    Convert *src_path* to a 48 kHz, mono, 16-bit PCM WAV at *dest_path*.
    pydub delegates the heavy lifting to ffmpeg.
    """
    audio = AudioSegment.from_file(src_path)
    audio = audio.set_frame_rate(48_000).set_channels(1).set_sample_width(2)
    audio.export(dest_path, format="wav")


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyze", response_model=AnalysisResponse)
async def analyze_audio(audio: UploadFile = File(...)):
    """
    Accept any audio upload, convert it to 48 kHz mono WAV,
    run BirdNET inference, and return detected species with regional data.
    """
    suffix = Path(audio.filename or "recording.webm").suffix or ".webm"

    with tempfile.TemporaryDirectory() as tmpdir:
        # 1. Save uploaded file
        raw_path = os.path.join(tmpdir, f"input{suffix}")
        with open(raw_path, "wb") as f:
            shutil.copyfileobj(audio.file, f)

        # 2. Convert to BirdNET-compatible WAV
        wav_path = os.path.join(tmpdir, "converted.wav")
        try:
            to_birdnet_wav(raw_path, wav_path)
        except Exception as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Audio conversion failed: {exc}. "
                       "Ensure ffmpeg is installed and on your PATH.",
            )

        # 3. Run BirdNET inference
        try:
            recording = Recording(
                analyzer,
                wav_path,
                min_conf=0.25,   # minimum confidence threshold (0–1)
            )
            recording.analyze()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"BirdNET error: {exc}")

        # 4. Build response
        detections: List[Detection] = []
        seen: set[str] = set()  # deduplicate same species across time windows

        for det in recording.detections:
            name = det.get("common_name", "Unknown")
            if name in seen:
                continue
            seen.add(name)
            detections.append(
                Detection(
                    common_name=name,
                    scientific_name=det.get("scientific_name", ""),
                    confidence=round(float(det.get("confidence", 0)), 4),
                    start_time=float(det.get("start_time", 0)),
                    end_time=float(det.get("end_time", 3)),
                    regions=get_regions(name),
                )
            )

        # Sort by confidence descending
        detections.sort(key=lambda d: d.confidence, reverse=True)

        return AnalysisResponse(detections=detections, total=len(detections))