CREATE TABLE verification_challenges (
    id INT NOT NULL AUTO_INCREMENT,
    discord_id BIGINT UNSIGNED NOT NULL,
    discord_name VARCHAR(50) NOT NULL,
    player_tag VARCHAR(16) NOT NULL,
    player_name VARCHAR(50) NOT NULL,
    challenge_code VARCHAR(32) NOT NULL,
    status ENUM('pending', 'approved', 'cancelled', 'expired') NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    reviewed_by_discord_id BIGINT UNSIGNED DEFAULT NULL,
    reviewed_at TIMESTAMP NULL DEFAULT NULL,
    PRIMARY KEY (id),
    KEY discord_id (discord_id),
    KEY player_tag (player_tag),
    KEY status (status),
    KEY expires_at (expires_at)
);
