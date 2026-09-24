# Regenerate the pyuic6 output from the Qt Designer sources in designer/.
#
# The .ui files are the source of truth; GUI.py and star_options_ui.py are
# generated and must never be hand-edited. That rule is not theoretical: commit
# 80c6c5b hand-edited GUI.py (title font 27 -> 24, camera min height 1000 ->
# 700) and those changes never reached GUI.ui, so the two drifted apart for
# nearly a year. `make check` exists to catch exactly that.
#
#   make          regenerate both modules from designer/
#   make check    fail if a generated module differs from its source
#
# NOT regenerable: resources_rc.py.
#   Its header says "Created by: The Resource Compiler for PyQt5". PyQt6 dropped
#   pyrcc, so there is no pyrcc6, and /usr/bin/rcc emits C++ rather than Python.
#   resources.qrc and images/ therefore describe what is inside the committed
#   resources_rc.py but cannot rebuild it with the current toolchain. Leave all
#   three alone unless you are prepared to install PyQt5 to regenerate.

PYUIC := pyuic6
DESIGNER := designer

GENERATED := GUI.py star_options_ui.py

.PHONY: all check clean

all: $(GENERATED)

GUI.py: $(DESIGNER)/GUI.ui
	$(PYUIC) $< -o $@

star_options_ui.py: $(DESIGNER)/star_options.ui
	$(PYUIC) $< -o $@

# Regenerate into a temp file and compare, so drift is visible without
# clobbering the working tree.
check:
	@status=0; \
	for pair in "GUI.py:$(DESIGNER)/GUI.ui" "star_options_ui.py:$(DESIGNER)/star_options.ui"; do \
	    out=$${pair%%:*}; src=$${pair#*:}; \
	    tmp=$$(mktemp); \
	    $(PYUIC) $$src -o $$tmp; \
	    if diff -q $$out $$tmp >/dev/null 2>&1; then \
	        echo "ok    $$out matches $$src"; \
	    else \
	        echo "DRIFT $$out differs from $$src -- run 'make' and review"; \
	        diff -u $$out $$tmp | head -40; \
	        status=1; \
	    fi; \
	    rm -f $$tmp; \
	done; \
	exit $$status

clean:
	rm -f $(GENERATED)
