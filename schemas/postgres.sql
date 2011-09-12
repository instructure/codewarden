create table tests (
  id serial not null primary key,
  problem_id integer not null,
  stdin text,
  stdout text,
  timelimit real);
create index tests_problem_id_idx on tests(problem_id);

create table problems (
  id serial not null primary key,
  hash varchar(80),
  ip varchar(80),
  name varchar(80),
  description text,
  deleted boolean,
  created_at bigint,
  user_id integer);
create index problems_hash_idx on problems(hash);

create table submissions (
  id serial not null primary key,
  problem_id integer not null,
  source text,
  ip varchar(80),
  language varchar(80),
  tests_passed integer,
  created_at bigint,
  user_id integer,
  errors text,
  runtime real);
create index submissions_problem_id_user_id_idx on submissions(problem_id, user_id);

create table users (
  id serial not null primary key,
  name varchar(80),
  email varchar(80),
  ip varchar(80),
  created_at bigint,
  openid_url varchar(4096),
  admin boolean);
create index users_openid_url_idx on users(openid_url);

create table announcements (
  id serial not null primary key,
  announcement text,
  created_at bigint,
  user_id integer);
create index announcements_created_at_idx on announcements(created_at);

create table session_data (
  id serial not null primary key,
  hash varchar(80),
  data text
);
create index session_data_hash_idx on session_data(hash);

CREATE TABLE oid_nonces (
    server_url VARCHAR(2047) NOT NULL,
    timestamp INTEGER NOT NULL,
    salt CHAR(40) NOT NULL,
    PRIMARY KEY (server_url, timestamp, salt)
);

CREATE TABLE oid_associations
(
    server_url VARCHAR(2047) NOT NULL,
    handle VARCHAR(255) NOT NULL,
    secret BYTEA NOT NULL,
    issued INTEGER NOT NULL,
    lifetime INTEGER NOT NULL,
    assoc_type VARCHAR(64) NOT NULL,
    PRIMARY KEY (server_url, handle),
    CONSTRAINT secret_length_constraint CHECK (LENGTH(secret) <= 128)
);
