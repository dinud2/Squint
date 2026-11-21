// OttoFace.h - plays the Otto eye GIFs in the face zone of an upright Tab5.
//
// - The GIFs are 480 x 480, 16 grey levels, made by tools/otto/generate_emojis.py.
//   AnimatedGIF decodes at most 480 px wide on the ESP32, so the face is drawn
//   1.25x larger (600 x 600) with smoothing.
// - They are flashed with the sketch (src/gifs/*.h), so no SD card is needed.
// - Each reaction picks one GIF and one colour. The grey levels become shades
//   of that colour, so the eyes turn amber for "check this" and red for STOP.
// - Every GIF loop starts and ends on the neutral eyes, so switching is smooth.

#pragma once

#include <M5Unified.h>
// Keep AnimatedGIF after M5Unified: both define PROGMEM helpers.
#include <AnimatedGIF.h>

#include <algorithm>

#include "Reactions.h"
#include "src/gifs/otto_confused.h"
#include "src/gifs/otto_embarrassed.h"
#include "src/gifs/otto_happy.h"
#include "src/gifs/otto_loving.h"
#include "src/gifs/otto_neutral.h"
#include "src/gifs/otto_asleep.h"
#include "src/gifs/otto_fall_asleep.h"
#include "src/gifs/otto_shocked.h"
#include "src/gifs/otto_winking.h"

namespace face {

// ---- Layout (screen pixels, portrait 720 x 1280) ---------------------------
constexpr int kWidth = 720;
constexpr int kFaceBottom = 600;  // Face zone is y 0 .. 600.
constexpr int kGifSize = 480;         // AnimatedGIF's width limit on ESP32.
constexpr float kGifZoom = 1.25f;     // 480 -> 600 px on screen.
constexpr int kFaceCenterX = kWidth / 2;
constexpr int kFaceCenterY = kFaceBottom / 2;

// ---- Colours ---------------------------------------------------------------
struct Rgb {
  uint8_t r, g, b;
};
constexpr Rgb kWhite{0xFF, 0xFF, 0xFF};
constexpr Rgb kAmber{0xEF, 0x9F, 0x27};
constexpr Rgb kRed{0xE2, 0x4B, 0x4A};
constexpr Rgb kSleepBlue{0x5A, 0x86, 0xC4};
constexpr uint16_t kBackground = 0x0000;

inline Rgb colorFor(Reaction r) {
  switch (r) {
    case Reaction::Concerned:
    case Reaction::WrongPerson: return kAmber;
    case Reaction::Stop:        return kRed;
    case Reaction::Sleep:       return kSleepBlue;
    default:                    return kWhite;
  }
}

inline uint16_t color565(Rgb c) {
  return ((c.r & 0xF8) << 8) | ((c.g & 0xFC) << 3) | (c.b >> 3);
}

// ---- Which GIF for which reaction ------------------------------------------
struct Gif {
  const uint8_t* data;
  uint32_t len;
};

// intro plays once (if set), then loop repeats.
struct Clip {
  Gif intro;
  Gif loop;
};

inline Clip clipFor(Reaction r) {
  switch (r) {
    case Reaction::Greeting:    return {{}, {kOtto_happy, kOtto_happy_len}};
    case Reaction::Reminder:    return {{}, {kOtto_winking, kOtto_winking_len}};
    case Reaction::Happy:       return {{}, {kOtto_loving, kOtto_loving_len}};
    case Reaction::Concerned:   return {{}, {kOtto_confused, kOtto_confused_len}};
    case Reaction::Stop:        return {{}, {kOtto_shocked, kOtto_shocked_len}};
    case Reaction::WrongPerson: return {{}, {kOtto_embarrassed, kOtto_embarrassed_len}};
    case Reaction::Sleep:       // Eyes close once, then stay closed.
      return {{kOtto_fall_asleep, kOtto_fall_asleep_len}, {kOtto_asleep, kOtto_asleep_len}};
    default:                    return {{}, {kOtto_neutral, kOtto_neutral_len}};
  }
}

// ---- Player ----------------------------------------------------------------
class OttoFace {
 public:
  bool begin() {
    gifCanvas_.setPsram(true);
    gifCanvas_.setColorDepth(16);
    frameCanvas_.setPsram(true);
    frameCanvas_.setColorDepth(16);
    if (!gifCanvas_.createSprite(kGifSize, kGifSize)) return false;
    if (!frameCanvas_.createSprite(kWidth, kFaceBottom)) return false;
    gif_.begin(GIF_PALETTE_RGB565_LE);
    return true;
  }

  // Call often from loop(). Draws the next frame when it is due.
  void update() {
    const ReactionState s = reactions::get();
    if (!open_ || s.reaction != reaction_ || s.sinceMs != sinceMs_) start(s);

    const uint32_t now = lgfx::millis();
    if ((int32_t)(now - nextFrameMs_) < 0) return;

    int delayMs = 80;
    if (gif_.playFrame(false, &delayMs, this) == 0) {
      if (inIntro_) {
        openGif(clipFor(reaction_).loop);  // Intro done: start the loop.
        inIntro_ = false;
      } else {
        gif_.reset();  // Loop.
      }
    }
    nextFrameMs_ = now + (delayMs > 0 ? delayMs : 80);
    present();
  }

 private:
  AnimatedGIF gif_;
  M5Canvas gifCanvas_{&M5.Display};    // Keeps the GIF picture between delta frames.
  M5Canvas frameCanvas_{&M5.Display};  // Whole face zone: GIF + STOP frame.
  uint16_t lut_[16] = {};              // Grey level -> tinted colour (byte-swapped).
  Reaction reaction_ = Reaction::Idle;
  uint32_t sinceMs_ = 0;
  uint32_t nextFrameMs_ = 0;
  bool open_ = false;
  bool inIntro_ = false;

  void start(const ReactionState& s) {
    // Same GIF and only new words (or a refreshed timer)? Keep playing.
    const bool sameClip = open_ && clipFor(s.reaction).loop.data == clipFor(reaction_).loop.data;
    reaction_ = s.reaction;
    sinceMs_ = s.sinceMs;
    buildLut(colorFor(s.reaction));
    if (sameClip) return;

    const Clip clip = clipFor(s.reaction);
    inIntro_ = clip.intro.data != nullptr;
    openGif(inIntro_ ? clip.intro : clip.loop);
    gifCanvas_.fillSprite(kBackground);
    nextFrameMs_ = lgfx::millis();
  }

  void openGif(const Gif& g) {
    if (open_) gif_.close();
    open_ = gif_.open(const_cast<uint8_t*>(g.data), (int)g.len, onDraw) != 0;
  }

  void buildLut(Rgb c) {
    for (int i = 0; i < 16; ++i) {
      Rgb shade{(uint8_t)(c.r * i / 15), (uint8_t)(c.g * i / 15), (uint8_t)(c.b * i / 15)};
      const uint16_t v = color565(shade);
      lut_[i] = (uint16_t)((v << 8) | (v >> 8));  // Sprites store RGB565 big-endian.
    }
  }

  // AnimatedGIF calls this once per line of each frame.
  static void onDraw(GIFDRAW* d) {
    auto* self = static_cast<OttoFace*>(d->pUser);
    const int y = d->iY + d->y;
    if (y < 0 || y >= kGifSize) return;
    auto* row = static_cast<uint16_t*>(self->gifCanvas_.getBuffer()) + y * kGifSize;
    const uint8_t* px = d->pPixels;
    const bool transparent = d->ucHasTransparency;
    const uint8_t clear = d->ucTransparent;
    const int x0 = d->iX;
    const int w = std::min(d->iWidth, kGifSize - x0);
    for (int i = 0; i < w; ++i) {
      const uint8_t index = px[i];
      if (transparent && index == clear) continue;  // Unchanged pixel (delta frame).
      row[x0 + i] = self->lut_[index & 15];
    }
  }

  void present() {
    frameCanvas_.fillSprite(kBackground);
    gifCanvas_.pushRotateZoomWithAA(&frameCanvas_, kFaceCenterX, kFaceCenterY, 0.0f,
                                    kGifZoom, kGifZoom);
    if (reaction_ == Reaction::Stop) {
      // Steady red frame round the face, plus a thicker flash every 400 ms.
      const int width = (lgfx::millis() / 400) % 2 == 0 ? 22 : 9;
      const uint16_t red = color565(kRed);
      for (int i = 0; i < width; ++i) {
        frameCanvas_.drawRoundRect(i, i, kWidth - 2 * i, kFaceBottom - 2 * i, 40, red);
      }
    }
    frameCanvas_.pushSprite(&M5.Display, 0, 0);
  }
};

}  // namespace face
