-- AI Customer Service System Database Initialization Script
-- MySQL 8.0 compatible
-- Execute: mysql -u root -p < init_db.sql

CREATE DATABASE IF NOT EXISTS ai_customer_service
DEFAULT CHARACTER SET utf8mb4
DEFAULT COLLATE utf8mb4_unicode_ci;

USE ai_customer_service;

-- ============================================
-- Table users
-- User accounts with phone/email login support
-- ============================================
CREATE TABLE IF NOT EXISTS users (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    phone VARCHAR(20) NULL,
    email VARCHAR(255) NULL,
    password_hash VARCHAR(255) NOT NULL,
    salt VARCHAR(64) NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE KEY uk_phone (phone),
    UNIQUE KEY uk_email (email),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='User accounts table';

-- ============================================
-- Table sessions
-- Chat sessions for multi-turn conversations
-- ============================================
CREATE TABLE IF NOT EXISTS sessions (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(255) NOT NULL DEFAULT '新对话',
    intent_tag VARCHAR(50) NULL COMMENT='Intent classification: product_consult/after_sale/chat/complaint',
    msg_count INT UNSIGNED DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user_updated (user_id, updated_at DESC),
    INDEX idx_intent (intent_tag)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Chat sessions table';

-- ============================================
-- Table messages
-- Individual messages in conversations
-- ============================================
CREATE TABLE IF NOT EXISTS messages (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    session_id BIGINT UNSIGNED NOT NULL,
    role ENUM('user', 'assistant') NOT NULL,
    content TEXT NOT NULL,
    intent VARCHAR(50) NULL COMMENT='Message intent classification',
    token_in INT UNSIGNED DEFAULT 0 COMMENT='Input tokens for LLM',
    token_out INT UNSIGNED DEFAULT 0 COMMENT='Output tokens from LLM',
    latency_ms INT UNSIGNED DEFAULT 0 COMMENT='LLM response latency in milliseconds',
    finish_reason VARCHAR(50) NULL COMMENT='stop/length/no_context/error',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    INDEX idx_session_created (session_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Chat messages table';

-- ============================================
-- Table message_citations
-- Source references for AI-generated answers
-- ============================================
CREATE TABLE IF NOT EXISTS message_citations (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    message_id BIGINT UNSIGNED NOT NULL,
    doc_id BIGINT UNSIGNED NOT NULL,
    chunk_id VARCHAR(100) NOT NULL,
    score DECIMAL(5,4) NOT NULL COMMENT='Similarity score 0-1',
    snippet TEXT NOT NULL COMMENT='Cited content snippet',
    
    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE,
    INDEX idx_message (message_id),
    INDEX idx_doc (doc_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Message citation sources table';

-- ============================================
-- Table kb_documents
-- Knowledge base documents metadata
-- ============================================
CREATE TABLE IF NOT EXISTS kb_documents (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    kb_id VARCHAR(50) NOT NULL DEFAULT 'default' COMMENT='Knowledge base ID for multi-kb support',
    name VARCHAR(255) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    file_type ENUM('txt', 'md', 'pdf') NOT NULL,
    size BIGINT UNSIGNED NOT NULL COMMENT='File size in bytes',
    char_count INT UNSIGNED DEFAULT 0,
    chunk_count INT UNSIGNED DEFAULT 0,
    status ENUM('processing', 'ready', 'failed', 'deleting') NOT NULL DEFAULT 'processing',
    error_msg TEXT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_kb_status (kb_id, status),
    INDEX idx_created (created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Knowledge base documents table';

-- ============================================
-- Table kb_chunks
-- Text chunks with vector mapping
-- ============================================
CREATE TABLE IF NOT EXISTS kb_chunks (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    doc_id BIGINT UNSIGNED NOT NULL,
    chunk_index INT UNSIGNED NOT NULL,
    content TEXT NOT NULL,
    char_count INT UNSIGNED NOT NULL,
    vector_id VARCHAR(100) NOT NULL COMMENT='Chroma vector ID',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (doc_id) REFERENCES kb_documents(id) ON DELETE CASCADE,
    UNIQUE KEY uk_vector (vector_id),
    INDEX idx_doc_chunk (doc_id, chunk_index)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Knowledge base text chunks table';

-- ============================================
-- Table feedbacks
-- User feedback on AI responses
-- ============================================
CREATE TABLE IF NOT EXISTS feedbacks (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    message_id BIGINT UNSIGNED NOT NULL,
    user_id BIGINT UNSIGNED NOT NULL,
    rating TINYINT NOT NULL COMMENT='1 for thumbs up, -1 for thumbs down',
    comment TEXT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE KEY uk_message_user (message_id, user_id),
    INDEX idx_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='User feedback table';

-- ============================================
-- Table usage_quota
-- Daily usage quota tracking
-- ============================================
CREATE TABLE IF NOT EXISTS usage_quota (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    date DATE NOT NULL,
    ask_count INT UNSIGNED DEFAULT 0,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE KEY uk_user_date (user_id, date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Daily usage quota tracking table';

-- ============================================
-- Initial seed data (optional)
-- ============================================

-- Insert a test user (password: test123 - hashed with bcrypt)
-- In production, use proper password hashing
INSERT INTO users (phone, email, password_hash, salt) VALUES
('13800138000', 'test@example.com', '$2b$12$placeholder_hash', 'placeholder_salt')
ON DUPLICATE KEY UPDATE phone=phone;
