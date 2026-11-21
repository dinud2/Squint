// Ask.h - the "Did you take it?" Yes / No question (docs/tab5-pi.md).
//
//   ask <Med>|Did you take it?     Yes / No, waits for a tap (no timeout here: the Pi gives up
//                                  after 30 s and sends another line).
//   taken <Med>|Did you take it?   hand-to-mouth was >= 90% sure: Yes is pre-selected and ticks
//                                  itself after 2 s. The Pi records that by itself, so nothing is
//                                  sent unless the person taps No within the 2 s.
//
// A tap answers the Pi with POST /doses/confirm {"taken": true|false} (from PiLink's background
// task, never from the UI loop). After Yes the Pi sends "happy Well done!|<Med>", after No "idle".
//
// Everything here runs on the loop task (handleCommand, readTouch, the face), so no lock.

#pragma once

#include <M5Unified.h>

#include <cstdio>
#include <cstring>

#include "Reactions.h"

namespace ask {

enum class Phase {
  Waiting,   // "ask": waiting for a tap
  Counting,  // "taken": Yes ticks itself when the 2 s are up
  Yes,       // tapped Yes: waiting for the Pi's "happy"
  No,        // tapped No: waiting for the Pi's "idle"
  AutoYes,   // "taken" ticked itself (or Yes was tapped): green check, then "Well done!"
};

constexpr uint32_t kAutoMs = 2000;          // "taken": Yes ticks itself after this
constexpr uint32_t kAutoShowMs = 1500;      // then the green check stays this long
constexpr uint32_t kAnswerTimeoutMs = 8000;  // the Pi did not answer a tap: back to idle

struct State {
  Phase phase = Phase::Waiting;
  char med[48] = "";
  char question[64] = "";
  uint32_t startMs = 0;   // when the question appeared
  uint32_t answerMs = 0;  // when it was answered
  uint32_t version = 0;   // bumps on every change the screen must redraw
};

inline State& state() {
  static State s;
  return s;
}

inline bool active() { return reactions::get().reaction == Reaction::Ask; }

// Set by the sketch: sends the answer to the Pi (PiLink on the Tab5, a printf in the preview).
inline void (*&sender())(bool) {
  static void (*f)(bool) = nullptr;
  return f;
}

inline void send(bool taken) {
  if (sender()) sender()(taken);
}

// "ask" (autoYes = false) or "taken" (autoYes = true).
inline void start(bool autoYes, const char* med, const char* question) {
  State& s = state();
  s.phase = autoYes ? Phase::Counting : Phase::Waiting;
  snprintf(s.med, sizeof(s.med), "%s", med ? med : "");
  snprintf(s.question, sizeof(s.question), "%s", question && *question ? question : "Did you take it?");
  s.startMs = lgfx::millis();
  s.answerMs = 0;
  ++s.version;
  reactions::set(Reaction::Ask, s.med, s.question, 0);  // holds until the Pi's next line
}

inline void answer(Phase p) {
  State& s = state();
  s.phase = p;
  s.answerMs = lgfx::millis();
  ++s.version;
}

// A tap on a button (yes = true for Yes).
inline void tap(bool yes) {
  if (!active()) return;
  State& s = state();
  switch (s.phase) {
    case Phase::Waiting:
      answer(yes ? Phase::Yes : Phase::No);
      send(yes);
      break;
    case Phase::Counting:
      // No cancels the Pi's auto-confirm. Yes only ticks early: the Pi records it by itself.
      answer(yes ? Phase::AutoYes : Phase::No);
      if (!yes) send(false);
      break;
    default:
      break;  // already answered
  }
}

// 0..1 of the "taken" countdown (1 when not counting).
inline float countdown() {
  const State& s = state();
  if (s.phase != Phase::Counting) return 1;
  const float f = (float)(lgfx::millis() - s.startMs) / kAutoMs;
  return f < 0 ? 0 : (f > 1 ? 1 : f);
}

// Call often from loop().
inline void tick() {
  if (!active()) return;
  State& s = state();
  const uint32_t now = lgfx::millis();
  if (s.phase == Phase::Counting && now - s.startMs >= kAutoMs) answer(Phase::AutoYes);
  // The Pi does not send "happy" after its own auto-confirm, so say it here.
  if (s.phase == Phase::AutoYes && now - s.answerMs >= kAutoShowMs) {
    reactions::set(Reaction::Happy, "Well done!", s.med);
    return;
  }
  // A tap the Pi never answered (Wi-Fi down?): don't stay stuck on the question.
  if ((s.phase == Phase::Yes || s.phase == Phase::No) && now - s.answerMs >= kAnswerTimeoutMs)
    reactions::set(Reaction::Idle);
}

}  // namespace ask
