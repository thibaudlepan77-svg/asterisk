# Live demo

A small Gradio front end over the same engine. Paste an offer page, get the
promises and the sentences that take them back.

```bash
pip install gradio
python demo/app.py
```

**Status, written the day it was created.** The audit logic was moved out of
this file into `asterisk/service.py`, precisely so that the part that does the
work can be tested without starting a server, and it is, in
`tests_asterisk.py` under `Service`. What remains here is the Gradio shell,
about thirty lines of layout.

**The server itself has still not been started**, so the layout has not been
seen rendered. That is stated rather than implied, because this repository is a
tool about claims a page does not back up and it would be a poor joke to make
one.
