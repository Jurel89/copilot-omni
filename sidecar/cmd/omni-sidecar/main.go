package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/copilot-omni/sidecar/internal/mcp"
	"github.com/copilot-omni/sidecar/internal/version"
)

func main() {
	if err := run(os.Args[1:]); err != nil {
		log.New(os.Stderr, "sidecar: ", log.LstdFlags).Printf("fatal error: %v", err)
		os.Exit(1)
	}
}

func run(args []string) error {
	command := "serve"
	if len(args) > 0 {
		command = args[0]
	}

	switch command {
	case "serve":
		return serve()
	case "version":
		_, err := fmt.Fprintln(os.Stderr, version.Version)
		return err
	default:
		return fmt.Errorf("unknown subcommand: %s", command)
	}
}

func serve() error {
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	return mcp.Serve(ctx, os.Stdin, os.Stdout, os.Stderr, time.Now())
}
