# Sports Ticker — Hardware Setup Guide

## Step-by-step instructions for MatrixPortal S3 + Four 64x32 LED Matrices

---

## Shopping List

| Item | Qty | Link |
|------|-----|------|
| Adafruit MatrixPortal S3 | 1 | [adafruit.com/product/5778](https://www.adafruit.com/product/5778) |
| 64x32 RGB LED Matrix (4mm pitch) | 4 | [adafruit.com/product/2278](https://www.adafruit.com/product/2278) |
| 5V 4A Power Supply | 2 | [adafruit.com/product/1466](https://www.adafruit.com/product/1466) |
| Female DC Jack to Screw Terminal | 2 | [adafruit.com/product/368](https://www.adafruit.com/product/368) |
| USB-C cable (data + power) | 1 | Any USB-C cable that supports data |
| Black LED Diffusion Acrylic (optional) | 4 | [adafruit.com/product/4749](https://www.adafruit.com/product/4749) |

---

## Step 1 — Install Mu Editor

1. Download Mu Editor from **[codewith.mu](https://codewith.mu/en/download)**
2. Install and open it
3. When prompted for a mode, select **CircuitPython**

---

## Step 2 — Install CircuitPython on the MatrixPortal S3

1. Go to **[circuitpython.org/board/adafruit_matrixportal_s3](https://circuitpython.org/board/adafruit_matrixportal_s3/)**
2. Download the latest **stable** `.uf2` file (9.x or later)
3. Connect the MatrixPortal S3 to your computer via USB-C
4. **Double-click the RESET button** on the board quickly — a drive called **MATRIXS3BOOT** should appear
   - If it doesn't appear, your board may need the UF2 bootloader installed first. See [Adafruit's factory reset instructions](https://learn.adafruit.com/adafruit-matrixportal-s3/factory-reset)
5. Drag the `.uf2` file onto the **MATRIXS3BOOT** drive
6. The board will reboot and a new drive called **CIRCUITPY** will appear

---

## Step 3 — Install Required CircuitPython Libraries

The code needs these libraries that aren't built into CircuitPython:

- `adafruit_requests`
- `adafruit_display_text`
- `adafruit_ticks`
- `adafruit_datetime`
- `neopixel`

**How to install them:**

1. Go to **[circuitpython.org/libraries](https://circuitpython.org/libraries)**
2. Download the **Bundle for Version 9.x** (match your CircuitPython version)
3. Unzip the downloaded file
4. Open the `lib` folder inside the unzipped bundle
5. Copy these files/folders to the `lib` folder on your **CIRCUITPY** drive:

| Copy this | Type |
|-----------|------|
| `adafruit_requests.mpy` | File |
| `adafruit_display_text/` | Folder (entire folder) |
| `adafruit_ticks.mpy` | File |
| `adafruit_datetime.mpy` | File |
| `neopixel.mpy` | File |

Your CIRCUITPY `lib/` folder should now contain those 5 items.

---

## Step 4 — Set Up WiFi (settings.toml)

1. On the **CIRCUITPY** drive, find or create a file called `settings.toml`
2. Open it in Mu Editor and add:

```toml
CIRCUITPY_WIFI_SSID = "YOUR_WIFI_NAME"
CIRCUITPY_WIFI_PASSWORD = "YOUR_WIFI_PASSWORD"
```

3. Replace with your actual WiFi name and password (keep the quotes)
4. Save the file

---

## Step 5 — Download Team Logos

On your regular computer (not the board), run the logo downloader:

1. Make sure you have Python 3 installed with `Pillow` and `requests`:
   ```
   pip install Pillow requests
   ```
2. Run the logo downloader script:
   ```
   python get_team_logos.py
   ```
3. This creates a `sport_logos/` folder with subfolders:
   - `team0_logos/` (NFL)
   - `team1_logos/` (MLB)
   - `team2_logos/` (NHL)
   - `team3_logos/` (NBA)
   - `team4_logos/` (College Football)
   - `team5_logos/` (College Basketball)
   - `team6_logos/` (College Hockey)
4. Copy **all seven `teamX_logos/` folders** to the root of your **CIRCUITPY** drive

> **Note:** College sports have hundreds of teams. The download may take a few minutes. If you're low on space on the CIRCUITPY drive, you can skip the college logo folders you don't need.

---

## Step 6 — Copy code.py to the Board

1. Open `code.py` from the sports_ticker.zip in Mu Editor
2. **Edit your settings near the top of the file:**

   **Timezone** (line ~33):
   ```python
   timezone_info = [-5, "EST"]  # Change to your timezone
   ```

   **Your favorite teams** (line ~55):
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

3. Save the file as `code.py` on the **CIRCUITPY** drive (replacing any existing code.py)

---

## Step 7 — Wire the Panels

### Panel Layout (2x2 grid, 128x64 total)

Looking at the **back** of the panels:

```
┌──────────────┬──────────────┐
│  Panel 1     │  Panel 2     │  ← Top row
│  (start)     │              │
├──────────────┼──────────────┤
│  Panel 4     │  Panel 3     │  ← Bottom row
│  (rotated)   │  (rotated)   │
└──────────────┴──────────────┘
```

### Daisy-chain wiring (serpentine)

The panels chain in an S-pattern. Use the short ribbon cables that came with the panels:

1. **MatrixPortal S3** plugs directly into Panel 1's **INPUT** (left connector on back)
2. Panel 1 **OUTPUT** → ribbon cable → Panel 2 **INPUT**
3. Panel 2 **OUTPUT** → ribbon cable → Panel 3 **INPUT** (Panel 3 is rotated 180°)
4. Panel 3 **OUTPUT** → ribbon cable → Panel 4 **INPUT** (Panel 4 is rotated 180°)

> The bottom row panels (3 and 4) are physically flipped upside-down. The code's `serpentine=True` setting handles this automatically. This keeps the ribbon cables short.

### Orientation check

- The MatrixPortal S3 plugs into the **top-left panel** (Panel 1)
- The white arrow on Panel 1 should point **up and to the right**
- Remove the amber tape circles from the MatrixPortal S3 power standoffs before attaching

---

## Step 8 — Power the Panels

**Use two separate 5V 4A power supplies** — one per row of two panels.

### Power Supply 1 (top two panels):
1. Connect 5V power supply → DC jack adapter → screw terminals
2. Run the red (+5V) and black (GND) wires to Panel 1's power connector
3. Use a Y-splitter cable to also power Panel 2

### Power Supply 2 (bottom two panels):
1. Same setup for Panels 3 and 4

### MatrixPortal S3 power:
- The MatrixPortal S3 is powered separately via its **USB-C** port
- Use a USB-C cable connected to a USB power adapter or your computer

> **Important:** Do NOT try to power all four panels from a single 4A supply. The panels can draw up to 4A each at full white brightness. Insufficient power causes flickering and scrambled displays.

---

## Step 9 — Verify It Works

1. With everything wired up and powered on, the board should auto-run `code.py`
2. The NeoPixel LED on the MatrixPortal will:
   - Flash **green** = WiFi connecting
   - Flash **blue** = fetching data from ESPN
   - Turn **off** = running normally
3. The display should show "Loading..." then start cycling through games
4. If you see the Mu Editor serial console (click "Serial" button), you'll see debug output

### Button Controls

The MatrixPortal S3 has two built-in buttons:

| Button | Location | Action |
|--------|----------|--------|
| UP (BUTTON_UP) | Middle button | Cycle leagues: ALL → NHL → NBA → NFL → MLB → NCAAF → NCAAB → NCAAH |
| DOWN (BUTTON_DOWN) | Bottom button | Toggle between ALL TEAMS and MY TEAMS |

---

## Step 10 — Final CIRCUITPY Drive Layout

When everything is set up, your CIRCUITPY drive should look like this:

```
CIRCUITPY/
├── code.py                  ← The main sports ticker code
├── settings.toml            ← WiFi credentials
├── lib/
│   ├── adafruit_requests.mpy
│   ├── adafruit_display_text/
│   ├── adafruit_ticks.mpy
│   ├── adafruit_datetime.mpy
│   └── neopixel.mpy
├── team0_logos/             ← NFL logos (32x32 BMP)
├── team1_logos/             ← MLB logos
├── team2_logos/             ← NHL logos
├── team3_logos/             ← NBA logos
├── team4_logos/             ← College Football logos
├── team5_logos/             ← College Basketball logos
└── team6_logos/             ← College Hockey logos
```

---

## Troubleshooting

### Display is blank
- Check that the MatrixPortal S3 is plugged into Panel 1's INPUT (not OUTPUT)
- Check the white arrow orientation on the panel
- Make sure the amber tape was removed from the power standoffs

### Scrambled or flickering display
- Power supply is too weak — use two 5V 4A supplies (one per row)
- Check all ribbon cable connections are firm

### "No games" message
- Verify WiFi credentials in `settings.toml`
- Check the serial console in Mu Editor for error messages
- There may simply be no games today in the leagues you have filtered

### Board doesn't show CIRCUITPY drive
- Try a different USB-C cable (some cables are charge-only, no data)
- Double-click RESET to enter bootloader mode

### MemoryError
- College sports return a lot of data. Use `filter_leagues` or `my_teams` to limit which leagues are fetched
- Reduce the number of college logo folders if the drive is full

### Updating code.py later
- Just plug in the USB-C cable, open CIRCUITPY, and drag the new `code.py` on. The board restarts automatically.

---

## Useful Links

- [Adafruit LED Matrix Sports Scoreboard Guide](https://learn.adafruit.com/led-matrix-sports-scoreboard/overview)
- [MatrixPortal S3 Guide](https://learn.adafruit.com/adafruit-matrixportal-s3)
- [Multiple Panel Wiring Guide](https://learn.adafruit.com/rgb-led-matrices-matrix-panels-with-circuitpython/advanced-multiple-panels)
- [CircuitPython Downloads for MatrixPortal S3](https://circuitpython.org/board/adafruit_matrixportal_s3/)
- [CircuitPython Library Bundle](https://circuitpython.org/libraries)
