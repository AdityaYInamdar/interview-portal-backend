-- Migration: Add join tracking timestamps to interviews table
-- These columns record the first time each party enters the interview room.

ALTER TABLE interviews
  ADD COLUMN IF NOT EXISTS interviewer_joined_at TIMESTAMP WITH TIME ZONE,
  ADD COLUMN IF NOT EXISTS candidate_joined_at   TIMESTAMP WITH TIME ZONE;

COMMENT ON COLUMN interviews.interviewer_joined_at IS 'Timestamp of the first time the interviewer/admin joined the live room';
COMMENT ON COLUMN interviews.candidate_joined_at   IS 'Timestamp of the first time the candidate joined the live room';
