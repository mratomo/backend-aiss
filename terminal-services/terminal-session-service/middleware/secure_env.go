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
			// If not set, generate a warning and create a temporary key
			// This should never happen in production - always set ENCRYPTION_KEY environment variable
			fmt.Println("WARNING: ENCRYPTION_KEY not set in environment. Using insecure default key.")
			fmt.Println("Set ENCRYPTION_KEY to a 32-byte hex string for secure encryption.")
			envKey = "0000000000000000000000000000000000000000000000000000000000000000"
		}

		// Decode the key
		var err error
		secretKey, err = base64.StdEncoding.DecodeString(envKey)
		if err != nil || len(secretKey) != 32 {
			// If the key is invalid, generate a new one
			secretKey = make([]byte, 32)
			if _, err := io.ReadFull(rand.Reader, secretKey); err != nil {
				panic(fmt.Sprintf("failed to generate random key: %v", err))
			}
			fmt.Println("WARNING: Invalid ENCRYPTION_KEY format. Generated a temporary key.")
			fmt.Println("New key (use this in your environment): ", base64.StdEncoding.EncodeToString(secretKey))
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