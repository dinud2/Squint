// TextPanel.h - the words in the middle of the body (below the face).
//
// Big, rounded, extra-bold font (M PLUS Rounded 1c ExtraBold, SIL OFL 1.1).
// Title: up to 2 lines. Detail: 1 line. Long text shrinks to fit.

#pragma once

#include <M5Unified.h>

#include <cmath>
#include <cstring>

#include "OttoFace.h"
#include "Reactions.h"
#include "src/fonts/font_body.h"
#include "src/fonts/font_title.h"

namespace text {

// ---- Layout (screen pixels). Change these to fit the 3D-printed body. --------
// Landscape 1280 x 720: the panel is the band under the eyes.
constexpr int kPanelTop = face::kFaceBottom;  // Panel covers y 440 .. 720.
constexpr int kPanelHeight = face::kHeight - kPanelTop;
constexpr int kTextTop = 450;                 // The words are centred in this zone.
constexpr int kTextBottom = 705;
constexpr int kMaxWidth = 1160;               // wide: titles fit on one line
constexpr int kWidth = face::kWidth;

constexpr uint16_t kTextWhite = 0xFFFF;
constexpr uint16_t kSubText = ((0xD3 & 0xF8) << 8) | ((0xD1 & 0xFC) << 3) | (0xC7 >> 3);

class TextPanel {
 public:
  bool begin() {
    canvas_.setPsram(true);
    canvas_.setColorDepth(16);
    if (!canvas_.createSprite(kWidth, kPanelHeight)) return false;
    title_.loadFont(&titleData_);
    body_.loadFont(&bodyData_);
    return true;
  }

  // Call often from loop(). Redraws only when the words change.
  void update() {
    const ReactionState s = reactions::get();
    if (s.sinceMs != shownSinceMs_ || s.reaction != shownReaction_) {
      shownSinceMs_ = s.sinceMs;
      shownReaction_ = s.reaction;
      redraw(s);
    }
  }

 private:
  M5Canvas canvas_{&M5.Display};
  lgfx::PointerWrapper titleData_{kFontTitle, kFontTitle_len};
  lgfx::PointerWrapper bodyData_{kFontBody, kFontBody_len};
  lgfx::VLWfont title_;
  lgfx::VLWfont body_;
  uint32_t shownSinceMs_ = UINT32_MAX;
  Reaction shownReaction_ = Reaction::Idle;

  void redraw(const ReactionState& s) {
    canvas_.fillSprite(face::kBackground);
    if (s.title[0] != '\0' || s.detail[0] != '\0') drawWords(s);
    // The display stays in its fast native portrait rotation (see face::kFlip), so the
    // landscape text band is pushed turned 90 degrees. It only redraws when the words change.
    const float cx = face::kFlip ? kPanelTop + kPanelHeight / 2.0f : face::kPanelW - 1 - (kPanelTop + kPanelHeight / 2.0f);
    const float cy = face::kFlip ? face::kWidth - 1 - face::kWidth / 2.0f : face::kWidth / 2.0f;
    canvas_.pushRotateZoom(&M5.Display, cx, cy, face::kFlip ? 270.0f : 90.0f, 1.0f, 1.0f);
  }

  void drawWords(const ReactionState& s) {
    char lines[2][64] = {"", ""};
    int lineCount = 0;
    if (s.title[0] != '\0') {
      canvas_.setFont(&title_);
      lineCount = wrap(s.title, lines);
    }
    const int titleH = 124;  // Line height of the 96 px font.
    const int detailH = 100;
    const int blockH = lineCount * titleH + (s.detail[0] ? detailH : 0);
    int y = (kTextTop + kTextBottom) / 2 - blockH / 2 - kPanelTop;  // Canvas y.

    const bool stop = s.reaction == Reaction::Stop;
    if (stop) {
      const int boxW = 980;  // centred, not the full landscape width
      canvas_.fillSmoothRoundRect((kWidth - boxW) / 2, y - 20, boxW, blockH + 30, 40,
                                  face::color565(face::kRed));
    }

    canvas_.setTextDatum(textdatum_t::top_center);
    canvas_.setTextColor(kTextWhite);
    canvas_.setFont(&title_);
    for (int i = 0; i < lineCount; ++i) {
      drawFitted(lines[i], y);
      y += titleH;
    }
    if (s.detail[0] != '\0') {
      canvas_.setFont(&body_);
      canvas_.setTextColor(stop ? kTextWhite : kSubText);
      drawFitted(s.detail, y + 8);
    }
  }

  // Draws one line, centred. Shrinks it if it is wider than the zone.
  void drawFitted(const char* line, int y) {
    canvas_.setTextSize(1);
    const int w = canvas_.textWidth(line);
    if (w > kMaxWidth) canvas_.setTextSize((float)kMaxWidth / w);
    canvas_.drawString(line, kWidth / 2, y);
    canvas_.setTextSize(1);
  }

  // Greedy word wrap into at most 2 lines. Extra words go on the last line.
  int wrap(const char* src, char lines[2][64]) {
    char words[16][32];
    int n = 0;
    const char* p = src;
    while (*p && n < 16) {
      while (*p == ' ') ++p;
      int len = 0;
      while (p[len] && p[len] != ' ' && len < 31) ++len;
      if (len == 0) break;
      memcpy(words[n], p, len);
      words[n][len] = '\0';
      ++n;
      p += len;
    }
    int line = 0;
    for (int i = 0; i < n; ++i) {
      char trial[64];
      snprintf(trial, sizeof(trial), "%s%s%s", lines[line], lines[line][0] ? " " : "", words[i]);
      if (lines[line][0] && line == 0 && canvas_.textWidth(trial) > kMaxWidth) {
        line = 1;
        snprintf(trial, sizeof(trial), "%s", words[i]);
      }
      snprintf(lines[line], 64, "%s", trial);
    }
    return lines[0][0] ? line + 1 : 0;
  }
};

}  // namespace text
