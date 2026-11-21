// Voice.h - plays voice clips from the audio pack.
//
// Clip contract (for the Gemini audio pack):
//   - One WAV file per clip: 16-bit PCM, mono. 24 kHz is fine (Gemini TTS output).
//   - File path on the Tab5: /voice/<clipId>.wav in LittleFS (sketch folder: data/voice/).
//   - clipId: lowercase letters, digits and "_" only. Example: stop_double.
//
// The bar above the words pulses while a clip plays (see isTalking() in tab5-face.ino).
// If a clip is missing, playClip() returns false, and the bar pulses for a
// fixed time instead.

#pragma once

#include <M5Unified.h>

#if defined(ARDUINO)
#include <LittleFS.h>
#endif

namespace voice {

#if defined(ARDUINO)
inline uint8_t*& buffer() {
  static uint8_t* b = nullptr;
  return b;
}

inline bool begin() {
  M5.Speaker.begin();
  M5.Speaker.setVolume(220);  // Loud: many older adults have hearing loss.
  return LittleFS.begin(false);
}

inline bool playClip(const char* clipId) {
  if (!clipId || !*clipId) return false;
  char path[64];
  snprintf(path, sizeof(path), "/voice/%s.wav", clipId);
  File f = LittleFS.open(path, "r");
  if (!f) return false;

  M5.Speaker.stop();
  free(buffer());
  size_t len = f.size();
  buffer() = (uint8_t*)ps_malloc(len);  // Clips live in PSRAM while they play.
  if (!buffer()) return false;
  f.read(buffer(), len);
  f.close();
  return M5.Speaker.playWav(buffer(), len, 1, -1, true);
}
#else
// Desktop preview: no audio.
inline bool begin() { return false; }
inline bool playClip(const char*) { return false; }
#endif

}  // namespace voice
