#!/usr/bin/env python
#
# Copyright (C) 2011 Instructure, Inc.
#
# This file is part of CodeWarden.
#
# CodeWarden is free software: you can redistribute it and/or modify it under
# the terms of the GNU Affero General Public License as published by the Free
# Software Foundation, version 3 of the License.
#
# CodeWarden is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE. See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along
# with this program. If not, see <http://www.gnu.org/licenses/>.
#

import web, re, hashlib, time, ConfigParser, os, json, calendar
from lib.straitjacket_client import StraitJacketClient
from lib.webopenid import OpenIDWrapper
from collections import defaultdict

__author__ = "JT Olds"
__copyright__ = "Copyright 2011 Instructure, Inc."
__license__ = "AGPLv3"
__email__ = "jt@instructure.com"

ANNOUNCEMENT_LIMIT = 1
ANNOUNCEMENT_EXPIRY = 30
STATIC_FILE_EXPIRY = 900
CONFIG_PATH = "server.conf"
config = ConfigParser.SafeConfigParser()
config.readfp(file(CONFIG_PATH))

STDOUT_MATCH = re.compile(r'^stdout_([0-9]+)$')
def timestamp(): return calendar.timegm(time.gmtime())
def gen_new_hash(id_):
  return hashlib.sha1("%d-%d" % (id_, timestamp())).hexdigest()

web.config.debug = False
static_files_cache = {}
announcements_cache = {"expiration": 0}

def webapp(skip_language_checks=False):
  sj_client = StraitJacketClient(config.get("straitjacket", "base_url"))
  render = web.template.render("templates/")

  database_config = dict(config.items("database"))
  general_config = dict(config.items("general"))
  db = web.database(**database_config)
  oid = OpenIDWrapper(db, database_config)
  theme = web.template.render("themes/%s/templates/" %
      general_config.get("theme", "default"))

  def get_test_counts(problem_id, user_id):
    completed_cases = db.query("select max(tests_passed) as max from "
        "submissions where problem_id=$problem_id and user_id=$user_id",
        vars={"problem_id": problem_id, "user_id": user_id}).list()[0].max
    if not completed_cases: completed_cases = 0
    test_cases = db.query("select count(*) as count from tests where "
        "problem_id = $id", vars={"id": problem_id}).list()[0].count
    return completed_cases, test_cases

  class BaseHandler(object):
    def get_user(self):
      if hasattr(self, "user"): return
      if not hasattr(self, "openid_url"):
        self.openid_url = oid.identity()
        if not self.openid_url: raise web.seeother("/settings")
      t = db.transaction()
      try:
        rows = list(db.select("users", where="users.openid_url=$x",
            vars={"x": self.openid_url}, limit=1))
        if rows:
          self.user_id = rows[0].id
          self.user = rows[0]
          self.super_user = rows[0].admin
        elif self.openid_url:
          name, email, created_at = oid.name(), oid.email(), timestamp()
          self.user_id = db.insert("users", openid_url=self.openid_url,
              ip=web.ctx.ip, created_at=created_at, name=name, email=email)
          self.user = web.storage(id=self.user_id, name=name, email=email,
              ip=web.ctx.ip, created_at=created_at, openid_url=self.openid_url)
          self.super_user = None
        else:
          self.user_id = None
          self.user = None
          self.super_user = None
      except:
        t.rollback()
        raise
      t.commit()
    def wrapper(self, body):
      self.get_user()
      web.header('Content-Type', 'text/html')
      total_test_cases = 0
      total_completed_cases = 0
      for problem in db.select("problems", where="deleted is null"):
        completed_cases, test_cases = get_test_counts(problem.id, self.user_id)
        total_completed_cases += completed_cases
        total_test_cases += test_cases
      return theme.main(total_test_cases, total_completed_cases, self.user,
          body, web.ctx.path, self.super_user, general_config.get("app_title",
          "unconfigured_title"))

  class Announcements(BaseHandler):
    def GET(self, is_json):
      if is_json:
        web.header('Content-Type', 'text/json')
        since = long(web.input(since="0").since)
        now = timestamp()
        if announcements_cache["expiration"] < now:
          announcements_cache["announcements"] = [
              {"announcement": x.announcement,
               "created_at": x.created_at,
               "id": x.id} for x in db.select("announcements",
                                              order="created_at desc",
                                              limit=ANNOUNCEMENT_LIMIT)]
          announcements_cache["expiration"] = now + ANNOUNCEMENT_EXPIRY
        return json.dumps([x for x in announcements_cache["announcements"]
                             if x["created_at"] > since])
      self.get_user()
      if not self.super_user: return web.seeother("/")
      return self.wrapper(render.announcements())
    def POST(self, is_json):
      if not is_json:
        self.get_user()
        if not self.super_user: return web.seeother("/")
        f = web.input("announcement")
        db.insert("announcements", created_at=timestamp(),
            announcement=f.announcement, user_id = self.user_id)
        announcements_cache["expiration"] = 0
      return self.GET(is_json)

  class Settings(BaseHandler):
    def GET(self):
      self.openid_url = oid.identity()
      self.get_user()
      return self.wrapper(render.settings(oid.form('/openid', '/'), self.user))
    def POST(self):
      self.openid_url = oid.identity()
      if not self.openid_url: raise web.seeother("/settings")
      f = web.input(email=(oid.email() or ""), name=(oid.name() or ""))
      db.update("users", where="openid_url=$url", name=f.name, email=f.email,
          vars={"url": self.openid_url})
      return self.GET()

  class Index(BaseHandler):
    def GET(self):
      return self.wrapper(theme.index(general_config.get("app_title",
          "unconfigured_title")))

  class Redirect(BaseHandler):
    def GET(self):
      return web.seeother("/")

  class Help(BaseHandler):
    def GET(self):
      enabled_languages = sj_client.enabled_languages()
      languages = [enabled_languages[lang]
          for lang in sorted(enabled_languages)]
      return self.wrapper(render.help(languages, general_config.get(
          "contact_email", "unconfigured_contact_email")))

  class Problems(BaseHandler):
    def GET(self):
      self.get_user()
      problems = db.select("problems", where="deleted is null").list()
      test_case_counts = {}
      completed_case_counts = {}
      for problem in problems:
        completed_cases, test_cases = get_test_counts(problem.id, self.user_id)
        test_case_counts[problem.id] = test_cases
        completed_case_counts[problem.id] = completed_cases
      problems.sort(lambda x, y: cmp(
          (completed_case_counts[x.id] - test_case_counts[x.id], x.name),
          (completed_case_counts[y.id] - test_case_counts[y.id], y.name)))
      return self.wrapper(render.problems(problems, test_case_counts,
          completed_case_counts, self.super_user))

  class NewProblem(BaseHandler):
    def GET(self):
      self.get_user()
      if self.super_user: return self.wrapper(render.new_problem())
      return web.seeother("/problems")

    def POST(self):
      self.get_user()
      if not self.super_user: return web.seeother("/problems")
      f = web.input()
      tests = []
      for key in f.keys():
        match = STDOUT_MATCH.search(key)
        if not match: continue
        test = int(match.group(1))
        if len(f["stdout_%d" % test]) == 0: continue
        if len(f["stdin_%d" % test]) == 0: continue
        tests.append(test)
      if not tests: return web.badrequest()
      problem_id = db.insert("problems", ip=web.ctx.ip, name=f.name,
          description=f.description, created_at=timestamp(),
          user_id=self.user_id)
      hash = gen_new_hash(problem_id)
      db.update("problems", where="id=$id", hash=hash, vars={"id": problem_id})
      for test in tests:
        timelimit = None
        if len(f["timelimit_%d" % test]) > 0:
          try: timelimit = float(f["timelimit_%d" % test])
          except: pass
        db.insert("tests", problem_id=problem_id,
            stdin=f["stdin_%d" % test], stdout=f["stdout_%d" % test],
            timelimit=timelimit)
      return web.seeother("/problems/show/%s" % hash)

  class DeleteProblem(BaseHandler):
    def POST(self, hash):
      self.get_user()
      if not self.super_user: return web.seeother("/")
      db.update("problems", where="hash=$hash", deleted=True,
          vars={"hash": hash})
      return web.seeother("/problems")

  class ShowProblem(BaseHandler):
    def check_problem(self, hash):
      problems = db.select("problems", where="hash=$hash",
          vars={"hash": hash}, limit=1).list()
      if not problems: raise web.seeother("/problems")
      return problems[0]

    def GET(self, hash):
      self.get_user()
      return self.render(hash)

    def POST(self, hash):
      self.get_user()
      problem = self.check_problem(hash)
      tests = db.select("tests", where="problem_id=$id",
          vars={"id": problem.id}).list()
      f = web.input()
      try: f.source.decode('utf8')
      except: raise web.notacceptable('please submit code encoded in utf8')
      successful_tests = 0
      total_runtime = 0
      error_counts = defaultdict(lambda: 0)
      for test in tests:
        stdout, stderr, exitstatus, runtime, error = sj_client.run(f.language,
            f.source, test.stdin, custom_timelimit=test.timelimit)
        total_runtime += runtime
        if error:
          error_counts[error] += 1
        elif stdout == str(test.stdout):
          successful_tests += 1
        else:
          error_counts["wrong_answer"] += 1
      if len(error_counts) == 1:
        error_counts = error_counts.keys()[0]
      else:
        error_counts = ", ".join("%d %s" % (x[1], x[0]) for x in sorted(
            error_counts.iteritems()))
      db.insert("submissions", problem_id=problem.id, source=f.source,
          ip=web.ctx.ip, language=f.language, tests_passed=successful_tests,
          created_at=timestamp(), user_id=self.user_id, errors=error_counts,
          runtime=total_runtime)
      return self.render(hash, "%d/%d tests passed in %0.2f seconds.%s" % (
          successful_tests, len(tests), total_runtime,
          error_counts and " Errors: %s" % error_counts or ""), problem)

    def render(self, hash, flash=None, problem=None):
      if not problem: problem = self.check_problem(hash)

      stats = db.query("select avg(max_tests_passed) as tests_passed, "
          "count(*) as attempts from ("
            "select user_id, max(tests_passed) as max_tests_passed "
            "from submissions where problem_id=$id group by user_id"
          ") as t", vars={"id": problem.id}).list()[0]

      enabled_languages = sj_client.enabled_languages()
      languages = [[lang, enabled_languages[lang]]
          for lang in sorted(enabled_languages)]

      tests = db.select("tests", where="problem_id=$id",
          vars={"id": problem.id}).list()
      return self.wrapper(render.problem(problem, tests, languages,
          stats.tests_passed, stats.attempts, flash))

  class Users(BaseHandler):
    def GET(self):
      self.get_user()
      if not self.super_user: return web.seeother("/")
      problems = db.select("problems", where="deleted is null").list()
      users = db.select("users").list()
      user_submissions = {}
      user_score = {}
      test_counts = {}
      for problem in problems:
        test_counts[problem.id] = db.query("select count(*) as count from "
            "tests where problem_id = $id;", vars={"id": problem.id}).list()[0]\
            .count
      for user in users:
        user_score[user.id] = 0
        for problem in problems:
          submissions = db.select("submissions",
              where="problem_id = $id and user_id = $user_id",
              vars={"id": problem.id, "user_id": user.id},
              order="created_at desc").list()
          if submissions:
            user_submissions[(user.id, problem.id)] = submissions
            max_score = max((s.tests_passed for s in submissions))
            user_score[user.id] += max_score
      users.sort(lambda x, y: cmp(user_score[y.id], user_score[x.id]))
      return self.wrapper(render.users(users, problems, user_submissions,
          user_score, time, test_counts))

  class Submission(BaseHandler):
    def GET(self, submission_id):
      submission_id = int(submission_id)
      self.get_user()
      if not self.super_user: return web.seeother("/")
      submissions = db.select("submissions", where="id=$id",
          vars={"id": submission_id}, limit=1).list()
      if not submissions: return web.seeother("/users")
      return self.wrapper(render.submission(submissions[0]))

  safe_filename = re.compile(r'^\w(\w|\.)*$')
  class StaticFiles(object):
    def GET(self, path):
      now = timestamp()
      if not static_files_cache.has_key(path) or \
          static_files_cache[path]["expiration"] < now:

        if not safe_filename.match(path):
          raise web.notfound()

        mime_type = "application/octet-stream"
        if path[-4:] == ".css":
          mime_type = "text/css"
        elif path[-3:] == ".js":
          mime_type = "text/javascript"

        static_files_cache[path] = {"mime": mime_type,
                            "content": file("themes/%s/static/%s" %
                            (general_config.get("theme", "default"), path)
                            ).read(), "expiration": now + STATIC_FILE_EXPIRY}

      web.header('Content-Type', static_files_cache[path]["mime"])
      return static_files_cache[path]["content"]

  OpenID = oid.generate_handler()

  app = web.application((
      '/', 'Index',
      '/announcements(|.json)', 'Announcements',
      '/settings', 'Settings',
      '/help', 'Help',
      '/problems', 'Problems',
      '/problems/new', 'NewProblem',
      '/problems/delete/([a-f0-9]+)', 'DeleteProblem',
      '/problems/show/([a-f0-9]+)', 'ShowProblem',
      '/users', 'Users',
      '/submissions/([0-9]+)', 'Submission',
      '/theme/(.*)', 'StaticFiles',
      '/openid', 'OpenID',
      '.*', 'Redirect'
    ), locals(), autoreload=False)

  return app

if __name__ == "__main__": webapp().run()
