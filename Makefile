# dnfs — Distributed NFS multipath client
#
# Targets:
#   make build   — prepare DKMS source (no compile needed for tools)
#   make install — install to /usr/local
#   make deb     — build .deb packages (dnfs-dkms + dnfs-tools)
#   make clean   — remove build artifacts

PACKAGE    = dnfs
VERSION   := $(shell grep -oP '\((.*?)\)' debian/changelog 2>/dev/null | head -1 | tr -d '()' || echo "0.1.0")
ARCH      := $(shell dpkg --print-architecture 2>/dev/null || echo "amd64")
PREFIX    ?= /usr/local

all: build

build:
	@echo "dnfs — no compiled artifacts (Python/Ansible tools are interpreted)"
	@echo "Run 'make deb' to build .deb packages"

install:
	install -d $(DESTDIR)$(PREFIX)/bin
	install -m 755 tests/nfs-stress.py $(DESTDIR)$(PREFIX)/bin/dnfs-stress
	install -d $(DESTDIR)$(PREFIX)/share/dnfs
	cp -r ansible $(DESTDIR)$(PREFIX)/share/dnfs/
	install -d $(DESTDIR)$(PREFIX)/share/doc/dnfs
	install -m 644 AGENTS.md README.md docs/*.md $(DESTDIR)$(PREFIX)/share/doc/dnfs/

uninstall:
	rm -f $(DESTDIR)$(PREFIX)/bin/dnfs-stress
	rm -rf $(DESTDIR)$(PREFIX)/share/dnfs $(DESTDIR)$(PREFIX)/share/doc/dnfs

deb: clean
	@echo "Building $(PACKAGE) .deb packages..."
	debuild -b -us -uc
	@echo ""
	@echo "Packages:"
	@ls -1 ../$(PACKAGE)*.deb 2>/dev/null || echo "  (not found)"
	@ls -1 ../$(PACKAGE)*.buildinfo 2>/dev/null || true

clean:
	rm -rf debian/$(PACKAGE)-dkms debian/$(PACKAGE)-tools debian/.debhelper debian/tmp
	rm -f debian/debhelper-build-stamp debian/files debian/*.log debian/*.substvars
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true

.PHONY: all build install uninstall deb clean
