create table if not exists tests (
  id integer primary key asc,
  problem_id integer,
  stdin blob,
  stdout blob,
  timelimit real);
create index tests_problem_id_idx on tests (problem_id);

create table if not exists problems (
  id integer primary key asc,
  hash text,
  ip text,
  name text,
  description text,
  deleted,
  created_at integer,
  user_id integer);
create index problems_hash_idx on problems(hash);

create table if not exists submissions (
  id integer primary key asc,
  problem_id integer,
  source blob,
  ip text,
  language text,
  tests_passed integer,
  created_at integer,
  user_id integer,
  errors text,
  runtime real);
create index submissions_problem_id_user_id_idx on submissions(problem_id, user_id);

create table if not exists users (
  id integer primary key asc,
  name text,
  email text,
  ip text,
  created_at integer,
  openid_url blob,
  admin);
create index users_openid_url_idx on users(openid_url);

create table announcements (
  id integer primary key asc,
  announcement text,
  created_at integer,
  user_id integer);
create index announcements_created_at_idx on announcements(created_at);

create table session_data (
  id integer primary key asc,
  hash text,
  data blob
);
create index session_data_hash_idx on session_data(hash);

CREATE TABLE oid_nonces (
    server_url VARCHAR,
    timestamp INTEGER,
    salt CHAR(40),
    UNIQUE(server_url, timestamp, salt)
);

CREATE TABLE oid_associations
(
    server_url VARCHAR(2047),
    handle VARCHAR(255),
    secret BLOB(128),
    issued INTEGER,
    lifetime INTEGER,
    assoc_type VARCHAR(64),
    PRIMARY KEY (server_url, handle)
);
