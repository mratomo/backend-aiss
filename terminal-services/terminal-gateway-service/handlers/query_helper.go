package handlers

import (
	"fmt"
	"log"
	"strings"
	"time"

	"github.com/gorilla/websocket"

	"terminal-gateway-service/models"
	"terminal-gateway-service/utils"
)

// queryModeHandler is a helper for handling query mode operations
type queryModeHandler struct {
	manager *SSHManager
	logger  *utils.Logger
}

// newQueryModeHandler creates a new query mode handler
func newQueryModeHandler(manager *SSHManager) *queryModeHandler {
	return &queryModeHandler{
		manager: manager,
		logger:  utils.GetLogger("query_mode"),
	}
}

// toggleQueryMode toggles between normal and query mode
func (q *queryModeHandler) toggleQueryMode(sessionID string, ws *websocket.Conn, conn *models.SSHConnection) {
	// Check current mode state
	conn.Lock.Lock()
	currentlyInQueryMode := conn.IsInQueryMode
	activeAreaID := conn.ActiveAreaID
	conn.Lock.Unlock()

	if currentlyInQueryMode {
		// Currently in query mode, switch to normal mode
		q.disableQueryMode(sessionID, ws, conn)
	} else {
		// Currently in normal mode, switch to query mode
		// If no active area is set, we need to ask the user to select one
		if activeAreaID == "" {
			// Try to get the most recently used area for this user
			recentArea, err := q.manager.sessionClient.GetUserRecentArea(conn.UserID)
			if err != nil || recentArea == "" {
				// No recent area, send a message asking the user to select one
				ws.WriteJSON(models.WebSocketMessage{
					Type: "mode_change_request",
					Data: map[string]interface{}{
						"message":  "Please select a knowledge area for query mode",
						"required": true,
					},
				})
				return
			}

			// Use the most recent area
			activeAreaID = recentArea
		}

		// Enable query mode with the active area
		q.enableQueryMode(sessionID, ws, conn, activeAreaID)
	}
}

// enableQueryMode switches the terminal to RAG query mode
func (q *queryModeHandler) enableQueryMode(sessionID string, ws *websocket.Conn, conn *models.SSHConnection, areaID string) {
	// Get area name for better user experience
	areaName := areaID
	areaInfo, err := q.manager.sessionClient.GetAreaInfo(areaID)
	if err == nil && areaInfo.Name != "" {
		areaName = areaInfo.Name
	}

	// Update the session state
	conn.Lock.Lock()
	previousMode := "normal"
	if conn.IsInQueryMode {
		previousMode = "query"
	}
	conn.IsInQueryMode = true
	conn.ActiveAreaID = areaID
	conn.Lock.Unlock()

	// Update the session in the session service
	err = q.manager.sessionClient.UpdateSessionMode(sessionID, string(models.SessionModeQuery), areaID)
	if err != nil {
		q.logger.Error("Failed to update session mode in session service: %v", err)
	}

	// Send a notification about the mode change
	ws.WriteJSON(models.WebSocketMessage{
		Type: "mode_changed",
		Data: models.ModeChange{
			PreviousMode: previousMode,
			NewMode:      string(models.SessionModeQuery),
			AreaID:       areaID,
		},
	})

	// Broadcast to other clients on this session
	go q.manager.broadcastToSessionExcept(sessionID, ws, "mode_changed", models.ModeChange{
		PreviousMode: previousMode,
		NewMode:      string(models.SessionModeQuery),
		AreaID:       areaID,
	})

	// Send visual indicator to the terminal
	promptMsg := utils.FormatQueryModeActivation(areaID, areaName)

	// Send the message to the client
	ws.WriteJSON(models.WebSocketMessage{
		Type: "terminal_output",
		Data: models.TerminalOutput{
			Data: promptMsg,
		},
	})
}

// disableQueryMode switches the terminal back to normal mode
func (q *queryModeHandler) disableQueryMode(sessionID string, ws *websocket.Conn, conn *models.SSHConnection) {
	// Update the session state
	conn.Lock.Lock()
	previousMode := "query"
	if !conn.IsInQueryMode {
		previousMode = "normal"
	}
	activeAreaID := conn.ActiveAreaID
	conn.IsInQueryMode = false
	conn.Lock.Unlock()

	// Update the session in the session service
	err := q.manager.sessionClient.UpdateSessionMode(sessionID, string(models.SessionModeNormal), "")
	if err != nil {
		q.logger.Error("Failed to update session mode in session service: %v", err)
	}

	// Send a notification about the mode change
	ws.WriteJSON(models.WebSocketMessage{
		Type: "mode_changed",
		Data: models.ModeChange{
			PreviousMode: previousMode,
			NewMode:      string(models.SessionModeNormal),
			AreaID:       activeAreaID,
		},
	})

	// Broadcast to other clients on this session
	go q.manager.broadcastToSessionExcept(sessionID, ws, "mode_changed", models.ModeChange{
		PreviousMode: previousMode,
		NewMode:      string(models.SessionModeNormal),
		AreaID:       activeAreaID,
	})

	// Send visual indicator to the terminal
	promptMsg := utils.FormatQueryModeDeactivation()

	// Send the message to the client
	ws.WriteJSON(models.WebSocketMessage{
		Type: "terminal_output",
		Data: models.TerminalOutput{
			Data: promptMsg,
		},
	})
}

// handleRagQuery processes a RAG query and sends the response back to the client
func (q *queryModeHandler) handleRagQuery(sessionID string, userID string, query string, areaID string, ws *websocket.Conn) {
	// Don't process empty queries
	query = strings.TrimSpace(query)
	if query == "" {
		return
	}

	// Send a "thinking" indicator to the client
	progressRenderer := utils.NewProgressRenderer(nil, "Processing query...")
	ws.WriteJSON(models.WebSocketMessage{
		Type: "terminal_output",
		Data: models.TerminalOutput{
			Data: "\033[3m\033[90mProcessing query...\033[0m\r\n",
		},
	})

	// Start timer for tracking query duration
	startTime := time.Now()

	// Get terminal context if needed
	terminalContext, err := q.getTerminalContext(sessionID)
	if err != nil {
		q.logger.Error("Failed to get terminal context: %v", err)
		// Continue without context
	}

	// Call the RAG Agent via the session client
	response, err := q.manager.sessionClient.ProcessRagQuery(query, userID, areaID, terminalContext)

	// Stop progress renderer
	progressRenderer.Stop()

	// Calculate query time
	queryTime := time.Since(startTime)

	if err != nil {
		q.logger.Error("Failed to process RAG query (%s): %v", query, err)
		// Send error message to the client
		ws.WriteJSON(models.WebSocketMessage{
			Type: "terminal_output",
			Data: models.TerminalOutput{
				Data: fmt.Sprintf("\r\n\033[1;31mError processing query: %v\033[0m\r\n> ", err),
			},
		})
		return
	}

	// Format the response
	formattedResponse := utils.FormatRagResponse(response.Answer, response.Sources)

	// Log successful completion
	q.logger.Info("RAG Query completed in %v: %s", queryTime, query)

	// Send the response to the client
	ws.WriteJSON(models.WebSocketMessage{
		Type: "terminal_output",
		Data: models.TerminalOutput{
			Data: formattedResponse,
		},
	})

	// Also send the structured response for the UI to handle
	ws.WriteJSON(models.WebSocketMessage{
		Type: "rag_response",
		Data: response,
	})
}

// getTerminalContext retrieves the terminal context for a session
func (q *queryModeHandler) getTerminalContext(sessionID string) (map[string]interface{}, error) {
	// First try to get from MCP if available
	if q.manager.mcpClient != nil {
		// Get basic session context first
		basicContext, err := q.manager.sessionClient.GetSessionContext(sessionID)
		if err != nil {
			q.logger.Warning("Failed to get session context from session service: %v", err)
			// Continue with empty context, we'll try to enrich from MCP
		}

		// Try to get enriched context from MCP
		enrichedContext, err := q.manager.mcpClient.RetrieveTerminalContext(sessionID, "", basicContext)
		if err == nil && enrichedContext != nil {
			// Check if we have relevant context
			if relevantContext, ok := enrichedContext["relevant_context"]; ok && relevantContext != nil {
				q.logger.Info("Retrieved enriched terminal context from MCP for session %s", sessionID)
				return enrichedContext, nil
			}
		} else if err != nil {
			q.logger.Warning("Failed to get context from MCP: %v", err)
		}

		// Return basic context if we couldn't get enriched
		if basicContext != nil {
			return basicContext, nil
		}
	}

	// Fallback to session service context
	context, err := q.manager.sessionClient.GetSessionContext(sessionID)
	if err != nil {
		return nil, fmt.Errorf("failed to get session context: %w", err)
	}

	return context, nil
}

// isShortcutKey checks if the input is the shortcut key combination
func isShortcutKey(input string, shortcut string) bool {
	// This is a simplified check - in a real terminal client,
	// we would receive proper keyboard events with key codes

	// Check for control characters that might represent the shortcut
	if shortcut == "ctrl+alt+q" {
		// Check for variations of Ctrl+Alt+Q
		variants := []string{
			"\x11q",     // Ctrl+Q
			"\x11\x01q", // Some terminals might send this for Ctrl+Alt+Q
			"^Qq",       // Another representation
		}

		for _, variant := range variants {
			if strings.Contains(input, variant) {
				return true
			}
		}
	}

	// Also check for a literal string match (for testing)
	return strings.Contains(strings.ToLower(input), shortcut)
}
