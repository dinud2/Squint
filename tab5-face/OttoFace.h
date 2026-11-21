// OttoFace.h - the companion's eyes, drawn in code at the display's 60 Hz.
//
// Same expressions as the Otto eye GIFs (docs/all-reactions.png), redrawn from smooth,
// anti-aliased shapes every frame instead of played from GIFs, so motion is fluid:
// blinks, glances, bounces and heartbeats are computed per frame, and changing
// expression is a quick blink (close the old eyes, open the new ones).
// Minimal on purpose: just the eyes and the words.
//
// Only the eyes: no frames, boxes or symbols around them.
//   idle       round eyes that glance around and blink          white
//   greet      ^^ smiling crescents, gentle bounce               white
//   remind     one eye + a wink                                   white
//   happy      hearts with a heartbeat                            white
//   concerned  tall eye + half-closed eye                         amber
//   stop       ring eyes                                          red
//   wrong      lowered eyes glancing away                         amber
//   sleep      closed eyes, slow breathing                        dim blue

#pragma once

#include <M5Unified.h>

#include <algorithm>
#include <cmath>
#include <cstdlib>

#include "Reactions.h"

namespace face {

// ---- Layout (screen pixels, landscape 1280 x 720; the C270 sits on top) -----
constexpr int kWidth = 1280;
constexpr int kHeight = 720;
constexpr int kFaceBottom = 440;  // Face zone is y 0 .. 440 (text panel below).
constexpr float kEyeSize = 240.0f;     // Eye diameter.
constexpr float kEyeGap = 430.0f;      // Distance between eye centres.
constexpr float kEyeY = 225.0f;        // Eye centre height.
constexpr uint32_t kFrameUs = 16667;   // 60 Hz.

// The panel is portrait in memory (720 x 1280). Pushing in a landscape rotation made M5GFX
// transpose every pixel (~15 ms per frame), so the display stays in its native portrait
// rotation and the face is drawn already rotated: every shape helper maps landscape
// (logical) points to portrait (physical) ones with T(). Set kFlip if it shows upside down.
constexpr bool kFlip = false;
constexpr int kPanelW = 720;                    // physical (portrait) width
constexpr int kCanvasW = kFaceBottom;           // face canvas, physical: 440 x 1280
constexpr int kCanvasH = kWidth;
constexpr int kCanvasX = kFlip ? 0 : kPanelW - kFaceBottom;  // physical x of the face canvas

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
inline Rgb scaled(Rgb c, float k) {
  k = std::max(0.0f, std::min(1.0f, k));
  return {(uint8_t)(c.r * k), (uint8_t)(c.g * k), (uint8_t)(c.b * k)};
}

// ---- Easing ----------------------------------------------------------------
inline float clamp01(float x) { return x < 0 ? 0 : (x > 1 ? 1 : x); }
inline float easeInOut(float x) { x = clamp01(x); return x * x * (3 - 2 * x); }
inline float easeOutBack(float x) {
  x = clamp01(x);
  const float c1 = 1.4f, c3 = c1 + 1;
  return 1 + c3 * powf(x - 1, 3) + c1 * powf(x - 1, 2);
}
inline float frand(float a, float b) { return a + (b - a) * (float)(rand() % 10000) / 10000.0f; }
constexpr float kPi = 3.14159265f;

// ---- Renderer ----------------------------------------------------------------
class OttoFace {
 public:
  bool begin() {
    canvas_.setPsram(true);
    canvas_.setColorDepth(16);
    if (!canvas_.createSprite(kCanvasW, kCanvasH)) return false;
    // Pre-render the hearts: anti-aliased circles are costly, copying a sprite is not.
    for (int i = 0; i < kHeartSteps; ++i) {
      const float sz = kEyeSize * 1.08f * (1 + 0.07f * i / (kHeartSteps - 1));
      heartSize_[i] = sz;
      const int w = (int)(sz * 1.12f) + 8;
      hearts_[i].setPsram(true);
      hearts_[i].setColorDepth(16);
      if (!hearts_[i].createSprite(w, w)) return false;
      hearts_[i].fillSprite(kBackground);
      g_ = &hearts_[i];
      heart(w / 2.0f, w / 2.0f, sz, color565(kWhite));
      g_ = &canvas_;
    }
    lastUs_ = nextUs_ = lgfx::micros();
    nextBlinkMs_ = lgfx::millis() + 2500;
    nextGlanceMs_ = lgfx::millis() + 1500;
    return true;
  }

  // Call often from loop(): draws a frame every 16.7 ms.
  void update() {
    const uint32_t nowUs = lgfx::micros();
    if ((int32_t)(nowUs - nextUs_) < 0) return;
    nextUs_ += kFrameUs;
    if ((int32_t)(nowUs - nextUs_) > 0) nextUs_ = nowUs + kFrameUs;  // fell behind: don't burst
    const float dt = std::min(0.1f, (nowUs - lastUs_) / 1e6f);
    lastUs_ = nowUs;

    const ReactionState s = reactions::get();
    if (s.reaction != shown_) {
      if (!started_) {
        shown_ = prev_ = s.reaction;
        started_ = true;
      } else {
        prev_ = shown_;
        shown_ = s.reaction;
        changeMs_ = lgfx::millis();
      }
    }
    const uint32_t t0 = lgfx::micros();
    // Dirty rectangles: only what was drawn last frame is cleared, and only the union of
    // last frame's and this frame's ink is sent to the display (the whole face zone is
    // 430k pixels; pushing it every frame alone took ~36 ms).
    fill(prevInk_[0], kBackground);
    fill(prevInk_[1], kBackground);
    ink_[0] = ink_[1] = Box{};
    frameW_ = 0;
    draw(dt);
    const uint32_t t1 = lgfx::micros();
    const Box l = unite(prevInk_[0], ink_[0]), r = unite(prevInk_[1], ink_[1]);
    if (!l.empty() && !r.empty() && l.x0 <= r.x1 && r.x0 <= l.x1 && l.y0 <= r.y1 && r.y0 <= l.y1) {
      push(unite(l, r));  // they overlap: one push
    } else {
      push(l);
      push(r);
    }
    // The STOP frame is steady: drawn and sent only when it appears or goes away.
    if (frameW_ != prevFrameW_) {
      if (prevFrameW_) clearStrips(prevFrameW_);
      if (frameW_) drawStrips(frameW_);
      pushStrips(std::max(frameW_, prevFrameW_));
    }
    prevInk_[0] = ink_[0];
    prevInk_[1] = ink_[1];
    prevFrameW_ = frameW_;
    drawUs_ += t1 - t0;
    stats(lgfx::micros() - t0);
  }

 private:
  M5Canvas canvas_{&M5.Display};
  M5Canvas* g_ = &canvas_;  // where the shape helpers draw
  static constexpr int kHeartSteps = 8;
  M5Canvas hearts_[kHeartSteps];  // the heart at each heartbeat size, drawn once at start
  float heartSize_[kHeartSteps] = {};
  Reaction shown_ = Reaction::Sleep, prev_ = Reaction::Sleep;
  bool started_ = false;
  uint32_t changeMs_ = 0, nextUs_ = 0, lastUs_ = 0;
  // idle motion
  float gazeX_ = 0, gazeY_ = 0, gazeTX_ = 0, gazeTY_ = 0;
  uint32_t nextBlinkMs_ = 0, blinkStartMs_ = 0, nextGlanceMs_ = 0;
  bool doubleBlink_ = false;
  // stats
  uint32_t frames_ = 0, workUs_ = 0, statMs_ = 0, drawUs_ = 0;
  // dirty rectangles
  struct Box {
    int x0 = 1 << 20, y0 = 1 << 20, x1 = -1, y1 = -1;  // empty
    bool empty() const { return x1 < x0 || y1 < y0; }
  };
  Box ink_[2], prevInk_[2];  // left / right half: the gap between the eyes is never sent
  int frameW_ = 0, prevFrameW_ = 0;

  static Box unite(const Box& a, const Box& b) {
    if (a.empty()) return b;
    if (b.empty()) return a;
    return {std::min(a.x0, b.x0), std::min(a.y0, b.y0), std::max(a.x1, b.x1), std::max(a.y1, b.y1)};
  }
  // ---- landscape (logical) -> portrait (physical) mapping, for the current target g_
  struct Pt {
    float x, y;
  };
  Pt T(float X, float Y) const {
    const int W = g_->width(), H = g_->height();
    return kFlip ? Pt{Y, H - 1 - X} : Pt{W - 1 - Y, X};
  }
  static int bucket(float x) { return x < kWidth / 2 ? 0 : 1; }  // left / right eye
  // Logical box -> physical ink box.
  void mark(float x0, float y0, float x1, float y1) {
    const Pt a = T(x0, y0), b = T(x1, y1);
    markPhys(bucket((x0 + x1) / 2), std::min(a.x, b.x), std::min(a.y, b.y), std::max(a.x, b.x), std::max(a.y, b.y));
  }
  void markPhys(int i, float x0, float y0, float x1, float y1) {
    const int m = 3;  // anti-aliasing fringe
    ink_[i] = unite(ink_[i], Box{std::max(0, (int)x0 - m), std::max(0, (int)y0 - m),
                                 std::min((int)g_->width() - 1, (int)x1 + m), std::min((int)g_->height() - 1, (int)y1 + m)});
  }
  void fillRectL(float X, float Y, float w, float h, uint16_t c) {  // logical rect
    const Pt a = T(X, Y), b = T(X + w, Y + h);
    g_->fillRect((int)std::min(a.x, b.x), (int)std::min(a.y, b.y), (int)fabsf(b.x - a.x) + 1, (int)fabsf(b.y - a.y) + 1, c);
  }
  void fill(const Box& b, uint16_t c) {
    if (!b.empty()) g_->fillRect(b.x0, b.y0, b.x1 - b.x0 + 1, b.y1 - b.y0 + 1, c);
  }
  void push(const Box& b) {
    if (b.empty()) return;
    M5.Display.setClipRect(kCanvasX + b.x0, b.y0, b.x1 - b.x0 + 1, b.y1 - b.y0 + 1);
    canvas_.pushSprite(&M5.Display, kCanvasX, 0);
    M5.Display.clearClipRect();
  }
  // STOP frame strips (top, bottom, left, right) of width w.
  // (physical canvas coordinates: the frame goes round the whole face canvas)
  static constexpr int kFrameR = 40, kCorner = 44;
  // Clear the whole band the frame can reach, corners included (clearing only w px used
  // to leave little red corner triangles on screen after STOP).
  void clearStrips(int w) {
    const int e = std::max(w, kCorner);
    g_->fillRect(0, 0, kCanvasW, e, kBackground);
    g_->fillRect(0, kCanvasH - e, kCanvasW, e, kBackground);
    g_->fillRect(0, 0, e, kCanvasH, kBackground);
    g_->fillRect(kCanvasW - e, 0, e, kCanvasH, kBackground);
  }
  // One clean anti-aliased ring (stacked round rects left jagged bits in the corners).
  void drawStrips(int w) {
    g_->fillSmoothRoundRect(0, 0, kCanvasW, kCanvasH, kFrameR, color565(kRed));
    g_->fillSmoothRoundRect(w, w, kCanvasW - 2 * w, kCanvasH - 2 * w, std::max(4, kFrameR - w), kBackground);
    prevInk_[0] = prevInk_[1] = Box{0, 0, kCanvasW - 1, kCanvasH - 1};  // the inside was cleared: redraw it all next frame
  }
  void pushStrips(int w) {
    const int e = std::max(w, kCorner);  // rounded corners reach a little further in
    push(Box{0, 0, kCanvasW - 1, e});
    push(Box{0, kCanvasH - 1 - e, kCanvasW - 1, kCanvasH - 1});
    push(Box{0, 0, e, kCanvasH - 1});
    push(Box{kCanvasW - 1 - e, 0, kCanvasW - 1, kCanvasH - 1});
  }

  static constexpr uint32_t kCloseMs = 110, kOpenMs = 170;  // expression change = a blink

  // ---------------------------------------------------------------- stamp cache
  // A shape that does not change between frames is drawn once into its own small
  // sprite (cropped to its ink) and then copied each frame: anti-aliased edges are the
  // costly part of drawing, copying is cheap. Blinks and pop-ins still draw live.
  struct Stamp {
    uint32_t key;
    M5Canvas* spr;
    int ax, ay;  // where the anchor point (x, y) sits inside the sprite
  };
  static constexpr int kMaxStamps = 96;
  Stamp stamps_[kMaxStamps];
  int nStamps_ = 0;

  template <typename F>
  void stamp(uint32_t key, int size, float x, float y, F render) {
    Stamp* st = nullptr;
    for (int i = 0; i < nStamps_; ++i)
      if (stamps_[i].key == key) { st = &stamps_[i]; break; }
    if (!st) {
      if (nStamps_ == kMaxStamps) {  // full (should not happen): draw live
        render(x, y);
        return;
      }
      // Render at the centre of a size x size scratch sprite, then crop to the ink.
      M5Canvas scratch;
      scratch.setPsram(true);
      scratch.setColorDepth(16);
      if (!scratch.createSprite(size, size)) { render(x, y); return; }
      scratch.fillSprite(kBackground);
      Box keep[2] = {ink_[0], ink_[1]};
      ink_[0] = ink_[1] = Box{};
      g_ = &scratch;
      render(size / 2.0f, size / 2.0f);
      const Pt anchor = T(size / 2.0f, size / 2.0f);  // where the logical centre landed
      g_ = &canvas_;
      Box tb = unite(ink_[0], ink_[1]);
      ink_[0] = keep[0];
      ink_[1] = keep[1];
      if (tb.empty()) return;
      tb.x1 = std::min(tb.x1, size - 1);
      tb.y1 = std::min(tb.y1, size - 1);
      auto* spr = new M5Canvas();
      spr->setPsram(true);
      spr->setColorDepth(16);
      if (!spr->createSprite(tb.x1 - tb.x0 + 1, tb.y1 - tb.y0 + 1)) { delete spr; render(x, y); return; }
      scratch.pushSprite(spr, -tb.x0, -tb.y0);
      scratch.deleteSprite();
      stamps_[nStamps_] = {key, spr, (int)lroundf(anchor.x) - tb.x0, (int)lroundf(anchor.y) - tb.y0};
      st = &stamps_[nStamps_++];
    }
    const Pt P = T(x, y);
    const int px = (int)lroundf(P.x) - st->ax, py = (int)lroundf(P.y) - st->ay;
    // Transparent copy: skipping the black pixels measured faster than an opaque copy.
    st->spr->pushSprite(&canvas_, px, py, kBackground);
    markPhys(bucket(x), px + 3, py + 3, px + st->spr->width() - 4, py + st->spr->height() - 4);
  }
  static uint32_t key(uint32_t shape, uint32_t a = 0, uint32_t b = 0) { return (shape << 24) | (a << 12) | b; }

  // ---------------------------------------------------------------- primitives
  // Rounded eye (circle when w == h, pill when squashed). Anti-aliased.
  void blob(float cx, float cy, float w, float h, uint16_t c) {
    w = std::max(w, 6.0f);
    h = std::max(h, 6.0f);
    const float r = std::min(w, h) / 2;
    mark(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2);
    const Pt p = T(cx, cy);  // rotated 90 degrees: width and height swap
    g_->fillSmoothRoundRect((int32_t)(p.x - h / 2), (int32_t)(p.y - w / 2), (int32_t)h, (int32_t)w, (int32_t)r, c);
  }
  // Thick anti-aliased arc with round ends. Angles in degrees, y down.
  void stroke(float cx, float cy, float r, float a0, float a1, float thick, uint16_t c) {
    // ~15 degrees per segment: still round at these thicknesses, and drawWideLine is the
    // costly part (18 segments made the sleeping face run at 28 fps).
    const int n = std::max(4, std::min(18, (int)(fabsf(a1 - a0) / 15.0f + 0.5f)));
    float px = cx + r * cosf(a0 * kPi / 180), py = cy + r * sinf(a0 * kPi / 180);
    float x0 = px, y0 = py, x1 = px, y1 = py;  // tight box: an arc covers a thin band, not its circle
    for (int i = 1; i <= n; ++i) {
      const float a = (a0 + (a1 - a0) * i / n) * kPi / 180;
      const float x = cx + r * cosf(a), y = cy + r * sinf(a);
      const Pt p0 = T(px, py), p1 = T(x, y);
      g_->drawWideLine(p0.x, p0.y, p1.x, p1.y, thick / 2, c);
      px = x;
      py = y;
      x0 = std::min(x0, x); x1 = std::max(x1, x); y0 = std::min(y0, y); y1 = std::max(y1, y);
    }
    mark(x0 - thick, y0 - thick, x1 + thick, y1 + thick);
  }
  void disc(float cx, float cy, float r, uint16_t c) {
    if (c != kBackground) mark(cx - r, cy - r, cx + r, cy + r);
    const Pt p = T(cx, cy);
    g_->fillSmoothCircle(p.x, p.y, r, c);
  }
  void line(float x0, float y0, float x1, float y1, float thick, uint16_t c) {
    mark(std::min(x0, x1) - thick, std::min(y0, y1) - thick, std::max(x0, x1) + thick, std::max(y0, y1) + thick);
    const Pt a = T(x0, y0), b = T(x1, y1);
    g_->drawWideLine(a.x, a.y, b.x, b.y, thick / 2, c);
  }
  void heart(float cx, float cy, float s, uint16_t c) {
    const float r = 0.27f * s;
    mark(cx - 0.55f * s, cy - 0.42f * s, cx + 0.55f * s, cy + 0.55f * s);
    const Pt c1 = T(cx - 0.25f * s, cy - 0.12f * s), c2 = T(cx + 0.25f * s, cy - 0.12f * s);
    g_->fillSmoothCircle(c1.x, c1.y, r, c);
    g_->fillSmoothCircle(c2.x, c2.y, r, c);
    const float lx = cx - 0.5f * s, rx = cx + 0.5f * s, ty = cy - 0.02f * s, by = cy + 0.5f * s;
    const Pt t0 = T(lx, ty), t1 = T(rx, ty), t2 = T(cx, by);
    g_->fillTriangle(t0.x, t0.y, t1.x, t1.y, t2.x, t2.y, c);
    fillRectL(cx - 0.25f * s, cy - 0.15f * s, 0.5f * s, 0.2f * s, c);
    line(lx + 1, ty, cx, by - 1, 3, c);  // soften the slanted edges
    line(rx - 1, ty, cx, by - 1, 3, c);
  }
  void sparkle(float cx, float cy, float s, uint16_t c) {
    const float w = 0.16f * s;
    mark(cx - s, cy - s, cx + s, cy + s);
    const Pt o = T(cx, cy);  // a 4-point star is the same after a 90 degree turn
    g_->drawWedgeLine(o.x, o.y, o.x, o.y - s, w, 0.5f, c);
    g_->drawWedgeLine(o.x, o.y, o.x, o.y + s, w, 0.5f, c);
    g_->drawWedgeLine(o.x, o.y, o.x - s, o.y, w, 0.5f, c);
    g_->drawWedgeLine(o.x, o.y, o.x + s, o.y, w, 0.5f, c);
  }
  void question(float cx, float cy, float s, uint16_t c) {
    const float r = 0.32f * s, th = 0.16f * s;
    mark(cx - 0.55f * s, cy - 0.7f * s, cx + 0.55f * s, cy + 0.65f * s);
    stroke(cx, cy - 0.25f * s, r, 180, 420, th, c);  // hook over the top
    const float ex = cx + r * cosf(420 * kPi / 180), ey = cy - 0.25f * s + r * sinf(420 * kPi / 180);
    line(ex, ey, cx, cy + 0.22f * s, th, c);
    const Pt d = T(cx, cy + 0.48f * s);
    g_->fillSmoothCircle(d.x, d.y, th * 0.6f, c);
  }
  void zee(float cx, float cy, float s, uint16_t c) {
    const float h = s / 2, th = std::max(4.0f, 0.18f * s);
    line(cx - h, cy - h, cx + h, cy - h, th, c);
    line(cx + h, cy - h, cx - h, cy + h, th, c);
    line(cx - h, cy + h, cx + h, cy + h, th, c);
  }

  // ---------------------------------------------------------------- idle motion
  void updateIdleMotion(float dt, uint32_t now, bool glance) {
    if (glance && (int32_t)(now - nextGlanceMs_) >= 0) {
      const bool center = (rand() % 3) == 0;
      gazeTX_ = center ? 0 : frand(-1, 1);
      gazeTY_ = center ? 0 : frand(-0.6f, 0.6f);
      nextGlanceMs_ = now + (uint32_t)frand(1400, 3800);
    }
    if (!glance) gazeTX_ = gazeTY_ = 0;
    const float k = 1 - expf(-dt / 0.07f);  // quick, smooth saccade
    gazeX_ += (gazeTX_ - gazeX_) * k;
    gazeY_ += (gazeTY_ - gazeY_) * k;
    if ((int32_t)(now - nextBlinkMs_) >= 0) {
      blinkStartMs_ = now;
      doubleBlink_ = (rand() % 5) == 0;
      nextBlinkMs_ = now + (uint32_t)frand(2600, 5600);
    }
  }
  // 1 = open, ~0 = closed.
  float blinkOpen(uint32_t now) const {
    const uint32_t d = now - blinkStartMs_;
    const uint32_t len = 150;
    auto one = [&](uint32_t x) { return x >= len ? 1.0f : fabsf(1 - 2.0f * x / len); };
    float o = one(d);
    if (doubleBlink_ && d >= 220) o = std::min(o, one(d - 220));
    return 0.06f + 0.94f * easeInOut(o);
  }

  // ---------------------------------------------------------------- one frame
  void draw(float dt) {
    const uint32_t now = lgfx::millis();
    const float t = now / 1000.0f;

    // Expression change: close the old eyes, then open the new ones.
    const uint32_t since = now - changeMs_;
    Reaction r = shown_;
    float openT = 1;  // 0..1 opening of the new expression
    if (since < kCloseMs) {
      r = prev_;
      const float closing = 1 - easeInOut((float)since / kCloseMs);
      drawExpression(r, t, dt, now, 0.08f + 0.92f * closing, true);
      drawFrame(r, now);
      return;
    }
    if (since < kCloseMs + kOpenMs) openT = (float)(since - kCloseMs) / kOpenMs;
    drawExpression(r, t, dt, now, openT, false);
    drawFrame(r, now);
  }

  // open: 0..1. closing=true squashes the eyes shut (generic pill), else the new
  // expression opens (round eyes grow, other shapes pop in).
  void drawExpression(Reaction r, float t, float dt, uint32_t now, float open, bool closing) {
    const Rgb base = colorFor(r);
    const uint16_t c = color565(base);
    const float lx = kWidth / 2 - kEyeGap / 2, rx = kWidth / 2 + kEyeGap / 2;
    const float D = kEyeSize;

    if (closing) {  // any expression closes into two thin lids
      const float h = std::max(10.0f, D * open);
      blob(lx, kEyeY, D * 0.92f, h, c);
      blob(rx, kEyeY, D * 0.92f, h, c);
      return;
    }
    const float pop = open >= 1 ? 1 : easeOutBack(open);   // shapes
    const float grow = open >= 1 ? 1 : easeInOut(open);     // round eyes

    switch (r) {
      case Reaction::Idle: {
        updateIdleMotion(dt, now, true);
        const float o = blinkOpen(now) * (0.08f + 0.92f * grow);
        const float gx = gazeX_ * 46, gy = gazeY_ * 22;
        for (float x : {lx, rx}) {
          if (o > 0.995f)
            stamp(key(1, (uint32_t)r), (int)D + 16, x + gx, kEyeY + gy,
                  [&](float px, float py) { blob(px, py, D, D, c); });
          else
            blob(x + gx, kEyeY + gy, D, D * o, c);
        }
        break;
      }
      case Reaction::Greeting: {  // ^^ crescents
        const float s = D * pop, y = kEyeY - 10 + 7 * sinf(t * 2 * kPi * 1.1f);
        auto crescent = [&](float px, float py) {
          disc(px, py, s / 2, c);
          disc(px, py + s * 0.34f, s * 0.47f, kBackground);
        };
        for (float x : {lx, rx}) {
          if (pop >= 1) stamp(key(2), (int)D + 16, x, y, crescent);
          else crescent(x, y);
        }
        break;
      }
      case Reaction::Reminder: {  // one eye + wink, sparkle
        updateIdleMotion(dt, now, false);
        const float o = blinkOpen(now) * (0.08f + 0.92f * grow);
        if (o > 0.995f) stamp(key(1, (uint32_t)r), (int)D + 16, lx, kEyeY, [&](float px, float py) { blob(px, py, D, D, c); });
        else blob(lx, kEyeY, D, D * o, c);
        if (pop >= 1)
          stamp(key(3), (int)D + 60, rx, kEyeY + D * 0.28f,
                [&](float px, float py) { stroke(px, py, D * 0.42f, 215, 325, 26, c); });
        else
          stroke(rx, kEyeY + D * 0.28f, D * 0.42f * pop, 215, 325, 26, c);
        break;
      }
      case Reaction::Happy: {  // hearts with a heartbeat
        const float beat = powf(fabsf(sinf(t * kPi * 1.25f)), 6.0f);  // 0..1
        if (open < 1) {  // popping in: draw live at any size (only for ~170 ms)
          const float s = D * 1.08f * pop;
          heart(lx, kEyeY, s, c);
          heart(rx, kEyeY, s, c);
        } else {
          M5Canvas& h = hearts_[std::min(kHeartSteps - 1, (int)(beat * kHeartSteps))];
          const int w = h.width();
          const int ax = kFlip ? w / 2 : w - 1 - w / 2, ay = kFlip ? w - 1 - w / 2 : w / 2;  // T(w/2, w/2)
          for (float x : {lx, rx}) {
            const Pt P = T(x, kEyeY);
            const int px = (int)lroundf(P.x) - ax, py = (int)lroundf(P.y) - ay;
            h.pushSprite(&canvas_, px, py, kBackground);
            markPhys(bucket(x), px, py, px + w, py + w);
          }
        }
        break;
      }
      case Reaction::Concerned: {  // tall eye + half-closed eye, "?"
        updateIdleMotion(dt, now, false);
        const float o = blinkOpen(now) * (0.08f + 0.92f * grow);
        if (o > 0.995f)
          stamp(key(5), (int)(D * 1.1f) + 16, lx, kEyeY, [&](float px, float py) { blob(px, py, D * 0.78f, D * 1.08f, c); });
        else
          blob(lx, kEyeY, D * 0.78f, D * 1.08f * o, c);
        const float ry = kEyeY + D * 0.12f;
        auto half = [&](float px, float py, float h) {  // round eye with a flat upper lid
          blob(px, py, D, D, c);
          fillRectL(px - D, py - D, 2 * D, D * 0.5f + (D * 0.62f - h), kBackground);
        };
        if (grow >= 1)
          stamp(key(6), (int)D + 16, rx, ry, [&](float px, float py) { half(px, py, D * 0.62f); });
        else
          half(rx, ry, D * 0.62f * grow);
        break;
      }
      case Reaction::Stop: {  // ring eyes
        const float w = D * 0.86f * pop, h = D * 1.02f * pop, th = 30 * pop;
        const float wob = 2.5f * sinf(t * 2 * kPi * 7.0f);
        auto ring = [&](float px, float py) {
          blob(px, py, w, h, c);
          blob(px, py, w - 2 * th, h - 2 * th, kBackground);
        };
        for (float x : {lx, rx}) {
          if (pop >= 1) stamp(key(8), (int)(D * 1.05f) + 16, x, kEyeY, ring);
          else ring(x, kEyeY);
          disc(x + wob, kEyeY, 15 * pop, c);
        }
        break;
      }
      case Reaction::WrongPerson: {  // lowered eyes glancing away
        const float ax = 26 * sinf(t * 2 * kPi * 0.35f);
        auto lowered = [&](float px, float py, float g) {
          blob(px, py, D * 0.92f, D * 0.92f, c);
          fillRectL(px - D, py - D, 2 * D, D - D * 0.46f + D * 0.5f * (1 - g), kBackground);
        };
        for (float x : {lx, rx}) {
          const float ex = x + ax, ey = kEyeY + D * 0.1f;
          if (grow >= 1) stamp(key(9), (int)D + 16, ex, ey, [&](float px, float py) { lowered(px, py, 1); });
          else lowered(ex, ey, grow);
        }
        break;
      }
      case Reaction::Sleep:
      default: {  // closed eyes, breathing, z's
        const float y = kEyeY + 4 * sinf(t * 2 * kPi * 0.22f);
        for (float x : {lx, rx}) {
          if (pop >= 1)
            stamp(key(10), (int)D + 60, x, y - D * 0.32f,
                  [&](float px, float py) { stroke(px, py, D * 0.42f, 35, 145, 22, c); });
          else
            stroke(x, y - D * 0.32f, D * 0.42f * (0.9f + 0.1f * pop), 35, 145, 22, c);
        }

        break;
      }
    }
  }

  // Steady red frame round the face for STOP (drawn by update() when it changes).
  void drawFrame(Reaction, uint32_t) {}  // no frame: STOP is shown by red eyes only

  void stats(uint32_t workUs) {
    ++frames_;
    workUs_ += workUs;
    const uint32_t now = lgfx::millis();
    if (statMs_ == 0) statMs_ = now;
    if (now - statMs_ >= 5000) {
#if defined(ARDUINO)
      Serial.printf("[face] %.1f fps, %.1f ms per frame (draw %.1f + push %.1f)\n",
                    frames_ * 1000.0f / (now - statMs_), workUs_ / 1000.0f / frames_, drawUs_ / 1000.0f / frames_,
                    (workUs_ - drawUs_) / 1000.0f / frames_);
#endif
      frames_ = workUs_ = drawUs_ = 0;
      statMs_ = now;
    }
  }
};

}  // namespace face
