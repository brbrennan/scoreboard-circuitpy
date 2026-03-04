# Sports Ticker - Score Display for LED Matrix

Displays live scores for NFL, MLB, NHL, and NBA games on an LED matrix display,
pulling data from ESPN's public API. Based on the project by Liz Clark / Prof G
for Adafruit Industries.

This package includes three versions of the code:

| File | Runs On | Purpose |
|------|---------|---------|
| `code.py` | Microcontroller (CIRCUITPY) | The real hardware display |
| `emulator_ticker/emulator_ticker.py` | Your PC | Visual LED simulation in browser |
| `test_sports_ticker.py` | Your PC | Text-only API + logic testing |
| `get_team_logos.py` | Your PC | Downloads all team logos from ESPN |

---

## Features Added Beyond Original

- **League filtering** — show only NHL, NBA, or any combo
- **Team filtering** — show only your teams (e.g. BOS, NYR)
- **Smart refresh** — 30s refresh during live games, 5min otherwise
- **Emulator support** — preview the display on your PC before building hardware

---

## 1. Hardware Setup (code.py)

### What You Need

- Adafruit MatrixPortal S3 (or similar HUB75-compatible board)
- Two 64x64 HUB75 RGB LED matrix panels, daisy-chained (128x64 total)
- 5V power supply (4A+ per panel)

### Install Steps

1. **Install CircuitPython** on your board from https://circuitpython.org/downloads
   The board appears as a USB drive called `CIRCUITPY`.

2. **Install libraries** — copy these into `CIRCUITPY/lib/`:
   (Get them from the Adafruit CircuitPython Bundle: https://circuitpython.org/libraries)
   - `adafruit_requests`
   - `adafruit_display_text`
   - `adafruit_ticks`
   - `adafruit_datetime`
   - `neopixel`

3. **Configure WiFi** — create `CIRCUITPY/settings.toml`:
   ```
   CIRCUITPY_WIFI_SSID = "YourWiFiName"
   CIRCUITPY_WIFI_PASSWORD = "YourWiFiPassword"
   ```

4. **Add team logos** — copy the logo folders to the root of CIRCUITPY:
   ```
   CIRCUITPY/
     team0_logos/   (NFL logos — e.g. KC.bmp, BUF.bmp)
     team1_logos/   (MLB logos — e.g. NYY.bmp, LAD.bmp)
     team2_logos/   (NHL logos — e.g. BOS.bmp, TOR.bmp)
     team3_logos/   (NBA logos — e.g. LAL.bmp, GSW.bmp)
   ```
   Each file is a small .bmp named by ESPN team abbreviation.

5. **Copy code.py** to `CIRCUITPY/code.py` — it runs automatically on boot.

### Configure Filters

Edit these lines near the top of `code.py`:

```python
# Show only NHL games:
filter_leagues = ["nhl"]
filter_teams = []

# Show only your teams across all leagues:
filter_leagues = []
filter_teams = ["BOS", "NYR", "LAL"]

# Show only your NHL team:
filter_leagues = ["nhl"]
filter_teams = ["BOS"]

# Show everything (default):
filter_leagues = []
filter_teams = []
```

### Configure Timezone

```python
# EST = -5, EDT = -4, CST = -6, CDT = -5
# MST = -7, MDT = -6, PST = -8, PDT = -7
timezone_info = [-5, "EST"]
```

### Configure Refresh Speed

```python
fetch_interval_live = 30   # Seconds between refreshes during live games
fetch_interval_idle = 300  # Seconds between refreshes when no live games
```

---

## 2. LED Emulator (emulator_ticker/)

Simulates the 128x64 LED matrix in your browser so you can preview the display
without any hardware.

### Install

```bash
pip install RGBMatrixEmulator Pillow requests
```

### Run

```bash
cd emulator_ticker
python emulator_ticker.py
```

Then open **http://localhost:8888** in your browser.

### Logo Files

Place your logo folders inside `emulator_ticker/sport_logos/`:
```
emulator_ticker/
  emulator_ticker.py
  emulator_config.json
  sport_logos/
    team0_logos/   (NFL)
    team1_logos/   (MLB)
    team2_logos/   (NHL)
    team3_logos/   (NBA)
```

If a logo file is missing, it falls back to a colored block with the team initial.

Note: Logos may appear brighter in the emulator than on real hardware. The emulator
boosts very dark palette colors so they're visible on a monitor. On actual LED panels,
the original dark values display correctly.

### Emulator Display Options

Edit `emulator_config.json`:
- `"display_adapter": "browser"` — view at http://localhost:8888 (default)
- `"display_adapter": "pygame"` — desktop window
- `"pixel_style": "circle"` — round LEDs (or `"square"`, `"real"`)
- `"pixel_size": 8` — size of each LED dot

### Configure Filters

Same settings as code.py — edit lines near the top of `emulator_ticker.py`:
```python
filter_leagues = ["nhl"]
filter_teams = ["BOS"]
```

### Stop the Emulator

Press **Ctrl+C** in the terminal (or the stop button in PyCharm).

---

## 3. Text-Only Test Script (test_sports_ticker.py)

Tests the ESPN API calls and game parsing logic with no display needed.
Useful for checking that filters work and seeing team abbreviations.

### Install

```bash
pip install requests
```

### Run

```bash
python test_sports_ticker.py
```

### What It Shows

- All games found across each league
- Scores, status (live/final/scheduled)
- Which .bmp logo files you'll need for the hardware
- What refresh rate the board would use (30s vs 5min)

If the ESPN API is unreachable, it uses built-in sample data to test the
parsing logic.

### Configure Filters

Same as the other files — edit lines near the top:
```python
filter_leagues = ["nhl"]
filter_teams = ["BOS"]
```

---

## Filter Quick Reference

| What you want | filter_leagues | filter_teams |
|---|---|---|
| NHL only | `["nhl"]` | `[]` |
| NHL + NBA | `["nhl", "nba"]` | `[]` |
| Just your teams, any league | `[]` | `["BOS", "NYR", "LAL"]` |
| Only your NHL team | `["nhl"]` | `["BOS"]` |
| Everything (no filter) | `[]` | `[]` |

Team abbreviations use ESPN's format. Run `test_sports_ticker.py` with no
filters to see all abbreviations.

---

## 4. Logo Downloader (get_team_logos.py)

Downloads all team logos from ESPN, converts them to 32x32 .bmp files named
by ESPN's exact abbreviation, and organizes them into the correct folders.
This guarantees filenames match what the ticker expects (e.g. `UTA.bmp` not
`UTAH.bmp`).

### Install

```bash
pip install requests Pillow
```

### Run

```bash
python get_team_logos.py
```

This creates:
```
sport_logos/
  team0_logos/   (NFL — 32 logos)
  team1_logos/   (MLB — 30 logos)
  team2_logos/   (NHL — 32 logos)
  team3_logos/   (NBA — 30 logos)
```

### Using the Logos

**For the emulator:** Copy `sport_logos/` into your `emulator_ticker/` folder.

**For the hardware:** Copy each `teamX_logos/` folder to the root of your
CIRCUITPY drive:
```
CIRCUITPY/
  team0_logos/
  team1_logos/
  team2_logos/
  team3_logos/
```

Running the script again skips logos that were already downloaded.

---

## Troubleshooting

**No games showing:** Normal on off-days. The ticker shows "NO GAMES TODAY".

**Memory errors on hardware:** Reduce the number of leagues in `filter_leagues`
to fetch less data. NHL-only uses much less memory than all four leagues.

**WiFi connection fails:** Check `settings.toml` formatting. Values must be quoted.

**Missing logo:** The team abbreviation in the filename must match ESPN's format
exactly (e.g. `WSH.bmp` not `WAS.bmp`). Run the test script to see correct names.

**Emulator logos look blank:** Some logos use very dark colors meant for LEDs.
The emulator auto-brightens them, but if one is still invisible, check that the
.bmp file exists in the correct `sport_logos/teamX_logos/` folder.
