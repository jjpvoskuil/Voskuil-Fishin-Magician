# Quickdraw survey data

Drop CSV exports here from your own Garmin Quickdraw Contours recordings
(converted with [qdc-converter](https://github.com/interlark/qdc-converter),
e.g. `qdc-converter -i "Garmin/Quickdraw/Contours/C" -o "trip1.csv" -l 1`).

Any number of files is fine - `core/survey_points.py` reads every `*.csv` in
this folder and combines them, so you can drop in one file per outing as you
explore more of the lake, or replace with a single merged export any time
(Quickdraw already merges new passes into your device's existing contour
data automatically, so a fresh export is usually your full coverage-to-date
anyway).

Expected format (qdc-converter's default CSV output): a header row followed
by `X,Y,Depth(m)` columns, where X = longitude (decimal degrees), Y =
latitude (decimal degrees), and depth is in meters. `core/survey_points.py`
converts depth to feet automatically.

This is your own recorded sonar data, not a third-party chart - `core/bathymetry.py`
blends it into the modeled depth grid, using real data wherever you've recorded it
and falling back to the modeled channel surface everywhere else.
