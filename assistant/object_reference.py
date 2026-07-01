"""
Max object reference data (MAXCLASS conventions + fixed inlet/outlet counts).

This module is NOT currently imported or used by anything — it's preparation
for the planned patch-analyzer feature. It was originally embedded as prompt
text inside GENERATE_SYSTEM_PROMPT (now removed) and is preserved here rather
than deleted, since it's intended reference data for future patch-analysis
code, not dead code.

Note: gain~ is corrected here to 2 inlets, 2 outlets (the accurate default
per docs.cycling74.com/legacy/max8/refpages/gain~ — a 3rd inlet only appears
if the non-default 'interpinlet' attribute is explicitly enabled). The
original text this table was moved from had it wrong as "3 2". Separately,
validate.py's own TRUSTED_PORT_COUNTS["gain~"] = (1, 2) is also wrong and
remains an open, not-yet-addressed follow-up — validate.py was not touched
as part of this change.
"""

MAX_OBJECT_REFERENCE_TABLE = """INLET/OUTLET REFERENCE TABLE — MANDATORY
You must use these exact numinlets and numoutlets values. Do not deviate.

MAXCLASS RULES:
- Use maxclass: newobj for ALL of the following (object name goes in "text" field):
  cycle~, saw~, rect~, tri~, noise~, pink~, sig~, *~, +~, -~, /~, gain~, snapshot~,
  line~, phasor~, delay~, tapin~, tapout~, groove~, play~, record~, buffer~, wave~,
  lookup~, index~, biquad~, lores~, highpass~, onepole~, svf~, filtercoeff~, cascade~,
  allpass~, comb~, teeth~, degrade~, overdrive~, scope~, meter~, peakamp~, average~,
  rms~, delta~, abs~, clip~, maximum~, minimum~, scale~, slide~, rampsmooth~,
  changebang~, rate~, pfft~, fftin~, fftout~, stft~, ifft~, cartopol~, poltocar~,
  2d.wave~, msinfo~, thispoly~, edge~, threshold~, number~, matrix~,
  plugin~, plugout~, dac~, adc~, ezdac~, ezadc~,
  live.path, live.object, live.observer, live.remote~, live.banks,
  metro, delay, pipe, timer, clocker, counter, accum, gate, switch,
  change, past, thresh, split, Moses, speedlim, prob, random, drunk,
  scale, clip, abs, maximum, minimum, modulo, zl, coll, dict, table,
  pattr, autopattr, pattrstorage, send, receive, send~, receive~,
  print, loadbang, loadmess, inlet, outlet, in, out, in~, out~,
  poly~, makenote, stripnote, midiparse, midiformat,
  notein, noteout, ctlin, ctlout, pgmin, pgmout,
  bendin, bendout, touchin, touchout, polytouchin, polytouchout,
  midiin, midiout, pitchin

- Use the object's own name as maxclass ONLY for these UI objects:
  number, number~, flonum, toggle, button, slider, dial, message, comment,
  multislider, umenu, kslider, textbutton,
  live.dial, live.numbox, live.button, live.slider, live.text,
  live.menu, live.tab, live.thisdevice

FIXED INLET/OUTLET COUNTS:
Object               numinlets  numoutlets
---                  ---        ---
*~                   2          1
+~                   2          1
-~                   2          1
/~                   2          1
2d.wave~             6          1
abs                  1          1
abs~                 1          1
accum                2          1
adc~                 0          2
allpass~             3          1
autopattr            1          1
average~             2          1
avg~                 1          1
bang                 1          1
bendin               0          2
bendout              2          0
biquad~              3          1
buffer~              1          2
button               1          1
cartopol~            2          2
cascade~             3          1
change               1          1
changebang~          1          1
clip                 1          1
clip~                3          1
clocker              2          1
coll                 2          3
comb~                3          1
comment              1          0
counter              4          3
ctlin                0          3
ctlout               3          0
cycle~               2          1
dac~                 2          0
degrade~             3          1
delay                2          1
delay~               2          1
delta~               1          1
dial                 1          1
dict                 1          3
drunk                2          1
edge~                1          2
ezadc~               0          2
ezdac~               2          0
fftin~               1          3
fftout~              3          0
filtercoeff~         6          5
float                2          1
flonum               2          2
gain~                2          2
gate                 2          1
groove~              4          3
highpass~            3          1
if                   1          1
ifft~                3          1
in                   0          1
index~               2          1
inlet                0          1
int                  2          1
in~                  0          1
kslider              2          2
line~                2          1
live.banks           1          0
live.button          1          1
live.dial            1          2
live.menu            1          2
live.numbox          1          2
live.object          2          2
live.observer        2          1
live.path            1          2
live.remote~         2          0
live.slider          1          2
live.tab             1          2
live.text            1          2
live.thisdevice      0          2
loadbang             0          1
loadmess             0          1
lookup~              2          1
lores~               3          1
makenote             3          2
matrix~              2          2
maximum              2          1
maximum~             2          1
message              2          1
meter~               1          0
metro                2          1
midiformat           5          1
midiin               0          2
midiout              2          0
midiparse            1          5
minimum              2          1
minimum~             2          1
modulo               2          1
Moses                2          2
msinfo~              0          5
multislider          2          2
noise~               0          1
notein               0          3
noteout              3          0
number               2          2
number~              2          2
onepole~             2          1
out                  1          0
outlet               1          0
out~                 1          0
overdrive~           2          1
past                 2          1
pattr                2          2
pattrstorage         1          3
peakamp~             2          1
pfft~                1          1
pgmin                0          2
pgmout               2          0
phasor~              2          1
pink~                0          1
pipe                 2          1
pitchin              0          2
play~                3          2
plugin~              2          0
plugout~             0          2
poltocar~            2          2
polytouchin          0          3
polytouchout         3          0
poly~                2          1
print                1          0
prob                 2          1
rampsmooth~          3          1
random               2          1
rate~                2          1
receive              0          1
receive~             0          1
record~              3          1
rect~                2          1
rms~                 2          1
saw~                 2          1
scale                1          1
scale~               3          1
scope~               2          0
send                 1          0
send~                1          0
sig~                 1          1
slider               1          1
slide~               3          1
snapshot~            1          1
speedlim             1          1
split                2          2
stft~                2          2
stripnote            2          2
svf~                 3          4
switch               2          1
table                2          2
tapin~               1          1
tapout~              2          1
teeth~               4          1
textbutton           1          2
thispoly~            2          2
thresh               2          2
threshold~           1          2
timer                2          1
toggle               1          1
touchin              0          2
touchout             2          0
tri~                 2          1
umenu                2          3
wave~                5          1
zl                   2          2

VARIABLE-OUTLET OBJECTS — count from arguments:
sel, route, pack, unpack: numoutlets = number of typed arguments + 1 (overflow outlet)
trigger: numoutlets = number of typed arguments
iter, join, flush: numoutlets = 1 unless arguments specify otherwise

M4L DEVICE RULES:
- Audio Effect: must include plugin~ (numinlets=2) and plugout~ (numoutlets=2)
- MIDI Effect: must include midiin and midiout, no plugin~/plugout~
- Instrument: must include plugout~ (numoutlets=2), no plugin~
- Any patch using live.* API objects must include live.thisdevice
"""
