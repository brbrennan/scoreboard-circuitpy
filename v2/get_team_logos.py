"""
Get Team Logos v2 - Downloads team logos from ESPN for the Sports Ticker

Usage:
    python get_team_logos_v2.py                            # Download all (skip existing)
    python get_team_logos_v2.py --force                     # Re-download ALL logos
    python get_team_logos_v2.py --team BOS                  # Re-download BOS across all leagues
    python get_team_logos_v2.py --team BOS --league nhl     # Just NHL BOS
    python get_team_logos_v2.py --league nhl                # All NHL logos
    python get_team_logos_v2.py --custom logo.png --team BOS --league nhl  # Custom image
    python get_team_logos_v2.py --all-college               # Include ALL college teams

Requires: pip install requests Pillow

College football and basketball: only Power 4 conference teams (ACC, Big 12,
Big Ten, SEC) + Notre Dame + Big East (basketball) are downloaded by default.
Teams without logos get an auto-generated letter block fallback on the display.
"""

import os, sys, re, argparse, requests, colorsys
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from io import BytesIO

LOGO_SIZE = 32
PALETTE_PRO = 128
PALETTE_COLLEGE = 256
OUTPUT_BASE = "sport_logos"

FOLDERS = {
    "nfl": "team0_logos", "mlb": "team1_logos",
    "nhl": "team2_logos", "nba": "team3_logos",
    "ncaaf": "team4_logos", "ncaab": "team5_logos",
    "ncaah": "team6_logos",
}
SPORTS = {
    "nfl": "football", "mlb": "baseball",
    "nhl": "hockey", "nba": "basketball",
    "ncaaf": "football", "ncaab": "basketball",
    "ncaah": "hockey",
}
ESPN_SLUGS = {
    "nfl": "nfl", "mlb": "mlb", "nhl": "nhl", "nba": "nba",
    "ncaaf": "college-football",
    "ncaab": "mens-college-basketball",
    "ncaah": "mens-college-hockey",
}
COLLEGE = {"ncaaf", "ncaab", "ncaah"}

# ============================================================
# Power 4 + Notre Dame (football) — 2024-25 memberships
#
# Abbreviations verified against actual ESPN API responses
# (cross-checked against downloaded logo filenames).
# Fixes from golden baseline:
#   NCST  -> NCSU  (NC State)
#   MIZZ  -> MIZ   (Missouri)
#   NW    -> NU    (Northwestern)
#   OKLA  -> OU    (Oklahoma)
#   TAMU  -> TA&M  (Texas A&M — ESPN uses ampersand)
#   RUT   -> RUTG  (Rutgers)
# ============================================================
POWER4_FOOTBALL = {
    # ACC
    "BC", "CLEM", "DUKE", "FSU", "GT", "LOU", "MIA", "UNC", "NCSU", "PITT",
    "SYR", "UVA", "VT", "WAKE", "CAL", "STAN", "SMU",
    # Big 12
    "BAY", "BYU", "CIN", "COL", "HOU", "ISU", "KU", "KSU",
    "OKST", "TCU", "TTU", "UCF", "WVU", "ARIZ", "ASU", "UTAH",
    # Big Ten
    "ILL", "IND", "IOWA", "MD", "MICH", "MSU", "MINN", "NEB",
    "NU", "OSU", "PUR", "PSU", "RUTG", "WIS", "UCLA", "USC", "ORE", "WASH",
    # SEC
    "ALA", "ARK", "AUB", "FLA", "UGA", "UK", "LSU", "MISS",
    "MSST", "MIZ", "SC", "TENN", "TA&M", "VAN", "OU", "TEX",
    # Independent
    "ND",
}

# Power 4 + Big East (basketball) — same football schools + Big East
POWER_BASKETBALL = POWER4_FOOTBALL | {
    # Big East (basketball conference, no football)
    "BUT", "CREI", "DEP", "GTWN", "MARQ", "CONN",
    "VILL", "HALL", "XAV", "SJU", "PROV",
}


def best_logo_url(logos):
    """Pick the best logo URL, preferring 'dark' variants for black LED background."""
    if not logos:
        return ""

    # First pass: look for a "dark" variant (designed for dark backgrounds)
    dark_url = ""
    for lg in logos:
        rel = lg.get("rel", [])
        if "dark" in rel:
            dark_url = lg.get("href", "")
            break

    # Second pass: largest default logo as fallback
    best_url = logos[0].get("href", "")
    best_sz = 0
    for lg in logos:
        sz = max(lg.get("width", 0), lg.get("height", 0))
        if sz > best_sz:
            best_sz = sz
            best_url = lg.get("href", "")

    # Prefer dark variant if found
    url = dark_url if dark_url else best_url

    # Request larger size from ESPN CDN
    if url and ("&w=" in url or "?w=" in url):
        url = re.sub(r'([?&])w=\d+', r'\1w=200', url)
        url = re.sub(r'([?&])h=\d+', r'\1h=200', url)
    return url


def get_teams(sport, league):
    slug = ESPN_SLUGS.get(league, league)
    url = f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{slug}/teams?limit=500"
    print(f"  Fetching {league.upper()} team list...")
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        raw = data.get("sports", [{}])[0].get("leagues", [{}])[0].get("teams", [])
        teams = []
        for entry in raw:
            t = entry.get("team", {})
            abbr = t.get("abbreviation", "")
            name = t.get("displayName", "")
            logos = t.get("logos", [])
            lurl = best_logo_url(logos)
            if abbr:
                teams.append({"abbreviation": abbr, "name": name, "logo_url": lurl})
        return teams
    except Exception as e:
        print(f"  Error: {e}")
        return []


def is_power_team(abbr, league):
    """Check if a team abbreviation is in a Power conference."""
    if league not in COLLEGE:
        return True
    if league == "ncaah":
        return True  # College hockey is small, include all
    if league == "ncaaf":
        return abbr in POWER4_FOOTBALL
    if league == "ncaab":
        return abbr in POWER_BASKETBALL
    return True


def generate_letter_logo(abbr, out_path, league):
    """Generate a colored block with the first letter as a fallback logo."""
    letter = abbr[0] if abbr else "?"
    hue = sum(ord(c) for c in abbr) % 360
    r, g, b = colorsys.hsv_to_rgb(hue / 360.0, 0.7, 0.9)
    color = (int(r * 255), int(g * 255), int(b * 255))

    img = Image.new("RGB", (LOGO_SIZE, LOGO_SIZE), color)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
    except (IOError, OSError):
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), letter, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = (LOGO_SIZE - tw) // 2
    y = (LOGO_SIZE - th) // 2 - bbox[1]
    draw.text((x, y), letter, fill=(255, 255, 255), font=font)

    for bx in range(LOGO_SIZE):
        img.putpixel((bx, 0), (0, 0, 0))
        img.putpixel((bx, LOGO_SIZE - 1), (0, 0, 0))
    for by in range(LOGO_SIZE):
        img.putpixel((0, by), (0, 0, 0))
        img.putpixel((LOGO_SIZE - 1, by), (0, 0, 0))

    nc = PALETTE_COLLEGE if league in COLLEGE else PALETTE_PRO
    img.quantize(colors=nc, method=Image.Quantize.MEDIANCUT).save(out_path, format="BMP")
    return nc


def convert_save(img, out_path, league):
    """Convert image to 32x32 8-bit palette BMP."""
    img = img.convert("RGBA")
    if max(img.size) < LOGO_SIZE:
        img = img.resize((LOGO_SIZE, LOGO_SIZE), Image.NEAREST)
    else:
        img = img.resize((LOGO_SIZE, LOGO_SIZE), Image.LANCZOS)
    bg = Image.new("RGB", (LOGO_SIZE, LOGO_SIZE), (0, 0, 0))
    bg.paste(img, mask=img.split()[3])
    bg = ImageEnhance.Sharpness(bg).enhance(1.3)
    nc = PALETTE_COLLEGE if league in COLLEGE else PALETTE_PRO
    bg.quantize(colors=nc, method=Image.Quantize.MEDIANCUT).save(out_path, format="BMP")
    return nc


def download_logo(team, out_dir, league, force=False):
    abbr = team["abbreviation"]
    path = os.path.join(out_dir, f"{abbr}.bmp")
    if os.path.exists(path) and not force:
        return "skip"

    logo_url = team.get("logo_url", "")
    if not logo_url:
        nc = generate_letter_logo(abbr, path, league)
        kb = os.path.getsize(path) / 1024
        print(f"    {abbr:6s} - {team['name']:35s} [GENERATED letter block]")
        return "ok"

    try:
        resp = requests.get(logo_url, timeout=15)
        resp.raise_for_status()
        nc = convert_save(Image.open(BytesIO(resp.content)), path, league)
        kb = os.path.getsize(path) / 1024
        print(f"    {abbr:6s} - {team['name']:35s} [{kb:.1f}KB, {nc} colors]")
        return "ok"
    except Exception as e:
        print(f"    {abbr:6s} - download failed ({e}), generating letter block")
        try:
            generate_letter_logo(abbr, path, league)
            return "ok"
        except Exception:
            print(f"    {abbr:6s} - FAILED completely")
            return "fail"


def main():
    p = argparse.ArgumentParser(description="Download team logos for Sports Ticker")
    p.add_argument("--force", action="store_true", help="Re-download (replace existing)")
    p.add_argument("--team", type=str, help="Team abbreviation (e.g. BOS, NE, BC)")
    p.add_argument("--league", type=str, help="League (nfl/mlb/nhl/nba/ncaaf/ncaab/ncaah)")
    p.add_argument("--custom", type=str, help="Custom image file (requires --team and --league)")
    p.add_argument("--all-college", action="store_true",
                   help="Include ALL college teams (not just Power 4)")
    args = p.parse_args()

    # Custom logo mode
    if args.custom:
        if not args.team or not args.league:
            print("Error: --custom requires both --team and --league")
            sys.exit(1)
        league = args.league.lower()
        abbr = args.team.upper()
        folder = FOLDERS.get(league)
        if not folder:
            print(f"Unknown league. Valid: {', '.join(FOLDERS.keys())}")
            sys.exit(1)
        out_dir = os.path.join(OUTPUT_BASE, folder)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"{abbr}.bmp")
        try:
            nc = convert_save(Image.open(args.custom), out_path, league)
            kb = os.path.getsize(out_path) / 1024
            print(f"Saved: {out_path} [{kb:.1f}KB, {nc} colors]")
            print("Re-upload LittleFS to update the board.")
        except Exception as e:
            print(f"Failed: {e}")
            sys.exit(1)
        return

    # Normal mode
    target_team = args.team.upper() if args.team else None
    target_league = args.league.lower() if args.league else None
    force = args.force or target_team is not None
    power_only = not args.all_college

    print("=" * 55)
    print("  SPORTS TICKER - LOGO DOWNLOADER v2")
    print("=" * 55)
    print(f"  Size: {LOGO_SIZE}x{LOGO_SIZE}  Pro: {PALETTE_PRO} colors  College: {PALETTE_COLLEGE} colors")
    if power_only:
        print(f"  College FB/BB: Power 4 + Notre Dame + Big East only")
        print(f"  College hockey: all teams (small league)")
        print(f"  Use --all-college to download every college team")
    else:
        print(f"  College: ALL teams")
    if target_league: print(f"  League: {target_league.upper()}")
    if target_team:   print(f"  Team:   {target_team}")
    if force:         print(f"  Mode:   FORCE (replacing existing)")
    print()

    ok = skip = fail = 0
    for league in ([target_league] if target_league else list(SPORTS.keys())):
        if league not in SPORTS:
            print(f"  Unknown league: {league}. Valid: {', '.join(SPORTS.keys())}")
            continue
        folder = FOLDERS[league]
        out_dir = os.path.join(OUTPUT_BASE, folder)
        os.makedirs(out_dir, exist_ok=True)
        print(f"  {league.upper()} -> {folder}/")
        teams = get_teams(SPORTS[league], league)
        if not teams:
            continue
        if target_team:
            teams = [t for t in teams if t["abbreviation"] == target_team]
            if not teams:
                continue

        # Filter to Power 4 for college football/basketball (not hockey)
        if power_only and league in ("ncaaf", "ncaab"):
            all_count = len(teams)
            teams = [t for t in teams if is_power_team(t["abbreviation"], league)]
            print(f"  Filtered to {len(teams)} Power conference teams (from {all_count} total)")

        print(f"  Processing {len(teams)} teams\n")
        for team in teams:
            r = download_logo(team, out_dir, league, force=force)
            if r == "ok": ok += 1
            elif r == "skip": skip += 1
            else: fail += 1
        print()

    print(f"  DONE: {ok} downloaded, {skip} skipped, {fail} failed\n")
    for league, folder in FOLDERS.items():
        path = os.path.join(OUTPUT_BASE, folder)
        if os.path.exists(path):
            files = [f for f in os.listdir(path) if f.endswith(".bmp")]
            if files:
                sz = sum(os.path.getsize(os.path.join(path, f)) for f in files)
                print(f"  {path:25s} {len(files):4d} logos  ({sz/1024:.0f} KB)")
    print()
    print("  Upload: copy teamX_logos/ into sketch data/ folder, then LittleFS upload")
    print("  Fix blurry: python get_team_logos_v2.py --custom my.png --team BOS --league nhl")
    print()
    print("  Non-Power teams showing in games will display as a colored letter")
    print("  block on the LED matrix (no logo file needed).")
    print()


if __name__ == "__main__":
    main()
