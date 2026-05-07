# Makefile for dnfs unit tests
#
# Compiles the kernel option parsing code (nfs_multipath.c) in user space
# using mock kernel headers, then runs the unit tests.
#
# Usage:
#   make          # Build and run all tests
#   make build    # Build only
#   make run      # Run only (requires build)
#   make clean    # Clean build artifacts

CC := gcc
CFLAGS := -Wall -Werror -Wextra -Wno-unused-parameter \
	  -Wno-missing-field-initializers \
	  -g -O0 -std=gnu11 \
	  -fsanitize=address -fsanitize=undefined

# Include paths for mock kernel headers and production source.
INCLUDES := -I. \
	    -I./mocks \
	    -I../fs \
	    -I../fs/nfs

# Test source files.
SRCS := unit/test_nfs_multipath.c

# All test binaries.
BINS := test_nfs_multipath

.PHONY: all build run clean

all: build
	@echo "=== Running all tests ==="
	@for test in $(BINS); do \
		echo; \
		echo "--- $$test ---"; \
		./$$test; \
		if [ $$? -ne 0 ]; then \
			exit 1; \
		fi; \
	done
	@echo "=== All tests passed ==="

build: $(BINS)

run: build
	@for test in $(BINS); do \
		echo "--- $$test ---"; \
		./$$test; \
	done

test_nfs_multipath: unit/test_nfs_multipath.c
	$(CC) $(CFLAGS) $(INCLUDES) -o $@ $^

clean:
	rm -f $(BINS)
