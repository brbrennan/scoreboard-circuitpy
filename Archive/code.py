# SPDX-FileCopyrightText: 2025 Liz Clark / Prof G for Adafruit Industries
# SPDX-License-Identifier: MIT
# Displays scores for professiona l games NFL, MLB, NHL, NBA, ESPN score-tracker-style.
# Build video at: https://YouTube.com/@BuildWithProfG
# Meant for educational purposes only. Logos are properties of respective teams / leagues

import os
import gc
import ssl
import time
import wifi
import socketpool
import adafruit_requests
import adafruit_display_text.label
import board
import terminalio
import displayio
import framebufferio
import rgbmatrix
import microcontroller
from adafruit_ticks import ticks_ms, ticks_add, ticks_diff
from adafruit_datetime import datetime, timedelta
import neopixel
import digitalio

displayio.release_displays()

# SETUP
# Font color for text on matrix
font_color = 0xFFFFFF

# Your timezone UTC offset and timezone name. US zones displayed below
# EST = -5, EDT = -4, CST = -6, CDT = -5, MST = -7, MDT = -6, PST = -8, PDT = -7
timezone_info = [-5, "EST"]

# Sports and leagues to follow (must match logo folder order)
# team0_logos = NFL, team1_logos = MLB, team2_logos = NHL, team3_logos = NBA
# team4_logos = CFB, team5_logos = CBB, team6_logos = CHK
sport_names = ["football", "baseball", "hockey", "basketball",
               "football", "basketball", "hockey"]
sport_leagues = ["nfl", "mlb", "nhl", "nba",
                 "cfb", "cbb", "chk"]
logo_folders = ["team0_logos", "team1_logos", "team2_logos", "team3_logos",
                "team4_logos", "team5_logos", "team6_logos"]

# ESPN API uses different league slugs than our short names
espn_league_slugs = {
    "nfl": "nfl",
    "mlb": "mlb",
    "nhl": "nhl",
    "nba": "nba",
    "cfb": "college-football",
    "cbb": "mens-college-basketball",
    "chk": "mens-college-hockey",
}

# Display names shown on the LED
league_display_names = {
    "nfl": "NFL", "mlb": "MLB", "nhl": "NHL", "nba": "NBA",
    "cfb": "NCAAF", "cbb": "NCAAB", "chk": "NCAAH",
}

# ---- FILTER SETTINGS ----
# Filter by league: e.g. ["nhl"] or ["nhl", "nba"] or [] for all leagues
filter_leagues = ["mlb", "nhl", "nba", "cbb", "chk"]

# Filter by team abbreviation: e.g. ["BOS", "TOR", "NYR"] or [] for all teams
# Uses ESPN abbreviations (run the PC test script to see them all)
filter_teams = []

# ---- BUTTON FILTER MODES ----
# UP button cycles through these league modes.
# DOWN button toggles between all teams and your favorite teams (my_teams).
# Edit my_teams with the teams you want to follow PER LEAGUE.
# Leave a league's list empty [] to see all teams in that league.
my_teams = {
    "nhl": ["BOS"],
    "nba": ["BOS"],
    "nfl": ["NE"],
    "mlb": ["BOS"],
    "cfb": ["BC"],
    "cbb": ["BC"],
    "chk": ["BC"],
}

# League modes the UP button cycles through
league_modes = [
    {"name": "ALL", "leagues": []},
    {"name": "NHL", "leagues": ["nhl"]},
    {"name": "NBA", "leagues": ["nba"]},
    {"name": "NFL", "leagues": ["nfl"]},
    {"name": "MLB", "leagues": ["mlb"]},
    {"name": "NCAAF", "leagues": ["cfb"]},
    {"name": "NCAAB", "leagues": ["cbb"]},
    {"name": "NCAAH", "leagues": ["chk"]},
]
current_league_mode = 0
my_teams_active = False  # DOWN button toggles this

# Setup buttons (built-in on MatrixPortal S3)
button_up = digitalio.DigitalInOut(board.BUTTON_UP)
button_up.direction = digitalio.Direction.INPUT
button_up.pull = digitalio.Pull.UP

button_down = digitalio.DigitalInOut(board.BUTTON_DOWN)
button_down.direction = digitalio.Direction.INPUT
button_down.pull = digitalio.Pull.UP

# Debounce tracking
last_button_time = 0
DEBOUNCE_MS = 300  # Minimum milliseconds between button presses

# Time between ESPN API calls for score refresh (seconds)
# Uses the fast interval when any game is live, slow interval otherwise
fetch_interval_live = 30   # 30 seconds when games are in progress
fetch_interval_idle = 300  # 5 minutes when no live games

# Time to display each game (seconds)
display_interval = 5  # 5 seconds per game

# ============================================================
#  MATRIX PANEL CONFIGURATION
#  Uncomment the setup that matches your hardware.
# ============================================================
pixel = neopixel.NeoPixel(board.NEOPIXEL, 1, brightness=0.3, auto_write=True)

# --- OPTION A: Four 64x32 panels in a 2x2 grid (128x64) ---
# This matches the Adafruit LED Matrix Sports Scoreboard guide.
# Two panels across, two panels tall, daisy-chained in serpentine.
base_width = 64
base_height = 32   # 32-row panels
chain_across = 2   # Two panels side by side
tile_down = 2      # Two panels stacked vertically

# --- OPTION B: Two 64x64 panels side by side (128x64) ---
# Uncomment below and comment out Option A if using 64x64 panels.
# base_width = 64
# base_height = 64   # 64-row panels
# chain_across = 2   # Two panels side by side
# tile_down = 1      # Single row of panels

DISPLAY_WIDTH = base_width * chain_across  # 128
DISPLAY_HEIGHT = base_height * tile_down  # 64

# Address pins: 32-row panels use A-D (4 pins), 64-row panels need A-E (5 pins)
addr_pins = [
    board.MTX_ADDRA,
    board.MTX_ADDRB,
    board.MTX_ADDRC,
    board.MTX_ADDRD,
]
if base_height == 64:
    addr_pins.append(board.MTX_ADDRE)

matrix = rgbmatrix.RGBMatrix(
    width=DISPLAY_WIDTH,
    height=DISPLAY_HEIGHT,
    bit_depth=4,
    rgb_pins=[
        board.MTX_R1,
        board.MTX_G1,
        board.MTX_B1,
        board.MTX_R2,
        board.MTX_G2,
        board.MTX_B2
    ],
    addr_pins=addr_pins,
    clock_pin=board.MTX_CLK,
    latch_pin=board.MTX_LAT,
    output_enable_pin=board.MTX_OE,
    tile=tile_down,
    serpentine=True,
    doublebuffer=True
)

display = framebufferio.FramebufferDisplay(matrix, auto_refresh=False)

# Connect to WiFi - IMPORTANT Requires properly configured settings.toml file for your WiFi!!!
# No API key required, though.

print("Connecting to WiFi...")
wifi.radio.connect(os.getenv("CIRCUITPY_WIFI_SSID"), os.getenv("CIRCUITPY_WIFI_PASSWORD"))
print(f"Connected to {os.getenv('CIRCUITPY_WIFI_SSID')}")

context = ssl.create_default_context()
pool = socketpool.SocketPool(wifi.radio)
requests = adafruit_requests.Session(pool, context)

# Builds URL used for API call to include all leagues in sports_leagues list.
SPORT_URLS = []
for i in range(len(sport_leagues)):
    league = sport_leagues[i]
    espn_slug = espn_league_slugs[league]
    url = f"https://site.api.espn.com/apis/site/v2/sports/{sport_names[i]}/{espn_slug}/scoreboard"
    SPORT_URLS.append(url)
    print(f"Added URL for {league_display_names[league]}")

# Print active filters
if filter_leagues:
    print(f"Filtering leagues: {', '.join(l.upper() for l in filter_leagues)}")
if filter_teams:
    print(f"Filtering teams: {', '.join(filter_teams)}")
if not filter_leagues and not filter_teams:
    print("No filters active - showing all games")

# Date/Time conversion - Convert UTC time from ESPN API to local timezone display format.
def convert_date_format(date_str, tz_info):
    try:
        year = int(date_str[0:4])
        month = int(date_str[5:7])
        day = int(date_str[8:10])
        hour = int(date_str[11:13])
        minute = int(date_str[14:16])

        dt = datetime(year, month, day, hour, minute)
        dt_adjusted = dt + timedelta(hours=tz_info[0])

        month = dt_adjusted.month
        day = dt_adjusted.day
        hour = dt_adjusted.hour
        minute = dt_adjusted.minute

        am_pm = "AM" if hour < 12 else "PM"
        hour_12 = hour if hour <= 12 else hour - 12
        if hour_12 == 0:
            hour_12 = 12

        return f"{month}/{day} {hour_12}:{minute:02d}{am_pm}"
    except Exception as e:
        print(f"Date conversion error: {e}")
        return "TBD"

# Get the logo folder index for a league.
def get_league_index(league):
    try:
        return sport_leagues.index(league)
    except ValueError:
        return 0

# Fetch all games from all leagues and return a list of game data
def fetch_all_games():
    all_games = []

    for league_idx, url in enumerate(SPORT_URLS):
        league = sport_leagues[league_idx]

        # Skip leagues not in filter (if filter is set)
        if filter_leagues and league not in filter_leagues:
            print(f"Skipping {league.upper()} (filtered out)")
            continue

        print(f"Fetching {league.upper()} games...")
        pixel.fill((0, 0, 255))  # Blue while fetching

        try:
            resp = requests.get(url)
            data = resp.json()
            resp.close()

            events = data.get("events", [])
            print(f"  Found {len(events)} {league.upper()} games")

            for event in events:
                try:
                    game = parse_game(event, league_idx)
                    if game:
                        # Apply team filter
                        if filter_teams and game["home_team"] not in filter_teams and game["away_team"] not in filter_teams:
                            continue
                        all_games.append(game)
                except Exception as e:
                    print(f"  Error parsing game: {e}")
                    continue

        except Exception as e:
            print(f"  Error fetching {league.upper()}: {e}")
            continue

        gc.collect()

    pixel.fill((0, 0, 0))  # Turn off LED
    print(f"Total games after filtering: {len(all_games)}")
    return all_games

# Parse a single game event into a display-friendly dictionary.
def parse_game(event, league_idx):
    try:
        competition = event["competitions"][0]
        competitors = competition["competitors"]

        if len(competitors) != 2:
            return None

        # Get team info - ESPN lists home team first (index 0)
        home_team = competitors[0]["team"]["abbreviation"]
        away_team = competitors[1]["team"]["abbreviation"]
        home_score = competitors[0].get("score", "0")
        away_score = competitors[1].get("score", "0")

        # Get game status
        status_type = event["status"]["type"]
        status_name = status_type.get("name", "STATUS_SCHEDULED")
        status_detail = status_type.get("shortDetail", "")

        # Get game date
        game_date = event.get("date", "")

        # Determine display status
        if status_name == "STATUS_FINAL":
            display_status = "FINAL"
        elif status_name == "STATUS_IN_PROGRESS":
            display_status = status_detail  # e.g., "Q3 5:42" or "2nd 12:30"
        elif status_name == "STATUS_SCHEDULED":
            display_status = convert_date_format(game_date, timezone_info)
        elif status_name == "STATUS_POSTPONED":
            display_status = "POSTPONED"
        elif status_name == "STATUS_CANCELED":
            display_status = "CANCELED"
        else:
            display_status = status_detail if status_detail else "SCHEDULED"

        return {
            "league": league_display_names.get(sport_leagues[league_idx], sport_leagues[league_idx].upper()),
            "league_idx": league_idx,
            "home_team": home_team,
            "away_team": away_team,
            "home_score": str(home_score),
            "away_score": str(away_score),
            "status": display_status,
            "is_final": status_name == "STATUS_FINAL",
            "is_live": status_name == "STATUS_IN_PROGRESS",
            "is_scheduled": status_name == "STATUS_SCHEDULED",
        }
    except Exception as e:
        print(f"Parse error: {e}")
        return None

# Build a displayio Group for a single game
def build_game_display(game):
    group = displayio.Group()

    league_idx = game["league_idx"]
    folder = logo_folders[league_idx]

    # Load team logos
    try:
        home_logo_path = f"/{folder}/{game['home_team']}.bmp"
        home_bitmap = displayio.OnDiskBitmap(home_logo_path)
        home_grid = displayio.TileGrid(home_bitmap, pixel_shader=home_bitmap.pixel_shader, x=4, y=4)
        group.append(home_grid)
    except Exception as e:
        print(f"Can't load home logo {game['home_team']}: {e}")

    try:
        away_logo_path = f"/{folder}/{game['away_team']}.bmp"
        away_bitmap = displayio.OnDiskBitmap(away_logo_path)
        away_grid = displayio.TileGrid(away_bitmap, pixel_shader=away_bitmap.pixel_shader, x=92, y=4)
        group.append(away_grid)
    except Exception as e:
        print(f"Can't load away logo {game['away_team']}: {e}")

    # League label at top center
    league_label = adafruit_display_text.label.Label(
        terminalio.FONT,
        color=0xFFFF00,  # Yellow
        text=game["league"]
    )
    league_label.anchor_point = (0.5, 0.0)
    league_label.anchored_position = (DISPLAY_WIDTH // 2, 2)
    group.append(league_label)

    # Team abbreviations below logos
    home_abbr = adafruit_display_text.label.Label(
        terminalio.FONT,
        color=font_color,
        text=game["home_team"]
    )
    home_abbr.anchor_point = (0.5, 0.0)
    home_abbr.anchored_position = (20, 38)
    group.append(home_abbr)

    away_abbr = adafruit_display_text.label.Label(
        terminalio.FONT,
        color=font_color,
        text=game["away_team"]
    )
    away_abbr.anchor_point = (0.5, 0.0)
    away_abbr.anchored_position = (108, 38)
    group.append(away_abbr)

    # Score or VS in center
    if game["is_scheduled"]:
        score_text = "VS"
        score_color = font_color
    else:
        score_text = f"{game['home_score']} - {game['away_score']}"
        score_color = 0x00FF00 if game["is_live"] else font_color  # Green if live

    score_label = adafruit_display_text.label.Label(
        terminalio.FONT,
        color=score_color,
        text=score_text
    )
    score_label.anchor_point = (0.5, 0.5)
    score_label.anchored_position = (DISPLAY_WIDTH // 2, 24)
    group.append(score_label)

    # Status at bottom
    status_label = adafruit_display_text.label.Label(
        terminalio.FONT,
        color=0xFF0000 if game["is_live"] else font_color,  # Red if live
        text=game["status"]
    )
    status_label.anchor_point = (0.5, 1.0)
    status_label.anchored_position = (DISPLAY_WIDTH // 2, DISPLAY_HEIGHT - 2)
    group.append(status_label)

    return group

# Display a startup message
def show_startup():
    group = displayio.Group()

    title = adafruit_display_text.label.Label(
        terminalio.FONT,
        color=0xFFFF00,
        text="SPORTS TICKER"
    )
    title.anchor_point = (0.5, 0.5)
    title.anchored_position = (DISPLAY_WIDTH // 2, 20)
    group.append(title)

    subtitle = adafruit_display_text.label.Label(
        terminalio.FONT,
        color=font_color,
        text="Loading..."
    )
    subtitle.anchor_point = (0.5, 0.5)
    subtitle.anchored_position = (DISPLAY_WIDTH // 2, 40)
    group.append(subtitle)

    display.root_group = group
    display.refresh(minimum_frames_per_second=0)

# Display a message if no games are found
def show_no_games():
    group = displayio.Group()

    msg = adafruit_display_text.label.Label(
        terminalio.FONT,
        color=font_color,
        text="NO GAMES TODAY"
    )
    msg.anchor_point = (0.5, 0.5)
    msg.anchored_position = (DISPLAY_WIDTH // 2, DISPLAY_HEIGHT // 2)
    group.append(msg)

    display.root_group = group
    display.refresh(minimum_frames_per_second=0)

# Display the current filter mode briefly on screen
def show_mode():
    group = displayio.Group()

    mode = league_modes[current_league_mode]
    mode_text = mode["name"]
    if my_teams_active:
        if filter_teams:
            teams_text = "MY TEAMS"
        else:
            teams_text = "ALL TEAMS"  # No favorites set for this league
    else:
        teams_text = "ALL TEAMS"

    title = adafruit_display_text.label.Label(
        terminalio.FONT,
        color=0xFFFF00,
        text=mode_text
    )
    title.anchor_point = (0.5, 0.5)
    title.anchored_position = (DISPLAY_WIDTH // 2, 20)
    group.append(title)

    subtitle = adafruit_display_text.label.Label(
        terminalio.FONT,
        color=0x00FF00,
        text=teams_text
    )
    subtitle.anchor_point = (0.5, 0.5)
    subtitle.anchored_position = (DISPLAY_WIDTH // 2, 40)
    group.append(subtitle)

    display.root_group = group
    display.refresh(minimum_frames_per_second=0)

# Apply current button mode to the filter settings
def apply_filters():
    global filter_leagues, filter_teams
    mode = league_modes[current_league_mode]
    filter_leagues = mode["leagues"]

    if my_teams_active:
        # Build team list based on which leagues are active
        if filter_leagues:
            # Specific league selected - use that league's teams
            filter_teams = []
            for league in filter_leagues:
                filter_teams.extend(my_teams.get(league, []))
        else:
            # ALL leagues - combine all teams from all leagues
            filter_teams = []
            for league_teams in my_teams.values():
                filter_teams.extend(league_teams)
    else:
        filter_teams = []

    print(f"Filter mode: {mode['name']} | Teams: {', '.join(filter_teams) if filter_teams else 'ALL'}")

# Check for button presses (returns True if filters changed)
def check_buttons():
    global current_league_mode, my_teams_active, last_button_time
    current = ticks_ms()

    # Debounce check
    if ticks_diff(current, last_button_time) < DEBOUNCE_MS:
        return False

    changed = False

    # UP button - cycle league modes (buttons are active LOW with pull-up)
    if not button_up.value:
        current_league_mode = (current_league_mode + 1) % len(league_modes)
        last_button_time = current
        changed = True
        print(f"UP pressed -> {league_modes[current_league_mode]['name']}")

    # DOWN button - toggle my teams on/off
    if not button_down.value:
        my_teams_active = not my_teams_active
        last_button_time = current
        changed = True
        print(f"DOWN pressed -> {'MY TEAMS' if my_teams_active else 'ALL TEAMS'}")

    if changed:
        apply_filters()
        show_mode()
        time.sleep(1.5)  # Show mode briefly

    return changed

print("=" * 40)
print("Sports Ticker Starting")
print(f"Display: {DISPLAY_WIDTH}x{DISPLAY_HEIGHT}")
print(f"My teams:")
for league, teams in my_teams.items():
    if teams:
        print(f"  {league.upper()}: {', '.join(teams)}")
print("UP button: cycle leagues | DOWN button: toggle my teams")
if filter_leagues:
    print(f"Leagues: {', '.join(l.upper() for l in filter_leagues)}")
if filter_teams:
    print(f"Teams: {', '.join(filter_teams)}")
print("=" * 40)

# Show startup screen
show_startup()
time.sleep(2)

# Initial fetch
games = fetch_all_games()

if not games:
    print("No games found on initial fetch")
    show_no_games()
    time.sleep(10)
    games = fetch_all_games()

# Convert intervals to milliseconds
fetch_interval_live_ms = fetch_interval_live * 1000
fetch_interval_idle_ms = fetch_interval_idle * 1000
display_interval_ms = display_interval * 1000

# Check if any games are currently live
def any_games_live(game_list):
    return any(g["is_live"] for g in game_list)

# Set initial fetch interval based on whether games are live
fetch_interval_ms = fetch_interval_live_ms if any_games_live(games) else fetch_interval_idle_ms

# Initialize timers
fetch_clock = ticks_ms()
display_clock = ticks_ms()
game_index = 0

# ============================================================
#  SCORE CHANGE ALERTS
#  Detects goals/runs/scores in NHL, NFL, MLB and flashes an alert.
#  Basketball is excluded (too many baskets).
# ============================================================
alert_leagues = ["NHL", "MLB", "NFL", "NCAAF", "NCAAH"]
previous_scores = {}  # key: "LEAGUE-HOME-AWAY", value: (home_score, away_score)

def get_game_key(game):
    return f"{game['league']}-{game['home_team']}-{game['away_team']}"

def detect_score_changes(old_games, new_games):
    """Compare old vs new scores. Returns list of games where score changed."""
    # Build lookup from old games
    old_lookup = {}
    for g in old_games:
        if g["is_live"] and g["league"] in alert_leagues:
            old_lookup[get_game_key(g)] = (g["home_score"], g["away_score"])

    changed = []
    for g in new_games:
        if not g["is_live"]:
            continue
        if g["league"] not in alert_leagues:
            continue
        key = get_game_key(g)
        new_score = (g["home_score"], g["away_score"])
        if key in old_lookup and old_lookup[key] != new_score:
            print(f"  SCORE CHANGE: {g['away_team']} @ {g['home_team']} {old_lookup[key][0]}-{old_lookup[key][1]} -> {new_score[0]}-{new_score[1]}")
            changed.append(g)
    return changed

def build_alert_display(game):
    """Build a score alert display with GOAL!/SCORE! header."""
    group = displayio.Group()

    league_idx = game["league_idx"]
    folder = logo_folders[league_idx]

    # Load team logos
    try:
        home_bitmap = displayio.OnDiskBitmap(f"/{folder}/{game['home_team']}.bmp")
        group.append(displayio.TileGrid(home_bitmap, pixel_shader=home_bitmap.pixel_shader, x=4, y=4))
    except Exception:
        pass
    try:
        away_bitmap = displayio.OnDiskBitmap(f"/{folder}/{game['away_team']}.bmp")
        group.append(displayio.TileGrid(away_bitmap, pixel_shader=away_bitmap.pixel_shader, x=92, y=4))
    except Exception:
        pass

    # Alert text at top
    if game["league"] in ("NHL", "NCAAH"):
        alert_text = "GOAL!"
    elif game["league"] in ("NFL", "NCAAF"):
        alert_text = "SCORE!"
    else:
        alert_text = "RUN SCORED!"

    alert_label = adafruit_display_text.label.Label(
        terminalio.FONT, color=0xFFFF00, text=alert_text)
    alert_label.anchor_point = (0.5, 0.0)
    alert_label.anchored_position = (DISPLAY_WIDTH // 2, 2)
    group.append(alert_label)

    # Team abbreviations
    home_abbr = adafruit_display_text.label.Label(
        terminalio.FONT, color=font_color, text=game["home_team"])
    home_abbr.anchor_point = (0.5, 0.0)
    home_abbr.anchored_position = (20, 38)
    group.append(home_abbr)

    away_abbr = adafruit_display_text.label.Label(
        terminalio.FONT, color=font_color, text=game["away_team"])
    away_abbr.anchor_point = (0.5, 0.0)
    away_abbr.anchored_position = (108, 38)
    group.append(away_abbr)

    # Score in bright green
    score_label = adafruit_display_text.label.Label(
        terminalio.FONT, color=0x00FF00,
        text=f"{game['home_score']} - {game['away_score']}")
    score_label.anchor_point = (0.5, 0.5)
    score_label.anchored_position = (DISPLAY_WIDTH // 2, 24)
    group.append(score_label)

    # Status at bottom in red
    status_label = adafruit_display_text.label.Label(
        terminalio.FONT, color=0xFF0000, text=game["status"])
    status_label.anchor_point = (0.5, 1.0)
    status_label.anchored_position = (DISPLAY_WIDTH // 2, DISPLAY_HEIGHT - 2)
    group.append(status_label)

    return group

def show_score_alerts(changed_games):
    """Flash each changed game as an alert, then return to normal cycle."""
    for game in changed_games:
        print(f"  ALERT: {game['league']} {game['away_team']} @ {game['home_team']} {game['home_score']}-{game['away_score']}")
        gc.collect()

        # Flash 3 times
        for i in range(3):
            display.root_group = build_alert_display(game)
            display.refresh(minimum_frames_per_second=0)
            time.sleep(0.5)
            if i < 2:
                display.root_group = displayio.Group()  # blank flash
                display.refresh(minimum_frames_per_second=0)
                time.sleep(0.2)

        # Hold final alert
        time.sleep(2)
        gc.collect()

is_live = any_games_live(games)
print(f"Starting ticker with {len(games)} games")
print(f"Live games: {'YES' if is_live else 'NO'}")
print(f"Fetch interval: {fetch_interval_live if is_live else fetch_interval_idle}s, Display interval: {display_interval}s")

# Main loop
while True:
    try:
        current_time = ticks_ms()

        # Check for button presses
        if check_buttons():
            # Re-fetch with new filters
            print("Filters changed, refreshing...")
            gc.collect()
            games = fetch_all_games()
            fetch_clock = ticks_ms()
            game_index = 0

            if not games:
                show_no_games()
                time.sleep(2)
                continue

            is_live = any_games_live(games)
            fetch_interval_ms = fetch_interval_live_ms if is_live else fetch_interval_idle_ms
            continue

        # Time to refresh data from ESPN?
        if ticks_diff(current_time, fetch_clock) >= fetch_interval_ms:
            print("Refreshing game data...")
            gc.collect()
            new_games = fetch_all_games()
            fetch_clock = ticks_add(fetch_clock, fetch_interval_ms)

            if new_games:
                # Detect score changes before updating games list
                changed = detect_score_changes(games, new_games)
                games = new_games

                # Flash alerts for any score changes
                if changed:
                    # Save current position
                    saved_index = game_index
                    show_score_alerts(changed)

                    # Show each changed game's updated score briefly
                    for cg in changed:
                        for idx, g in enumerate(games):
                            if get_game_key(g) == get_game_key(cg):
                                gc.collect()
                                display.root_group = build_game_display(g)
                                display.refresh(minimum_frames_per_second=0)
                                time.sleep(display_interval)
                                break

                    # Restore position
                    game_index = saved_index
                    if game_index >= len(games):
                        game_index = 0
                    display_clock = ticks_ms()

                # Keep game_index in bounds but don't reset to 0
                if game_index >= len(games):
                    game_index = 0
            elif not games:
                show_no_games()
                fetch_interval_ms = fetch_interval_idle_ms
                time.sleep(5)
                continue

            # Switch fetch speed based on live games
            is_live = any_games_live(games)
            new_interval = fetch_interval_live_ms if is_live else fetch_interval_idle_ms
            if new_interval != fetch_interval_ms:
                if is_live:
                    print(f"Live game detected! Refreshing every {fetch_interval_live}s")
                else:
                    print(f"No live games. Refreshing every {fetch_interval_idle}s")
                fetch_interval_ms = new_interval

        # Time to show next game?
        if ticks_diff(current_time, display_clock) >= display_interval_ms:
            if games:
                # Build and display current game
                game = games[game_index]
                print(f"Showing: {game['league']} - {game['away_team']} @ {game['home_team']}")

                gc.collect()
                game_group = build_game_display(game)
                display.root_group = game_group
                display.refresh(minimum_frames_per_second=0)

                # Advance to next game
                game_index = (game_index + 1) % len(games)

            display_clock = ticks_add(display_clock, display_interval_ms)

        # Small delay to prevent tight loop
        time.sleep(0.1)

    except MemoryError:
        print("Memory error - resetting...")
        gc.collect()
        time.sleep(5)
        microcontroller.reset()

    except Exception as e:
        print(f"Error in main loop: {e}")
        time.sleep(10)
        gc.collect()
        time.sleep(5)
        microcontroller.reset()
