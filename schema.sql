PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS tracks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    difficulty TEXT NOT NULL CHECK (difficulty IN ('beginner', 'intermediate', 'advanced')),
    typical_duration_weeks INTEGER NOT NULL CHECK (typical_duration_weeks BETWEEN 1 AND 104),
    minimum_education TEXT NOT NULL CHECK (
        minimum_education IN ('any', 'secondary', 'diploma', 'undergraduate', 'postgraduate')
    ),
    recommended_hours_per_week INTEGER NOT NULL CHECK (recommended_hours_per_week BETWEEN 1 AND 60),
    goal_fit_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS track_skills (
    track_id TEXT NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    skill TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('skill', 'prerequisite', 'keyword')),
    PRIMARY KEY (track_id, skill, category)
);

CREATE TABLE IF NOT EXISTS recommendations (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    profile_json TEXT NOT NULL,
    recommended_track_id TEXT NOT NULL REFERENCES tracks(id),
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0.0 AND 1.0),
    source TEXT NOT NULL CHECK (source IN ('llm', 'fallback')),
    model_name TEXT,
    prompt_version TEXT NOT NULL,
    latency_ms INTEGER NOT NULL CHECK (latency_ms >= 0)
);

CREATE TABLE IF NOT EXISTS feedback (
    id TEXT PRIMARY KEY,
    recommendation_id TEXT NOT NULL REFERENCES recommendations(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    rating INTEGER NOT NULL CHECK (rating IN (-1, 1)),
    consent INTEGER NOT NULL CHECK (consent = 1)
);

CREATE TABLE IF NOT EXISTS rate_limits (
    bucket_type TEXT NOT NULL CHECK (bucket_type IN ('session', 'ip', 'daily')),
    bucket_key TEXT NOT NULL,
    window_start TEXT NOT NULL,
    request_count INTEGER NOT NULL CHECK (request_count > 0),
    PRIMARY KEY (bucket_type, bucket_key)
);

CREATE INDEX IF NOT EXISTS idx_recommendations_created_at
    ON recommendations(created_at);
CREATE INDEX IF NOT EXISTS idx_recommendations_input_hash
    ON recommendations(input_hash);
