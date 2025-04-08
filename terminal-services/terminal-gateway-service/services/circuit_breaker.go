package services

import (
	"errors"
	"fmt"
	"sync"
	"time"
)

// CircuitState represents the state of a circuit breaker
type CircuitState int

const (
	// StateClose represents a closed circuit (allowing calls)
	StateClosed CircuitState = iota
	// StateOpen represents an open circuit (blocking calls)
	StateOpen
	// StateHalfOpen represents a half-open circuit (allowing a test call)
	StateHalfOpen
)

// CircuitBreaker implements the circuit breaker pattern
type CircuitBreaker struct {
	name           string
	state          CircuitState
	failureCount   int
	lastFailureTime time.Time
	mutex          sync.RWMutex
	timeout        time.Duration
	failureThreshold int
	successThreshold int
	currentSuccess   int
}

// CircuitBreakerOption is a function that configures a CircuitBreaker
type CircuitBreakerOption func(*CircuitBreaker)

// WithTimeout sets the timeout duration for the circuit breaker
func WithTimeout(timeout time.Duration) CircuitBreakerOption {
	return func(cb *CircuitBreaker) {
		cb.timeout = timeout
	}
}

// WithFailureThreshold sets the failure threshold for the circuit breaker
func WithFailureThreshold(threshold int) CircuitBreakerOption {
	return func(cb *CircuitBreaker) {
		cb.failureThreshold = threshold
	}
}

// WithSuccessThreshold sets the success threshold for the circuit breaker
func WithSuccessThreshold(threshold int) CircuitBreakerOption {
	return func(cb *CircuitBreaker) {
		cb.successThreshold = threshold
	}
}

// NewCircuitBreaker creates a new circuit breaker
func NewCircuitBreaker(name string, opts ...CircuitBreakerOption) *CircuitBreaker {
	cb := &CircuitBreaker{
		name:             name,
		state:            StateClosed,
		failureCount:     0,
		lastFailureTime:  time.Time{},
		timeout:          5 * time.Second,
		failureThreshold: 3,
		successThreshold: 2,
		currentSuccess:   0,
	}

	// Apply options
	for _, opt := range opts {
		opt(cb)
	}

	return cb
}

// Execute executes the given function within the circuit breaker pattern
func (cb *CircuitBreaker) Execute(fn func() (interface{}, error)) (interface{}, error) {
	// Get state with lock and check timeout together to avoid race conditions
	cb.mutex.Lock()
	
	// Check if circuit is open and if timeout has elapsed
	currentState := cb.state
	if currentState == StateOpen {
		elapsed := time.Since(cb.lastFailureTime)
		if elapsed > cb.timeout {
			// Transition to half-open state
			cb.state = StateHalfOpen
			currentState = StateHalfOpen
		}
	}
	
	// Release lock after getting state and possibly updating it
	cb.mutex.Unlock()
	
	// Handle open circuit
	if currentState == StateOpen {
		return nil, ErrCircuitOpen
	}

	// Execute the function
	result, err := fn()

	// Handle the result
	if err != nil {
		cb.handleFailure()
		return nil, err
	}

	cb.handleSuccess()
	return result, nil
}

// handleFailure updates the circuit breaker state after a failure
func (cb *CircuitBreaker) handleFailure() {
	cb.mutex.Lock()
	defer cb.mutex.Unlock()

	cb.failureCount++
	cb.lastFailureTime = time.Now()
	cb.currentSuccess = 0

	// Check if we need to open the circuit
	if (cb.state == StateClosed && cb.failureCount >= cb.failureThreshold) ||
		cb.state == StateHalfOpen {
		cb.state = StateOpen
	}
}

// handleSuccess updates the circuit breaker state after a success
func (cb *CircuitBreaker) handleSuccess() {
	cb.mutex.Lock()
	defer cb.mutex.Unlock()

	// Reset failure count
	cb.failureCount = 0

	// If we're in half-open state, increment success count
	if cb.state == StateHalfOpen {
		cb.currentSuccess++
		if cb.currentSuccess >= cb.successThreshold {
			cb.state = StateClosed
			cb.currentSuccess = 0
		}
	}
}

// IsOpen returns true if the circuit breaker is in the open state
func (cb *CircuitBreaker) IsOpen() bool {
	cb.mutex.RLock()
	defer cb.mutex.RUnlock()
	return cb.state == StateOpen
}

// ForceClose forces the circuit breaker to close
func (cb *CircuitBreaker) ForceClose() {
	cb.mutex.Lock()
	defer cb.mutex.Unlock()
	cb.state = StateClosed
	cb.failureCount = 0
	cb.currentSuccess = 0
}

// ForceOpen forces the circuit breaker to open
func (cb *CircuitBreaker) ForceOpen() {
	cb.mutex.Lock()
	defer cb.mutex.Unlock()
	cb.state = StateOpen
	cb.lastFailureTime = time.Now()
}

// ErrCircuitOpen is returned when a circuit breaker is open
var ErrCircuitOpen = errors.New("circuit breaker is open")