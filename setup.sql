USE `fedibooks`;
CREATE TABLE IF NOT EXISTS `users` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `email` VARCHAR(128) UNIQUE NOT NULL,
  `password` BINARY(60) NOT NULL,
  `email_verified` BOOLEAN DEFAULT 0,
  `fetch` ENUM('always', 'once', 'never') DEFAULT 'once',
  `submit` ENUM('always', 'once', 'never') DEFAULT 'once',
  `generation` ENUM('always', 'once', 'never') DEFAULT 'once',
  `reply` ENUM('always', 'once', 'never') DEFAULT 'once'
) ENGINE=INNODB;
CREATE TABLE IF NOT EXISTS `credentials` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `client_id` VARCHAR(128) NOT NULL,
  `client_secret` VARCHAR(128) NOT NULL,
  `secret` VARCHAR(128) NOT NULL
) ENGINE=INNODB;
CREATE TABLE IF NOT EXISTS `bots` (
  `handle` VARCHAR(128) PRIMARY KEY,
  `user_id` INT NOT NULL,
  `credentials_id` INT NOT NULL,
  `push_private_key` BINARY(128) NOT NULL,
  `push_public_key` BINARY(128) NOT NULL,
  `push_secret` BINARY(16),
  `instance_type` VARCHAR(64) NOT NULL DEFAULT 'Mastodon',
  `enabled` BOOLEAN DEFAULT 0,
  `replies_enabled` BOOLEAN DEFAULT 1,
  `post_frequency` SMALLINT UNSIGNED DEFAULT 30,
  `content_warning` VARCHAR(128),
  `length` SMALLINT UNSIGNED DEFAULT 500,
  `fake_mentions` ENUM('always', 'middle', 'never') DEFAULT 'middle',
  `fake_mentions_full` BOOLEAN DEFAULT 0,
  `post_privacy` ENUM('public', 'unlisted', 'private') DEFAULT 'unlisted',
  `learn_from_cw` BOOLEAN DEFAULT 0,
  `last_post` DATETIME DEFAULT CURRENT_TIMESTAMP(),
  `icon` VARCHAR(512),
  `icon_update_time` DATETIME DEFAULT '1000-01-01 00:00:00',
  FOREIGN KEY (`user_id`) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (`credentials_id`) REFERENCES credentials(id) ON DELETE CASCADE
) ENGINE=INNODB;
CREATE TABLE IF NOT EXISTS `fedi_accounts` (
  `handle` VARCHAR(128) PRIMARY KEY,
  `outbox` VARCHAR(256),
  `credentials_id` INT,
  `icon` VARCHAR(512),
  `icon_update_time` DATETIME DEFAULT 0,
  FOREIGN KEY (`credentials_id`) REFERENCES credentials(id) ON DELETE CASCADE
) ENGINE=INNODB;
CREATE TABLE IF NOT EXISTS `bot_learned_accounts` (
  `bot_id` VARCHAR(128) NOT NULL,
  `fedi_id` VARCHAR(128) NOT NULL,
  `enabled` BOOLEAN DEFAULT 1,
  FOREIGN KEY (`bot_id`) REFERENCES bots(handle) ON DELETE CASCADE,
  FOREIGN KEY (`fedi_id`) REFERENCES fedi_accounts(handle) ON DELETE CASCADE
) ENGINE=INNODB;
CREATE TABLE IF NOT EXISTS `posts` (
  `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
  `fedi_id` VARCHAR(128),
  `post_id` VARCHAR(64) NOT NULL,
  `content` TEXT NOT NULL,
  `cw` BOOLEAN NOT NULL,
  FOREIGN KEY (`fedi_id`) REFERENCES fedi_accounts(handle) ON DELETE CASCADE
) ENGINE=INNODB;
CREATE TABLE IF NOT EXISTS `word_blacklist` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `bot_id` VARCHAR(128) NOT NULL,
  `phrase` VARCHAR(128) NOT NULL,
  `whole_word` BOOLEAN NOT NULL,
  FOREIGN KEY (`bot_id`) REFERENCES bots(handle) ON DELETE CASCADE
) ENGINE=INNODB;
CREATE TABLE IF NOT EXISTS `contact_history` (
  `user_id` INT NOT NULL,
  `fetch` BOOLEAN DEFAULT 0,
  `submit` BOOLEAN DEFAULT 0,
  `generation` BOOLEAN DEFAULT 0,
  `reply` BOOLEAN DEFAULT 0,
  FOREIGN KEY (`user_id`) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=INNODB;
