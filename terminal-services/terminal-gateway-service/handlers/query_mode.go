package handlers

import (
	"fmt"
	"log"
	"strings"
	"time"

	"github.com/gorilla/websocket"

	"terminal-gateway-service/models"
)

// isShortcutKey checks if the input is the shortcut key combination
func isShortcutKey(input string, shortcut string) bool {
	// This is a simple implementation that looks for "Ctrl+Alt+Q" key sequence
	// In a real implementation, this would handle the actual key code from the terminal emulator
	return strings.Contains(input, shortcut)
}

// handleKeyboardShortcut processes keyboard shortcuts from the terminal
func (m *SSHManager) handleKeyboardShortcut(sessionID string, ws *websocket.Conn, conn *models.SSHConnection, shortcutKey string) {
	// Handle Ctrl+Alt+Q for query mode toggle
	if shortcutKey == "ctrl+alt+q" {
		m.toggleQueryMode(sessionID, ws, conn)
	}
}

// toggleQueryMode toggles between normal and query mode
func (m *SSHManager) toggleQueryMode(sessionID string, ws *websocket.Conn, conn *models.SSHConnection) {
	conn.Lock.Lock()
	currentlyInQueryMode := conn.IsInQueryMode
	activeAreaID := conn.ActiveAreaID
	conn.Lock.Unlock()

	if currentlyInQueryMode {
		// Currently in query mode, switch back to normal
		m.disableQueryMode(sessionID, ws, conn)
	} else {
		// Currently in normal mode, switch to query
		// If no active area is set, we need to ask the user to select one
		if activeAreaID == "" {
			// Send a message asking the user to select an area
			ws.WriteJSON(models.WebSocketMessage{
				Type: "mode_change_request",
				Data: map[string]interface{}{
					"message": "Please select a knowledge area for query mode",
					"required": true,
				},
			})
			return
		}
		
		// If we have an active area, enable query mode
		m.enableQueryMode(sessionID, ws, conn, activeAreaID)
	}
}

// enableQueryMode switches the terminal to RAG query mode
func (m *SSHManager) enableQueryMode(sessionID string, ws *websocket.Conn, conn *models.SSHConnection, areaID string) {
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
	err := m.sessionClient.UpdateSessionMode(sessionID, string(models.SessionModeQuery), areaID)
	if err != nil {
		log.Printf("Failed to update session mode in session service: %v", err)
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
	go m.broadcastToSessionExcept(sessionID, ws, "mode_changed", models.ModeChange{
		PreviousMode: previousMode,
		NewMode:      string(models.SessionModeQuery),
		AreaID:       areaID,
	})

	// Send visual indicator to the terminal
	promptMsg := "\r\n\033[1;32m>>> Query Mode Activated <<<\033[0m\r\n"
	promptMsg += fmt.Sprintf("\033[1;34mKnowledge Area: %s\033[0m\r\n", areaID)
	promptMsg += "Type your questions directly, or press Ctrl+Alt+Q to exit query mode\r\n\r\n> "
	
	// Send the message to the client
	ws.WriteJSON(models.WebSocketMessage{
		Type: "terminal_output",
		Data: models.TerminalOutput{
			Data: promptMsg,
		},
	})
}

// disableQueryMode switches the terminal back to normal mode
func (m *SSHManager) disableQueryMode(sessionID string, ws *websocket.Conn, conn *models.SSHConnection) {
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
	err := m.sessionClient.UpdateSessionMode(sessionID, string(models.SessionModeNormal), "")
	if err != nil {
		log.Printf("Failed to update session mode in session service: %v", err)
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
	go m.broadcastToSessionExcept(sessionID, ws, "mode_changed", models.ModeChange{
		PreviousMode: previousMode,
		NewMode:      string(models.SessionModeNormal),
		AreaID:       activeAreaID,
	})

	// Send visual indicator to the terminal
	promptMsg := "\r\n\033[1;33m<<< Exited Query Mode >>>\033[0m\r\n"
	promptMsg += "Returned to normal terminal mode\r\n\r\n"
	
	// Send the message to the client
	ws.WriteJSON(models.WebSocketMessage{
		Type: "terminal_output",
		Data: models.TerminalOutput{
			Data: promptMsg,
		},
	})
}

// handleTerminalInput processes input from the terminal
func (m *SSHManager) handleTerminalInput(sessionID string, userID string, input string, conn *models.SSHConnection, ws *websocket.Conn) error {
	// Check for keyboard shortcut Ctrl+Alt+Q (this would be a more sophisticated detection in a real implementation)
	if isShortcutKey(input, "ctrl+alt+q") {
		// Handle shortcut to toggle query mode
		m.toggleQueryMode(sessionID, ws, conn)
		return nil
	}

	// Check if the session is in query mode
	conn.Lock.Lock()
	isInQueryMode := conn.IsInQueryMode
	activeAreaID := conn.ActiveAreaID
	conn.Lock.Unlock()

	if isInQueryMode {
		// In query mode, send input to RAG agent instead of terminal
		go m.handleRagQuery(sessionID, userID, input, activeAreaID, ws)
		return nil
	}

	// Normal mode - pass through to SSH
	_, err := conn.Stdin.Write([]byte(input))
	return err
}

// handleRagQuery processes a RAG query and sends the response back to the client
func (m *SSHManager) handleRagQuery(sessionID string, userID string, query string, areaID string, ws *websocket.Conn) {
	// Send a "thinking" indicator to the client
	ws.WriteJSON(models.WebSocketMessage{
		Type: "terminal_output",
		Data: models.TerminalOutput{
			Data: "\033[3m\033[90mProcessing query...\033[0m\r\n",
		},
	})

	// Get terminal context if needed
	terminalContext, err := m.getTerminalContext(sessionID)
	if err != nil {
		log.Printf("Failed to get terminal context: %v", err)
		// Continue without context
	}

	// Call the RAG Agent via the session client
	response, err := m.sessionClient.ProcessRagQuery(query, userID, areaID, terminalContext)
	if err != nil {
		log.Printf("Failed to process RAG query: %v", err)
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
	formattedResponse := "\r\n\033[1;36m" + response.Answer + "\033[0m\r\n"
	
	// Add sources if available
	if len(response.Sources) > 0 {
		formattedResponse += "\r\n\033[1;33mSources:\033[0m\r\n"
		for i, source := range response.Sources {
			formattedResponse += fmt.Sprintf("\033[1m%d.\033[0m %s\r\n", i+1, source.Title)
		}
	}
	
	formattedResponse += "\r\n> "

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
func (m *SSHManager) getTerminalContext(sessionID string) (map[string]interface{}, error) {
	// Get the session context from the session service
	context, err := m.sessionClient.GetSessionContext(sessionID)
	if err != nil {
		return nil, fmt.Errorf("failed to get session context: %w", err)
	}
	
	return context, nil
}