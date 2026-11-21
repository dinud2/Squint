"""Who is at the counter, steadily: turns noisy per-frame face results into
"people_present" changes the speaker can act on.

* someone joins the group only after being recognised for JOIN_S (1 s) on at least
  JOIN_FRAMES frames: a passer-by or one lucky frame doesn't trigger a greeting
* someone leaves only after not being recognised for LEAVE_S (3 s): turning your head,
  bending down or a missed frame doesn't make the speaker greet you again
* "unknown" faces are counted, never named
"""


class Presence:
    JOIN_S = 1.0
    JOIN_FRAMES = 3
    LEAVE_S = 3.0
    STREAK_GAP_S = 0.5   # a joining streak restarts after a gap this long (stray frames don't add up)

    def __init__(self):
        self.first_seen = {}     # name -> time first seen in the current streak
        self.hits = {}           # name -> frames seen in the current streak
        self.last_seen = {}      # name -> last time recognised
        self.present = set()     # the steady group
        self.unknown = 0

    def update(self, t, names, unknown=0):
        """names: people recognised in this frame. -> the new steady group if it changed, else None."""
        names = set(names)
        for n in names:
            gap = self.STREAK_GAP_S if n not in self.present else self.LEAVE_S
            if n not in self.first_seen or t - self.last_seen.get(n, -1e9) > gap:
                self.first_seen[n], self.hits[n] = t, 0
            self.hits[n] += 1
            self.last_seen[n] = t
        self.unknown = unknown
        group = {n for n in self.present if t - self.last_seen.get(n, -1e9) <= self.LEAVE_S}
        group |= {n for n in names
                  if t - self.first_seen[n] >= self.JOIN_S and self.hits[n] >= self.JOIN_FRAMES}
        if group != self.present:
            self.present = group
            return sorted(group)
        return None
