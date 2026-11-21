"""Make a Google Nest speaker play an audio file from this laptop.

How it works (the same thing your phone does when you "cast" a song):
  1. Find:  the Nest announces itself on the Wi-Fi (mDNS, like AirPlay). pychromecast listens for it.
  2. Tell:  we open a connection to the Nest (port 8009) and say "play this URL".
  3. Fetch: the Nest itself downloads the audio from that URL, which is this laptop's little web server.
  4. Play:  it plays it.
So the laptop and the Nest must be on the same network, and the laptop must accept incoming
connections on PORT (macOS asks once: click Allow).
"""
import socket
import time

import pychromecast

DISCOVERY_SECONDS = 6


def my_ip():
    """This laptop's address on the Wi-Fi, i.e. where the Nest can reach us."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))     # no packet is sent; this only picks the right network card
        return s.getsockname()[0]
    finally:
        s.close()


class Nests:
    """Keeps a list of the speakers on the network, so each announcement is instant."""

    def __init__(self):
        self.casts = {}
        self.browser = None

    def discover(self):
        if self.browser:
            self.browser.stop_discovery()
        casts, self.browser = pychromecast.get_chromecasts(timeout=DISCOVERY_SECONDS)
        self.casts = {c.cast_info.friendly_name: c for c in casts}
        return sorted(self.casts)

    def get(self, name=None):
        if not self.casts:
            self.discover()
        if not self.casts:
            raise LookupError("no Google speakers found: is this laptop on the same Wi-Fi as the Nest?")
        if name is None:
            name = sorted(self.casts)[0]
        if name not in self.casts:
            raise LookupError(f"no speaker called '{name}'. Found: {', '.join(sorted(self.casts))}")
        cast = self.casts[name]
        cast.wait(timeout=10)
        return cast

    def play(self, url, content_type, name=None, title="Squint", volume=None):
        cast = self.get(name)
        if volume is not None:
            cast.set_volume(volume)
        mc = cast.media_controller
        mc.play_media(url, content_type, title=title)
        mc.block_until_active(timeout=10)
        return cast.cast_info.friendly_name

    def close(self):
        if self.browser:
            self.browser.stop_discovery()


if __name__ == "__main__":
    n = Nests()
    t = time.time()
    names = n.discover()
    print(f"found {len(names)} speaker(s) in {time.time() - t:.1f} s:", names or "none")
    n.close()
