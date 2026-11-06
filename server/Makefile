# Define the Go compiler
GO := go

# Define the source files
SERVER_SRC := cmd/server/server.go
SEND_COMMAND_SRC := cmd/send_command/send_command.go

# Define the output directory
BIN_DIR := bin

# Define the output binaries
SERVER_BIN := $(BIN_DIR)/server
SEND_COMMAND_BIN := $(BIN_DIR)/send_command

# Default target
all: $(SERVER_BIN) $(SEND_COMMAND_BIN)

# Build the server binary
$(SERVER_BIN): $(SERVER_SRC)
	@mkdir -p $(BIN_DIR)
	$(GO) build -o $@ $<

# Build the send_command binary
$(SEND_COMMAND_BIN): $(SEND_COMMAND_SRC)
	@mkdir -p $(BIN_DIR)
	$(GO) build -o $@ $<

# Statically linked binaries, for copying to another machine (e.g. the trailer
# DAQ PC): no dependency on this machine's glibc version, and no Go toolchain or
# module download needed there. Always rebuilds.
static:
	@mkdir -p $(BIN_DIR)
	CGO_ENABLED=0 $(GO) build -o $(SERVER_BIN) ./cmd/server
	CGO_ENABLED=0 $(GO) build -o $(SEND_COMMAND_BIN) ./cmd/send_command

# Clean up the binaries
clean:
	rm -rf $(BIN_DIR)

.PHONY: all clean static