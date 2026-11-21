# hackwestern: Medicine Buddy

A counter-top medicine helper for elderly couples who keep their medicine together.

When someone walks up, the device recognises **who** it is, a Google Home speaker greets them
("Hi Dinu, today you take Tylenol and metformin"), and the camera checks that **the right person
takes the right bottle**. If it's more than 90% sure the pill was taken, the Tab5 screen marks it
done; otherwise the screen asks "Did you take it?". It warns if someone picks up the other
person's medicine or a bottle that isn't on today's list.

## Pieces

| Part | Where | Status |
|---|---|---|
| Camera stream (`pi/`) | QNX 8 on a Raspberry Pi 5, Logitech C270 USB webcam | working: MJPEG at `http://<pi>:8080/stream`, 960×544 @ 20 fps |
| Face recognition (2 people) | QNX Pi | to do: pretrained face detector + embedding, enrolled from ~30 photos per person at the counter angle |
| Pill bottle recognition (several types) | QNX Pi | to do: which bottle is in the person's hand |
| Taken check | QNX Pi | to do: right person + right bottle + hand to mouth → confidence; ≥ 90% auto-confirms, otherwise ask on the Tab5 |
| Voice + Tab5 screen + schedule | teammate | consumes recognition events; the daily schedule comes from the Tab5 / app |

## History

The previous idea (Squint, intake anticipation) is on the `old-idea` branch.
