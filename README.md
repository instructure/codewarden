CodeWarden 0.1
=====

This web application is a simple online coding competition framework.
It was initially used for Instructure's Mebipenny 2011 coding competition.

Installation
=====

This application is a standard web.py WSGI-capable web app. A sample Apache
configuration is provided in files/etc/apache2/sites-available.

This application relies on a separate web application called StraitJacket to
do all the hard work. Please see https://github.com/instructure/straitjacket
for more info.

Be sure to take a look at server.conf to configure your database connection and
StraitJacket setup appropriately.

You will probably need to use one of the files in the schema subdirectory to
initialize your database for the first run.

Last, make sure to generate a file called ".openid_secret_key" filled with some
random data.

License
=====

CodeWarden is released under the AGPLv3. Please see COPYRIGHT and LICENSE.
