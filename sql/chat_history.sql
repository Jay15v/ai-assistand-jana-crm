-- Chat history log tables. Created by hand (DBeaver) in the CRM database; the app never runs
-- this file, it only inserts rows (app/features/conversation/repositories/history.py).
-- The schema name is spelled ai_assisstant on purpose: it matches the existing schema.
-- The tests run this same file against a throwaway local database.

CREATE TABLE ai_assisstant.chat_sessions (
    user_id          text        NOT NULL,
    session_id       text        NOT NULL,
    user_name        text,
    started_at       timestamptz NOT NULL DEFAULT now(),
    last_message_at  timestamptz NOT NULL DEFAULT now(),
    turn_count       integer     NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, session_id)
);

CREATE TABLE ai_assisstant.chat_messages (
    id                   bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id              text        NOT NULL,
    session_id           text        NOT NULL,
    turn_no              integer     NOT NULL,
    user_message         text        NOT NULL,
    standalone_question  text,
    answer               text        NOT NULL,
    scope                text        NOT NULL
        CHECK (scope IN ('allowed', 'partial', 'not_allowed', 'off_topic', 'error')),
    scope_reason         text,
    ui_lang              text        NOT NULL CHECK (ui_lang IN ('en', 'ar')),
    latency_ms           integer,
    created_at           timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (user_id, session_id)
        REFERENCES ai_assisstant.chat_sessions (user_id, session_id),
    UNIQUE (user_id, session_id, turn_no)
);

CREATE INDEX chat_messages_created_at_idx ON ai_assisstant.chat_messages (created_at);
