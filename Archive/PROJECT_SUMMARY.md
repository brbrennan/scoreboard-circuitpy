# Sports Ticker LED Scoreboard — Project Summary

## Overview
A live sports ticker for a 128x64 HUB75 RGB LED matrix display (four 64x32 panels in a 2x2 grid) using an Adafruit MatrixPortal S3 running CircuitPython. Pulls live scores from the ESPN API for 7 leagues: NFL, MLB, NHL, NBA, NCAAF, NCAAB, and NCAAH (college hockey).

---

## Architecture

### Files
| File | Purpose |
|------|---------|
| `code.py` | Main hardware code — runs on MatrixPortal S3 with CircuitPython |
| `emulator_ticker/emulator_ticker.py` | PC emulator — renders to browser via RGBMatrixEmulator at localhost:8888 |
| `emulator_ticker/emulator_config.json` | Emulator display settings (browser adapter, pixel style, port) |
| `test_sports_ticker.py` | Text-only API test script — validates ESPN parsing without display |
| `get_team_logos.py` | Downloads all team logos from ESPN, converts to 32x32 indexed-color BMP |
| `HARDWARE_SETUP_GUIDE.md` | Step-by-step hardware assembly and software setup |
| `README.md` | General project overview |
| `scoreboard_frame.scad` | OpenSCAD 3D printable frame with keyhole wall mounts |

### ESPN API Endpoints
No API key required. All use the same pattern:
```
https://site.api.espn.com/apis/site/v2/sports/{sport}/{league_slug}/scoreboard
```

| League | Sport | ESPN Slug | Display Name |
|--------|-------|-----------|-------------|
| nfl | football | nfl | NFL |
| mlb | baseball | mlb | MLB |
| nhl | hockey | nhl | NHL |
| nba | basketball | nba | NBA |
| cfb | football | college-football | NCAAF |
| cbb | basketball | mens-college-basketball | NCAAB |
| chk | hockey | mens-college-hockey | NCAAH |

Teams endpoint (for logos):
```
https://site.api.espn.com/apis/site/v2/sports/{sport}/{league_slug}/teams?limit=500
```

### Logo System
- Downloaded via `get_team_logos.py` from ESPN CDN
- Converted to 32x32 indexed-color BMP (palette mode)
- Organized into folders: team0_logos (NFL) through team6_logos (NCAAH)
- Named by ESPN abbreviation (e.g., `BOS.bmp`, `UTA.bmp` not `UTAH.bmp`)
- Hardware uses `displayio.OnDiskBitmap` (no color manipulation)
- Emulator uses PIL with corner-pixel transparency detection + brightness boost for dark logos

---

## Key Features & Design Decisions

### Per-League Favorite Teams
`my_teams` is a dict keyed by league, not a flat list. This solves the problem of abbreviations shared across leagues (e.g., "BOS" = Bruins, Celtics, and Red Sox):
```python
my_teams = {
    "nhl": ["BOS", "NYR"],
    "nba": ["BOS"],
    "nfl": ["NE"],
    "mlb": ["BOS"],
    "cfb": ["BC"],
    "cbb": ["BC"],
    "chk": ["BC"],
}
```
When MY TEAMS is active, the filter is built from the relevant league(s) only.

### Button Controls (Hardware)
- `board.BUTTON_UP` (middle): Cycles league modes — ALL → NHL → NBA → NFL → MLB → NCAAF → NCAAB → NCAAH
- `board.BUTTON_DOWN` (bottom): Toggles ALL TEAMS ↔ MY TEAMS
- Debounce: 300ms
- Displays mode briefly (1.5s) when pressed
- Re-fetches immediately with new filters

### Keyboard Controls (Emulator)
- `u` + Enter = UP button
- `d` + Enter = DOWN button
- `q` + Enter = quit
- Background daemon thread listens for input

### Smart Refresh (No Index Reset)
- Live games: refresh every 30 seconds
- No live games: refresh every 300 seconds (5 min)
- **Refresh does NOT reset `game_index`** — scores update in place and display continues cycling from where it left off
- Only resets to index 0 when filters change via button press

### Score Change Alerts
Detects score changes between refreshes for non-basketball leagues (basketball has too many baskets):
- **NHL / NCAAH**: Displays "GOAL!" in yellow
- **NFL / NCAAF**: Displays "SCORE!" in yellow  
- **MLB**: Displays "RUN SCORED!" in yellow
- Flashes 3 times (0.5s on, 0.2s blank) then holds for 2 seconds
- Compares old game list vs new game list by game key (`LEAGUE-HOME-AWAY`)
- After alerts finish, resumes normal cycle where it left off

### No Sample/Offline Data
All sample data and offline fallbacks have been removed. The ticker uses the ESPN API exclusively — if there are no games or the API is down, it shows "NO GAMES TODAY" and retries on the next refresh interval.

---

## Hardware Configuration

### Matrix Panel Setup
Default: Four 64x32 panels in 2x2 serpentine grid (128x64 total)
```python
base_width = 64
base_height = 32
chain_across = 2
tile_down = 2
```
Also includes commented-out Option B for two 64x64 panels.

Address pins auto-adjust: 4 pins (A-D) for 32-row panels, 5 pins (A-E) for 64-row panels.

### Power
- Two 5V 4A supplies (one per row of two panels)
- MatrixPortal S3 powered separately via USB-C
- Do NOT power all four panels from one supply

### Wiring (Serpentine)
```
Panel 1 (top-left) → Panel 2 (top-right) → Panel 3 (bottom-right, rotated 180°) → Panel 4 (bottom-left, rotated 180°)
```
MatrixPortal S3 plugs into Panel 1's INPUT connector.

---

## Required CircuitPython Libraries
Copy to CIRCUITPY `/lib/` folder:
- `adafruit_requests.mpy`
- `adafruit_display_text/` (folder)
- `adafruit_ticks.mpy`
- `adafruit_datetime.mpy`
- `neopixel.mpy`

WiFi credentials in `settings.toml`:
```toml
CIRCUITPY_WIFI_SSID = "YOUR_WIFI_NAME"
CIRCUITPY_WIFI_PASSWORD = "YOUR_WIFI_PASSWORD"
```

---

## Emulator Requirements (PC)
```
pip install RGBMatrixEmulator Pillow requests
```
Run: `python emulator_ticker.py`, open `http://localhost:8888`

---

## 3D Printed Frame
- OpenSCAD file: `scoreboard_frame.scad`
- Prints in 4 corner sections (2 unique mirrored pieces, print 2 of each)
- Each corner ~264mm x 136mm (fits 300mm+ print beds)
- Features: keyhole wall mount slots, front lip for panel retention, diffuser acrylic slot, cable pass-throughs
- PLA or PETG, 0.2mm layer height, 20% infill, no supports
- Also use Adafruit's 3D printed brackets (center + 6x seam brackets) for additional rigidity

---

## Troubleshooting Notes
- **Port conflicts**: `lsof -ti:8888 | xargs kill -9` to clear stuck emulator
- **Logo filename mismatches**: ESPN uses abbreviations like UTA (not UTAH) — `get_team_logos.py` handles this
- **College sports memory**: Hundreds of teams — always use team filters for college leagues on hardware
- **Dark logos invisible in emulator**: Brightness boost applied when max RGB channel < 80 (emulator only, not needed on hardware)
- **Emulator font**: Uses PIL `ImageFont.load_default()` to avoid BDF font missing character crashes
- **code.py auto-runs** on boot — just copy to CIRCUITPY and plug in
- **Updating code**: Plug in USB-C, drag new code.py onto CIRCUITPY drive, board restarts automatically

---

## Chat History
This project was developed across multiple conversations. Full transcripts are available in the project files.
