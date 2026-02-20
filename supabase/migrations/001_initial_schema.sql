-- Interview Portal Database Schema
-- Run this in your Supabase SQL editor

-- Enable necessary extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm"; -- For text search

-- ============================================
-- COMPANIES TABLE
-- ============================================
CREATE TABLE companies (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(200) NOT NULL,
    industry VARCHAR(100),
    company_size VARCHAR(50),
    website VARCHAR(500),
    description TEXT,
    logo_url VARCHAR(1000),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================
-- USERS TABLE (extends Supabase auth.users)
-- ============================================
CREATE TABLE users (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email VARCHAR(255) UNIQUE NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('admin', 'interviewer', 'candidate')),
    phone VARCHAR(20),
    timezone VARCHAR(50) DEFAULT 'UTC',
    avatar_url VARCHAR(1000),
    company_id UUID REFERENCES companies(id) ON DELETE SET NULL,
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'suspended')),
    email_verified BOOLEAN DEFAULT FALSE,
    last_login TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================
-- INTERVIEWER PROFILES
-- ============================================
CREATE TABLE interviewer_profiles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(100),
    bio TEXT,
    expertise_areas TEXT[], -- Array of expertise areas
    programming_languages TEXT[], -- Array of programming languages
    years_of_experience INTEGER,
    linkedin_url VARCHAR(500),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id)
);

-- ============================================
-- INTERVIEWER AVAILABILITY
-- ============================================
CREATE TABLE interviewer_availability (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    available_days TEXT[], -- ['monday', 'tuesday', ...]
    available_hours_start TIME DEFAULT '09:00',
    available_hours_end TIME DEFAULT '17:00',
    buffer_time_minutes INTEGER DEFAULT 15,
    max_interviews_per_day INTEGER DEFAULT 5,
    unavailable_dates DATE[], -- Array of unavailable dates
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id)
);

-- ============================================
-- CANDIDATES TABLE
-- ============================================
CREATE TABLE candidates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL, -- Link to user if they create an account
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    phone VARCHAR(20),
    position_applied VARCHAR(100) NOT NULL,
    resume_url VARCHAR(1000),
    linkedin_url VARCHAR(500),
    github_url VARCHAR(500),
    portfolio_url VARCHAR(500),
    current_company VARCHAR(200),
    years_of_experience INTEGER,
    location VARCHAR(200),
    skills TEXT[],
    education TEXT,
    status VARCHAR(50) DEFAULT 'applied' CHECK (status IN (
        'applied', 'screening', 'interview_scheduled', 'interviewing',
        'technical_round', 'final_round', 'offer_extended', 'hired',
        'rejected', 'withdrawn', 'talent_pool'
    )),
    source VARCHAR(50) DEFAULT 'direct',
    tags TEXT[],
    application_notes TEXT,
    internal_notes TEXT,
    applied_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_candidates_email ON candidates(email);
CREATE INDEX idx_candidates_company ON candidates(company_id);
CREATE INDEX idx_candidates_status ON candidates(status);

-- ============================================
-- INTERVIEWS TABLE
-- ============================================
CREATE TABLE interviews (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL,
    position VARCHAR(100) NOT NULL,
    interview_type VARCHAR(50) NOT NULL CHECK (interview_type IN (
        'phone_screen', 'technical', 'system_design', 'behavioral', 'hr', 'final', 'mixed'
    )),
    description TEXT,
    status VARCHAR(50) DEFAULT 'scheduled' CHECK (status IN (
        'scheduled', 'in_progress', 'completed', 'cancelled', 'rescheduled', 'no_show'
    )),
    duration_minutes INTEGER NOT NULL DEFAULT 60,
    scheduled_at TIMESTAMP WITH TIME ZONE NOT NULL,
    actual_start_time TIMESTAMP WITH TIME ZONE,
    actual_end_time TIMESTAMP WITH TIME ZONE,
    candidate_id UUID REFERENCES candidates(id) ON DELETE CASCADE,
    interviewer_id UUID REFERENCES users(id) ON DELETE SET NULL,
    round_number INTEGER DEFAULT 1,
    meeting_url VARCHAR(500) NOT NULL,
    room_id VARCHAR(100) UNIQUE NOT NULL,
    recording_enabled BOOLEAN DEFAULT TRUE,
    recording_url VARCHAR(1000),
    code_editor_enabled BOOLEAN DEFAULT FALSE,
    whiteboard_enabled BOOLEAN DEFAULT FALSE,
    programming_languages TEXT[],
    evaluation_criteria JSONB,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_interviews_candidate ON interviews(candidate_id);
CREATE INDEX idx_interviews_interviewer ON interviews(interviewer_id);
CREATE INDEX idx_interviews_scheduled_at ON interviews(scheduled_at);
CREATE INDEX idx_interviews_status ON interviews(status);
CREATE INDEX idx_interviews_company ON interviews(company_id);

-- ============================================
-- EVALUATIONS TABLE
-- ============================================
CREATE TABLE evaluations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    interview_id UUID REFERENCES interviews(id) ON DELETE CASCADE,
    evaluator_id UUID REFERENCES users(id) ON DELETE SET NULL,
    technical_skills INTEGER CHECK (technical_skills BETWEEN 1 AND 5),
    problem_solving INTEGER CHECK (problem_solving BETWEEN 1 AND 5),
    communication INTEGER CHECK (communication BETWEEN 1 AND 5),
    cultural_fit INTEGER CHECK (cultural_fit BETWEEN 1 AND 5),
    overall_rating INTEGER CHECK (overall_rating BETWEEN 1 AND 5),
    recommendation VARCHAR(50) CHECK (recommendation IN (
        'strong_hire', 'hire', 'maybe', 'no_hire', 'strong_no_hire'
    )),
    strengths TEXT,
    weaknesses TEXT,
    detailed_feedback TEXT,
    notes TEXT,
    custom_ratings JSONB,
    submitted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(interview_id, evaluator_id)
);

CREATE INDEX idx_evaluations_interview ON evaluations(interview_id);
CREATE INDEX idx_evaluations_evaluator ON evaluations(evaluator_id);

-- ============================================
-- CODE SNAPSHOTS TABLE
-- ============================================
CREATE TABLE code_snapshots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    interview_id UUID REFERENCES interviews(id) ON DELETE CASCADE,
    language VARCHAR(50) NOT NULL,
    code TEXT NOT NULL,
    author_id UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_code_snapshots_interview ON code_snapshots(interview_id);

-- ============================================
-- WHITEBOARD SNAPSHOTS TABLE
-- ============================================
CREATE TABLE whiteboard_snapshots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    interview_id UUID REFERENCES interviews(id) ON DELETE CASCADE,
    data JSONB NOT NULL,
    image_url VARCHAR(1000),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_whiteboard_snapshots_interview ON whiteboard_snapshots(interview_id);

-- ============================================
-- INTERVIEW RECORDINGS TABLE
-- ============================================
CREATE TABLE interview_recordings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    interview_id UUID REFERENCES interviews(id) ON DELETE CASCADE,
    status VARCHAR(50) DEFAULT 'recording' CHECK (status IN (
        'recording', 'processing', 'completed', 'failed'
    )),
    duration_seconds INTEGER,
    file_size_bytes BIGINT,
    video_url VARCHAR(1000),
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ended_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_recordings_interview ON interview_recordings(interview_id);

-- ============================================
-- NOTIFICATIONS TABLE
-- ============================================
CREATE TABLE notifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    notification_type VARCHAR(50) NOT NULL,
    title VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    data JSONB,
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_notifications_user ON notifications(user_id);
CREATE INDEX idx_notifications_read ON notifications(is_read);

-- ============================================
-- CANDIDATE NOTES TABLE
-- ============================================
CREATE TABLE candidate_notes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    candidate_id UUID REFERENCES candidates(id) ON DELETE CASCADE,
    author_id UUID REFERENCES users(id) ON DELETE SET NULL,
    content TEXT NOT NULL,
    is_internal BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_candidate_notes_candidate ON candidate_notes(candidate_id);

-- ============================================
-- RESCHEDULE REQUESTS TABLE
-- ============================================
CREATE TABLE reschedule_requests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    interview_id UUID REFERENCES interviews(id) ON DELETE CASCADE,
    requested_by UUID REFERENCES users(id) ON DELETE SET NULL,
    reason TEXT NOT NULL,
    proposed_times TIMESTAMP WITH TIME ZONE[] NOT NULL,
    status VARCHAR(50) DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    resolved_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_reschedule_requests_interview ON reschedule_requests(interview_id);

-- ============================================
-- EVALUATION TEMPLATES TABLE
-- ============================================
CREATE TABLE evaluation_templates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    criteria JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_evaluation_templates_company ON evaluation_templates(company_id);

-- ============================================
-- TRIGGERS FOR UPDATED_AT
-- ============================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_companies_updated_at BEFORE UPDATE ON companies
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_interviewer_profiles_updated_at BEFORE UPDATE ON interviewer_profiles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_candidates_updated_at BEFORE UPDATE ON candidates
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_interviews_updated_at BEFORE UPDATE ON interviews
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_evaluations_updated_at BEFORE UPDATE ON evaluations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- ROW LEVEL SECURITY (RLS) POLICIES
-- ============================================

-- Enable RLS on all tables
ALTER TABLE companies ENABLE ROW LEVEL SECURITY;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE interviewer_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE interviewer_availability ENABLE ROW LEVEL SECURITY;
ALTER TABLE candidates ENABLE ROW LEVEL SECURITY;
ALTER TABLE interviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE evaluations ENABLE ROW LEVEL SECURITY;
ALTER TABLE code_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE whiteboard_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE interview_recordings ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE candidate_notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE reschedule_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE evaluation_templates ENABLE ROW LEVEL SECURITY;

-- Note: RLS policies should be configured based on your specific requirements
-- These are examples and should be customized:

-- Users can read their own profile
CREATE POLICY "Users can view own profile" ON users
    FOR SELECT USING (auth.uid() = id);

-- Users can update their own profile
CREATE POLICY "Users can update own profile" ON users
    FOR UPDATE USING (auth.uid() = id);

-- Admin can view all users in their company
-- (Add more specific policies based on your needs)
