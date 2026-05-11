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
# Expanded Region lookup
# ─────────────────────────────────────────────────────────────────────────────
REGION_MAP: dict[str, List[str]] = {
    # ── North America ──────────────────────────────────────────────────────
    "American Robin":              ["Eastern North America", "Canada", "Mexico (winter)"],
    "Northern Cardinal":           ["Eastern & Central North America"],
    "House Sparrow":               ["Worldwide (introduced)", "North America", "Europe"],
    "European Starling":           ["North America (introduced)", "Europe", "Asia"],
    "Black-capped Chickadee":      ["Northern North America", "Canada"],
    "Carolina Chickadee":          ["Southeastern United States"],
    "Mourning Dove":               ["North America", "Central America"],
    "American Crow":               ["North America"],
    "Blue Jay":                    ["Eastern North America", "Southern Canada"],
    "Song Sparrow":                ["North America"],
    "Red-winged Blackbird":        ["North America", "Central America"],
    "Common Yellowthroat":         ["North & Central America"],
    "Wood Thrush":                 ["Eastern North America", "Central America (winter)"],
    "Hermit Thrush":               ["North America"],
    "Swainson's Thrush":           ["North America", "South America (winter)"],
    "White-throated Sparrow":      ["North America"],
    "Dark-eyed Junco":             ["North America"],
    "Cedar Waxwing":               ["North America"],
    "Baltimore Oriole":            ["Eastern North America", "Central America (winter)"],
    "Rose-breasted Grosbeak":      ["Eastern North America", "South America (winter)"],
    "Indigo Bunting":              ["Eastern North America", "Caribbean (winter)"],
    "House Finch":                 ["North America", "Mexico"],
    "Purple Finch":                ["North America", "Canada"],
    "American Goldfinch":          ["North America"],
    "Chipping Sparrow":            ["North America", "Central America (winter)"],
    "White-crowned Sparrow":       ["North America"],
    "Fox Sparrow":                 ["North America"],
    "Spotted Towhee":              ["Western North America"],
    "Eastern Towhee":              ["Eastern North America"],
    "Gray Catbird":                ["North America", "Caribbean (winter)"],
    "Northern Mockingbird":        ["North America", "Caribbean"],
    "Brown Thrasher":              ["Eastern North America"],
    "Carolina Wren":               ["Eastern North America"],
    "House Wren":                  ["North & South America"],
    "Ruby-throated Hummingbird":   ["Eastern North America", "Central America (winter)"],
    "Downy Woodpecker":            ["North America"],
    "Hairy Woodpecker":            ["North America"],
    "Red-bellied Woodpecker":      ["Eastern North America"],
    "Pileated Woodpecker":         ["North America"],
    "Northern Flicker":            ["North America"],
    "Eastern Wood-Pewee":          ["Eastern North America", "South America (winter)"],
    "Eastern Phoebe":              ["Eastern North America", "Mexico (winter)"],
    "Great Crested Flycatcher":    ["Eastern North America", "South America (winter)"],
    "Eastern Kingbird":            ["North America", "South America (winter)"],
    "Tree Swallow":                ["North America", "Central America (winter)"],
    "Barn Swallow":                ["Worldwide"],
    "Cliff Swallow":               ["North America", "South America (winter)"],
    "Purple Martin":               ["North America", "South America (winter)"],
    "Black-capped Vireo":          ["Texas/Oklahoma", "Mexico (winter)"],
    "Red-eyed Vireo":              ["North America", "South America (winter)"],
    "Yellow Warbler":              ["North America", "South America (winter)"],
    "Common Yellowthroat":         ["North & Central America"],
    "American Redstart":           ["North America", "Caribbean/South America (winter)"],
    "Ovenbird":                    ["Eastern North America", "Caribbean (winter)"],
    "Scarlet Tanager":             ["Eastern North America", "South America (winter)"],
    "Northern Bobwhite":           ["Eastern North America"],
    "Wild Turkey":                 ["North America"],
    "Canada Goose":                ["North America"],
    "Mallard":                     ["North America", "Europe", "Asia"],
    "Great Blue Heron":            ["North America", "Central America"],
    "Bald Eagle":                  ["North America"],
    "Red-tailed Hawk":             ["North America", "Central America"],
    "American Kestrel":            ["North & South America"],
    "Peregrine Falcon":            ["Worldwide"],
    "Killdeer":                    ["North & South America"],
    "American Woodcock":           ["Eastern North America"],
    "Rock Pigeon":                 ["Worldwide (introduced)"],
    "Chimney Swift":               ["Eastern North America", "South America (winter)"],
    "Common Nighthawk":            ["North America", "South America (winter)"],
    # ── Europe ────────────────────────────────────────────────────────────
    "Common Chaffinch":            ["Europe", "Western Asia", "North Africa"],
    "Eurasian Blackbird":          ["Europe", "Asia", "North Africa"],
    "Common Wood Pigeon":          ["Europe", "Central Asia"],
    "Common Swift":                ["Europe", "Africa (winter)"],
    "Great Tit":                   ["Europe", "Asia"],
    "Blue Tit":                    ["Europe", "Western Asia"],
    "European Robin":              ["Europe", "North Africa", "Western Asia"],
    "Common Cuckoo":               ["Europe", "Africa (winter)", "Asia"],
    "Eurasian Wren":               ["Europe", "Asia"],
    "Dunnock":                     ["Europe", "Western Asia"],
    "Eurasian Nuthatch":           ["Europe", "Asia"],
    "Eurasian Treecreeper":        ["Europe", "Asia"],
    "Long-tailed Tit":             ["Europe", "Asia"],
    "Coal Tit":                    ["Europe", "Asia"],
    "Marsh Tit":                   ["Europe", "Western Asia"],
    "Willow Tit":                  ["Europe", "Asia"],
    "Goldcrest":                   ["Europe", "Asia"],
    "Common Blackcap":             ["Europe", "Africa (winter)"],
    "Garden Warbler":              ["Europe", "Africa (winter)"],
    "Lesser Whitethroat":          ["Europe", "Asia", "Africa (winter)"],
    "Common Whitethroat":          ["Europe", "Africa (winter)"],
    "Sedge Warbler":               ["Europe", "Africa (winter)"],
    "Reed Warbler":                ["Europe", "Africa (winter)"],
    "Eurasian Reed Warbler":       ["Europe", "Africa (winter)"],
    "Willow Warbler":              ["Europe", "Africa (winter)"],
    "Common Chiffchaff":           ["Europe", "Asia", "Africa (winter)"],
    "Wood Warbler":                ["Europe", "Africa (winter)"],
    "Spotted Flycatcher":          ["Europe", "Africa (winter)"],
    "European Pied Flycatcher":    ["Europe", "Africa (winter)"],
    "Common Redstart":             ["Europe", "Africa (winter)"],
    "Whinchat":                    ["Europe", "Africa (winter)"],
    "European Stonechat":          ["Europe", "Asia", "Africa"],
    "Northern Wheatear":           ["Europe", "Asia", "Africa (winter)"],
    "Song Thrush":                 ["Europe", "Asia", "North Africa"],
    "Mistle Thrush":               ["Europe", "Central Asia"],
    "Fieldfare":                   ["Europe", "Asia"],
    "Redwing":                     ["Europe", "Asia"],
    "Eurasian Skylark":            ["Europe", "Asia"],
    "Woodlark":                    ["Europe", "North Africa"],
    "Sand Martin":                 ["Europe", "Africa (winter)"],
    "Common House Martin":         ["Europe", "Africa (winter)"],
    "Yellow Wagtail":              ["Europe", "Asia", "Africa (winter)"],
    "Grey Wagtail":                ["Europe", "Asia", "Africa (winter)"],
    "White Wagtail":               ["Europe", "Asia"],
    "Meadow Pipit":                ["Europe", "Asia", "Africa (winter)"],
    "Tree Pipit":                  ["Europe", "Africa (winter)"],
    "Common Linnet":               ["Europe", "North Africa", "Western Asia"],
    "European Greenfinch":         ["Europe", "Western Asia", "North Africa"],
    "European Goldfinch":          ["Europe", "Western Asia", "North Africa"],
    "Eurasian Siskin":             ["Europe", "Asia"],
    "Common Redpoll":              ["Europe", "Asia", "North America"],
    "Eurasian Bullfinch":          ["Europe", "Asia"],
    "Hawfinch":                    ["Europe", "Asia"],
    "Yellowhammer":                ["Europe", "Asia"],
    "Reed Bunting":                ["Europe", "Asia"],
    "Corn Bunting":                ["Europe", "North Africa", "Western Asia"],
    "Eurasian Jay":                ["Europe", "Asia"],
    "Eurasian Magpie":             ["Europe", "Asia"],
    "Western Jackdaw":             ["Europe", "Western Asia", "North Africa"],
    "Carrion Crow":                ["Europe", "Eastern Asia"],
    "Rook":                        ["Europe", "Asia"],
    "Common Raven":                ["North America", "Europe", "Asia"],
    "Common Starling":             ["Europe", "Asia", "North Africa"],
    "House Sparrow":               ["Worldwide (introduced)", "Europe", "Asia"],
    "Eurasian Tree Sparrow":       ["Europe", "Asia"],
    "Common Kingfisher":           ["Europe", "Asia", "North Africa"],
    "European Bee-eater":          ["Europe", "Africa (winter)"],
    "Eurasian Hoopoe":             ["Europe", "Asia", "Africa"],
    "Great Spotted Woodpecker":    ["Europe", "Asia"],
    "Lesser Spotted Woodpecker":   ["Europe", "Asia"],
    "Green Woodpecker":            ["Europe"],
    "Black Woodpecker":            ["Europe", "Asia"],
    "Common Kestrel":              ["Europe", "Asia", "Africa"],
    "Eurasian Hobby":              ["Europe", "Asia", "Africa (winter)"],
    "Common Buzzard":              ["Europe", "Asia", "Africa (winter)"],
    "Eurasian Sparrowhawk":        ["Europe", "Asia", "Africa (winter)"],
    "Northern Goshawk":            ["Europe", "Asia", "North America"],
    "White Stork":                 ["Europe", "Asia", "Africa (winter)"],
    "Grey Heron":                  ["Europe", "Asia", "Africa"],
    "Great Cormorant":             ["Worldwide"],
    "Mute Swan":                   ["Europe", "Asia", "Introduced North America"],
    "Greylag Goose":               ["Europe", "Asia"],
    "Eurasian Teal":               ["Europe", "Asia", "Africa (winter)"],
    "Common Moorhen":              ["Worldwide"],
    "Eurasian Coot":               ["Europe", "Asia", "Africa"],
    "Common Crane":                ["Europe", "Asia", "Africa (winter)"],
    "Eurasian Oystercatcher":      ["Europe", "Asia", "Africa"],
    "Northern Lapwing":            ["Europe", "Asia", "Africa (winter)"],
    "Common Snipe":                ["Europe", "Asia", "Africa (winter)"],
    "Black-headed Gull":           ["Europe", "Asia", "Africa (winter)"],
    "Herring Gull":                ["Europe", "North America"],
    "Common Tern":                 ["Europe", "Asia", "Africa (winter)"],
    "Stock Dove":                  ["Europe", "Western Asia"],
    "Eurasian Collared Dove":      ["Europe", "Asia", "North America (introduced)"],
    "Common Pheasant":             ["Asia", "Introduced Europe & North America"],
    "Grey Partridge":              ["Europe", "Asia"],
    # ── Asia & Australasia ────────────────────────────────────────────────
    "Common Myna":                 ["South Asia", "Southeast Asia", "Introduced globally"],
    "Rose-ringed Parakeet":        ["South Asia", "Sub-Saharan Africa", "Introduced Europe"],
    "Zebra Finch":                 ["Australia"],
    "Superb Fairywren":            ["Australia"],
    "Laughing Kookaburra":         ["Australia", "Introduced New Zealand"],
    "Australian Magpie":           ["Australia", "New Zealand (introduced)"],
    "Willie Wagtail":              ["Australia", "Papua New Guinea"],
    "Rainbow Lorikeet":            ["Australia", "Eastern Indonesia"],
    "Sulphur-crested Cockatoo":    ["Australia", "New Guinea"],
    "Galah":                       ["Australia"],
    "Oriental Magpie-Robin":       ["South Asia", "Southeast Asia"],
    "Red-vented Bulbul":           ["South Asia", "Southeast Asia"],
    "Red-whiskered Bulbul":        ["South Asia", "Southeast Asia"],
    "Asian Koel":                  ["South Asia", "Southeast Asia", "Australia"],
    "Common Tailorbird":           ["South Asia", "Southeast Asia"],
    "Spotted Dove":                ["South Asia", "Southeast Asia", "Introduced worldwide"],
    "Japanese White-eye":          ["East Asia", "Japan"],
    "Light-vented Bulbul":         ["East Asia", "China", "Taiwan"],
    "Eurasian Tree Sparrow":       ["Europe", "Asia"],
    # ── Africa ────────────────────────────────────────────────────────────
    "African Fish Eagle":          ["Sub-Saharan Africa"],
    "Hadada Ibis":                 ["Sub-Saharan Africa"],
    "African Grey Hornbill":       ["Sub-Saharan Africa"],
    "Village Weaver":              ["Sub-Saharan Africa"],
    "Common Waxbill":              ["Sub-Saharan Africa", "Introduced globally"],
    "Pin-tailed Whydah":           ["Sub-Saharan Africa"],
    "African Penduline Tit":       ["Sub-Saharan Africa"],
    "Cape Turtle Dove":            ["Sub-Saharan Africa"],
    "Laughing Dove":               ["Africa", "South Asia", "Middle East"],
    # ── South America ─────────────────────────────────────────────────────
    "Rufous-collared Sparrow":     ["South America", "Central America"],
    "Southern Lapwing":            ["South America"],
    "Great Kiskadee":              ["South America", "Central America", "Texas"],
    "Tropical Kingbird":           ["South & Central America", "Southern USA"],
    "Sayaca Tanager":              ["South America"],
    "House Wren":                  ["North & South America"],
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

@app.options("/analyze")
async def options_analyze(request: Request):
    return JSONResponse(content={}, headers={
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "*",
    })

@app.options("/health")
async def options_health(request: Request):
    return JSONResponse(content={}, headers={
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "*",
    })


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
            raise HTTPException(status_code=422, detail=f"Audio conversion failed: {exc}")

        try:
            recording = Recording(analyzer, wav_path, min_conf=0.1)
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
            detections.append(Detection(
                common_name=name,
                scientific_name=det.get("scientific_name", ""),
                confidence=round(float(det.get("confidence", 0)), 4),
                start_time=float(det.get("start_time", 0)),
                end_time=float(det.get("end_time", 3)),
                regions=get_regions(name),
            ))

        detections.sort(key=lambda d: d.confidence, reverse=True)
        return AnalysisResponse(detections=detections, total=len(detections))