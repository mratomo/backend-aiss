package utils

import (
	"log"
	"runtime"
	"runtime/debug"
	"sync"
	"sync/atomic"
	"time"
)

// MemorySafeguard helps manage memory usage in the application
type MemorySafeguard struct {
	// Channels for memory clean up events
	cleanupRequest       chan struct{}
	cleanupDone          chan struct{}
	stopped              atomic.Bool
	memoryCheckInterval  time.Duration
	memoryThresholdRatio float64
	totalAllocLimit      uint64
	maxBufferSize        int64
	statsLock            sync.RWMutex
	bytesProcessed       int64
	lastCleanupTime      time.Time

	// Buffer pool para optimizar el uso de memoria
	bufferPool sync.Pool
}

// NewMemorySafeguard creates a new memory safeguard
func NewMemorySafeguard() *MemorySafeguard {
	ms := &MemorySafeguard{
		cleanupRequest:       make(chan struct{}, 1),
		cleanupDone:          make(chan struct{}, 1),
		memoryCheckInterval:  30 * time.Second,
		memoryThresholdRatio: 0.75,     // 75% of total available memory
		totalAllocLimit:      1 << 30,  // 1GB default limit
		maxBufferSize:        50 << 20, // 50MB default buffer limit
		lastCleanupTime:      time.Now(),
	}

	// Inicializar el pool de buffers
	// Usar un tamaño inicial común para comandos de terminal (4KB)
	const initialBufferSize = 4 * 1024
	ms.bufferPool = sync.Pool{
		New: func() interface{} {
			buffer := make([]byte, 0, initialBufferSize)
			return &buffer
		},
	}

	return ms
}

// Start starts the memory safeguard
func (ms *MemorySafeguard) Start() {
	ms.stopped.Store(false)
	go ms.monitorMemory()
}

// Stop stops the memory safeguard
func (ms *MemorySafeguard) Stop() {
	if ms.stopped.CompareAndSwap(false, true) {
		// Signal cleanup one last time and wait for completion
		ms.cleanupRequest <- struct{}{}
		<-ms.cleanupDone

		// Close channels
		close(ms.cleanupRequest)
		close(ms.cleanupDone)
	}
}

// RequestCleanup requests a memory cleanup
func (ms *MemorySafeguard) RequestCleanup() {
	// Non-blocking send to avoid deadlocks
	select {
	case ms.cleanupRequest <- struct{}{}:
		// Request sent successfully
	default:
		// Channel is full, a cleanup is already scheduled
	}
}

// monitorMemory periodically checks and manages memory usage
func (ms *MemorySafeguard) monitorMemory() {
	ticker := time.NewTicker(ms.memoryCheckInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ms.cleanupRequest:
			// Cleanup request received
			if ms.stopped.Load() {
				return
			}
			ms.performCleanup()
			ms.cleanupDone <- struct{}{}

		case <-ticker.C:
			// Regular interval check
			if ms.stopped.Load() {
				return
			}

			if ms.shouldCleanup() {
				ms.performCleanup()
			}
		}
	}
}

// shouldCleanup checks if a memory cleanup is needed
func (ms *MemorySafeguard) shouldCleanup() bool {
	var memStats runtime.MemStats
	runtime.ReadMemStats(&memStats)

	// Check if we've exceeded our memory threshold
	if float64(memStats.Alloc) > float64(ms.totalAllocLimit)*ms.memoryThresholdRatio {
		return true
	}

	// Check if we should periodically clean up anyway
	ms.statsLock.RLock()
	timeSinceLastCleanup := time.Since(ms.lastCleanupTime)
	bytesProcessed := ms.bytesProcessed
	ms.statsLock.RUnlock()

	// If we've processed a lot of data or it's been a while since last cleanup
	return bytesProcessed > ms.maxBufferSize || timeSinceLastCleanup > 5*time.Minute
}

// performCleanup performs memory cleanup
func (ms *MemorySafeguard) performCleanup() {
	// Get pre-cleanup stats
	var memStatsBefore runtime.MemStats
	runtime.ReadMemStats(&memStatsBefore)

	// Run garbage collection
	debug.FreeOSMemory()

	// Get post-cleanup stats
	var memStatsAfter runtime.MemStats
	runtime.ReadMemStats(&memStatsAfter)

	// Reset counters
	ms.statsLock.Lock()
	ms.bytesProcessed = 0
	ms.lastCleanupTime = time.Now()
	ms.statsLock.Unlock()

	// Log cleanup results
	freedBytes := int64(memStatsBefore.Alloc - memStatsAfter.Alloc)
	if freedBytes > 0 {
		log.Printf("Memory cleanup completed: freed %d bytes, current usage: %d bytes",
			freedBytes, memStatsAfter.Alloc)
	}
}

// AddBytesProcessed adds the number of bytes processed to the counter
func (ms *MemorySafeguard) AddBytesProcessed(bytes int64) {
	if bytes <= 0 {
		return
	}

	ms.statsLock.Lock()
	ms.bytesProcessed += bytes
	ms.statsLock.Unlock()

	// Check if we need to request a cleanup
	if ms.bytesProcessed > ms.maxBufferSize {
		ms.RequestCleanup()
	}
}

// GetBuffer obtiene un buffer del pool para reutilización
func (ms *MemorySafeguard) GetBuffer() *[]byte {
	return ms.bufferPool.Get().(*[]byte)
}

// ReturnBuffer devuelve un buffer al pool cuando ya no se necesita
func (ms *MemorySafeguard) ReturnBuffer(buffer *[]byte) {
	// Resetear el buffer para reutilización
	*buffer = (*buffer)[:0]
	ms.bufferPool.Put(buffer)
}

// SetMaxBufferSize sets the maximum buffer size before cleanup
func (ms *MemorySafeguard) SetMaxBufferSize(maxBytes int64) {
	if maxBytes > 0 {
		ms.maxBufferSize = maxBytes
	}
}

// GlobalMemorySafeguard is the global memory safeguard instance
var GlobalMemorySafeguard = NewMemorySafeguard()

func init() {
	// Start the global memory safeguard
	GlobalMemorySafeguard.Start()
}
