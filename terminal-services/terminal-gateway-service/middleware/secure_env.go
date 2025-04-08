package middleware

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"encoding/base64"
	"fmt"
	"io"
	"os"
	"sync"
)

// secretKey is a global variable that holds the encryption key
var (
	secretKey []byte
	keyOnce   sync.Once
)

// initSecretKey initializes the secret key for encryption
func initSecretKey() {
	keyOnce.Do(func() {
		// Get encryption key from environment
		envKey := os.Getenv("ENCRYPTION_KEY")
		if envKey == "" {
			// In production, we should fail securely
			if os.Getenv("ENV") == "production" {
				panic("ENCRYPTION_KEY environment variable is required in production")
			}

			// For development only, generate a secure random key
			fmt.Println("WARNING: ENCRYPTION_KEY not set in environment. Generating a secure random key.")
			fmt.Println("This key will change on service restart. For persistent encryption, set ENCRYPTION_KEY.")

			// Generate a secure random key
			newKey := make([]byte, 32)
			if _, err := io.ReadFull(rand.Reader, newKey); err != nil {
				panic(fmt.Sprintf("failed to generate random key: %v", err))
			}

			encodedKey := base64.StdEncoding.EncodeToString(newKey)
			fmt.Println("Generated key (add to your environment): ", encodedKey)
			envKey = encodedKey
		}

		// Decode the key
		var err error
		secretKey, err = base64.StdEncoding.DecodeString(envKey)
		if err != nil || len(secretKey) != 32 {
			// If the key is invalid, fail rather than use an insecure key
			panic(fmt.Sprintf("Invalid ENCRYPTION_KEY: must be a 32-byte key encoded as base64. Current length: %d", len(secretKey)))
		}
	})
}

// EncryptSensitive encrypts sensitive data like passwords and credentials
func EncryptSensitive(plaintext string) (string, error) {
	initSecretKey()

	// Create a new AES cipher using the key
	block, err := aes.NewCipher(secretKey)
	if err != nil {
		return "", err
	}

	// Create a new GCM
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return "", err
	}

	// Create a nonce
	nonce := make([]byte, gcm.NonceSize())
	if _, err = io.ReadFull(rand.Reader, nonce); err != nil {
		return "", err
	}

	// Encrypt the data
	ciphertext := gcm.Seal(nonce, nonce, []byte(plaintext), nil)

	// Return base64 encoded string
	return base64.StdEncoding.EncodeToString(ciphertext), nil
}

// DecryptSensitive decrypts sensitive data like passwords and credentials
func DecryptSensitive(encrypted string) (string, error) {
	initSecretKey()

	// Decode from base64
	ciphertext, err := base64.StdEncoding.DecodeString(encrypted)
	if err != nil {
		return "", err
	}

	// Create a new AES cipher using the key
	block, err := aes.NewCipher(secretKey)
	if err != nil {
		return "", err
	}

	// Create a new GCM
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return "", err
	}

	// Check valid ciphertext length
	if len(ciphertext) < gcm.NonceSize() {
		return "", fmt.Errorf("ciphertext too short")
	}

	// Get the nonce and ciphertext
	nonce, ciphertext := ciphertext[:gcm.NonceSize()], ciphertext[gcm.NonceSize():]

	// Decrypt the data
	plaintext, err := gcm.Open(nil, nonce, ciphertext, nil)
	if err != nil {
		return "", err
	}

	return string(plaintext), nil
}

// CreateEncryptionKey generates a new encryption key and prints it
func CreateEncryptionKey() string {
	key := make([]byte, 32)
	if _, err := io.ReadFull(rand.Reader, key); err != nil {
		panic(fmt.Sprintf("failed to generate random key: %v", err))
	}

	encodedKey := base64.StdEncoding.EncodeToString(key)
	return encodedKey
}
