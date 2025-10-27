Process to setup data sending to separate telemetry channel. Use packet_loopback_hier.grc


***
A) Easiest from any external app (recommended if you don’t need ZMQ features)

External (Python) → TCP Socket → GNU Radio

# external_producer.py
import socket
s = socket.create_connection(("127.0.0.1", 52001))
s.sendall(b"hello, radio")        # send any bytes as a “PDU”


GRC:

Add Socket PDU block, Type=TCP Server, Port=52001.

Its output is a PDU you can feed straight into packet_tx.

***





Commands to setup ffmpeg -> tsp -> fifo -> gnuradio

ffmpeg -re -fflags +genpts -i tablesaw-trim.mp4   -vf "scale=1920:1080,format=yuv420p" -r 30   -c:v libx264 -preset veryfast -tune zerolatency   -g 30 -keyint_min 30   -b:v 700k -maxrate 700k -bufsize 500k   -c:a mp2 -b:a 128k   -f mpegts -muxrate 965326 -mpegts_flags +resend_headers   "udp://239.1.1.1:5001?pkt_size=1316"

tsp -I ip 239.1.1.1:5001 -P regulate --bitrate 965326 -O file /tmp/tsfifo


Here are the dvbs2rates for a 1Msymb/s stream. As you can see, we are using QPSK Pilots On coderate 1/2 

charleshood@mac dtv-utils-master % ./dvbs2rate 1000000
DVB-S2 normal FECFRAME
QPSK, pilots off
coderate = 1/4,  BCH rate = 12, ts rate = 490243.151739
coderate = 1/3,  BCH rate = 12, ts rate = 656448.137889
coderate = 2/5,  BCH rate = 12, ts rate = 789412.126808
coderate = 1/2,  BCH rate = 12, ts rate = 988858.110188
coderate = 3/5,  BCH rate = 12, ts rate = 1188304.093567
coderate = 2/3,  BCH rate = 10, ts rate = 1322253.000923
coderate = 3/4,  BCH rate = 12, ts rate = 1487473.068637
coderate = 4/5,  BCH rate = 12, ts rate = 1587196.060326
coderate = 5/6,  BCH rate = 10, ts rate = 1654662.973223
coderate = 8/9,  BCH rate =  8, ts rate = 1766451.215759
coderate = 9/10, BCH rate =  8, ts rate = 1788611.880579
QPSK, pilots on
coderate = 1/4,  BCH rate = 12, ts rate = 478577.008593
coderate = 1/3,  BCH rate = 12, ts rate = 640826.873385
coderate = 2/5,  BCH rate = 12, ts rate = 770626.765218
coderate = 1/2,  BCH rate = 12, ts rate = 965326.602969
coderate = 3/5,  BCH rate = 12, ts rate = 1160026.440719
coderate = 2/3,  BCH rate = 10, ts rate = 1290787.813232
coderate = 3/4,  BCH rate = 12, ts rate = 1452076.197344
coderate = 4/5,  BCH rate = 12, ts rate = 1549426.116219
coderate = 5/6,  BCH rate = 10, ts rate = 1615287.542816
coderate = 8/9,  BCH rate =  8, ts rate = 1724415.600024
coderate = 9/10, BCH rate =  8, ts rate = 1746048.915330
8PSK, pilots off
coderate = 3/5,  BCH rate = 12, ts rate = 1779990.779161
coderate = 2/3,  BCH rate = 10, ts rate = 1980636.237898
coderate = 3/4,  BCH rate = 12, ts rate = 2228123.559244
coderate = 5/6,  BCH rate = 10, ts rate = 2478561.549101
coderate = 8/9,  BCH rate =  8, ts rate = 2646011.987091
coderate = 9/10, BCH rate =  8, ts rate = 2679207.007838
8PSK, pilots on
coderate = 3/5,  BCH rate = 12, ts rate = 1739569.252951
coderate = 2/3,  BCH rate = 10, ts rate = 1935658.286023
coderate = 3/4,  BCH rate = 12, ts rate = 2177525.457331
coderate = 5/6,  BCH rate = 10, ts rate = 2422276.290889
coderate = 8/9,  BCH rate =  8, ts rate = 2585924.123637
coderate = 9/10, BCH rate =  8, ts rate = 2618365.323961
16APSK, pilots off
coderate = 2/3,  BCH rate = 10, ts rate = 2637200.736648
coderate = 3/4,  BCH rate = 12, ts rate = 2966728.054021
coderate = 4/5,  BCH rate = 12, ts rate = 3165623.081645
coderate = 5/6,  BCH rate = 10, ts rate = 3300184.162063
coderate = 8/9,  BCH rate =  8, ts rate = 3523143.032535
coderate = 9/10, BCH rate =  8, ts rate = 3567341.927563
16APSK, pilots on
coderate = 2/3,  BCH rate = 10, ts rate = 2574613.448400
coderate = 3/4,  BCH rate = 12, ts rate = 2896320.268489
coderate = 4/5,  BCH rate = 12, ts rate = 3090495.025770
coderate = 5/6,  BCH rate = 10, ts rate = 3221862.639338
coderate = 8/9,  BCH rate =  8, ts rate = 3439530.145032
coderate = 9/10, BCH rate =  8, ts rate = 3482680.091094
32APSK, pilots off
coderate = 3/4,  BCH rate = 12, ts rate = 3703295.019157
coderate = 4/5,  BCH rate = 12, ts rate = 3951570.881226
coderate = 5/6,  BCH rate = 10, ts rate = 4119540.229885
coderate = 8/9,  BCH rate =  8, ts rate = 4397854.406130
coderate = 9/10, BCH rate =  8, ts rate = 4453026.819923
32APSK, pilots on
coderate = 3/4,  BCH rate = 12, ts rate = 3623331.833858
coderate = 4/5,  BCH rate = 12, ts rate = 3866246.813615
coderate = 5/6,  BCH rate = 10, ts rate = 4030589.293747
coderate = 8/9,  BCH rate =  8, ts rate = 4302893.987105
coderate = 9/10, BCH rate =  8, ts rate = 4356875.093717