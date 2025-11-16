set xlabel "time [s]"
set ylabel "Throughput [Mbps]"
set key bottom right

plot "tcp1.tr" using 1:2 title "tcp1: n0->n5" with linespoints, \
     "tcp2.tr" using 1:2 title "tcp2: n3->n5" with linespoints

pause -1
