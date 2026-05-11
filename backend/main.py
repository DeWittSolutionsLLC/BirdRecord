"""
BirdNET Audio Analysis API
Run with: uvicorn main:app --reload --port 8000
"""

import os
import shutil
import tempfile
from pathlib import Path
from typing import List

from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from birdnetlib import Recording
from birdnetlib.analyzer import Analyzer
from pydub import AudioSegment


# ─────────────────────────────────────────────────────────────────────────────
# Region lookup
# ─────────────────────────────────────────────────────────────────────────────
REGION_MAP: dict[str, List[str]] = {
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
    "Common Chaffinch":         ["Europe", "Western Asia", "North Africa"],
    "Eurasian Blackbird":       ["Europe", "Asia", "North Africa"],
    "Common Wood Pigeon":       ["Europe", "Central Asia"],
    "Barn Swallow":             ["Worldwide"],
    "Common Swift":             ["Europe", "Africa (winter)"],
    "Great Tit":                ["Europe", "Asia"],
    "Blue Tit":                 ["Europe", "Western Asia"],
    "European Robin":           ["Europe", "North Africa", "Western Asia"],
    "Common Cuckoo":            ["Europe", "Africa (winter)", "Asia"],
    "Common Myna":              ["South Asia", "Southeast Asia", "Introduced globally"],
    "Rose-ringed Parakeet":     ["South Asia", "Sub-Saharan Africa", "Introduced Europe"],
    "Zebra Finch":              ["Australia"],
    "Superb Fairywren":         ["Australia"],
}

FALLBACK_REGIONS = ["Widespread across multiple continents"]


def get_regions(common_name: str) -> List[str]:
    if common_name in REGION_MAP:
        return REGION_MAP[common_name]
    for key, regions in REGION_MAP.items():
        if key.lower() in common_name.lower() or common_name.lower() in key.lower():
            return regions
    return FALLBACK_REGIONS


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic models
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
# App + CORS
# ─────────────────────────────────────────────────────────────────────────────
app = FastAPI(title="BirdNET API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=False,
    max_age=3600,
)

# Explicit OPTIONS handler so preflight never gets a 405
@app.options("/analyze")
async def options_analyze(request: Request):
    return JSONResponse(
        content={},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "*",
        },
    )

@app.options("/health")
async def options_health(request: Request):
    return JSONResponse(
        content={},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "*",
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Model load
# ─────────────────────────────────────────────────────────────────────────────
print("Loading BirdNET model...")
analyzer = Analyzer()
print("BirdNET model ready.")


# ─────────────────────────────────────────────────────────────────────────────
# Audio conversion
# ─────────────────────────────────────────────────────────────────────────────
def to_birdnet_wav(src_path: str, dest_path: str) -> None:
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
    suffix = Path(audio.filename or "recording.webm").suffix or ".webm"

    with tempfile.TemporaryDirectory() as tmpdir:
        raw_path = os.path.join(tmpdir, f"input{suffix}")
        with open(raw_path, "wb") as f:
            shutil.copyfileobj(audio.file, f)

        wav_path = os.path.join(tmpdir, "converted.wav")
        try:
            to_birdnet_wav(raw_path, wav_path)
        except Exception as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Audio conversion failed: {exc}. Ensure ffmpeg is installed.",
            )

        try:
            recording = Recording(analyzer, wav_path, min_conf=0.25)
            recording.analyze()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"BirdNET error: {exc}")

        detections: List[Detection] = []
        seen: set[str] = set()

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

        detections.sort(key=lambda d: d.confidence, reverse=True)
        return AnalysisResponse(detections=detections, total=len(detections))