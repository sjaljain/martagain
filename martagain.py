import os
import re
import random
import hashlib
import hmac
import logging
import json
import urllib
import cgi
from string import letters

import webapp2
import jinja2
import facebook

from google.appengine.ext import db
from google.appengine.api import images
from google.appengine.api.datastore import Query, Put

FACEBOOK_APP_ID = "1398507617030667"
FACEBOOK_APP_SECRET = "c5e18e6dfcf8920428c5bca868f2d8bb"

template_dir = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = jinja2.Environment(loader = jinja2.FileSystemLoader(template_dir),
                               autoescape = True)

secret = 'fart'


def make_secure_val(val):
    return '%s|%s' % (val, hmac.new(secret, val).hexdigest())

def check_secure_val(secure_val):
    val = secure_val.split('|')[0]
    if secure_val == make_secure_val(val):
        return val

def render_str(template, **params):
    t = jinja_env.get_template(template)
    return t.render(params)

class BlogHandler(webapp2.RequestHandler):
    def write(self, *a, **kw):
        self.response.out.write(*a, **kw)

    def render_str(self, template, **params):
        params['user'] = self.user
        t = jinja_env.get_template(template)
        return t.render(params)

    def render(self, template, **kw):
        self.write(self.render_str(template, **kw))

    def render_json(self, d):
        json_txt = json.dumps(d)
        self.response.headers['Content-Type'] = 'application/json; charset=UTF-8'
        self.write(json_txt)

    def set_secure_cookie(self, name, val):
        cookie_val = make_secure_val(val)
        self.response.headers.add_header(
            'Set-Cookie',
            '%s=%s; Path=/' % (name, cookie_val))

    def read_secure_cookie(self, name):
        cookie_val = self.request.cookies.get(name)
        return cookie_val and check_secure_val(cookie_val)

    def login(self, user):
        self.set_secure_cookie('user_id', str(user.key().id()))

    def logout(self):
        self.response.headers.add_header('Set-Cookie', 'user_id=; Path=/')

    def initialize(self, *a, **kw):
        webapp2.RequestHandler.initialize(self, *a, **kw)
        uid = self.read_secure_cookie('user_id')
        self.user = uid
        

        if self.request.url.endswith('.json'):
            self.format = 'json'
        else:
            self.format = 'html'


class MainPage(BlogHandler):
  def get(self):
      self.redirect('/')


##### user stuff
def users_key(group = 'default'):
    return db.Key.from_path('users', group)

class User(db.Model):
    fid = db.StringProperty(required = True)
    name = db.StringProperty(required = True)
    email = db.StringProperty(required = True)
    created = db.DateTimeProperty(auto_now_add = True)	

    @classmethod
    def by_id(cls, uid):
        return User.get_by_id(uid, parent = users_key())

    @classmethod
    def by_name(cls, name):
        u = User.all().filter('name =', name).get()
        return u

    @classmethod
    def by_fid(cls, fid):
        u = User.all().filter('fid =', fid).get()
        return u

class Login(BlogHandler):
    def get(self):
        redirecturl = "http://localhost:8080/login"
        args = dict(client_id=FACEBOOK_APP_ID, redirect_uri=redirecturl)

        """redirect_url points to */login* URL of our app"""
        args["client_secret"] = FACEBOOK_APP_SECRET  #facebook APP Secret
        args["code"] = self.request.get("code")
        response = cgi.parse_qs(urllib.urlopen("https://graph.facebook.com/oauth/access_token?" + urllib.urlencode(args)).read())
        access_token = response["access_token"][-1]
        profile = json.load(urllib.urlopen("https://graph.facebook.com/me?" + urllib.urlencode(dict(access_token=access_token))))
        self.set_secure_cookie('user_id', str(profile["id"]))
        u = User.by_fid(str(profile["id"]))
        print u
        if not u:
                print "Registering another user..."
                p = User(fid = str(profile["id"]), name = str(profile["name"]), email = str(profile["email"]))
                p.put()
           
        self.redirect("/")

class Logout(BlogHandler):
    def get(self):
        self.response.headers.add_header('Set-Cookie', 'user_id=; Path=/')
        self.redirect('/')

##### blog stuff

def blog_key(name = 'default'):
    return db.Key.from_path('blogs', name)

class Post(db.Model):
    producttype = db.StringProperty(required = True)
    name = db.TextProperty(required = True)
    detail = db.TextProperty(required = True)
    author = db.ReferenceProperty(User, required = True)
    avatar = db.BlobProperty(required = False)
    created = db.DateTimeProperty(auto_now_add = True)
    last_modified = db.DateTimeProperty(auto_now = True)


    def render(self):
        self._render_text = self.detail.replace('\n', '<br>')
        return render_str("post.html", p = self)

    def as_dict(self):
        time_fmt = '%c'
        d = {'product_type': self.producttype,
	     'name'   : self.name,
	     'detail' : self.detail,
             'author' : self.author,
             'created': self.created.strftime(time_fmt),
             'last_modified': self.last_modified.strftime(time_fmt)}
        return d



class BlogFront(BlogHandler):
    def get(self):

# Add the lines below for updating the datastore
# Demo code to add extra column 'authors' to existing table
#		query = Query("Post")
#		for item in query.Run():
#			if not 'author' in item:
#				item['author'] = "Sajal Jain"
#				print "author added"
#			Put(item)
        
	posts = greetings = Post.all().order('-created')
	if self.format == 'html':
	     self.render('front.html', posts = posts)
	else:
	     return self.render_json([p.as_dict() for p in posts])

class PostPage(BlogHandler):
    def get(self, post_id):
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)

        if not post:
            self.error(404)
            return
        if self.format == 'html':
            self.render("permalink.html", post = post)
        else:
            self.render_json(post.as_dict())



class SellItem(BlogHandler):
    def get(self):
        productseq = ['Computer', 'Bicycle', 'Book']
        if self.user:
	    self.render("sellitem.html", productseq = productseq)
        else:
            self.redirect("/")

    def post(self):
        productseq = ['Computer', 'Bicycle', 'Book']
        if not self.user:
            self.redirect('/')

        producttype = self.request.get('producttype')
        name = self.request.get('name')
        detail = self.request.get('detail')
        print self.user
        author = User.by_fid(self.user)
        print author
        pseudoavatar = self.request.get('img')
        #avatar = db.Blob(pseudoavatar)
        avatar = "abc"	
	
        if producttype and name and detail and author:
            p = Post(parent = blog_key(), producttype = producttype, name = name, detail = detail, avatar = avatar, author = author)
            p.put()
            self.redirect('/%s' % str(p.key().id()))
        else:
            error = "fill in the details, please!"
            self.render("sellitem.html", productseq = productseq, producttype = producttype, name = name, detail = detail, author = author, avatar = avatar, error=error) #add author here as well

class Interest(db.Model):
    user = db.ReferenceProperty(User)
    post = db.ReferenceProperty(Post)
    created = db.DateTimeProperty(auto_now_add = True)



class Interested(BlogHandler):
    def get(self):
        self.redirect("/")

    def post(self):
        postkey = self.request.get("postkey")
        post = db.get(postkey)
        u = User.by_fid(self.user)
        i = Interest(user = u, post = post)
        i.put()
        #r = json.dumps({"status" : "ok", "interest": u.email})
        #self.response.headers["Content-Type"] = "application/json; charset=UTF-8"
        #self.write(r) 


class Image(webapp2.RequestHandler):
    def get(self):
        p = db.get(self.request.get('img_id'))
        if p.avatar:
            self.response.headers['Content-Type'] = 'image/png'
            self.response.out.write(p.avatar)
        else:
            self.response.out.write('No image')





app = webapp2.WSGIApplication([#('/', MainPage),
                               ('/?(?:.json)?', BlogFront),
                               ('/([0-9]+)(?:.json)?', PostPage),
                               ('/sellitem', SellItem),
		                       ('/logout', Logout),
			                   ('/login', Login),
                               ('/interested', Interested),
                               ('/img', Image),
                               ],
                              debug=True)
