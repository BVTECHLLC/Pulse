-- REFERENCE ONLY. DO NOT RUN on the current Linode before inspecting existing schema.
-- PostgreSQL: additively define game-specific tables referencing the existing identity ID.
-- Replace the TEXT user_id with correct FK/type only after discovering the current auth schema.
CREATE TABLE IF NOT EXISTS gs_profiles (
  user_id TEXT PRIMARY KEY,
  account_xp BIGINT NOT NULL DEFAULT 0 CHECK (account_xp >= 0),
  coins BIGINT NOT NULL DEFAULT 0 CHECK (coins >= 0),
  souls BIGINT NOT NULL DEFAULT 0 CHECK (souls >= 0),
  selected_character VARCHAR(50) NOT NULL DEFAULT 'warden',
  selected_skin VARCHAR(50) NOT NULL DEFAULT 'default',
  selected_map VARCHAR(50) NOT NULL DEFAULT 'cemetery',
  version INTEGER NOT NULL DEFAULT 1,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS gs_upgrade_ranks (
  user_id TEXT NOT NULL REFERENCES gs_profiles(user_id) ON DELETE CASCADE,
  upgrade_id VARCHAR(50) NOT NULL,
  rank INTEGER NOT NULL DEFAULT 0 CHECK (rank BETWEEN 0 AND 10),
  PRIMARY KEY (user_id, upgrade_id)
);
CREATE TABLE IF NOT EXISTS gs_unlocks (
  user_id TEXT NOT NULL REFERENCES gs_profiles(user_id) ON DELETE CASCADE,
  unlock_type VARCHAR(30) NOT NULL,
  unlock_id VARCHAR(70) NOT NULL,
  unlocked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (user_id, unlock_type, unlock_id)
);
CREATE TABLE IF NOT EXISTS gs_sessions (
  id UUID PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES gs_profiles(user_id) ON DELETE CASCADE,
  seed BIGINT NOT NULL,
  game_version VARCHAR(50) NOT NULL,
  mode VARCHAR(50) NOT NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at TIMESTAMPTZ NOT NULL,
  finished_at TIMESTAMPTZ,
  status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK(status IN ('active','finished','expired','rejected')),
  validated_kills INTEGER,
  validated_xp BIGINT,
  validated_coins BIGINT,
  validated_souls BIGINT,
  validated_duration_ms BIGINT,
  CHECK (expires_at > started_at)
);
CREATE INDEX IF NOT EXISTS gs_sessions_user_started_idx ON gs_sessions(user_id,started_at DESC);
CREATE TABLE IF NOT EXISTS gs_achievements (
  user_id TEXT NOT NULL REFERENCES gs_profiles(user_id) ON DELETE CASCADE,
  achievement_id VARCHAR(50) NOT NULL,
  unlocked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (user_id, achievement_id)
);
CREATE TABLE IF NOT EXISTS gs_character_mastery (
  user_id TEXT NOT NULL REFERENCES gs_profiles(user_id) ON DELETE CASCADE,
  character_id VARCHAR(50) NOT NULL,
  xp BIGINT NOT NULL DEFAULT 0 CHECK(xp>=0),
  level INTEGER NOT NULL DEFAULT 1 CHECK(level>=1),
  equipped_skin VARCHAR(50) NOT NULL DEFAULT 'default',
  PRIMARY KEY (user_id, character_id)
);
-- Do not update balances without row lock / atomic transaction + validation.
-- Verify deterministic replay or signed server checkpoints before rewarding a finished run.
