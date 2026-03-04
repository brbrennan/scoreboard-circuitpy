# Sports Ticker — LED Matrix Scoreboard

## What Is This?

A live sports scoreboard that hangs on your wall. It connects to WiFi, pulls real game scores from ESPN, and displays them on a glowing LED matrix with team logos, scores, and flashing alerts when someone scores.

Think of it like having a mini jumbotron in your house that automatically cycles through every game happening across multiple sports leagues.

---

## What You See on the Display

The 128×64 pixel LED display shows one game at a time, cycling every 5 seconds:

```
           ┌──────────────────────────────┐
  Row 1    │           NHL                │  League name (yellow)
           │                              │
  Row 2    │  [Away Logo]  3 - 1  [Home]  │  Team logos with score
           │                              │
  Row 3    │     TOR              BOS     │  Team abbreviations
  Row 4    │        2nd Period            │  Game status (green=live)
           └──────────────────────────────┘
```

- **Away team** is always on the **left**
- **Home team** is always on the **right**
- **Score** reads left-to-right matching the logos (away score - home score)
- **Status line** is color-coded: green = live, red = final, gray = scheduled

---

## Supported Leagues

The ticker cycles through leagues in this order:

| # | League | Sport | Score Alert |
|---|--------|-------|-------------|
| 1 | NFL | Football | "TOUCHDOWN!" |
| 2 | MLB | Baseball | "RUN SCORED!" |
| 3 | NHL | Hockey | "GOAL!" |
| 4 | NCAAH | College Hockey | "GOAL!" |
| 5 | NBA | Basketball | None (scores too often) |
| 6 | NCAAF | College Football | "TOUCHDOWN!" |
| 7 | NCAAB | College Basketball | None (scores too often) |

All scores come from ESPN's free public API. No API key or account needed.

---

## Score Change Alerts

When a goal, run, or touchdown is scored in a live game, the ticker interrupts its normal cycle and plays a ~5-second animation:

1. **Old score flashing** (~1.6s) — The alert text (e.g., "GOAL!") flashes red at the bottom. The number that's about to change blinks on and off so your eye is drawn to it.

2. **New score revealed** (~1.6s) — The score updates. The changed number flashes green so you can instantly see which team scored.

3. **Hold** (~1s) — The final score is displayed cleanly so you can read it.

Basketball leagues (NBA and NCAAB) don't trigger alerts because scoring happens too frequently.

---

## Button Controls

The MatrixPortal S3 has two built-in buttons:

**UP button (left)** — Cycles through league filters. Each press shows only one league:
- Press 1: NFL only
- Press 2: MLB only
- Press 3: NHL only
- Press 4: NCAAH only
- Press 5: NBA only
- Press 6: NCAAF only
- Press 7: NCAAB only
- Press 8: Back to ALL leagues

When filtered, the league name appears in the bottom-left corner in blue.

**DOWN button (right)** — Toggles between all teams and your favorites only. When active, "FAV" appears in the bottom-right corner in yellow. Only games involving your favorite teams are shown.

Both buttons show immediate visual feedback ("Loading...") and include debounce protection (250ms) so accidental double-presses are ignored.

---

## Hardware Required

| Part | Description |
|------|-------------|
| Adafruit MatrixPortal S3 | The brain — ESP32-S3 with WiFi, plugs directly into the LED panels |
| 4× HUB75 64×32 LED panels | The display — arranged in a 2×2 grid for 128×64 total resolution |
| 5V power supply (4A+) | Powers the LEDs — these panels are hungry! |
| USB-C cable | For programming and serial monitoring |

The four panels are wired in a **serpentine** pattern: the second row is flipped 180° relative to the first, which simplifies cabling.

---

## Software Setup

### Step 1: Install Arduino IDE

Download and install the [Arduino IDE](https://www.arduino.cc/en/software) (version 2.x recommended).

### Step 2: Add ESP32-S3 Board Support

1. Open Arduino IDE
2. Go to **File → Preferences**
3. In "Additional Board Manager URLs" add:
   ```
   https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
   ```
4. Go to **Tools → Board → Board Manager**
5. Search "esp32" and install **esp32 by Espressif Systems**
6. Select board: **Tools → Board → esp32 → Adafruit MatrixPortal ESP32-S3**

### Step 3: Install Required Libraries

Open **Tools → Manage Libraries** and install:

- **Adafruit Protomatter** — drives the LED panels
- **Adafruit GFX Library** — graphics primitives (text, shapes, pixels)
- **Adafruit NeoPixel** — controls the onboard status LED
- **ArduinoJson** by Benoit Blanchon — parses ESPN's JSON responses

LittleFS is built into the ESP32 core, no separate install needed.

### Step 4: Create Your Secrets File

Create a file called `secrets.h` in the same folder as `sports_ticker.ino`:

```cpp
#define WIFI_SSID     "YourNetworkName"
#define WIFI_PASSWORD "YourPassword"
```

**Important:** Never share this file or commit it to GitHub. It contains your WiFi password.

### Step 5: Upload Team Logos

Logos are stored on the MatrixPortal's flash memory using LittleFS. Each league has its own folder:

| Folder | League |
|--------|--------|
| `team0_logos/` | NFL |
| `team1_logos/` | MLB |
| `team2_logos/` | NHL |
| `team3_logos/` | NBA |
| `team4_logos/` | NCAAF |
| `team5_logos/` | NCAAB |
| `team6_logos/` | NCAAH |

Each logo is a **32×32 pixel BMP file** named by ESPN abbreviation (e.g., `BOS.bmp`, `NYR.bmp`).

Use the included `get_team_logos.py` script to download and convert all logos automatically:

```bash
python get_team_logos.py
```

To upload the logos to the board, install the **ESP32 LittleFS upload plugin** for Arduino IDE, place the logo folders inside a `data/` directory next to your sketch, and use **Tools → ESP32 Sketch Data Upload**.

### Step 6: Upload the Sketch

1. Connect the MatrixPortal S3 via USB-C
2. Select the correct port in **Tools → Port**
3. Click **Upload** (the arrow button)
4. Open **Tools → Serial Monitor** (set to 115200 baud) to see debug output

---

## Customizing Your Ticker

### Change Your Favorite Teams

Edit the `my_teams` arrays near line 128. Use ESPN abbreviations:

```cpp
const char* my_nhl[]   = {"BOS", NULL};         // One team
const char* my_mlb[]   = {"BOS", "NYY", NULL};  // Multiple teams
const char* my_nba[]   = {"BOS", NULL};
```

Always end each list with `NULL` — it tells the code "that's the end of the list."

To find the right abbreviation for a team, check the ESPN scoreboard for that sport — the abbreviation shown on their website is what the API uses.

### Enable or Disable Leagues

Edit the `enabled_leagues` array near line 115:

```cpp
bool enabled_leagues[] = {
  false,  // NFL     — disabled (off-season)
  true,   // MLB     — enabled
  true,   // NHL     — enabled
  true,   // NCAAH   — enabled
  true,   // NBA     — enabled
  false,  // NCAAF   — disabled (off-season)
  true,   // NCAAB   — enabled
};
```

Set a league to `false` to skip it entirely. Useful for hiding off-season leagues so the ticker doesn't waste time fetching empty scoreboards.

### Change the Display Cycle Speed

Edit the timing constants near line 174:

```cpp
unsigned long display_interval = 5000;        // How long each game shows (ms)
unsigned long fetch_interval_live = 60000;    // How often to check ESPN during live games
unsigned long fetch_interval_idle = 300000;   // How often to check ESPN when no live games
```

### Change the League Order

The ticker displays games in the order the leagues appear in the arrays at the top of the file. To reorder, rearrange all the parallel arrays together — `league_names`, `sport_names`, `espn_slugs`, `logo_folders`, `alert_messages`, `enabled_leagues`, and `my_teams` must all stay in sync.

---

## How It Works (Technical Overview)

### Boot Sequence
1. Initialize the LED matrix (Protomatter library with hardware timer interrupt)
2. Connect to WiFi
3. Show "Loading games..." splash screen
4. Fetch scores from ESPN for all enabled leagues
5. Begin the display cycle

### Main Loop (runs ~20 times per second)
1. Check if either button was pressed → apply filter, re-fetch
2. Check if it's time to re-fetch scores from ESPN → fetch and compare for score changes
3. Check if it's time to show the next game → render it on the display

### ESPN API Communication
The ticker connects to ESPN over plain HTTP (port 80) using HTTP/1.0 to avoid chunked transfer encoding issues on the ESP32. It uses ArduinoJson's stream filter to parse only the fields it needs directly from the network stream — this keeps memory usage low even when ESPN sends back 100KB+ responses.

### Score Change Detection
After each fetch, the ticker compares every live game's scores against the previous fetch. If the total score increased, it identifies which team scored (by comparing individual home/away scores) and triggers the alert animation.

### Display Rendering
The Protomatter library drives the LED panels using a hardware timer interrupt. This means the display keeps refreshing (no flickering) even when the main code is busy fetching data. All drawing goes to a back buffer, then `matrix.show()` atomically swaps it to the front — so there's never a partially-drawn frame visible.

---

## Troubleshooting

**Display is blank or garbled** — Check panel wiring and power. These panels need a good 5V supply with at least 4 amps. The serpentine tiling (`-2`) requires the second row of panels to be physically rotated 180°.

**No games showing** — Open Serial Monitor at 115200 baud. Look for "Fetching NHL..." messages. If you see "Connect failed" or "JSON error", check your WiFi connection. If you see "0 events" for every league, there may genuinely be no games today.

**Logos not appearing** — Make sure the logo BMP files are uploaded to LittleFS and the filenames match ESPN abbreviations exactly (case-sensitive). The fallback is a colored block with the team's first letter.

**Buttons not responding** — The MatrixPortal S3 buttons are on pins 6 (UP) and 7 (DOWN). Serial Monitor should print button state at boot: `Buttons: UP=pin6(HIGH) DOWN=pin7(HIGH)`. If a button reads LOW at boot, it may be stuck or wired wrong.

**Scores not updating for some leagues** — If the JSON buffer is too small, parsing fails silently for leagues with many games. Check Serial Monitor for "JSON error: NoMemory" messages. The buffer is set to 24KB which handles most days, but a packed NCAAB tournament slate may need more.

---

## File Inventory

| File | Purpose |
|------|---------|
| `sports_ticker_golden.ino` | The golden baseline — the known-good version to roll back to |
| `sports_ticker.ino` | The working copy where new changes are made |
| `secrets.h` | Your WiFi credentials (you create this, never share it) |
| `get_team_logos.py` | Python script to download and convert team logos from ESPN |
| `data/team0_logos/` through `data/team6_logos/` | 32×32 BMP logo files organized by league |

---

## Golden Image Info

This README documents the **golden baseline** version of the sports ticker. This is the stable, tested version that all future enhancements branch from.

**Date:** March 2026
**Lines of code:** 1,167
**Features included:**
- Away-left / Home-right display layout
- 7-league support (NFL, MLB, NHL, NCAAH, NBA, NCAAF, NCAAB)
- Per-league favorite teams with button toggle
- League filter cycling with button
- Score change alerts with 3-phase animation (~5 seconds)
- Adaptive refresh intervals (60s live / 5min idle)
- Visual button feedback with debounce
- Double-buffered display rendering
- HTTP/1.0 stream parsing for large JSON responses
- LittleFS logo storage with fallback letter blocks
