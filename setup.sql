USE `fedibooks`;
CREATE TABLE IF NOT EXISTS `users` (
  `id` BINARY(64) PRIMARY KEY,
  `email` VARCHAR(128) UNIQUE NOT NULL,
  `password` BINARY(60) NOT NULL
);
CREATE TABLE IF NOT EXISTS `contact_settings` (
  FOREIGN KEY (`user_id`) REFERENCES users(id) ON DELETE CASCADE,
  `fetch` ENUM('always', 'once', 'never') DEFAULT 'once',
  `submit` ENUM('always', 'once', 'never') DEFAULT 'once',
  `generation` ENUM('always', 'once', 'never') DEFAULT 'once',
  `reply` ENUM('always', 'once', 'never') DEFAULT 'once'
);
CREATE TABLE IF NOT EXISTS `bots` (
  `id` BINARY(64) PRIMARY KEY,
  FOREIGN KEY (`user_id`) REFERENCES users(id) ON DELETE CASCADE,
  `enabled` BOOLEAN DEFAULT 1,
  `replies_enabled` BOOLEAN DEFAULT 1,
  `post_frequency` SMALLINT UNSIGNED DEFAULT 30,
  `content_warning` VARCHAR(128),
  `length` SMALLINT UNSIGNED DEFAULT 500,
  `fake_mentions` ENUM('always', 'start', 'never') DEFAULT 'start',
  `fake_mentions_full` BOOLEAN DEFAULT 0,
  `post_privacy` ENUM('public', 'unlisted', 'followers_only') DEFAULT 'unlisted',
  `learn_from_cw` BOOLEAN DEFAULT 0,
  `last_post` DATETIME DEFAULT 0,
  `icon` VARCHAR(512),
  `icon_update_time` DATETIME DEFAULT 0,
  FOREIGN KEY (`credentials_id`) REFERENCES credentials(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS `credentials` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `client_id` VARCHAR(128) NOT NULL,
  `client_secret` VARCHAR(128) NOT NULL,
  `secret` VARCHAR(128) NOT NULL
);
CREATE TABLE IF NOT EXISTS `fedi_account` (
  `handle` VARCHAR(128) NOT NULL PRIMARY KEY,
  `outbox` VARCHAR(256),
  `icon` VARCHAR(512),
  `icon_update_time` DATETIME DEFAULT 0,
  FOREIGN KEY (`credentials_id`) REFERENCES credentials(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS `posts` (
  `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
  `post_id` VARCHAR(64) NOT NULL,
  `content` TEXT NOT NULL,
  `cw` BOOLEAN NOT NULL
);
CREATE TABLE IF NOT EXISTS `word_blacklist` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  FOREIGN KEY (`bot_id`) REFERENCES bots(id) ON DELETE CASCADE,
  `phrase` VARCHAR(128) NOT NULL,
  `whole_word` BOOLEAN NOT NULL
);
CREATE TABLE IF NOT EXISTS `contact_history` (
  FOREIGN KEY (`user_id`) REFERENCES users(id) ON DELETE CASCADE,
  `fetch` BOOLEAN DEFAULT 0,
  `submit` BOOLEAN DEFAULT 0,
  `generation` BOOLEAN DEFAULT 0,
  `reply` BOOLEAN DEFAULT 0
);
