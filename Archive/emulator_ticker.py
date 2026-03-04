"""
Sports Ticker - LED Matrix Emulator Version
Runs on your PC using RGBMatrixEmulator to visually simulate the 128x64 LED display.

Install requirements:
    pip install RGBMatrixEmulator Pillow requests

Run:
    python emulator_ticker.py

Then open http://localhost:8888 in your browser to see the display.
(Or change display_adapter to "pygame" in emulator_config.json for a desktop window)
"""

import os
import time
import threading
import sys
import requests
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont

from RGBMatrixEmulator import RGBMatrix, RGBMatrixOptions

# ============================================================
#  CONFIG - same settings as code.py, edit these to match
# ============================================================
timezone_info = [-5, "EST"]

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

# Path to sport_logos folder (relative to this script)
LOGO_BASE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sport_logos")

# ---- FILTER SETTINGS ----
filter_leagues = []     # e.g. ["nhl"] or ["nhl", "nba"] or [] for all
filter_teams = []       # e.g. ["BOS", "TOR"] or [] for all

# ---- BUTTON FILTER MODES (mirrors code.py) ----
# UP arrow / 'u' key cycles through league modes
# DOWN arrow / 'd' key toggles between all teams and my_teams
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
my_teams_active = False
button_pressed = False  # Flag for main loop to detect changes

# Refresh intervals (seconds)
fetch_interval_live = 30
fetch_interval_idle = 300

# Time to display each game (seconds)
display_interval = 5

# ============================================================
#  DISPLAY SETUP
# ============================================================
DISPLAY_WIDTH = 128
DISPLAY_HEIGHT = 64

options = RGBMatrixOptions()
options.rows = 64
options.cols = 64
options.chain_length = 2
options.parallel = 1
options.hardware_mapping = "regular"

matrix = RGBMatrix(options=options)

# Use PIL's built-in bitmap font (always available, no external files needed)
pil_font = ImageFont.load_default()

# Team colors for logo placeholders
TEAM_COLORS = {
    # NHL
    "BOS": (252, 186, 3),  "TOR": (0, 32, 159),   "NYR": (0, 56, 168),
    "MTL": (175, 30, 45),  "DET": (206, 17, 38),   "CHI": (207, 10, 44),
    "PIT": (252, 186, 3),  "WSH": (200, 16, 46),   "PHI": (247, 73, 2),
    "TB":  (0, 40, 104),   "FLA": (200, 16, 46),   "CAR": (206, 17, 38),
    "CBJ": (0, 38, 84),    "NJ":  (206, 17, 38),   "NYI": (0, 83, 155),
    "OTT": (200, 16, 46),  "BUF": (0, 38, 84),     "COL": (111, 38, 61),
    "DAL": (0, 104, 71),   "MIN": (2, 73, 48),     "STL": (0, 47, 135),
    "WPG": (4, 30, 66),    "NSH": (255, 184, 28),  "ARI": (140, 38, 51),
    "CGY": (210, 0, 28),   "EDM": (4, 30, 66),     "VAN": (0, 32, 91),
    "SEA": (0, 72, 90),    "VGK": (185, 151, 91),  "SJ":  (0, 109, 117),
    "LA":  (162, 170, 173), "ANA": (252, 76, 2),   "UTA": (105, 160, 205),
    # NBA
    "LAL": (85, 37, 130),  "GSW": (29, 66, 138),   "MIL": (0, 71, 27),
    "PHX": (29, 17, 96),   "DEN": (13, 34, 64),    "MIA": (152, 0, 46),
    "CLE": (134, 0, 56),   "ATL": (225, 68, 52),   "SAC": (91, 43, 130),
    "IND": (0, 45, 98),    "OKC": (0, 125, 195),   "MEM": (93, 118, 169),
    "CHA": (29, 17, 96),   "ORL": (0, 125, 197),   "SAS": (196, 206, 211),
    "POR": (224, 58, 62),  "HOU": (206, 17, 65),   "NO":  (0, 22, 65),
    "LAC": (200, 16, 46),  "BKN": (0, 0, 0),
    # NFL
    "KC":  (227, 24, 55),  "SF":  (170, 0, 0),     "BAL": (36, 23, 115),
    "GB":  (24, 48, 40),   "NE":  (0, 34, 68),
    # MLB
    "NYY": (0, 48, 135),   "LAD": (0, 90, 156),
}

# ============================================================
#  ESPN API (same logic as code.py)
# ============================================================
SPORT_URLS = [
    f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{espn_league_slugs[league]}/scoreboard"
    for sport, league in zip(sport_names, sport_leagues)
]

def convert_date_format(date_str, tz_info):
    try:
        dt = datetime.strptime(date_str[:16], "%Y-%m-%dT%H:%M")
        dt_adjusted = dt + timedelta(hours=tz_info[0])
        hour = dt_adjusted.hour
        am_pm = "AM" if hour < 12 else "PM"
        hour_12 = hour if hour <= 12 else hour - 12
        if hour_12 == 0:
            hour_12 = 12
        return f"{dt_adjusted.month}/{dt_adjusted.day} {hour_12}:{dt_adjusted.minute:02d}{am_pm}"
    except Exception as e:
        return "TBD"

def parse_game(event, league_idx):
    try:
        competition = event["competitions"][0]
        competitors = competition["competitors"]
        if len(competitors) != 2:
            return None

        home_team = competitors[0]["team"]["abbreviation"]
        away_team = competitors[1]["team"]["abbreviation"]
        home_score = competitors[0].get("score", "0")
        away_score = competitors[1].get("score", "0")

        status_type = event["status"]["type"]
        status_name = status_type.get("name", "STATUS_SCHEDULED")
        status_detail = status_type.get("shortDetail", "")
        game_date = event.get("date", "")

        if status_name == "STATUS_FINAL":
            display_status = "FINAL"
        elif status_name == "STATUS_IN_PROGRESS":
            display_status = status_detail
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
        return None

def fetch_all_games():
    all_games = []
    for league_idx, url in enumerate(SPORT_URLS):
        league = sport_leagues[league_idx]
        if filter_leagues and league not in filter_leagues:
            continue

        print(f"Fetching {league.upper()} games...")
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            events = data.get("events", [])
            print(f"  Found {len(events)} {league.upper()} events")

            for event in events:
                game = parse_game(event, league_idx)
                if game:
                    if filter_teams and game["home_team"] not in filter_teams and game["away_team"] not in filter_teams:
                        continue
                    all_games.append(game)
        except Exception as e:
            print(f"  Error fetching {league.upper()}: {e}")
            continue

    print(f"Total games after filtering: {len(all_games)}")
    return all_games

def any_games_live(game_list):
    return any(g["is_live"] for g in game_list)

# ============================================================
#  PIL-BASED DRAWING (renders to Image, then pushes to matrix)
# ============================================================
def text_width(text):
    """Get pixel width of text using the PIL font."""
    bbox = pil_font.getbbox(text)
    return bbox[2] - bbox[0]

def draw_text_centered(draw, y, text, color):
    """Draw text horizontally centered."""
    tw = text_width(text)
    x = (DISPLAY_WIDTH - tw) // 2
    draw.text((x, y), text, fill=color, font=pil_font)

def load_team_logo(team_abbr, league_idx, size=24):
    """Load a team's .bmp logo and resize it. Returns a PIL Image or None."""
    folder = logo_folders[league_idx]
    logo_path = os.path.join(LOGO_BASE_PATH, folder, f"{team_abbr}.bmp")
    try:
        logo = Image.open(logo_path)

        if logo.mode == "P":
            palette = logo.getpalette()  # flat list: [r0, g0, b0, r1, g1, b1, ...]
            pixel_indices = list(logo.convert("L").getdata())  # just to get count
            pixel_indices = []
            for y in range(logo.height):
                for x in range(logo.width):
                    pixel_indices.append(logo.getpixel((x, y)))

            # Find background: most common index in corner pixels
            corners = [
                pixel_indices[0],
                pixel_indices[logo.width - 1],
                pixel_indices[(logo.height - 1) * logo.width],
                pixel_indices[(logo.height - 1) * logo.width + logo.width - 1],
            ]
            bg_index = max(set(corners), key=corners.count)

            # Get all palette colors and find the max brightness of non-bg colors
            non_bg_colors = []
            for idx in set(pixel_indices):
                if idx != bg_index:
                    r = palette[idx * 3]
                    g = palette[idx * 3 + 1]
                    b = palette[idx * 3 + 2]
                    non_bg_colors.append((r, g, b))

            # Calculate brightness boost if the logo is too dark
            max_channel = 0
            for r, g, b in non_bg_colors:
                max_channel = max(max_channel, r, g, b)

            # If brightest color is below 80, scale everything up
            if max_channel > 0 and max_channel < 80:
                brightness_scale = 200.0 / max_channel
            elif max_channel > 0 and max_channel < 150:
                brightness_scale = 255.0 / max_channel
            else:
                brightness_scale = 1.0

            # Build the output image pixel by pixel
            logo_rgb = Image.new("RGB", logo.size, (0, 0, 0))
            for y in range(logo.height):
                for x in range(logo.width):
                    idx = pixel_indices[y * logo.width + x]
                    if idx == bg_index:
                        # Background = black (transparent on LED)
                        logo_rgb.putpixel((x, y), (0, 0, 0))
                    else:
                        r = min(255, int(palette[idx * 3] * brightness_scale))
                        g = min(255, int(palette[idx * 3 + 1] * brightness_scale))
                        b = min(255, int(palette[idx * 3 + 2] * brightness_scale))
                        logo_rgb.putpixel((x, y), (r, g, b))

            logo = logo_rgb

        elif logo.mode == "RGBA":
            background = Image.new("RGB", logo.size, (0, 0, 0))
            background.paste(logo, mask=logo.split()[3])
            logo = background
        else:
            logo = logo.convert("RGB")

        logo = logo.resize((size, size), Image.NEAREST)
        return logo
    except Exception as e:
        print(f"  Logo load error for {team_abbr}: {e}")
        return None

def draw_team_logo(draw, img, team_abbr, league_idx, x, y, size=24):
    """Paste a team logo onto the image, or draw a colored fallback block."""
    logo = load_team_logo(team_abbr, league_idx, size)
    if logo:
        img.paste(logo, (x, y))
    else:
        # Fallback: colored block with team initial
        color = TEAM_COLORS.get(team_abbr, (100, 100, 100))
        r, g, b = color
        draw.rectangle([x, y, x + size - 1, y + size - 1], fill=color,
                       outline=(max(r // 3, 0), max(g // 3, 0), max(b // 3, 0)))
        letter = team_abbr[0] if team_abbr else "?"
        lw = text_width(letter)
        lx = x + (size - lw) // 2
        ly = y + (size - 10) // 2
        draw.text((lx, ly), letter, fill=(255, 255, 255), font=pil_font)

def render_game(game):
    """Render a game to a PIL Image and push it to the matrix."""
    img = Image.new("RGB", (DISPLAY_WIDTH, DISPLAY_HEIGHT), (0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Colors
    white = (255, 255, 255)
    yellow = (255, 255, 0)
    green = (0, 255, 0)
    red = (255, 0, 0)
    dim = (120, 120, 120)

    # League label at top center
    draw_text_centered(draw, 1, game["league"], yellow)

    # Team logos
    draw_team_logo(draw, img, game["home_team"], game["league_idx"], 4, 10, 24)
    draw_team_logo(draw, img, game["away_team"], game["league_idx"], 100, 10, 24)

    # Team abbreviations below logos
    home_w = text_width(game["home_team"])
    draw.text((4 + (24 - home_w) // 2, 36), game["home_team"], fill=white, font=pil_font)

    away_w = text_width(game["away_team"])
    draw.text((100 + (24 - away_w) // 2, 36), game["away_team"], fill=white, font=pil_font)

    # Score or VS in center
    if game["is_scheduled"]:
        score_text = "VS"
        score_color = white
    else:
        score_text = f"{game['home_score']} - {game['away_score']}"
        score_color = green if game["is_live"] else white

    score_w = text_width(score_text)
    score_x = (DISPLAY_WIDTH - score_w) // 2
    draw.text((score_x, 20), score_text, fill=score_color, font=pil_font)

    # Status at bottom
    status_color = red if game["is_live"] else dim
    draw_text_centered(draw, DISPLAY_HEIGHT - 12, game["status"], status_color)

    # Push image to the matrix
    matrix.SetImage(img)

def render_message(text):
    """Render a centered message to the matrix."""
    img = Image.new("RGB", (DISPLAY_WIDTH, DISPLAY_HEIGHT), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw_text_centered(draw, DISPLAY_HEIGHT // 2 - 5, text, (255, 255, 0))
    matrix.SetImage(img)

def render_mode():
    """Show current filter mode on the display."""
    img = Image.new("RGB", (DISPLAY_WIDTH, DISPLAY_HEIGHT), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    mode = league_modes[current_league_mode]
    if my_teams_active and filter_teams:
        teams_text = "MY TEAMS"
    else:
        teams_text = "ALL TEAMS"
    draw_text_centered(draw, 20, mode["name"], (255, 255, 0))
    draw_text_centered(draw, 38, teams_text, (0, 255, 0))
    matrix.SetImage(img)

def apply_filters():
    """Apply current button mode to the filter settings."""
    global filter_leagues, filter_teams
    mode = league_modes[current_league_mode]
    filter_leagues = mode["leagues"]

    if my_teams_active:
        if filter_leagues:
            filter_teams = []
            for league in filter_leagues:
                filter_teams.extend(my_teams.get(league, []))
        else:
            filter_teams = []
            for league_teams in my_teams.values():
                filter_teams.extend(league_teams)
    else:
        filter_teams = []

    print(f"Filter mode: {mode['name']} | Teams: {', '.join(filter_teams) if filter_teams else 'ALL'}")

def keyboard_listener():
    """Listen for keyboard input in a background thread.
    Press 'u' for UP (cycle leagues), 'd' for DOWN (toggle my teams), 'q' to quit."""
    global current_league_mode, my_teams_active, button_pressed
    while True:
        try:
            key = input()
            if key.lower() == 'u':
                current_league_mode = (current_league_mode + 1) % len(league_modes)
                apply_filters()
                button_pressed = True
                print(f"UP -> {league_modes[current_league_mode]['name']}")
            elif key.lower() == 'd':
                my_teams_active = not my_teams_active
                apply_filters()
                button_pressed = True
                print(f"DOWN -> {'MY TEAMS' if my_teams_active else 'ALL TEAMS'}")
            elif key.lower() == 'q':
                print("Quitting...")
                os._exit(0)
        except EOFError:
            break

# ============================================================
#  SCORE CHANGE ALERTS
#  Detects goals/runs/scores in NHL, NFL, MLB and flashes an alert.
#  Basketball is excluded (too many baskets).
# ============================================================
alert_leagues = ["NHL", "MLB", "NFL", "NCAAF", "NCAAH"]

def get_game_key(game):
    return f"{game['league']}-{game['home_team']}-{game['away_team']}"

def detect_score_changes(old_games, new_games):
    """Compare old vs new scores. Returns list of games where score changed."""
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
            print(f"  SCORE CHANGE: {g['away_team']} @ {g['home_team']} "
                  f"{old_lookup[key][0]}-{old_lookup[key][1]} -> {new_score[0]}-{new_score[1]}")
            changed.append(g)
    return changed

def render_alert(game):
    """Render a score alert with GOAL!/SCORE! header."""
    img = Image.new("RGB", (DISPLAY_WIDTH, DISPLAY_HEIGHT), (0, 0, 0))
    draw = ImageDraw.Draw(img)

    white = (255, 255, 255)
    yellow = (255, 255, 0)
    green = (0, 255, 0)
    red = (255, 0, 0)

    # Alert text at top
    if game["league"] in ("NHL", "NCAAH"):
        alert_text = "GOAL!"
    elif game["league"] in ("NFL", "NCAAF"):
        alert_text = "SCORE!"
    else:
        alert_text = "RUN SCORED!"

    draw_text_centered(draw, 1, alert_text, yellow)

    # Team logos
    draw_team_logo(draw, img, game["home_team"], game["league_idx"], 4, 10, 24)
    draw_team_logo(draw, img, game["away_team"], game["league_idx"], 100, 10, 24)

    # Team abbreviations
    home_w = text_width(game["home_team"])
    draw.text((4 + (24 - home_w) // 2, 36), game["home_team"], fill=white, font=pil_font)
    away_w = text_width(game["away_team"])
    draw.text((100 + (24 - away_w) // 2, 36), game["away_team"], fill=white, font=pil_font)

    # Score in bright green
    score_text = f"{game['home_score']} - {game['away_score']}"
    score_w = text_width(score_text)
    draw.text(((DISPLAY_WIDTH - score_w) // 2, 20), score_text, fill=green, font=pil_font)

    # Status at bottom
    draw_text_centered(draw, DISPLAY_HEIGHT - 12, game["status"], red)

    matrix.SetImage(img)

def render_blank():
    """Render a blank screen for flash effect."""
    img = Image.new("RGB", (DISPLAY_WIDTH, DISPLAY_HEIGHT), (0, 0, 0))
    matrix.SetImage(img)

def show_score_alerts(changed_games):
    """Flash each changed game as an alert, then return to normal cycle."""
    for game in changed_games:
        print(f"  ALERT: {game['league']} {game['away_team']} @ {game['home_team']} "
              f"{game['home_score']}-{game['away_score']}")

        # Flash 3 times
        for i in range(3):
            render_alert(game)
            time.sleep(0.5)
            if i < 2:
                render_blank()
                time.sleep(0.2)

        # Hold final alert
        time.sleep(2)

# ============================================================
#  MAIN LOOP
# ============================================================
if __name__ == "__main__":
    print("=" * 50)
    print("  SPORTS TICKER - LED EMULATOR")
    print(f"  Display: {DISPLAY_WIDTH}x{DISPLAY_HEIGHT}")
    print(f"  My teams:")
    for league, teams in my_teams.items():
        if teams:
            print(f"    {league.upper()}: {', '.join(teams)}")
    if filter_leagues:
        print(f"  Leagues: {', '.join(l.upper() for l in filter_leagues)}")
    if filter_teams:
        print(f"  Teams: {', '.join(filter_teams)}")
    if not filter_leagues and not filter_teams:
        print("  Filters: None (showing all games)")
    print("=" * 50)
    print("\nOpen http://localhost:8888 in your browser to see the display!")
    print("\nKEYBOARD CONTROLS (type in terminal + Enter):")
    print("  u = UP button (cycle leagues: ALL > NHL > NBA > NFL > MLB)")
    print("  d = DOWN button (toggle MY TEAMS on/off)")
    print("  q = quit\n")

    # Start keyboard listener in background thread
    kb_thread = threading.Thread(target=keyboard_listener, daemon=True)
    kb_thread.start()

    # Startup screen
    render_message("SPORTS TICKER")
    time.sleep(2)

    render_message("Loading...")

    # Fetch games
    games = fetch_all_games()

    if not games:
        print("No games found")
        render_message("NO GAMES TODAY")
        time.sleep(10)

    # Set initial refresh interval
    is_live = any_games_live(games) if games else False
    fetch_interval = fetch_interval_live if is_live else fetch_interval_idle
    print(f"Starting with {len(games)} games, refresh every {fetch_interval}s")

    game_index = 0
    last_fetch = time.time()

    try:
        while True:
            current_time = time.time()

            # Check if a button was pressed (keyboard input)
            if button_pressed:
                button_pressed = False
                render_mode()
                time.sleep(1.5)

                # Re-fetch with new filters
                print("Filters changed, refreshing...")
                games = fetch_all_games()

                last_fetch = current_time
                game_index = 0

                if not games:
                    render_message("NO GAMES")
                    time.sleep(2)
                    continue

                is_live = any_games_live(games)
                fetch_interval = fetch_interval_live if is_live else fetch_interval_idle
                continue

            # Time to refresh from ESPN?
            if current_time - last_fetch >= fetch_interval:
                print("Refreshing game data...")
                new_games = fetch_all_games()
                if new_games:
                    # Detect score changes before updating
                    changed = detect_score_changes(games, new_games)
                    games = new_games

                    # Flash alerts for any score changes
                    if changed:
                        show_score_alerts(changed)

                    # Keep game_index in bounds but don't reset to 0
                    if game_index >= len(games):
                        game_index = 0

                last_fetch = current_time

                # Adjust refresh speed
                is_live = any_games_live(games) if games else False
                new_interval = fetch_interval_live if is_live else fetch_interval_idle
                if new_interval != fetch_interval:
                    if is_live:
                        print(f"Live game detected! Refreshing every {fetch_interval_live}s")
                    else:
                        print(f"No live games. Refreshing every {fetch_interval_idle}s")
                    fetch_interval = new_interval

            # Display current game
            if games:
                game = games[game_index]
                print(f"Showing: {game['league']} - {game['away_team']} @ {game['home_team']}  "
                      f"{'[LIVE]' if game['is_live'] else '[FINAL]' if game['is_final'] else ''}")

                render_game(game)

                game_index = (game_index + 1) % len(games)
            else:
                render_message("NO GAMES TODAY")

            time.sleep(display_interval)

    except KeyboardInterrupt:
        print("\nStopping ticker...")
        matrix.Clear()
