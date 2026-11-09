#lang sciencelogo
workflow "Pendulum period"
include "stages/setup.rkt"
include "stages/timing.rkt"
performer researcher [kind = "human" role = "scientist"]
to calculate-period :duration :count about "Divide the elapsed time by the count." [
  output :duration / :count
]
stage Report
print 3
phase Measurement
about "Measure the period."
[Setup Timing]
