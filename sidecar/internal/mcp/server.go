package mcp

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"os"
	"sync"
	"time"

	"github.com/copilot-omni/sidecar/internal/config"
	"github.com/copilot-omni/sidecar/internal/version"
)

const (
	jsonRPCVersion     = "2.0"
	errCodeParse       = -32700
	errCodeInvalidReq  = -32600
	errCodeMethod      = -32601
	errCodeInvalidArgs = -32602
)

type Server struct {
	logger         *log.Logger
	registry       *Registry
	stdin          io.ReadCloser
	encoder        *json.Encoder
	writeMu        sync.Mutex
	configResolver ConfigResolver
}

func NewServer(stdin io.ReadCloser, stdout io.Writer, stderr io.Writer, startedAt time.Time, resolver ConfigResolver) *Server {
	return &Server{
		logger:         log.New(stderr, "sidecar: ", log.LstdFlags),
		registry:       NewRegistry(startedAt, resolver),
		stdin:          stdin,
		encoder:        json.NewEncoder(stdout),
		configResolver: resolver,
	}
}

func NewDefaultServer() *Server {
	return NewServer(os.Stdin, os.Stdout, os.Stderr, time.Now(), config.Resolve)
}

func Serve(ctx context.Context, stdin io.ReadCloser, stdout io.Writer, stderr io.Writer, startedAt time.Time) error {
	return NewServer(stdin, stdout, stderr, startedAt, config.Resolve).Serve(ctx)
}

func (s *Server) Serve(ctx context.Context) error {
	go func() {
		<-ctx.Done()
		_ = s.stdin.Close()
	}()

	scanner := bufio.NewScanner(s.stdin)
	scanner.Buffer(make([]byte, 0, 64*1024), 1024*1024)

	for scanner.Scan() {
		select {
		case <-ctx.Done():
			return nil
		default:
		}

		line := scanner.Bytes()
		if len(line) == 0 {
			continue
		}

		if err := s.handleLine(ctx, line); err != nil {
			s.logger.Printf("request handling failed: %v", err)
		}
	}

	if err := scanner.Err(); err != nil {
		if ctx.Err() != nil || errors.Is(err, os.ErrClosed) {
			return nil
		}
		return fmt.Errorf("scan stdin: %w", err)
	}

	return nil
}

func (s *Server) handleLine(ctx context.Context, line []byte) error {
	var request Request
	if err := json.Unmarshal(line, &request); err != nil {
		return s.writeResponse(Response{
			JSONRPC: jsonRPCVersion,
			Error: &RPCError{
				Code:    errCodeParse,
				Message: "parse error",
			},
		})
	}

	if request.JSONRPC != jsonRPCVersion || request.Method == "" {
		return s.writeResponse(Response{
			JSONRPC: jsonRPCVersion,
			ID:      rawIDToValue(request.ID),
			Error: &RPCError{
				Code:    errCodeInvalidReq,
				Message: "invalid request",
			},
		})
	}

	response, shouldReply := s.dispatch(ctx, request)
	if !shouldReply {
		return nil
	}

	return s.writeResponse(response)
}

func (s *Server) dispatch(ctx context.Context, request Request) (Response, bool) {
	response := Response{JSONRPC: jsonRPCVersion, ID: rawIDToValue(request.ID)}

	switch request.Method {
	case "initialize":
		var params InitializeParams
		if len(request.Params) > 0 {
			if err := json.Unmarshal(request.Params, &params); err != nil {
				response.Error = &RPCError{Code: errCodeInvalidArgs, Message: "invalid initialize params"}
				return response, true
			}
		}

		response.Result = InitializeResult{
			ProtocolVersion: ProtocolVersion,
			Capabilities: ServerCapabilities{
				Tools: ToolsCapability{ListChanged: false},
			},
			ServerInfo: ServerInfo{
				Name:    ServerName,
				Version: version.Version,
			},
		}
		return response, true
	case "notifications/initialized":
		s.logger.Println("client initialized")
		return Response{}, false
	case "tools/list":
		response.Result = ToolsListResult{Tools: s.registry.List()}
		return response, true
	case "tools/call":
		var params ToolCallParams
		if len(request.Params) > 0 {
			if err := json.Unmarshal(request.Params, &params); err != nil {
				response.Error = &RPCError{Code: errCodeInvalidArgs, Message: "invalid tools/call params"}
				return response, true
			}
		}

		result, err := s.registry.Call(ctx, params.Name, params.Arguments)
		if err != nil {
			response.Error = &RPCError{Code: errCodeInvalidArgs, Message: err.Error()}
			return response, true
		}

		response.Result = result
		return response, true
	default:
		response.Error = &RPCError{Code: errCodeMethod, Message: "method not found"}
		return response, true
	}
}

func (s *Server) writeResponse(response Response) error {
	s.writeMu.Lock()
	defer s.writeMu.Unlock()

	if err := s.encoder.Encode(response); err != nil {
		return fmt.Errorf("encode response: %w", err)
	}

	return nil
}

func rawIDToValue(raw *json.RawMessage) interface{} {
	if raw == nil {
		return nil
	}

	var value interface{}
	if err := json.Unmarshal(*raw, &value); err != nil {
		return nil
	}

	return value
}
