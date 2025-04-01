package utils

import (
	"fmt"
	"io"
	"log"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"time"
)

// LogLevel represents the severity of a log message
type LogLevel int

const (
	// DEBUG level for detailed troubleshooting
	DEBUG LogLevel = iota
	// INFO level for informational messages
	INFO
	// WARN level for warning conditions
	WARN
	// ERROR level for error conditions
	ERROR
	// FATAL level for critical errors that cause program termination
	FATAL
)

// String returns the string representation of the log level
func (l LogLevel) String() string {
	switch l {
	case DEBUG:
		return "DEBUG"
	case INFO:
		return "INFO"
	case WARN:
		return "WARN"
	case ERROR:
		return "ERROR"
	case FATAL:
		return "FATAL"
	default:
		return "UNKNOWN"
	}
}

// Color returns the ANSI color code for the log level
func (l LogLevel) Color() string {
	switch l {
	case DEBUG:
		return "\033[36m" // Cyan
	case INFO:
		return "\033[32m" // Green
	case WARN:
		return "\033[33m" // Yellow
	case ERROR:
		return "\033[31m" // Red
	case FATAL:
		return "\033[35m" // Magenta
	default:
		return "\033[0m" // Default
	}
}

// Logger provides structured logging capabilities
type Logger struct {
	level     LogLevel
	writer    io.Writer
	prefix    string
	mu        sync.Mutex
	formatter LogFormatter
}

// LogFormatter formats log entries
type LogFormatter interface {
	Format(level LogLevel, prefix, file, msg string, args ...interface{}) string
}

// DefaultFormatter implements a default log formatter
type DefaultFormatter struct {
	colored   bool
	showTime  bool
	timeFormat string
}

// Format formats the log entry according to the default format
func (f *DefaultFormatter) Format(level LogLevel, prefix, file, msg string, args ...interface{}) string {
	// Apply argument formatting if needed
	formattedMsg := msg
	if len(args) > 0 {
		formattedMsg = fmt.Sprintf(msg, args...)
	}

	var timeStr string
	if f.showTime {
		timeStr = time.Now().Format(f.timeFormat) + " "
	}

	if f.colored {
		reset := "\033[0m"
		return fmt.Sprintf("%s%s%s [%s%s%s] [%s] %s", 
			timeStr, level.Color(), level.String(), reset, prefix, level.Color(), file, formattedMsg) + reset
	}

	return fmt.Sprintf("%s%s [%s] [%s] %s", 
		timeStr, level.String(), prefix, file, formattedMsg)
}

// NewLogger creates a new logger
func NewLogger(prefix string, level LogLevel) *Logger {
	// Check if we should use color output
	colored := true
	
	// Disable colors when not in a terminal
	fileInfo, _ := os.Stdout.Stat()
	if (fileInfo.Mode() & os.ModeCharDevice) == 0 {
		colored = false
	}
	
	return &Logger{
		level:  level,
		writer: os.Stdout,
		prefix: prefix,
		formatter: &DefaultFormatter{
			colored:    colored,
			showTime:   true,
			timeFormat: "2006-01-02 15:04:05",
		},
	}
}

// SetLevel sets the logging level
func (l *Logger) SetLevel(level LogLevel) {
	l.mu.Lock()
	defer l.mu.Unlock()
	l.level = level
}

// SetOutput sets the output destination
func (l *Logger) SetOutput(w io.Writer) {
	l.mu.Lock()
	defer l.mu.Unlock()
	l.writer = w
}

// SetFormatter sets the log formatter
func (l *Logger) SetFormatter(formatter LogFormatter) {
	l.mu.Lock()
	defer l.mu.Unlock()
	l.formatter = formatter
}

// log logs a message with the specified level
func (l *Logger) log(level LogLevel, msg string, args ...interface{}) {
	if level < l.level {
		return
	}

	l.mu.Lock()
	defer l.mu.Unlock()

	// Get file and line information
	_, file, line, ok := runtime.Caller(2)
	fileInfo := "???"
	if ok {
		file = filepath.Base(file)
		fileInfo = fmt.Sprintf("%s:%d", file, line)
	}

	// Format the log entry
	logEntry := l.formatter.Format(level, l.prefix, fileInfo, msg, args...)
	fmt.Fprintln(l.writer, logEntry)

	// If level is FATAL, terminate the program
	if level == FATAL {
		os.Exit(1)
	}
}

// Debug logs a debug message
func (l *Logger) Debug(msg string, args ...interface{}) {
	l.log(DEBUG, msg, args...)
}

// Info logs an info message
func (l *Logger) Info(msg string, args ...interface{}) {
	l.log(INFO, msg, args...)
}

// Warn logs a warning message
func (l *Logger) Warn(msg string, args ...interface{}) {
	l.log(WARN, msg, args...)
}

// Error logs an error message
func (l *Logger) Error(msg string, args ...interface{}) {
	l.log(ERROR, msg, args...)
}

// Fatal logs a fatal message and terminates the program
func (l *Logger) Fatal(msg string, args ...interface{}) {
	l.log(FATAL, msg, args...)
}

// Global logger variables
var (
	DefaultLogger *Logger
	LoggerMap     = map[string]*Logger{}
	loggerMu      sync.Mutex
)

// GetLogger returns a logger with the specified name
func GetLogger(name string) *Logger {
	loggerMu.Lock()
	defer loggerMu.Unlock()

	if logger, ok := LoggerMap[name]; ok {
		return logger
	}

	// Get the log level from environment variable
	logLevel := getLogLevelFromEnv()

	// Create a new logger
	logger := NewLogger(name, logLevel)
	LoggerMap[name] = logger

	return logger
}

// getLogLevelFromEnv gets the log level from the environment variable
func getLogLevelFromEnv() LogLevel {
	logLevelStr := strings.ToUpper(os.Getenv("LOG_LEVEL"))
	switch logLevelStr {
	case "DEBUG":
		return DEBUG
	case "INFO":
		return INFO
	case "WARN":
		return WARN
	case "ERROR":
		return ERROR
	case "FATAL":
		return FATAL
	default:
		return INFO // Default to INFO
	}
}

// Configure standard logger to use our custom logger
func init() {
	// Create the default logger
	DefaultLogger = NewLogger("DEFAULT", getLogLevelFromEnv())

	// Configure the standard log package to use our logger
	log.SetFlags(0)
	log.SetOutput(&logAdapter{DefaultLogger})
}

// logAdapter adapts our logger to the io.Writer interface
type logAdapter struct {
	logger *Logger
}

// Write implements io.Writer for log adapter
func (a *logAdapter) Write(p []byte) (n int, err error) {
	msg := strings.TrimSuffix(string(p), "\n")
	a.logger.Info(msg)
	return len(p), nil
}