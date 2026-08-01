# Recommendation: 2 Msym/s for 1080p Video

## Why 2 Msym/s (not 4)

| Check | 2 Msym/s | 4 Msym/s |
|---|---|---|
| **TS rate** | 1.93 Mbps → 1.5 Mbps video | 3.86 Mbps → 3 Mbps video |
| **1080p quality** | 15 fps, good for low-motion | 30 fps, significantly better |
| **Min sample rate** | 6.7 MS/s | 9.4 MS/s |
| **Our sample rate** | **8 MS/s** (clean Nyquist) | Would need 10+ MS/s |
| **RF bandwidth** | 2.7 MHz | 5.4 MHz |
| **USB bandwidth** | 16 MB/s (8-bit) | 20+ MB/s |
| **Rock 2A CPU load** | Moderate | High (SPS=2.5 for DVB-S2) |
| **RX sample rate** | 8 MS/s (2× decim to BPSK) | 10 MS/s (5× decim to BPSK) |

4 Msym/s would need ~10+ MS/s composite rate, pushing HackRF USB bandwidth and Rock 2A CPU. The DVB-S2 baseband at 4 Msym/s starts at -0.7 MHz (nearly touching BPSK at -2 MHz), leaving little guard band. And the dvbs2/tx.py flowgraph would need non-integer SPS (2.5).

**2 Msym/s is the safe, conservative choice that's proven to work.** 1080p @ 15 fps with H.264 ultrafast at 1.5 Mbps will look good for balloon footage (slow pans, static landscapes). If we want higher later, we can scale up — the `--sym-rate` is just a CLI flag.
