package utils

import (
	"fmt"
	"io"
	"strings"
	"time"
)

// ProgressRenderer renders progress feedback for query operations
type ProgressRenderer struct {
	writer     io.Writer
	indicators []string
	interval   time.Duration
	message    string
	done       chan struct{}
}

// NewProgressRenderer creates a new progress renderer
func NewProgressRenderer(writer io.Writer, message string) *ProgressRenderer {
	return &ProgressRenderer{
		writer:     writer,
		indicators: []string{"⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"},
		interval:   100 * time.Millisecond,
		message:    message,
		done:       make(chan struct{}),
	}
}

// Start starts the progress animation
func (p *ProgressRenderer) Start() {
	go p.render()
}

// Stop stops the progress animation
func (p *ProgressRenderer) Stop() {
	close(p.done)
}

// render continually renders the progress indicator
func (p *ProgressRenderer) render() {
	ticker := time.NewTicker(p.interval)
	defer ticker.Stop()

	i := 0
	for {
		select {
		case <-ticker.C:
			indicator := p.indicators[i%len(p.indicators)]
			fmt.Fprintf(p.writer, "\r\033[K\033[3m\033[90m%s %s\033[0m", indicator, p.message)
			i++
		case <-p.done:
			// Clear the line when done
			fmt.Fprintf(p.writer, "\r\033[K")
			return
		}
	}
}

// FormatRagResponse formats a RAG response for terminal display
func FormatRagResponse(answer string, sources []struct { Title string; Snippet string }) string {
	var builder strings.Builder

	// Format the answer with a nice style
	builder.WriteString("\r\n\033[1;36m") // Bright cyan, bold
	builder.WriteString(answer)
	builder.WriteString("\033[0m\r\n")    // Reset formatting

	// Add sources if available
	if len(sources) > 0 {
		builder.WriteString("\r\n\033[1;33mSources:\033[0m\r\n") // Bright yellow, bold
		
		for i, source := range sources {
			builder.WriteString(fmt.Sprintf("\033[1m%d.\033[0m %s\r\n", i+1, source.Title))
			
			// Add snippet if available (shortened and formatted)
			if source.Snippet != "" {
				snippet := source.Snippet
				// Shorten if too long
				if len(snippet) > 200 {
					snippet = snippet[:197] + "..."
				}
				builder.WriteString(fmt.Sprintf("   \033[90m%s\033[0m\r\n", snippet))
			}
		}
	}
	
	// Add prompt
	builder.WriteString("\r\n> ")
	
	return builder.String()
}

// FormatQueryModeActivation formats the message shown when query mode is activated
func FormatQueryModeActivation(areaID string, areaName string) string {
	var builder strings.Builder
	
	builder.WriteString("\r\n\033[1;32m>>> Query Mode Activated <<<\033[0m\r\n")
	builder.WriteString(fmt.Sprintf("\033[1;34mKnowledge Area: %s", areaName))
	if areaID != "" {
		builder.WriteString(fmt.Sprintf(" (%s)", areaID))
	}
	builder.WriteString("\033[0m\r\n")
	builder.WriteString("Type your questions directly, or press Ctrl+Alt+Q to exit query mode\r\n\r\n> ")
	
	return builder.String()
}

// FormatQueryModeDeactivation formats the message shown when query mode is deactivated
func FormatQueryModeDeactivation() string {
	var builder strings.Builder
	
	builder.WriteString("\r\n\033[1;33m<<< Exited Query Mode >>>\033[0m\r\n")
	builder.WriteString("Returned to normal terminal mode\r\n\r\n")
	
	return builder.String()
}