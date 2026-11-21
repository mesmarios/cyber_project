-- Student Auctions (CSE423)
-- Shared MariaDB schema: all 4 branches must use these same tables.
-- MariaDB 11.4 / InnoDB / utf8mb4. All application dates use UTC.
-- The database 'student_auctions' is created by Docker Compose.

SET time_zone = '+00:00';

-- 1) Approved (fictional) student directory.
CREATE TABLE IF NOT EXISTS students (
    student_id       VARCHAR(12)  NOT NULL,
    full_name        VARCHAR(120) NOT NULL,
    university_email VARCHAR(160) NOT NULL,
    is_active        BOOLEAN      NOT NULL DEFAULT TRUE,

    PRIMARY KEY (student_id),
    UNIQUE KEY uq_students_email (university_email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2) Website accounts. One student can register at most once.
CREATE TABLE IF NOT EXISTS users (
    id            BIGINT       NOT NULL AUTO_INCREMENT,
    student_id    VARCHAR(12)  NOT NULL,
    username      VARCHAR(50)  NOT NULL,
    email         VARCHAR(160) NOT NULL,
    password_hash TEXT         NOT NULL,
    role          VARCHAR(10)  NOT NULL DEFAULT 'user',
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    UNIQUE KEY uq_users_student_id (student_id),
    UNIQUE KEY uq_users_username (username),
    UNIQUE KEY uq_users_email (email),
    CONSTRAINT fk_users_student
        FOREIGN KEY (student_id) REFERENCES students(student_id),
    CONSTRAINT chk_users_role CHECK (role IN ('user', 'admin'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3) One current delivery address per user (user_id is both PK and FK).
CREATE TABLE IF NOT EXISTS addresses (
    user_id     BIGINT       NOT NULL,
    line1       VARCHAR(180) NOT NULL,
    city        VARCHAR(80)  NOT NULL,
    postal_code VARCHAR(20)  NOT NULL,
    updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
    ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (user_id),
    CONSTRAINT fk_addresses_user
        FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4) Auction listings. B owns listing fields; C owns status/winner fields.
CREATE TABLE IF NOT EXISTS auctions (
    id              BIGINT        NOT NULL AUTO_INCREMENT,
    seller_id       BIGINT        NOT NULL,
    winner_user_id  BIGINT        NULL,
    title           VARCHAR(120)  NOT NULL,
    description     TEXT          NOT NULL,
    starting_price  DECIMAL(10,2) NOT NULL,
    is_public       BOOLEAN       NOT NULL DEFAULT TRUE,
    status          VARCHAR(10)   NOT NULL DEFAULT 'open',
    ends_at         DATETIME      NOT NULL,
    created_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    KEY idx_auctions_seller (seller_id),
    KEY idx_auctions_winner (winner_user_id),
    CONSTRAINT fk_auctions_seller
        FOREIGN KEY (seller_id) REFERENCES users(id),
    CONSTRAINT fk_auctions_winner
        FOREIGN KEY (winner_user_id) REFERENCES users(id),
    CONSTRAINT chk_auctions_status CHECK (status IN ('open', 'closed')),
    CONSTRAINT chk_auctions_price CHECK (starting_price >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5) Bids. Multiple bids from the same student are allowed.
CREATE TABLE IF NOT EXISTS bids (
    id         BIGINT        NOT NULL AUTO_INCREMENT,
    auction_id BIGINT        NOT NULL,
    bidder_id  BIGINT        NOT NULL,
    amount     DECIMAL(10,2) NOT NULL,
    created_at DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    KEY idx_bids_auction (auction_id),
    KEY idx_bids_bidder (bidder_id),
    CONSTRAINT fk_bids_auction
        FOREIGN KEY (auction_id) REFERENCES auctions(id),
    CONSTRAINT fk_bids_bidder
        FOREIGN KEY (bidder_id) REFERENCES users(id),
    CONSTRAINT chk_bids_amount CHECK (amount > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
