// AskPanel.h - the words and the Yes / No buttons of "Did you take it?" (Ask.h).
//
// Landscape layout (1280 x 720): small eyes on top (OttoFace.h, Reaction::Ask), then
//   the medicine name          big
//   "Did you take it?"         smaller
//   [  Yes  ]   [  No  ]       two big rounded buttons
// Drawn straight into the face canvas, turned to landscape with setRotation (the display stays
// in its fast portrait rotation, see face::kFlip), and only the parts that change.

#pragma once

#include <M5Unified.h>

#include <algorithm>
#include <cstdio>
#include <cstring>

#include "Ask.h"
#include "src/fonts/font_body.h"
#include "src/fonts/font_title.h"

namespace askpanel {

// ---- Layout (landscape pixels) ---------------------------------------------------
constexpr int kTop = 290;  // the panel covers y 290 .. 720; the eyes stay above it
constexpr int kW = 1280, kH = 720 - kTop;
constexpr int kTitleY = 300, kDetailY = 418;               // top of each line
constexpr int kBtnW = 420, kBtnH = 150, kBtnR = 52, kBtnY = 536;
constexpr int kYesX = 640 - 30 - kBtnW, kNoX = 640 + 30;   // left edges
constexpr int kBarY = 700, kBarH = 12;                     // "taken" countdown, under Yes
constexpr int kMaxTextW = 1160;
// Touch targets are a little bigger than the buttons.
constexpr int kHitPad = 40;

// ---- Colours (RGB565) ---------------------------------------------------------------
constexpr uint16_t rgb(uint8_t r, uint8_t g, uint8_t b) {
  return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3);
}
constexpr uint16_t kWhite = 0xFFFF;
constexpr uint16_t kSubText = rgb(0xD3, 0xD1, 0xC7);
constexpr uint16_t kGreen = rgb(0x4C, 0xC2, 0x6A);
constexpr uint16_t kGreenDim = rgb(0x1E, 0x4A, 0x2A);
constexpr uint16_t kGrey = rgb(0x3E, 0x3E, 0x3E);
constexpr uint16_t kGreyDim = rgb(0x22, 0x22, 0x22);
constexpr uint16_t kTextDim = rgb(0x70, 0x70, 0x70);

// Which button a landscape point is on: 1 = Yes, 0 = No, -1 = neither.
inline int hit(int x, int y) {
  if (y < kBtnY - kHitPad || y > kBtnY + kBtnH + kHitPad) return -1;
  if (x >= kYesX - kHitPad && x <= kYesX + kBtnW + kHitPad / 2) return 1;
  if (x >= kNoX - kHitPad / 2 && x <= kNoX + kBtnW + kHitPad) return 0;
  return -1;
}

// A landscape rectangle (inclusive).
struct Rect {
  int x0 = 0, y0 = 0, x1 = -1, y1 = -1;
  bool empty() const { return x1 < x0 || y1 < y0; }
};
inline Rect unite(const Rect& a, const Rect& b) {
  if (a.empty()) return b;
  if (b.empty()) return a;
  return {std::min(a.x0, b.x0), std::min(a.y0, b.y0), std::max(a.x1, b.x1), std::max(a.y1, b.y1)};
}

// Each part (name, question, button row) is redrawn only when it changes, and only its area
// is sent to the display: sending the whole panel took ~100 ms, a visible hitch.
class AskPanel {
 public:
  bool begin() {
    title_.loadFont(&titleData_);
    body_.loadFont(&bodyData_);
    return true;
  }

  // g: the face canvas, turned to landscape by the caller (setRotation). out(Rect) is called
  // for every area that changed and must be sent.
  template <typename Out>
  void draw(LGFX_Sprite& g, const ask::State& s, Out out) {
    if (!shown_ || strcmp(med_, s.med) != 0) {
      line(g, title_, s.med, kWhite, kTitleY, kTop + 2, kDetailY - 1, titleBox_, out);
      snprintf(med_, sizeof(med_), "%s", s.med);
    }
    if (!shown_ || strcmp(question_, s.question) != 0) {
      line(g, body_, s.question, kSubText, kDetailY, kDetailY, kBtnY - 14, questionBox_, out);
      snprintf(question_, sizeof(question_), "%s", s.question);
    }
    if (!shown_ || phase_ != s.phase) {
      const Rect row = buttonRow();
      g.fillRect(row.x0, row.y0, row.x1 - row.x0 + 1, row.y1 - row.y0 + 1, 0x0000);
      buttons(g, s.phase);
      out(row);
      phase_ = s.phase;
    }
    shown_ = true;
  }

  // Erases everything it drew.
  template <typename Out>
  void clear(LGFX_Sprite& g, Out out) {
    if (!shown_) return;
    for (Rect* r : {&titleBox_, &questionBox_}) {
      erase(g, *r, out);
      *r = Rect{};
    }
    Rect row = buttonRow();
    erase(g, row, out);
    shown_ = false;
  }

  bool shown() const { return shown_; }

 private:
  lgfx::PointerWrapper titleData_{kFontTitle, kFontTitle_len};
  lgfx::PointerWrapper bodyData_{kFontBody, kFontBody_len};
  lgfx::VLWfont title_;
  lgfx::VLWfont body_;
  bool shown_ = false;
  char med_[48] = "";
  char question_[64] = "";
  ask::Phase phase_ = ask::Phase::Waiting;
  Rect titleBox_, questionBox_;

  static Rect buttonRow() { return {kYesX - 14, kBtnY - 12, kNoX + kBtnW + 14, kBarY + kBarH + 2}; }

  template <typename Out>
  static void erase(LGFX_Sprite& g, const Rect& r, Out out) {
    if (r.empty()) return;
    g.fillRect(r.x0, r.y0, r.x1 - r.x0 + 1, r.y1 - r.y0 + 1, 0x0000);
    out(r);
  }

  // One centred line (top at textY) in the band y0..y1, shrunk to fit; clears the old one first.
  template <typename Out>
  void line(LGFX_Sprite& g, lgfx::VLWfont& font, const char* text, uint16_t color, int textY, int y0, int y1,
            Rect& box, Out out) {
    Rect now;
    g.setFont(&font);
    g.setTextSize(1);
    if (text && *text) {
      int w = g.textWidth(text);
      if (w > kMaxTextW) {
        g.setTextSize((float)kMaxTextW / w);
        w = kMaxTextW;
      }
      now = {kW / 2 - w / 2 - 12, y0, kW / 2 + w / 2 + 12, y1};
    }
    const Rect u = unite(box, now);
    if (!u.empty()) g.fillRect(u.x0, u.y0, u.x1 - u.x0 + 1, u.y1 - u.y0 + 1, 0x0000);
    if (!now.empty()) {
      g.setTextDatum(textdatum_t::top_center);
      g.setTextColor(color);
      g.drawString(text, kW / 2, textY);
    }
    g.setTextSize(1);
    box = now;
    if (!u.empty()) out(u);
  }

  void buttons(LGFX_Sprite& g, ask::Phase phase) {
    using P = ask::Phase;
    const bool yesPicked = phase == P::Yes || phase == P::AutoYes;
    const bool noPicked = phase == P::No;
    const bool counting = phase == P::Counting;
    // Hand to mouth was seen and Yes ticked itself: one wide green banner, big check, "Taken!" -
    // the moment the demo is about, so it has to be seen from across the room.
    if (phase == P::AutoYes) {
      const int x0 = kYesX - 10, w = kNoX + kBtnW + 10 - x0;
      g.fillSmoothRoundRect(x0, kBtnY - 10, w, kBtnH + 20, kBtnR + 10, kGreen);
      check(g, x0 + w / 2 - 150, kBtnY + kBtnH / 2);
      g.setFont(&title_);
      g.setTextSize(1);
      g.setTextColor(0x0000, kGreen);
      g.setTextDatum(textdatum_t::middle_left);
      g.drawString("Taken!", x0 + w / 2 - 60, kBtnY + kBtnH / 2 + 4);
      return;
    }
    // Yes: green. Ticked: a black check instead of the word. Dim when No was picked.
    // Counting ("taken"): starts dark and fills up bright from the left (progress(), per frame).
    button(g, kYesX, (noPicked || counting) ? kGreenDim : kGreen, yesPicked ? nullptr : "Yes",
           noPicked ? kTextDim : (counting ? kWhite : 0x0000), counting);
    if (yesPicked) check(g, kYesX + kBtnW / 2, kBtnY + kBtnH / 2);
    // No: grey; white when picked, dim once Yes is (being) picked.
    const bool noDim = yesPicked || counting;
    button(g, kNoX, noPicked ? kWhite : (noDim ? kGreyDim : kGrey), "No",
           noPicked ? 0x0000 : (noDim ? kTextDim : kWhite), false);
  }

  void button(LGFX_Sprite& g, int x, uint16_t fill, const char* label, uint16_t text, bool selected) {
    const int y = kBtnY;
    if (selected) {  // pre-selected: a white rim round it
      g.fillSmoothRoundRect(x - 10, y - 10, kBtnW + 20, kBtnH + 20, kBtnR + 10, kWhite);
      g.fillSmoothRoundRect(x - 4, y - 4, kBtnW + 8, kBtnH + 8, kBtnR + 4, 0x0000);
    }
    g.fillSmoothRoundRect(x, y, kBtnW, kBtnH, kBtnR, fill);
    if (!label) return;
    g.setFont(&title_);
    g.setTextSize(1);
    g.setTextColor(text, fill);
    g.setTextDatum(textdatum_t::middle_center);
    g.drawString(label, x + kBtnW / 2, y + kBtnH / 2 + 4);
  }

  public:
  // "taken" countdown: the Yes button fills with bright green from x px (of kBtnW) to x1 px.
  // Clipped to that slice, so each frame only draws and sends the new part.
  template <typename Out>
  void progress(LGFX_Sprite& g, int from, int to, Out out) {
    if (to <= from) return;
    const Rect r{kYesX + from, kBtnY, kYesX + to - 1, kBtnY + kBtnH - 1};
    g.setClipRect(r.x0, r.y0, r.x1 - r.x0 + 1, r.y1 - r.y0 + 1);
    g.fillSmoothRoundRect(kYesX, kBtnY, kBtnW, kBtnH, kBtnR, kGreen);
    g.setFont(&title_);
    g.setTextSize(1);
    g.setTextColor(0x0000, kGreen);
    g.setTextDatum(textdatum_t::middle_center);
    g.drawString("Yes", kYesX + kBtnW / 2, kBtnY + kBtnH / 2 + 4);
    g.clearClipRect();
    out(r);
  }

 private:

  static void check(LGFX_Sprite& g, int cx, int cy) {
    const float r = 13;
    g.drawWideLine(cx - 52, cy + 2, cx - 14, cy + 40, r, 0x0000);
    g.drawWideLine(cx - 14, cy + 40, cx + 56, cy - 38, r, 0x0000);
  }
};

}  // namespace askpanel
