// Desktop preview: compiles the real Tab5 sketch against M5GFX's SDL panel.
#include <M5Unified.h>
#include <AnimatedGIF.h>  // Listed here so PlatformIO finds the library. Keep after M5Unified.

#include "../../tab5-face.ino"

#include <cstdio>
#include <vector>

#if defined(FACE_SNAPSHOTS)
// Saves the window as snapshots/<name>.ppm after each reaction settles.
static void saveSnapshot(const char* name) {
  const int w = M5.Display.width();
  const int h = M5.Display.height();
  std::vector<lgfx::rgb888_t> px(w * h);
  M5.Display.readRect(0, 0, w, h, px.data());
  char path[128];
  snprintf(path, sizeof(path), "snapshots/%s.ppm", name);
  FILE* f = fopen(path, "wb");
  if (!f) return;
  fprintf(f, "P6\n%d %d\n255\n", w, h);
  for (auto& p : px) {
    uint8_t rgb[3] = {p.r, p.g, p.b};
    fwrite(rgb, 1, 3, f);
  }
  fclose(f);
  printf("saved %s\n", path);
}

static const DemoStep kShots[] = {
    {0, Reaction::Idle, nullptr, nullptr, nullptr},
    {0, Reaction::Greeting, "Hi Margaret!", "", nullptr},
    {0, Reaction::Reminder, "Warfarin", "1 pink pill", nullptr},
    {0, Reaction::Happy, nullptr, nullptr, nullptr},
    {0, Reaction::Concerned, nullptr, nullptr, nullptr},
    {0, Reaction::Stop, "STOP", "Taken at 8:02", nullptr},
    {0, Reaction::WrongPerson, "Robert's pills", "", nullptr},
    {0, Reaction::Sleep, nullptr, nullptr, nullptr},
};

static void runFor(uint32_t ms, bool* running) {
  uint32_t until = lgfx::millis() + ms;
  while (lgfx::millis() < until && *running) loop();
}

static int checks = 0, failures = 0;
static void expect(bool ok, const char* what) {
  ++checks;
  if (!ok) ++failures;
  printf("%s  %s\n", ok ? "PASS" : "FAIL", what);
}

// Checks the sleep / wake rules with short timers.
static void checkSleepWake(bool* running) {
  expect(reactions::isAsleep(), "boots asleep");
  onPresence("Margaret");
  expect(reactions::get().reaction == Reaction::Greeting, "presence wakes it with a greeting");
  expect(strcmp(reactions::get().title, "Hi Margaret!") == 0, "greeting uses the name");
  reactions::set(Reaction::Idle, "", "", 300);
  runFor(400, running);
  expect(reactions::isAsleep(), "idle falls asleep when its timer ends");
  react(Reaction::Reminder, "Warfarin", "1 pink pill");
  expect(reactions::get().reaction == Reaction::Reminder, "a reminder wakes it");
  reactions::away();
  runFor(200, running);
  expect(reactions::get().reaction == Reaction::Reminder, "away does not cut a reminder short");
  onPresence();
  expect(reactions::get().reaction == Reaction::Reminder, "presence does not cut a reminder short");
  react(Reaction::Idle);
  reactions::away();
  expect(reactions::get().holdMs == reactions::kAfterAwayMs, "away shortens the idle timer");
  react(Reaction::Sleep);
}

static void saveSmallFrame(int n) {
  const int w = M5.Display.width(), h = M5.Display.height();
  std::vector<lgfx::rgb888_t> px(w * h);
  M5.Display.readRect(0, 0, w, h, px.data());
  char path[64];
  snprintf(path, sizeof(path), "snapshots/rec/%04d.ppm", n);
  FILE* f = fopen(path, "wb");
  fprintf(f, "P6\n%d %d\n255\n", w / 4, h / 4);
  for (int y = 0; y < h; y += 4)
    for (int x = 0; x < w; x += 4) {
      auto& p = px[y * w + x];
      uint8_t rgb[3] = {p.r, p.g, p.b};
      fwrite(rgb, 1, 3, f);
    }
  fclose(f);
}

int user_func(bool* running) {
  setup();
  tapWakes = false;  // Stray SDL clicks must not change the shots.
  system("mkdir -p snapshots");
  checkSleepWake(running);

  // Asleep: the eyes close once, then stay closed.
  runFor(3500, running);
  saveSnapshot("sleep");
  for (const auto& s : kShots) {
    if (s.reaction == Reaction::Sleep) continue;
    react(s.reaction, s.title, s.detail, s.clip);
    // Mid-loop, the expression is at full strength (neutral blinks at ~1.9 s).
    runFor(1500, running);
    saveSnapshot(reactions::name(s.reaction));
  }
#if defined(FACE_RECORD)
  // Small frames (1/4 size) every 120 ms: asleep, wake on presence, then each reaction.
  system("mkdir -p snapshots/rec");
  int n = 0;
  auto record = [&](uint32_t ms) {
    uint32_t end = lgfx::millis() + ms, next = 0;
    while (lgfx::millis() < end && *running) {
      loop();
      if (lgfx::millis() < next) continue;
      next = lgfx::millis() + 120;
      saveSmallFrame(n++);
    }
  };
  react(Reaction::Sleep);
  record(5000);                    // Falls asleep, stays asleep.
  onPresence("Margaret");
  record(3300);                    // Wakes and greets.
  for (const auto& s : kShots) {
    if (s.reaction == Reaction::Sleep || s.reaction == Reaction::Idle ||
        s.reaction == Reaction::Greeting) continue;
    react(s.reaction, s.title, s.detail, s.clip);
    record(3300);
  }
  react(Reaction::Sleep);
  record(4000);
#endif
  printf("%d checks, %d failed\n", checks, failures);
  *running = false;
  exit(0);  // Panel_sdl keeps its window loop alive otherwise.
}
#endif

int user_func(bool* running);
int main(int, char**) { return lgfx::Panel_sdl::main(user_func, 0); }

#if !defined(FACE_SNAPSHOTS)
int user_func(bool* running) {
  setup();
  do { loop(); } while (*running);
  return 0;
}
#endif
