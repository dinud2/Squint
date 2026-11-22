"""Who is at the counter, steadily: turns noisy per-frame face results into
"people_present" changes the speaker can act on.

* someone joins the group after being recognised on JOIN_FRAMES (2) frames in a row over
  JOIN_S (0.2 s): fast enough to feel instant, but one lucky frame doesn't trigger a greeting
* someone leaves only after not being recognised for LEAVE_S (3 s): turning your head,
  bending down or a missed frame doesn't make the speaker greet you again
* "unknown" faces are counted, never named; `unknown_here` is a steady "someone I don't know is
  in view" (UNKNOWN_FRAMES in a row to start, LEAVE_S without one to end)
"""


class Presence:
    JOIN_S = 0.2         # walk up -> greeted after 2 face frames, ~0.25 s on the Pi (~4 frames/s)
    JOIN_FRAMES = 3      # three frames in a row: a look-alike visitor reached Dinu's bar 2 frames running
    LEAVE_S = 3.0
    STREAK_GAP_S = 0.5   # a joining streak restarts after a gap this long (stray frames don't add up)
    SWAP_S = 1.0
    UNKNOWN_FRAMES = 3   # a known face turning away can look "unknown" for a frame or two

    def __init__(self):
        self.first_seen = {}     # name -> time first seen in the current streak
        self.hits = {}           # name -> frames seen in the current streak
        self.last_seen = {}      # name -> last time recognised
        self.present = set()     # the steady group
        self.unknown = 0
        self.unknown_here = False
        self.unknown_hits, self.unknown_last = 0, -1e9

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
        if unknown:
            self.unknown_hits, self.unknown_last = self.unknown_hits + 1, t
        else:
            self.unknown_hits = 0
        uh = self.unknown_hits >= self.UNKNOWN_FRAMES or (self.unknown_here and t - self.unknown_last <= self.LEAVE_S)
        # A stranger in view replaces someone not seen for a second (not the full LEAVE_S): the
        # person holding the bottle now must not be taken for whoever stood there before.
        keep = self.SWAP_S if uh else self.LEAVE_S
        group = {n for n in self.present if t - self.last_seen.get(n, -1e9) <= keep}
        group |= {n for n in names
                  if t - self.first_seen[n] >= self.JOIN_S and self.hits[n] >= self.JOIN_FRAMES}
        if group != self.present or uh != self.unknown_here:
            self.present, self.unknown_here = group, uh
            return sorted(group)
        return None
