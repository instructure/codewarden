"""
Starting-to-look-heavily-modified version of web.py's open id consumer library.
Now supports attribute exchange and database-backed storage

web.py and this file are in the public domain.

- JT Olds (jt@instructure.com)
"""

import os
import binascii
import random
import hmac
import web
import cPickle
import openid.consumer.consumer
import openid.store.sqlstore
import psycopg2
import sqlite3
from openid.extensions import ax, sreg

class OpenIDWrapper(object):

  def __init__(self, db, database_config, secret):
    self.db = db
    self.database_config = database_config
    self.secret = secret

  def _get_openid_store(self):
    if self.database_config["dbn"] == "postgres":
      return openid.store.sqlstore.PostgreSQLStore(self.db.ctx["db"])
    elif self.database_config["dbn"] == "sqlite":
      return openid.store.sqlstore.SQLiteStore(self.db.ctx["db"])
    raise Exception, "unsupported database adapter"

  def _random_data(self): return os.urandom(20)

  def _new_session(self, initial_data):
    hash = None
    retry_count = 0
    while True:
      hash = binascii.hexlify(self._random_data())
      t = self.db.transaction()
      try:
        count = self.db.query("select count(*) as count from session_data "
            "where hash=$hash", vars={"hash": hash}).list()[0].count
        if count > 0: continue
        self.db.insert("session_data", hash=hash,
            data=cPickle.dumps(initial_data))
        count = self.db.query("select count(*) as count from session_data "
            "where hash=$hash", vars={"hash": hash}).list()[0].count
        if count > 1: raise "found dup"
      except:
        t.rollback()
        retry_count += 1
        if retry_count >= 20:
          raise
      else:
        t.commit()
        break
    return hash

  def _load_session(self, hash):
    return cPickle.loads(str(self.db.select("session_data", where="hash=$hash",
        vars={"hash": hash}).list()[0].data))

  def _save_session(self, hash, data):
    self.db.update("session_data", data=cPickle.dumps(data), where="hash=$hash",
        vars={"hash": hash})

  def _del_session(self, hash):
    self.db.delete("session_data", where="hash=$hash", vars={"hash": hash})

  def _hmac(self, thing):
    return hmac.new(self.secret, thing).hexdigest()

  def _get_field_from_cookies(self, field):
    oid_hash = web.cookies().get('openid_%s' % field, '').split(',', 1)
    if len(oid_hash) > 1 and oid_hash[0] == self._hmac(oid_hash[1]):
      return oid_hash[1]
    return None

  def _set_field_in_cookies(self, field, val):
    web.setcookie('openid_%s' % field, self._hmac(val) + ',' + val)

  def identity(self): return self._get_field_from_cookies('identity_hash')
  def logged_in(self): return self.identity()
  def name(self): return self._get_field_from_cookies('name')
  def email(self): return self._get_field_from_cookies('email')
  def display_name(self):
    name, email = self.name(), self.email()
    if name and email: return "%s (%s)" % (name, email)
    elif name or email: return name or email
    return self.identity()

  def form(self, openid_loc, return_to):
    oid = self.identity()
    if oid:
      return '''
      <form method="post" action="%s">
        <img src="http://openid.net/login-bg.gif" alt="OpenID" />
        <strong>%s</strong>
        <input type="hidden" name="action" value="logout" />
        <input type="hidden" name="return_to" value="%s" />
        <button type="submit" class="btn">log out</button>
      </form>''' % (openid_loc, self.display_name(), return_to)
    else:
      return '''
      <form method="post" action="%(action)s">
        <input type="hidden" name="openid"
            value="https://www.google.com/accounts/o8/id"/>
        <input type="hidden" name="return_to" value="%(return_to)s" />
        <dl><dt>You can either:</dt><dd>
        <button type="submit" class="btn">log in with Google</button>
        </dd></dl>
      </form>
      <form method="post" action="%(action)s">
        <dl><dt>or with <a href="http://openid.net/get-an-openid/">OpenID</a>:
        </dt><dd>
        <input type="text" name="openid" value=""
          style="background: url(http://openid.net/login-bg.gif) no-repeat;
          padding-left: 18px; background-position: 0 50%%;" />
        <input type="hidden" name="return_to" value="%(return_to)s" />
        <button type="submit" class="btn">log in</button>
        </dd></dl>
      </form>''' % {"action": openid_loc, "return_to": return_to}

  def logout(self):
    for field in ['identity_hash', 'name', 'email']:
      web.setcookie('openid_%s' % field, '', expires=-1)

  def generate_handler(oid):
    class host:
      def POST(self):
        # unlike the usual scheme of things, the POST is actually called
        # first here
        i = web.input(return_to='/')
        if i.get('action') == 'logout':
          oid.logout()
          return web.redirect(i.return_to)

        if not i.has_key('openid') or len(i.openid) == 0:
          return web.redirect(i.return_to)

        session_data = {'webpy_return_to': i.return_to}
        session_hash = oid._new_session(session_data)

        ax_req = ax.FetchRequest()
        ax_req.add(ax.AttrInfo('http://axschema.org/namePerson/first',
            required=True))
        ax_req.add(ax.AttrInfo('http://axschema.org/namePerson/last',
            required=True))
        ax_req.add(ax.AttrInfo('http://axschema.org/contact/email',
            required=True))

        c = openid.consumer.consumer.Consumer(session_data,
            oid._get_openid_store())
        a = c.begin(i.openid)
        a.addExtension(ax_req)
        a.addExtension(sreg.SRegRequest(optional=['email', 'fullname']))
        f = a.redirectURL(web.ctx.home, web.ctx.home + web.ctx.fullpath)

        oid._save_session(session_hash, session_data)

        web.setcookie('openid_session_id', session_hash)
        return web.redirect(f)

      def GET(self):
        session_hash = web.cookies('openid_session_id').openid_session_id
        web.setcookie('openid_session_id', '', expires=-1)
        session_data = oid._load_session(session_hash)
        return_to = session_data['webpy_return_to']

        c = openid.consumer.consumer.Consumer(session_data,
            oid._get_openid_store())
        a = c.complete(web.input(), web.ctx.home + web.ctx.fullpath)

        attributes = {}
        try:
          sreg_response = sreg.SRegResponse.fromSuccessResponse(a)
          if sreg_response:
            attributes['name'] = sreg_response.get('fullname')
            attributes['email'] = sreg_response.get('email')
            attributes['schema'] = 'sreg'
        except: pass

        try:
          ax_response = ax.FetchResponse.fromSuccessResponse(a)
          if ax_response:
            attributes['name'] = ax_response.get(
                'http://axschema.org/namePerson/first')[0] + " " + \
                ax_response.get('http://axschema.org/namePerson/last')[0]
            attributes['email'] = ax_response.get(
                'http://axschema.org/contact/email')[0]
            attributes['schema'] = 'ax'
        except: pass

        if a.status.lower() == 'success':
          oid._set_field_in_cookies('identity_hash', a.identity_url)
          if attributes.has_key('schema'):
            for field in ['name', 'email']:
              if attributes.has_key(field):
                oid._set_field_in_cookies(field, attributes[field])

        oid._del_session(session_hash)
        return web.redirect(return_to)
    return host
