// tab5-face.ino - Otto-eyes companion face for an upright M5Stack Tab5.
//
// Screen (720 x 1280, portrait):
//   - Face zone (top 600 px): animated Otto eye GIFs, coloured per reaction.
//   - Text zone (below): a few big words in the middle of the body.
//
// Sleep and wake:
//   - It sleeps by default (closed eyes, dim screen).
//   - It wakes when a person approaches ("presence", or a tap on the screen)
//     or when a dose is due ("remind").
//   - With nobody near and no pending reminder, it falls asleep after 1 min
//     (10 s after "away").
//
// Serial (115200), one command per line:
//   presence [name]        person approaches (from the Pi's ultrasonic / camera)
//   away                   person left
//   <reaction> [title][|detail][|clipId]
//     greet Margaret
//     remind Warfarin|1 pink pill|remind_warfarin
//     happy
//     concerned
//     stop STOP|Taken at 8:02|stop_double
//     wrong Robert's pills
//     sleep
//     idle
//   say greet_morning      play a clip only
//   next                   go to the next reaction (testing)
//   demo                   play Margaret's scripted morning
//
// Libraries: M5Unified / M5GFX, AnimatedGIF (Apache-2.0).
// Eye art: Otto emoji GIFs (MIT), see tools/otto/.

#include <M5Unified.h>

#include <cmath>
#include <cstdlib>
#include <cstring>

#include "OttoFace.h"
#include "Reactions.h"
#include "TextPanel.h"
#include "Voice.h"
#if defined(ARDUINO)
#include "PiLink.h"  // Wi-Fi commands from the Pi (docs/tab5-pi.md)
#endif

// Arduino puts function prototypes above the first function, i.e. above `struct Defaults`
// below; this forward declaration lets `static Defaults defaultsFor(Reaction)` compile.
struct Defaults;

face::OttoFace ottoFace;
text::TextPanel textPanel;

// ---- Voice -------------------------------------------------------------------
// Plays a clip from the audio pack. A missing clip is silent.
void say(const char* clipId) { voice::playClip(clipId); }

// ---- Reactions with their default words and clips --------------------------
// Keep words few and plain. The voice says the full sentence; the screen shows
// only the key words.
struct Defaults {
  const char* title;
  const char* detail;
  const char* clip;
};

static Defaults defaultsFor(Reaction r) {
  switch (r) {
    case Reaction::Greeting:    return {"Hi there!", "", "greet"};
    case Reaction::Reminder:    return {"Pill time", "", "remind"};
    case Reaction::Happy:       return {"Well done!", "", "happy"};
    case Reaction::Concerned:   return {"Show me the label", "", "concerned"};
    case Reaction::Stop:        return {"STOP", "Already taken", "stop"};
    case Reaction::WrongPerson: return {"Not your pills", "", "wrong"};
    default:                    return {"", "", ""};
  }
}

// title / detail / clip may be nullptr: then the defaults are used.
void react(Reaction r, const char* title = nullptr, const char* detail = nullptr,
           const char* clip = nullptr) {
  Defaults d = defaultsFor(r);
  reactions::set(r, title ? title : d.title, detail ? detail : d.detail);
  const char* c = clip ? clip : d.clip;
  if (c && *c) say(c);
}

// A person approaches. If it was asleep, it wakes and greets them.
void onPresence(const char* name = nullptr) {
  if (!reactions::presence()) return;  // Already awake (or busy).
  if (name && *name) {
    static char greeting[64];
    snprintf(greeting, sizeof(greeting), "Hi %s!", name);
    react(Reaction::Greeting, greeting);
  } else {
    react(Reaction::Greeting);
  }
}

// ---- Screen brightness: dim while asleep -------------------------------------
constexpr uint8_t kAwakeBrightness = 110;  // was 200: the panel ran hot
constexpr uint8_t kSleepBrightness = 15;

static void updateBrightness() {
  static int shown = -1;
  const int want = reactions::isAsleep() ? kSleepBrightness : kAwakeBrightness;
  if (want != shown) {
    M5.Display.setBrightness(want);
    shown = want;
  }
}

// ---- Demo: Margaret's scripted morning (from HANDOVER.md) -------------------
struct DemoStep {
  uint32_t atMs;
  Reaction reaction;
  const char* title;
  const char* detail;
  const char* clip;
};

static const DemoStep kDemo[] = {
    {0, Reaction::Sleep, nullptr, nullptr, nullptr},                          // Asleep.
    {4000, Reaction::Reminder, "Warfarin", "1 pink pill", "remind_warfarin"}, // 8:00 dose wakes it.
    {12000, Reaction::Happy, "Well done!", "", "happy_taken"},
    {19000, Reaction::Sleep, nullptr, nullptr, nullptr},                      // Fast-forward: asleep.
    {23000, Reaction::Greeting, "Hi Margaret!", "", "greet_margaret"},        // She walks up.
    {29000, Reaction::Stop, "STOP", "Taken at 8:02", "stop_double"},
    {37000, Reaction::Concerned, "Show me the label", "", "concerned_unknown"},
    {45000, Reaction::WrongPerson, "Robert's pills", "", "wrong_robert"},
    {54000, Reaction::Sleep, nullptr, nullptr, nullptr},
};
static constexpr int kDemoSteps = sizeof(kDemo) / sizeof(kDemo[0]);
static int demoIndex = -1;  // -1 = demo not running.
static uint32_t demoStartMs = 0;

void startDemo() {
  demoIndex = 0;
  demoStartMs = lgfx::millis();
}

static void updateDemo() {
  if (demoIndex < 0) return;
  if (lgfx::millis() - demoStartMs < kDemo[demoIndex].atMs) return;
  const DemoStep& s = kDemo[demoIndex];
  react(s.reaction, s.title, s.detail, s.clip);
  if (++demoIndex >= kDemoSteps) demoIndex = -1;
}

// ---- Input -------------------------------------------------------------------
static bool reactionFromName(const char* name, Reaction* out) {
  static const Reaction all[] = {Reaction::Idle,      Reaction::Greeting,
                                 Reaction::Reminder,  Reaction::Happy,
                                 Reaction::Concerned, Reaction::Stop,
                                 Reaction::WrongPerson, Reaction::Sleep};
  for (Reaction r : all) {
    if (strcmp(name, reactions::name(r)) == 0) {
      *out = r;
      return true;
    }
  }
  return false;
}

// Handles one text command, for example "remind Warfarin|1 pink pill|remind_warfarin".
void handleCommand(char* line) {
  while (*line == ' ') ++line;
  char* args = strchr(line, ' ');
  if (args) *args++ = '\0';

  if (strcmp(line, "demo") == 0) {
    startDemo();
    return;
  }
  if (strcmp(line, "say") == 0) {
    say(args);
    return;
  }
  if (strcmp(line, "next") == 0) {
    demoIndex = -1;
    react((Reaction)(((int)reactions::get().reaction + 1) % 8));
    return;
  }
  demoIndex = -1;  // A real event stops the demo.
  if (strcmp(line, "presence") == 0 || strcmp(line, "wake") == 0) {
    onPresence(args);
    return;
  }
  if (strcmp(line, "away") == 0) {
    reactions::away();
    return;
  }
  Reaction r;
  if (!reactionFromName(line, &r)) return;

  // Split "title|detail|clip". Missing parts use the defaults.
  const char* parts[3] = {nullptr, nullptr, nullptr};
  if (args && *args) {
    for (int i = 0; i < 3 && args; ++i) {
      parts[i] = args;
      args = strchr(args, '|');
      if (args) *args++ = '\0';
    }
  }
  // "greet Margaret" -> "Hi Margaret!".
  static char greeting[64];
  if (r == Reaction::Greeting && parts[0] && !strchr(parts[0], ' ') && !strchr(parts[0], '!')) {
    snprintf(greeting, sizeof(greeting), "Hi %s!", parts[0]);
    parts[0] = greeting;
  }
  react(r, parts[0], parts[1], parts[2]);
}

#if defined(ARDUINO)
static void readSerial() {
  static char buf[192];
  static size_t len = 0;
  while (Serial.available()) {
    char ch = (char)Serial.read();
    if (ch == '\n' || ch == '\r') {
      if (len > 0) {
        buf[len] = '\0';
        handleCommand(buf);
        len = 0;
      }
    } else if (len < sizeof(buf) - 1) {
      buf[len++] = ch;
    }
  }
}
#endif

bool tapWakes = true;  // A tap counts as a person nearby. Set false to ignore taps.

static void readTouch() {
  if (!tapWakes || !M5.Touch.isEnabled()) return;
  auto t = M5.Touch.getDetail();
  if (!t.wasPressed()) return;
  demoIndex = -1;
  onPresence();
}

// ---- Arduino entry points ------------------------------------------------------
void setup() {
  auto cfg = M5.config();
  M5.begin(cfg);
#if defined(ARDUINO)
  Serial.begin(115200);
#endif
  // Upright (portrait). If the face is upside down in the body, use rotation 2.
  if (M5.Display.width() > M5.Display.height()) M5.Display.setRotation(M5.Display.getRotation() ^ 1);
  M5.Display.fillScreen(face::kBackground);
  voice::begin();

  // Both need PSRAM (about 0.7 MB + 0.9 MB + 1 MB).
  if (!ottoFace.begin() || !textPanel.begin()) {
    M5.Display.setTextColor(TFT_RED);
    M5.Display.setFont(&fonts::DejaVu40);
    M5.Display.drawString("Enable PSRAM", 40, 40);
    while (true) lgfx::delay(1000);
  }

  react(Reaction::Sleep);  // Asleep until a person approaches or a dose is due.
#if defined(ARDUINO)
  piLink::begin();
#endif
}

void loop() {
  M5.update();
#if defined(ARDUINO)
  readSerial();
  piLink::poll(handleCommand);
#endif
  readTouch();
  updateDemo();
  reactions::tick();
  updateBrightness();
  ottoFace.update();
  textPanel.update();
  lgfx::delay(1);  // the face paces itself at 60 Hz; a longer wait here capped it near 50 fps
}
