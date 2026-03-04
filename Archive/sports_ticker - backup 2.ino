/*
 * Sports Ticker - LED Matrix (Arduino / Protomatter version)
 * For Adafruit MatrixPortal S3 with four 64x32 HUB75 panels (128x64)
 * 
 * Uses Adafruit_Protomatter for display (native MatrixPortal S3 support).
 * 2x2 serpentine panel tiling: width=128, tile=-2.
 *
 * Pulls scores from ESPN API for NFL, MLB, NHL, NBA, NCAAF, NCAAB, NCAAH.
 *
 * Features:
 *   - Per-league favorite teams (my_teams)
 *   - Button controls: UP cycles leagues, DOWN toggles my teams
 *   - Score change alerts (GOAL/SCORE/RUN SCORED) for non-basketball leagues
 *   - Adaptive refresh: 30s when live, 5min when idle
 *   - Logo display from LittleFS BMP files
 *   - Robust WiFi with auto-reconnect and retry
 *
 * Required libraries (install via Arduino Library Manager):
 *   - Adafruit Protomatter
 *   - Adafruit GFX Library
 *   - Adafruit NeoPixel
 *   - ArduinoJson (by Benoit Blanchon)
 *   - LittleFS (built-in with ESP32 core)
 *
 * Board: "Adafruit MatrixPortal ESP32-S3"
 */

#define ARDUINOJSON_DEFAULT_NESTING_LIMIT 20
#include <ArduinoJson.h>

#include <Adafruit_Protomatter.h>
#include <Adafruit_GFX.h>
#include <Adafruit_NeoPixel.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <LittleFS.h>
#include <StreamString.h>

#include "secrets.h"  // WIFI_SSID, WIFI_PASSWORD

// ============================================================
//  DISPLAY CONFIG - Protomatter for MatrixPortal ESP32-S3
// ============================================================
// MatrixPortal S3 pin definitions (from Adafruit examples)
uint8_t rgbPins[]  = {42, 41, 40, 38, 39, 37};
uint8_t addrPins[] = {45, 36, 48, 35, 21};
uint8_t clockPin   = 2;
uint8_t latchPin   = 47;
uint8_t oePin      = 14;

// 128 pixels wide (2 panels across), 32 rows per panel,
// 4 address lines, double-buffered, tile = -2 (2 rows, serpentine)
Adafruit_Protomatter matrix(
  128,             // width: 2 panels across x 64px each
  2,               // bit depth (lower = less flicker, 2 is minimum for decent color)
  1, rgbPins,      // 1 chain of RGB pins
  4, addrPins,     // 4 address pins (A-D for 32-row panels)
  clockPin, latchPin, oePin,
  true,            // double-buffer
  -2               // tile: 2 rows of panels, serpentine (negative = serpentine)
);

#define DISPLAY_WIDTH  128
#define DISPLAY_HEIGHT 64

// ============================================================
//  HARDWARE
// ============================================================
#define NEOPIXEL_PIN 4
Adafruit_NeoPixel pixel(1, NEOPIXEL_PIN, NEO_GRB + NEO_KHZ800);
#define BUTTON_UP_PIN   6
#define BUTTON_DOWN_PIN 7

// ============================================================
//  COLORS (565 format, set after matrix init)
// ============================================================
uint16_t COLOR_WHITE, COLOR_YELLOW, COLOR_GREEN, COLOR_RED;
uint16_t COLOR_DIM, COLOR_BLACK, COLOR_BLUE;

// ============================================================
//  NETWORK CONFIG
// ============================================================
#define WIFI_MAX_ATTEMPTS 30
#define HTTP_TIMEOUT      20000
#define HTTP_MAX_RETRIES  3
#define FETCH_DELAY_MS    1000

// ============================================================
//  LEAGUE DEFINITIONS
// ============================================================
#define NUM_LEAGUES 7
const char* league_names[] = {"NFL","MLB","NHL","NBA","NCAAF","NCAAB","NCAAH"};
const char* sport_names[]  = {"football","baseball","hockey","basketball",
                              "football","basketball","hockey"};
const char* espn_slugs[]   = {"nfl","mlb","nhl","nba",
                              "college-football","mens-college-basketball",
                              "mens-college-hockey"};
const char* logo_folders[] = {"team0_logos","team1_logos","team2_logos",
                              "team3_logos","team4_logos","team5_logos",
                              "team6_logos"};

// Alert messages per league (for score changes)
const char* alert_messages[] = {
  "TOUCHDOWN!", "RUN SCORED!", "GOAL!", NULL,
  "TOUCHDOWN!", NULL, "GOAL!"
};

// ============================================================
//  LEAGUE ENABLE/DISABLE
// ============================================================
// Set to false to skip fetching a league entirely.
// Useful for hiding off-season leagues (e.g. NCAAF in spring).
// Order: NFL, MLB, NHL, NBA, NCAAF, NCAAB, NCAAH
bool enabled_leagues[] = {
  false,   // NFL
  true,   // MLB
  true,   // NHL
  true,   // NBA
  false,   // NCAAF  — set false during off-season
  true,   // NCAAB  — set false during off-season
  true,   // NCAAH  — set false during off-season
};

// ============================================================
//  FAVORITE TEAMS
// ============================================================
const char* my_nfl[]   = {"NE", NULL};
const char* my_mlb[]   = {"BOS", NULL};
const char* my_nhl[]   = {"BOS", NULL};
const char* my_nba[]   = {"BOS", NULL};
const char* my_ncaaf[] = {"BC", NULL};
const char* my_ncaab[] = {"BC", NULL};
const char* my_ncaah[] = {"BC", NULL};

const char** my_teams[] = {
  my_nfl, my_mlb, my_nhl, my_nba, my_ncaaf, my_ncaab, my_ncaah
};

// ============================================================
//  GAME DATA
// ============================================================
#define MAX_GAMES 64

struct Game {
  char home_team[8];
  char away_team[8];
  char home_score[6];
  char away_score[6];
  char status[32];
  char league[8];
  int  league_idx;
  bool is_live;
  bool is_final;
  bool is_scheduled;
  int  home_score_int;
  int  away_score_int;
};

Game games[MAX_GAMES];
Game prev_games[MAX_GAMES];
int num_games = 0;
int prev_num_games = 0;

// ============================================================
//  STATE
// ============================================================
int game_index = 0;
int current_league_filter = -1;  // -1 = all
bool show_my_teams_only = false;

unsigned long last_fetch_time = 0;
unsigned long last_display_time = 0;
unsigned long fetch_interval_live = 60000;   // 60s when live (less flicker than 30s)
unsigned long fetch_interval_idle = 300000;  // 5min when idle
unsigned long fetch_interval = 300000;
unsigned long display_interval = 5000;       // 5s per game

// Button state
bool btn_up_last = true;
bool btn_down_last = true;
unsigned long last_button_time = 0;
#define DEBOUNCE_MS 250

// Active league list
bool league_active[NUM_LEAGUES];
int num_filter_teams = 0;
char filter_teams[32][8];

// ============================================================
//  SETUP
// ============================================================
void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\n=== SPORTS TICKER (Protomatter) ===");
  Serial.printf("Free heap: %d, PSRAM: %d\n", ESP.getFreeHeap(), ESP.getFreePsram());

  // NeoPixel
  pixel.begin();
  pixel.setPixelColor(0, pixel.Color(0, 0, 30));
  pixel.show();

  // Buttons
  pinMode(BUTTON_UP_PIN, INPUT_PULLUP);
  pinMode(BUTTON_DOWN_PIN, INPUT_PULLUP);
  Serial.printf("Buttons: UP=pin%d(%s) DOWN=pin%d(%s)\n",
                BUTTON_UP_PIN, digitalRead(BUTTON_UP_PIN) ? "HIGH" : "LOW",
                BUTTON_DOWN_PIN, digitalRead(BUTTON_DOWN_PIN) ? "HIGH" : "LOW");

  // LittleFS
  if (!LittleFS.begin(true)) {
    Serial.println("LittleFS mount failed!");
  } else {
    Serial.println("LittleFS mounted OK");
    // List root directory
    File root = LittleFS.open("/");
    File f = root.openNextFile();
    int fileCount = 0;
    while (f) {
      if (f.isDirectory()) {
        Serial.printf("  DIR: %s\n", f.name());
      } else {
        fileCount++;
      }
      f = root.openNextFile();
    }
    Serial.printf("  Total files: %d\n", fileCount);
  }

  // ---- Init Protomatter display ----
  ProtomatterStatus status = matrix.begin();
  Serial.printf("Protomatter begin() status: %d\n", (int)status);
  if (status != PROTOMATTER_OK) {
    Serial.println("Protomatter init FAILED!");
    while (1) delay(1000);
  }
  Serial.println("Protomatter display initialized");

  // Clear screen
  matrix.fillScreen(0);
  matrix.show();

  // Define colors
  COLOR_WHITE  = matrix.color565(255, 255, 255);
  COLOR_YELLOW = matrix.color565(255, 255, 0);
  COLOR_GREEN  = matrix.color565(0, 255, 0);
  COLOR_RED    = matrix.color565(255, 0, 0);
  COLOR_DIM    = matrix.color565(120, 120, 120);
  COLOR_BLACK  = matrix.color565(0, 0, 0);
  COLOR_BLUE   = matrix.color565(0, 0, 255);

  // Startup screen
  matrix.fillScreen(COLOR_BLACK);
  drawCenteredText(20, "SPORTS TICKER", COLOR_YELLOW);
  drawCenteredText(36, "Connecting...", COLOR_WHITE);
  matrix.show();

  // Connect WiFi
  ensureWiFi();

  // Print my teams
  Serial.println("My teams:");
  for (int i = 0; i < NUM_LEAGUES; i++) {
    if (my_teams[i][0] != NULL) {
      Serial.printf("  %s:", league_names[i]);
      for (int j = 0; my_teams[i][j] != NULL; j++)
        Serial.printf(" %s", my_teams[i][j]);
      Serial.println();
    }
  }

  // Print enabled leagues
  Serial.print("Enabled leagues:");
  for (int i = 0; i < NUM_LEAGUES; i++) {
    if (enabled_leagues[i]) Serial.printf(" %s", league_names[i]);
  }
  Serial.println();

  matrix.fillScreen(COLOR_BLACK);
  drawCenteredText(28, "Loading games...", COLOR_WHITE);
  matrix.show();
  delay(1000);

  // Initial fetch
  fetchAllGames();
  last_fetch_time = millis();

  if (num_games == 0) {
    matrix.fillScreen(COLOR_BLACK);
    drawCenteredText(28, "NO GAMES TODAY", COLOR_WHITE);
    matrix.show();
    delay(10000);
    fetchAllGames();
    last_fetch_time = millis();
  }

  fetch_interval = anyGamesLive() ? fetch_interval_live : fetch_interval_idle;
  Serial.printf("Starting: %d games, refresh every %lus\n",
                num_games, fetch_interval / 1000);
}

// ============================================================
//  MAIN LOOP
// ============================================================
void loop() {
  unsigned long now = millis();

  // Check buttons
  if (checkButtons()) {
    // Show loading message (fetch takes several seconds)
    matrix.fillScreen(COLOR_BLACK);
    drawCenteredText(28, "Loading...", COLOR_DIM);
    matrix.show();

    fetchAllGames();
    last_fetch_time = millis();
    game_index = 0;
    last_display_time = millis();
  }

  // Time to re-fetch?
  if (now - last_fetch_time >= fetch_interval) {
    int saved_index = game_index;
    savePreviousGames();
    fetchAllGames();
    last_fetch_time = millis();  // Use fresh millis() since fetch took time

    if (num_games > 0) {
      checkScoreChanges();

      // Restore position
      game_index = saved_index;
      if (game_index >= num_games) game_index = 0;

      // Reset display timer so next game shows after a full interval
      // (prevents rapid-fire game cycling after a long fetch)
      last_display_time = millis();
    } else {
      matrix.fillScreen(COLOR_BLACK);
      drawCenteredText(28, "NO GAMES TODAY", COLOR_WHITE);
      matrix.show();
      fetch_interval = fetch_interval_idle;
      delay(5000);
      last_display_time = millis();
      return;
    }

    bool live = anyGamesLive();
    unsigned long new_interval = live ? fetch_interval_live : fetch_interval_idle;
    if (new_interval != fetch_interval) {
      Serial.printf("%s -> refresh every %lus\n",
                    live ? "LIVE" : "IDLE", new_interval / 1000);
      fetch_interval = new_interval;
    }
  }

  // Time to show next game?
  unsigned long now2 = millis();  // Fresh time (fetch may have updated last_display_time)
  if (now2 - last_display_time >= display_interval) {
    if (num_games > 0) {
      renderGame(games[game_index]);
      Serial.printf("[%d/%d] %s: %s @ %s  %s-%s  %s\n",
                    game_index + 1, num_games,
                    games[game_index].league,
                    games[game_index].away_team,
                    games[game_index].home_team,
                    games[game_index].away_score,
                    games[game_index].home_score,
                    games[game_index].status);
      game_index = (game_index + 1) % num_games;
    }
    last_display_time = millis();
  }

  delay(50);
}

// ============================================================
//  WiFi MANAGEMENT (with reconnect)
// ============================================================
void ensureWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;

  Serial.print("WiFi connecting");
  WiFi.disconnect(true);
  delay(100);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < WIFI_MAX_ATTEMPTS) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf(" OK! IP: %s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println(" FAILED - will retry next fetch");
  }
}

// ============================================================
//  DRAWING HELPERS
// ============================================================
int textPixelWidth(const char* text) {
  return strlen(text) * 6;  // Default Adafruit GFX font: 6px per char
}

void drawCenteredText(int y, const char* text, uint16_t color) {
  int w = textPixelWidth(text);
  int x = (DISPLAY_WIDTH - w) / 2;
  if (x < 0) x = 0;
  matrix.setCursor(x, y);
  matrix.setTextColor(color);
  matrix.setTextSize(1);
  matrix.print(text);
}

void drawRightText(int x_right, int y, const char* text, uint16_t color) {
  int w = textPixelWidth(text);
  matrix.setCursor(x_right - w, y);
  matrix.setTextColor(color);
  matrix.setTextSize(1);
  matrix.print(text);
}

// ============================================================
//  BMP LOGO DRAWING (16-bit 565 BMP from LittleFS)
// ============================================================
uint16_t read16(File& f) {
  uint16_t result;
  f.read((uint8_t*)&result, 2);
  return result;
}

uint32_t read32(File& f) {
  uint32_t result;
  f.read((uint8_t*)&result, 4);
  return result;
}

void drawBMP(const char* filename, int16_t x, int16_t y, const char* teamAbbr = NULL) {
  Serial.printf("  Logo: %s ", filename);
  File file = LittleFS.open(filename, "r");
  if (!file) {
    Serial.println("NOT FOUND");
    // Draw a colored block with the first letter as fallback
    if (teamAbbr && teamAbbr[0]) {
      // Generate a color from the abbreviation
      uint16_t hue = 0;
      for (int i = 0; teamAbbr[i]; i++) hue += teamAbbr[i];
      hue = hue % 360;
      // Simple HSV->RGB (S=0.7, V=0.85)
      uint8_t r, g, b;
      uint8_t region = hue / 60;
      uint8_t rem = (hue % 60) * 255 / 60;
      uint8_t p = 55, q = 217 - (rem * 162 / 255), t = 55 + (rem * 162 / 255);
      switch (region) {
        case 0: r=217; g=t;   b=p;   break;
        case 1: r=q;   g=217; b=p;   break;
        case 2: r=p;   g=217; b=t;   break;
        case 3: r=p;   g=q;   b=217; break;
        case 4: r=t;   g=p;   b=217; break;
        default:r=217; g=p;   b=q;   break;
      }
      uint16_t blockColor = matrix.color565(r, g, b);
      matrix.fillRect(x + 2, y + 2, 28, 28, blockColor);
      matrix.drawRect(x + 1, y + 1, 30, 30, COLOR_BLACK);
      // Draw first letter centered in the block
      char letter[2] = {teamAbbr[0], 0};
      int lw = textPixelWidth(letter);
      matrix.setCursor(x + 16 - lw / 2, y + 10);
      matrix.setTextColor(COLOR_WHITE);
      matrix.setTextSize(1);
      matrix.print(letter);
    } else {
      matrix.drawRect(x + 4, y + 4, 24, 24, COLOR_DIM);
    }
    return;
  }
  Serial.printf("OK (%d bytes) ", file.size());

  uint16_t sig = read16(file);
  if (sig != 0x4D42) {
    Serial.println("BAD SIG");
    file.close();
    return;
  }

  read32(file); // file size
  read16(file); // reserved
  read16(file); // reserved
  uint32_t imageOffset = read32(file);

  uint32_t headerSize = read32(file);
  int32_t bmpWidth  = (int32_t)read32(file);
  int32_t bmpHeight = (int32_t)read32(file);
  read16(file); // planes
  uint16_t bpp = read16(file);
  uint32_t compression = read32(file);

  Serial.printf("%dx%d %dbpp\n", bmpWidth, abs(bmpHeight), bpp);

  bool flip = (bmpHeight > 0);
  if (bmpHeight < 0) bmpHeight = -bmpHeight;

  if (bpp == 8) {
    // 8-bit palette BMP
    // Skip rest of header to get to palette (at offset 54 usually)
    // Palette starts after the DIB header (14 byte file header + headerSize)
    file.seek(14 + headerSize);

    // Read palette (up to 256 entries, 4 bytes each: B, G, R, A)
    uint8_t palette[256][3];
    int numColors = (imageOffset - 14 - headerSize) / 4;
    if (numColors > 256) numColors = 256;
    for (int i = 0; i < numColors; i++) {
      uint8_t b = file.read();
      uint8_t g = file.read();
      uint8_t r = file.read();
      file.read(); // skip alpha/padding
      palette[i][0] = r;
      palette[i][1] = g;
      palette[i][2] = b;
    }

    file.seek(imageOffset);
    int rowSize = ((bmpWidth + 3) & ~3);  // 8-bit: 1 byte per pixel, padded to 4
    uint8_t* row = (uint8_t*)malloc(rowSize);
    if (!row) { file.close(); return; }

    for (int r = 0; r < bmpHeight; r++) {
      int drawRow = flip ? (bmpHeight - 1 - r) : r;
      file.read(row, rowSize);
      for (int c = 0; c < bmpWidth; c++) {
        uint8_t idx = row[c];
        uint8_t pr = palette[idx][0];
        uint8_t pg = palette[idx][1];
        uint8_t pb = palette[idx][2];
        // Skip black pixels (transparent on LED matrix)
        if (pr > 5 || pg > 5 || pb > 5) {
          matrix.drawPixel(x + c, y + drawRow, matrix.color565(pr, pg, pb));
        }
      }
    }
    free(row);

  } else if (bpp == 16) {
    // 16-bit 565 BMP
    file.seek(imageOffset);
    int rowSize = ((bmpWidth * 2 + 3) & ~3);
    uint8_t* row = (uint8_t*)malloc(rowSize);
    if (!row) { file.close(); return; }

    for (int r = 0; r < bmpHeight; r++) {
      int drawRow = flip ? (bmpHeight - 1 - r) : r;
      file.read(row, rowSize);
      for (int c = 0; c < bmpWidth; c++) {
        uint16_t color = row[c * 2] | (row[c * 2 + 1] << 8);
        if (color != 0) {
          matrix.drawPixel(x + c, y + drawRow, color);
        }
      }
    }
    free(row);

  } else if (bpp == 24) {
    // 24-bit RGB BMP
    file.seek(imageOffset);
    int rowSize = ((bmpWidth * 3 + 3) & ~3);
    uint8_t* row = (uint8_t*)malloc(rowSize);
    if (!row) { file.close(); return; }

    for (int r = 0; r < bmpHeight; r++) {
      int drawRow = flip ? (bmpHeight - 1 - r) : r;
      file.read(row, rowSize);
      for (int c = 0; c < bmpWidth; c++) {
        uint8_t b = row[c * 3];
        uint8_t g = row[c * 3 + 1];
        uint8_t pr = row[c * 3 + 2];
        if (pr > 5 || g > 5 || b > 5) {
          matrix.drawPixel(x + c, y + drawRow, matrix.color565(pr, g, b));
        }
      }
    }
    free(row);

  } else {
    Serial.printf("  Unsupported BMP bpp: %d\n", bpp);
  }

  file.close();
}

// ============================================================
//  GAME RENDERING
// ============================================================
void renderGame(Game& game) {
  matrix.fillScreen(COLOR_BLACK);

  // Layout:  128 wide x 64 tall
  //   y=0:  League label
  //   y=10: Logos (32x32, end at y=42)
  //   y=22: Score/VS (centered in logo zone)
  //   y=44: Team abbreviations
  //   y=54: Status line

  // League label top center
  drawCenteredText(1, game.league, COLOR_YELLOW);

  // Away logo (left side, 32x32)
  char path[48];
  snprintf(path, sizeof(path), "/%s/%s.bmp",
           logo_folders[game.league_idx], game.away_team);
  drawBMP(path, 4, 10, game.away_team);

  // Home logo (right side, 32x32)
  snprintf(path, sizeof(path), "/%s/%s.bmp",
           logo_folders[game.league_idx], game.home_team);
  drawBMP(path, 92, 10, game.home_team);

  // "VS" or scores in center (vertically centered in logo zone)
  if (game.is_scheduled) {
    drawCenteredText(22, "VS", COLOR_WHITE);
  } else {
    char scoreDisplay[16];
    snprintf(scoreDisplay, sizeof(scoreDisplay), "%s - %s",
             game.away_score, game.home_score);
    drawCenteredText(22, scoreDisplay, COLOR_WHITE);
  }

  // Team abbreviations centered under logos
  // Away logo at x=4, 32px wide -> center at x=20
  int awayTextW = textPixelWidth(game.away_team);
  matrix.setCursor(20 - awayTextW / 2, 44);
  matrix.setTextColor(COLOR_WHITE);
  matrix.setTextSize(1);
  matrix.print(game.away_team);

  // Home logo at x=92, 32px wide -> center at x=108
  int homeTextW = textPixelWidth(game.home_team);
  matrix.setCursor(108 - homeTextW / 2, 44);
  matrix.setTextColor(COLOR_WHITE);
  matrix.setTextSize(1);
  matrix.print(game.home_team);

  // Status line (bottom)
  uint16_t statusColor = COLOR_DIM;
  if (game.is_live) statusColor = COLOR_GREEN;
  else if (game.is_final) statusColor = COLOR_RED;

  drawCenteredText(54, game.status, statusColor);

  // Filter indicator
  if (current_league_filter >= 0) {
    matrix.setCursor(2, 56);
    matrix.setTextColor(COLOR_BLUE);
    matrix.setTextSize(1);
    matrix.print(league_names[current_league_filter]);
  }
  if (show_my_teams_only) {
    drawRightText(126, 56, "FAV", COLOR_YELLOW);
  }

  matrix.show();
}

// ============================================================
//  SCORE CHANGE ALERTS
// ============================================================
void showScoreAlert(Game& game, int gameIdx, int oldAwayScore, int oldHomeScore) {
  const char* alert = alert_messages[game.league_idx];
  if (alert == NULL) return;

  // Jump to this game
  game_index = gameIdx;

  // Determine which team scored (for flashing the changing number)
  bool awayScored = (game.away_score_int > oldAwayScore);
  bool homeScored = (game.home_score_int > oldHomeScore);

  // Phase 1: Flash alert text with OLD score (2 flashes, ~1.6s)
  // Shows "GOAL!" flashing while score still shows old values
  for (int flash = 0; flash < 4; flash++) {
    matrix.fillScreen(COLOR_BLACK);
    drawCenteredText(1, game.league, COLOR_YELLOW);

    // Logos (away left, home right)
    char path[48];
    snprintf(path, sizeof(path), "/%s/%s.bmp",
             logo_folders[game.league_idx], game.away_team);
    drawBMP(path, 4, 10, game.away_team);
    snprintf(path, sizeof(path), "/%s/%s.bmp",
             logo_folders[game.league_idx], game.home_team);
    drawBMP(path, 92, 10, game.home_team);

    // OLD score — flash the scoring team's number
    char scoreDisplay[16];
    if (flash % 2 == 0) {
      // Show old score normally
      snprintf(scoreDisplay, sizeof(scoreDisplay), "%d - %d",
               oldAwayScore, oldHomeScore);
      drawCenteredText(22, scoreDisplay, COLOR_WHITE);
    } else {
      // Blank out the scoring team's number (flash effect)
      // Build score string with spaces where the changing number goes
      if (awayScored && !homeScored) {
        snprintf(scoreDisplay, sizeof(scoreDisplay), "  - %d", oldHomeScore);
        drawCenteredText(22, scoreDisplay, COLOR_WHITE);
      } else if (homeScored && !awayScored) {
        snprintf(scoreDisplay, sizeof(scoreDisplay), "%d -  ", oldAwayScore);
        drawCenteredText(22, scoreDisplay, COLOR_WHITE);
      } else {
        // Both scored (rare) or can't tell — flash whole score
        // leave score area blank
      }
    }

    // Team abbreviations
    int awayTextW = textPixelWidth(game.away_team);
    matrix.setCursor(20 - awayTextW / 2, 44);
    matrix.setTextColor(COLOR_WHITE);
    matrix.setTextSize(1);
    matrix.print(game.away_team);

    int homeTextW = textPixelWidth(game.home_team);
    matrix.setCursor(108 - homeTextW / 2, 44);
    matrix.setTextColor(COLOR_WHITE);
    matrix.setTextSize(1);
    matrix.print(game.home_team);

    // Flash alert text
    if (flash % 2 == 0) {
      drawCenteredText(54, alert, COLOR_RED);
    } else {
      drawCenteredText(54, game.status,
                       game.is_live ? COLOR_GREEN : COLOR_DIM);
    }

    matrix.show();
    delay(400);
  }

  // Phase 2: Flash NEW score (2 flashes, ~1.6s)
  // Score updates — flash the NEW number in green to highlight the change
  for (int flash = 0; flash < 4; flash++) {
    matrix.fillScreen(COLOR_BLACK);
    drawCenteredText(1, game.league, COLOR_YELLOW);

    // Logos
    char path[48];
    snprintf(path, sizeof(path), "/%s/%s.bmp",
             logo_folders[game.league_idx], game.away_team);
    drawBMP(path, 4, 10, game.away_team);
    snprintf(path, sizeof(path), "/%s/%s.bmp",
             logo_folders[game.league_idx], game.home_team);
    drawBMP(path, 92, 10, game.home_team);

    // NEW score — highlight the changed number in green
    // We draw the score manually so we can color each part independently
    char awayStr[6], dashStr[] = " - ", homeStr[6];
    snprintf(awayStr, sizeof(awayStr), "%s", game.away_score);
    snprintf(homeStr, sizeof(homeStr), "%s", game.home_score);

    // Calculate total width to center: "X - Y"
    int awayW = textPixelWidth(awayStr);
    int dashW = textPixelWidth(dashStr);
    int homeW = textPixelWidth(homeStr);
    int totalW = awayW + dashW + homeW;
    int startX = (128 - totalW) / 2;

    // Away score
    matrix.setCursor(startX, 22);
    uint16_t awayColor = (awayScored && flash % 2 == 0) ? COLOR_GREEN : COLOR_WHITE;
    matrix.setTextColor(awayColor);
    matrix.setTextSize(1);
    matrix.print(awayStr);

    // Dash
    matrix.setCursor(startX + awayW, 22);
    matrix.setTextColor(COLOR_WHITE);
    matrix.print(dashStr);

    // Home score
    matrix.setCursor(startX + awayW + dashW, 22);
    uint16_t homeColor = (homeScored && flash % 2 == 0) ? COLOR_GREEN : COLOR_WHITE;
    matrix.setTextColor(homeColor);
    matrix.print(homeStr);

    // Team abbreviations
    int awayTextW = textPixelWidth(game.away_team);
    matrix.setCursor(20 - awayTextW / 2, 44);
    matrix.setTextColor(COLOR_WHITE);
    matrix.setTextSize(1);
    matrix.print(game.away_team);

    int homeTextW = textPixelWidth(game.home_team);
    matrix.setCursor(108 - homeTextW / 2, 44);
    matrix.setTextColor(COLOR_WHITE);
    matrix.setTextSize(1);
    matrix.print(game.home_team);

    // Keep flashing alert
    if (flash % 2 == 0) {
      drawCenteredText(54, alert, COLOR_RED);
    } else {
      drawCenteredText(54, game.status,
                       game.is_live ? COLOR_GREEN : COLOR_DIM);
    }

    matrix.show();
    delay(400);
  }

  // Phase 3: Hold final state for ~1s so viewer can read the new score
  matrix.fillScreen(COLOR_BLACK);
  drawCenteredText(1, game.league, COLOR_YELLOW);

  char path[48];
  snprintf(path, sizeof(path), "/%s/%s.bmp",
           logo_folders[game.league_idx], game.away_team);
  drawBMP(path, 4, 10, game.away_team);
  snprintf(path, sizeof(path), "/%s/%s.bmp",
           logo_folders[game.league_idx], game.home_team);
  drawBMP(path, 92, 10, game.home_team);

  char scoreDisplay[16];
  snprintf(scoreDisplay, sizeof(scoreDisplay), "%s - %s",
           game.away_score, game.home_score);
  drawCenteredText(22, scoreDisplay, COLOR_WHITE);

  int awayTextW = textPixelWidth(game.away_team);
  matrix.setCursor(20 - awayTextW / 2, 44);
  matrix.setTextColor(COLOR_WHITE);
  matrix.setTextSize(1);
  matrix.print(game.away_team);

  int homeTextW = textPixelWidth(game.home_team);
  matrix.setCursor(108 - homeTextW / 2, 44);
  matrix.setTextColor(COLOR_WHITE);
  matrix.setTextSize(1);
  matrix.print(game.home_team);

  drawCenteredText(54, game.status,
                   game.is_live ? COLOR_GREEN : COLOR_DIM);

  matrix.show();
  delay(1000);

  // Advance past this game so the cycle continues
  game_index = (gameIdx + 1) % num_games;
  last_display_time = millis();
}

void savePreviousGames() {
  prev_num_games = num_games;
  memcpy(prev_games, games, sizeof(Game) * num_games);
}

void checkScoreChanges() {
  for (int i = 0; i < num_games; i++) {
    if (!games[i].is_live) continue;

    for (int j = 0; j < prev_num_games; j++) {
      if (strcmp(games[i].home_team, prev_games[j].home_team) == 0 &&
          strcmp(games[i].away_team, prev_games[j].away_team) == 0 &&
          games[i].league_idx == prev_games[j].league_idx) {
        int new_total = games[i].home_score_int + games[i].away_score_int;
        int old_total = prev_games[j].home_score_int + prev_games[j].away_score_int;
        if (new_total > old_total) {
          showScoreAlert(games[i], i,
                         prev_games[j].away_score_int,
                         prev_games[j].home_score_int);
        }
        break;
      }
    }
  }
}

// ============================================================
//  BUTTON HANDLING
// ============================================================
bool checkButtons() {
  // Debounce
  if (millis() - last_button_time < DEBOUNCE_MS) return false;

  bool up = digitalRead(BUTTON_UP_PIN);
  bool down = digitalRead(BUTTON_DOWN_PIN);
  bool changed = false;

  if (!up && btn_up_last) {
    last_button_time = millis();
    // UP pressed: cycle league filter (skip disabled leagues)
    int start = current_league_filter;
    do {
      current_league_filter++;
      if (current_league_filter >= NUM_LEAGUES) current_league_filter = -1;
    } while (current_league_filter >= 0 &&
             !enabled_leagues[current_league_filter] &&
             current_league_filter != start);
    const char* label = current_league_filter < 0 ? "ALL" : league_names[current_league_filter];
    Serial.printf(">> UP pressed -> League: %s\n", label);

    // Show feedback immediately
    matrix.fillScreen(COLOR_BLACK);
    drawCenteredText(20, "LEAGUE:", COLOR_DIM);
    drawCenteredText(34, label, COLOR_YELLOW);
    matrix.show();
    delay(800);
    changed = true;
  }

  if (!down && btn_down_last) {
    last_button_time = millis();
    // DOWN pressed: toggle my teams
    show_my_teams_only = !show_my_teams_only;
    const char* label = show_my_teams_only ? "MY TEAMS" : "ALL TEAMS";
    Serial.printf(">> DOWN pressed -> %s\n", label);

    // Show feedback immediately
    matrix.fillScreen(COLOR_BLACK);
    drawCenteredText(28, label, show_my_teams_only ? COLOR_YELLOW : COLOR_WHITE);
    matrix.show();
    delay(800);
    changed = true;
  }

  btn_up_last = up;
  btn_down_last = down;
  return changed;
}

// ============================================================
//  TEAM FILTERING HELPERS
// ============================================================
void buildFilterList() {
  num_filter_teams = 0;
  if (!show_my_teams_only) return;

  for (int i = 0; i < NUM_LEAGUES; i++) {
    if (current_league_filter >= 0 && i != current_league_filter) continue;
    if (my_teams[i] == NULL) continue;
    for (int j = 0; my_teams[i][j] != NULL; j++) {
      if (num_filter_teams < 32) {
        strncpy(filter_teams[num_filter_teams], my_teams[i][j], 7);
        filter_teams[num_filter_teams][7] = '\0';
        num_filter_teams++;
      }
    }
  }
}

bool isTeamFiltered(const char* team) {
  for (int i = 0; i < num_filter_teams; i++) {
    if (strcmp(team, filter_teams[i]) == 0) return false;
  }
  return true;
}

bool anyGamesLive() {
  for (int i = 0; i < num_games; i++) {
    if (games[i].is_live) return true;
  }
  return false;
}

// ============================================================
//  DATE HELPER
// ============================================================
void convertDate(const char* isoDate, char* out, int outSize) {
  int y, mo, d, h, mi;
  if (sscanf(isoDate, "%d-%d-%dT%d:%dZ", &y, &mo, &d, &h, &mi) == 5) {
    // Convert UTC to Eastern (UTC-5, ignoring DST for simplicity)
    h -= 5;
    if (h < 0) { h += 24; d--; }

    const char* ampm = "AM";
    if (h >= 12) { ampm = "PM"; if (h > 12) h -= 12; }
    if (h == 0) h = 12;

    snprintf(out, outSize, "%d/%d %d:%02d%s", mo, d, h, mi, ampm);
  } else {
    strncpy(out, isoDate, outSize - 1);
    out[outSize - 1] = '\0';
  }
}

// ============================================================
//  ESPN API FETCH
// ============================================================
bool fetchLeague(int li) {
  if (!enabled_leagues[li]) return false;  // Skip disabled leagues
  if (current_league_filter >= 0 && li != current_league_filter) return false;

  Serial.printf("Fetching %s...\n", league_names[li]);
  ensureWiFi();
  if (WiFi.status() != WL_CONNECTED) return false;

  char url[128];
  snprintf(url, sizeof(url),
           "http://site.api.espn.com/apis/site/v2/sports/%s/%s/scoreboard",
           sport_names[li], espn_slugs[li]);

  for (int attempt = 0; attempt < HTTP_MAX_RETRIES; attempt++) {
    if (attempt > 0) {
      Serial.printf("  Retry %d for %s\n", attempt, league_names[li]);
      delay(2000);
      ensureWiFi();
    }

    // Use raw WiFiClient with HTTP/1.0 to avoid chunked transfer encoding.
    // HTTPClient's chunked handling breaks after large responses on ESP32.
    WiFiClient client;
    if (!client.connect("site.api.espn.com", 80, 15000)) {
      Serial.printf("  Connect failed for %s\n", league_names[li]);
      continue;
    }

    // Send HTTP/1.0 request - server will send Content-Length and close connection
    char path[128];
    snprintf(path, sizeof(path),
             "/apis/site/v2/sports/%s/%s/scoreboard",
             sport_names[li], espn_slugs[li]);
    client.printf("GET %s HTTP/1.0\r\nHost: site.api.espn.com\r\nConnection: close\r\n\r\n", path);

    // Wait for response headers
    unsigned long headerStart = millis();
    while (client.connected() && !client.available() && millis() - headerStart < 15000) {
      delay(10);
    }
    if (!client.available()) {
      Serial.printf("  No response for %s\n", league_names[li]);
      client.stop();
      continue;
    }

    // Skip HTTP headers (read until blank line)
    bool headersOk = false;
    while (client.connected() || client.available()) {
      String line = client.readStringUntil('\n');
      if (line == "\r" || line.length() == 0) {
        headersOk = true;
        break;
      }
    }
    if (!headersOk) {
      Serial.printf("  Bad headers for %s\n", league_names[li]);
      client.stop();
      continue;
    }

    Serial.printf("  Free heap: %d\n", ESP.getFreeHeap());

    // Build filter so ArduinoJson only stores fields we need
    StaticJsonDocument<256> filter;
    filter["events"][0]["date"] = true;
    filter["events"][0]["status"]["type"]["name"] = true;
    filter["events"][0]["status"]["type"]["shortDetail"] = true;
    filter["events"][0]["competitions"][0]["competitors"][0]["team"]["abbreviation"] = true;
    filter["events"][0]["competitions"][0]["competitors"][0]["score"] = true;

    // Stream-parse JSON directly from WiFiClient.
    // This avoids buffering 110KB+ responses into RAM - ArduinoJson reads
    // from the stream and only stores the filtered fields (~2KB).
    client.setTimeout(30000);  // 30 second timeout for slow reads
    DynamicJsonDocument doc(24576);
    DeserializationError err = deserializeJson(doc, client,
                                                DeserializationOption::Filter(filter),
                                                DeserializationOption::NestingLimit(20));
    client.stop();
    if (err) {
      Serial.printf("  JSON error %s: %s\n", league_names[li], err.c_str());
      continue;
    }

    JsonArray events = doc["events"];
    Serial.printf("  %s: %d events\n", league_names[li], events.size());
    for (JsonObject event : events) {
      if (num_games >= MAX_GAMES) break;

      JsonArray competitors = event["competitions"][0]["competitors"];
      if (competitors.size() != 2) continue;

      const char* homeTeam = competitors[0]["team"]["abbreviation"];
      const char* awayTeam = competitors[1]["team"]["abbreviation"];

      if (num_filter_teams > 0) {
        if (isTeamFiltered(homeTeam) && isTeamFiltered(awayTeam)) continue;
      }

      Game& g = games[num_games];
      strncpy(g.home_team, homeTeam ? homeTeam : "???", sizeof(g.home_team) - 1);
      strncpy(g.away_team, awayTeam ? awayTeam : "???", sizeof(g.away_team) - 1);

      const char* homeScore = competitors[0]["score"];
      const char* awayScore = competitors[1]["score"];
      strncpy(g.home_score, homeScore ? homeScore : "0", sizeof(g.home_score) - 1);
      strncpy(g.away_score, awayScore ? awayScore : "0", sizeof(g.away_score) - 1);

      g.home_score_int = atoi(g.home_score);
      g.away_score_int = atoi(g.away_score);

      strncpy(g.league, league_names[li], sizeof(g.league) - 1);
      g.league_idx = li;

      const char* statusName = event["status"]["type"]["name"];
      const char* statusDetail = event["status"]["type"]["shortDetail"];
      const char* gameDate = event["date"];

      g.is_live = (statusName && strcmp(statusName, "STATUS_IN_PROGRESS") == 0);
      g.is_final = (statusName && strcmp(statusName, "STATUS_FINAL") == 0);
      g.is_scheduled = (statusName && strcmp(statusName, "STATUS_SCHEDULED") == 0);

      if (!statusName) statusName = "";
      if (!statusDetail) statusDetail = "";
      if (!gameDate) gameDate = "";

      if (g.is_live) {
        strncpy(g.status, statusDetail[0] ? statusDetail : "LIVE",
                sizeof(g.status) - 1);
        g.status[sizeof(g.status) - 1] = '\0';
      } else if (g.is_final) {
        strncpy(g.status, statusDetail[0] ? statusDetail : "FINAL",
                sizeof(g.status) - 1);
        g.status[sizeof(g.status) - 1] = '\0';
      } else if (g.is_scheduled) {
        convertDate(gameDate, g.status, sizeof(g.status));
      } else if (strcmp(statusName, "STATUS_POSTPONED") == 0) {
        strcpy(g.status, "POSTPONED");
      } else if (strcmp(statusName, "STATUS_CANCELED") == 0) {
        strcpy(g.status, "CANCELED");
      } else {
        strncpy(g.status, statusDetail[0] ? statusDetail : "SCHEDULED",
                sizeof(g.status) - 1);
        g.status[sizeof(g.status) - 1] = '\0';
      }

      num_games++;
    }

    return true;
  }
  return false;
}

void fetchAllGames() {
  buildFilterList();
  num_games = 0;

  for (int i = 0; i < NUM_LEAGUES; i++) {
    fetchLeague(i);
    delay(FETCH_DELAY_MS);
  }

  Serial.printf("Total games: %d\n", num_games);

  // NeoPixel indicator
  if (num_games > 0) {
    pixel.setPixelColor(0, pixel.Color(0, 30, 0));
  } else {
    pixel.setPixelColor(0, pixel.Color(30, 0, 0));
  }
  pixel.show();
}
