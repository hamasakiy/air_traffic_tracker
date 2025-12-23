# app.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from flight_core import get_plane_list, get_latest_state

app = FastAPI(title="Air Travel Tracker API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", response_class=HTMLResponse)
def root():
    return """
    <h2>Air Travel Tracker API</h2>
    <p><a href="/docs">/docs</a> から API を試せます。</p>
    """

@app.get("/planes")
def planes():
    return get_plane_list()

@app.get("/track/{callsign}")
def track(callsign: str):
    state = get_latest_state(callsign)
    if state is None:
        return {"error": "not found"}
    return state
