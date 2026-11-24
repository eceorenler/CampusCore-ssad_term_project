-- Runs once when the PostgreSQL container is first created.
-- A separate database for pytest, so tests never wipe the development data.
CREATE DATABASE campuscore_test OWNER campuscore;
