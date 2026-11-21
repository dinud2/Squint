// Reactions.h - the companion's reaction state.
//
// The main loop (or the network code) writes the state with reactions::set().
// The face and the text panel read it with reactions::get().
// A mutex guards the state, so network code may run in another task.

#pragma once

#include <M5Unified.h>

#include <cstring>
#include <mutex>

enum class Reaction {
  Idle,         // Otto "neutral": looks around, blinks. White.
  Greeting,     // Otto "happy": smiling eyes, bounce. White.
  Reminder,     // Otto "winking": wink and sparkle. White. Words show the pill.
  Happy,        // Otto "loving": heart eyes, floating heart. White.
  Concerned,    // Otto "confused": question mark. Amber.
  Stop,         // Otto "shocked": wide eyes, red, flashing frame. Holds until cleared.
  WrongPerson,  // Otto "embarrassed": eyes dart aside, sweat drop. Amber.
  Sleep,        // Otto "sleepy": eyes close, floating "z". Dim blue.
  Ask,          // "Did you take it?": small eyes on top, Yes / No buttons below (Ask.h).
                // Kept last: the "next" / cycle code steps through the first 8 only.
};

struct ReactionState {
  Reaction reaction = Reaction::Idle;
  uint32_t sinceMs = 0;   // When this reaction started (lgfx::millis()).
  uint32_t holdMs = 0;    // Return to Idle after this time. 0 = hold.
  char title[64] = "";    // Big caption line.
  char detail[96] = "";   // Smaller caption line.
};

namespace reactions {

inline std::mutex& mutex() {
  static std::mutex m;
  return m;
}

inline ReactionState& state() {
  static ReactionState s;
  return s;
}

// ---- Sleep and wake ------------------------------------------------------------
// The companion sleeps by default. It wakes when a person approaches
// ("presence") or when a dose is due ("remind"). It goes back to sleep after
// kAwakeMs with no person and no pending reminder.
constexpr uint32_t kAwakeMs = 60000;      // Idle -> Sleep after 1 min with nobody.
constexpr uint32_t kAfterAwayMs = 10000;  // Idle -> Sleep 10 s after the person leaves.

// How long each reaction stays. Timed reactions go back to Idle, and Idle
// goes back to Sleep. 0 = hold until the next event.
inline uint32_t defaultHoldMs(Reaction r) {
  switch (r) {
    case Reaction::Idle:        return kAwakeMs;
    case Reaction::Greeting:    return 6000;
    case Reaction::Happy:       return 6000;
    case Reaction::Concerned:   return 12000;
    case Reaction::WrongPerson: return 10000;
    case Reaction::Stop:        return 30000;  // Long, but never stuck forever.
    default:                    return 0;      // Reminder, Sleep and Ask hold.
  }
}

inline void set(Reaction r, const char* title = "", const char* detail = "",
                int32_t holdMs = -1) {
  std::lock_guard<std::mutex> lock(mutex());
  ReactionState& s = state();
  s.reaction = r;
  s.sinceMs = lgfx::millis();
  s.holdMs = holdMs < 0 ? defaultHoldMs(r) : (uint32_t)holdMs;
  strncpy(s.title, title ? title : "", sizeof(s.title) - 1);
  s.title[sizeof(s.title) - 1] = '\0';
  strncpy(s.detail, detail ? detail : "", sizeof(s.detail) - 1);
  s.detail[sizeof(s.detail) - 1] = '\0';
}

// Returns a copy, so the caller can draw without holding the lock.
inline ReactionState get() {
  std::lock_guard<std::mutex> lock(mutex());
  return state();
}

// Call this often from loop(). Timed reactions return to Idle; Idle falls asleep.
inline void tick() {
  ReactionState s = get();
  if (s.holdMs > 0 && lgfx::millis() - s.sinceMs > s.holdMs) {
    set(s.reaction == Reaction::Idle ? Reaction::Sleep : Reaction::Idle);
  }
}

inline bool isAsleep() { return get().reaction == Reaction::Sleep; }

// A person is near. Wakes the companion, or keeps it awake.
// Returns true if it was asleep (so the caller can greet).
inline bool presence() {
  ReactionState s = get();
  if (s.reaction == Reaction::Sleep) {
    set(Reaction::Idle);
    return true;
  }
  if (s.reaction == Reaction::Idle) set(Reaction::Idle);  // Restart the awake timer.
  return false;  // Busy with another reaction: leave it alone.
}

// The person left. Idle falls asleep soon. Other reactions are not cut short.
inline void away() {
  if (get().reaction == Reaction::Idle) set(Reaction::Idle, "", "", (int32_t)kAfterAwayMs);
}

inline const char* name(Reaction r) {
  switch (r) {
    case Reaction::Idle:        return "idle";
    case Reaction::Greeting:    return "greet";
    case Reaction::Reminder:    return "remind";
    case Reaction::Happy:       return "happy";
    case Reaction::Concerned:   return "concerned";
    case Reaction::Stop:        return "stop";
    case Reaction::WrongPerson: return "wrong";
    case Reaction::Sleep:       return "sleep";
    case Reaction::Ask:         return "ask";
  }
  return "idle";
}

}  // namespace reactions
