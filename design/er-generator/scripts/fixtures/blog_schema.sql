CREATE TABLE users (
  id UUID PRIMARY KEY,
  email VARCHAR(255) NOT NULL,
  role TEXT NOT NULL
);

CREATE TABLE posts (
  id UUID PRIMARY KEY,
  title VARCHAR(200) NOT NULL,
  author_id UUID NOT NULL REFERENCES users(id),
  CONSTRAINT chk_posts_something CHECK (title <> '')
);

CREATE TABLE weird_table (
  id UUID PRIMARY KEY,
  some_custom_type CUSTOMTYPE NOT NULL
);
