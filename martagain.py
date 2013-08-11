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
from datetime import datetime, timedelta

import webapp2
import jinja2
import facebook

from google.appengine.ext import db
from google.appengine.api import memcache
from google.appengine.api import images
from google.appengine.api.datastore import Query, Put

FACEBOOK_APP_ID = "1398507617030667"
FACEBOOK_APP_SECRET = "c5e18e6dfcf8920428c5bca868f2d8bb"

template_dir = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = jinja2.Environment(loader = jinja2.FileSystemLoader(template_dir),
                               autoescape = True)

secret = 'fart'
dev_mode = 'on'

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

### caching functions
def age_set(key, val):
    save_time = datetime.utcnow()
    memcache.set(key, (val, save_time))

def age_get(key):
    r = memcache.get(key)
    if r:
        val, save_time = r
        age = (datetime.utcnow() - save_time).total_seconds()
    else:
        val, age = None, 0

    return val, age

def add_post(post):
    post.put()
    get_posts(update = True)
    return str(post.key().id())

def get_posts(update = False):
    q = Post.all().order('-created').fetch(limit =10)
    mc_key = 'POST'

    posts, age = age_get(mc_key)
    if update or posts is None:
        posts = list(q)
        age_set(mc_key, posts)

    return posts, age

def add_wish(wish):
    wish.put()
    get_wishes(update = True)
    return str(wish.key().id())

def get_wishes(update = False):
    q = Wish.all().order('-created').fetch(limit =10)
    mc_key = 'WISH'

    wishes, age = age_get(mc_key)
    if update or wishes is None:
        wishes = list(q)
        age_set(mc_key, wishes)

    return wishes, age

def age_str(age):
    s = 'queried %s seconds ago'
    age = int(age)
    if age == 1:
        s = s.replace('seconds', 'second')
    return s % age



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


class Wish(db.Model):
    producttype = db.StringProperty(required = True)
    detail = db.TextProperty(required = True)
    author = db.ReferenceProperty(User, required = True)
    created = db.DateTimeProperty(auto_now_add = True)
    last_modified = db.DateTimeProperty(auto_now = True)


    def render(self):
        self._render_text = self.detail.replace('\n', '<br>')
        return render_str("wish.html", w = self)

    def as_dict(self):
        time_fmt = '%c'
        d = {   'product_type': self.producttype,
                'name'   : self.name,
                'detail' : self.detail,
                'author' : self.author,
                'created': self.created.strftime(time_fmt),
                'last_modified': self.last_modified.strftime(time_fmt)}
        return d

class Post(db.Model):
    producttype = db.StringProperty(required = True)
    name = db.TextProperty(required = True)
    detail = db.TextProperty(required = True)
    price = db.FloatProperty(required = False)
    author = db.ReferenceProperty(User, required = True)
    wish = db.ReferenceProperty(Wish, required = False)
    avatar = db.BlobProperty(required = False)
    created = db.DateTimeProperty(auto_now_add = True)
    last_modified = db.DateTimeProperty(auto_now = True)

   
    def render(self):
        self._render_text = self.detail.replace('\n', '<br>')
        return render_str("post.html", p = self)

    def as_dict(self):
        time_fmt = '%c'
        d = {   'product_type': self.producttype,
	            'name'   : self.name,
	            'detail' : self.detail,
                'price'  : self.price,
                'author' : self.author,
                'avatar' : self.avatar,
                'wish'   : self.wish,
                'created': self.created.strftime(time_fmt),
                'last_modified': self.last_modified.strftime(time_fmt)}
        return d

class BlogFront(BlogHandler):
    def get(self):
       	posts, age = get_posts()
        if self.format == 'html':
    	     self.render('postfront.html', posts = posts, age = age_str(age))
    	else:
    	     return self.render_json([p.as_dict() for p in posts])

class Computers(BlogHandler):
    def get(self):
        posts, age = get_posts()
        computers = []
        for p in posts:
            if p.producttype == 'Book':
                computers.append(p)

        if self.format == 'html':
             self.render('postfront.html', posts = computers, age = age_str(age))
        else:
             return self.render_json([p.as_dict() for p in posts])

class Books(BlogHandler):
    def get(self):
        posts, age = get_posts()
        books = []
        for p in posts:
            if p.producttype == 'Book':
                books.append(p)

        if self.format == 'html':
             self.render('postfront.html', posts = books, age = age_str(age))
        else:
             return self.render_json([p.as_dict() for p in posts])

class Bicycles(BlogHandler):
    def get(self):
        posts, age = get_posts()
        bicycles = []
        for p in posts:
            if p.producttype == 'Book':
                bicycles.append(p)

        if self.format == 'html':
             self.render('postfront.html', posts = bicycles, age = age_str(age))
        else:
             return self.render_json([p.as_dict() for p in posts])

class MyItems(BlogHandler):
    def get(self):
        posts, age = get_posts()
        myitems = []
        for p in posts:
            if p.author.fid == self.user:
                myitems.append(p)

        if self.format == 'html':
             self.render('postfront.html', posts = myitems, age = age_str(age))
        else:
             return self.render_json([p.as_dict() for p in posts])

class MyWishes(BlogHandler):
    def get(self):
        wishes, age = get_wishes()
        mywishes = []
        for w in wishes:
            if w.author.fid == self.user:
                mywishes.append(w)

        if self.format == 'html':
             self.render('wishfront.html', wishes = mywishes, age = age_str(age))
        else:
             return self.render_json([w.as_dict() for w in wishes])


class WishFront(BlogHandler):
    def get(self):
        wishes, age = get_wishes()
        wishes = greeting = Wish.all().order('-created')    
        self.render('wishfront.html', wishes = wishes, age = age_str(age))
        

class PostPage(BlogHandler):
    def get(self, post_id):
        post_key = 'POST_' + post_id

        post, age = age_get(post_key)
        if not post:
            key = db.Key.from_path('Post', int(post_id), parent=blog_key())
            post = db.get(key)
            age_set(post_key, post)
            age = 0 

        if not post:
            self.error(404)
            return
        if self.format == 'html':
            self.render("postpermalink.html", post = post, age = age_str(age))
        else:
            self.render_json(post.as_dict())

class WishPage(BlogHandler):
    def get(self, wish_id):
        wish_key = 'WISH_' + wish_id

        wish, age = age_get(wish_key)
        if not wish:
            key = db.Key.from_path('Wish', int(wish_id), parent=blog_key())
            wish = db.get(key)
            age_set(wish_key, wish)
            age = 0 

        if not wish:
            self.error(404)
            return
        if self.format == 'html':
            self.render("wishpermalink.html", wish = wish, age = age_str(age))
        else:
            self.render_json(wish.as_dict())



class SellItem(BlogHandler):
    wish = None
    def get(self):
        global wish
        wish = None
        productseq = ['Computer', 'Bicycle', 'Book']
        if self.request.get('wishkey'):
            wish = db.get(self.request.get('wishkey'))

        if self.user and wish:
	       self.render("sellitem.html", productseq = productseq, wish = wish)
        elif self.user:
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
        author = User.by_fid(self.user)
        price = None
        if self.request.get('price').isnumeric():
            price = float(self.request.get('price'))
        wish = None
        if self.request.get('wishkey'):
            wish = db.get(self.request.get('wishkey'))
        
        avatar = None
        if self.request.get('img'):
            pseudoavatar = self.request.get('img')
            avatar = db.Blob(pseudoavatar)   

        if producttype and name and detail and author:
            p = Post(parent = blog_key(), producttype = producttype, name = name, detail = detail, author = author)
            if price:
                p.price = price
            if avatar:
                p.avatar = avatar
            if wish:
                p.wish = wish
               
            add_post(p)
            self.redirect('/post/%s' % str(p.key().id()))
            #self.redirect('/')
        else:
            error = "fill in the details, please!"
            self.render("sellitem.html", productseq = productseq, producttype = producttype, wish = wish, name = name, detail = detail, author = author, error=error) #add author here as well

class AddWish(BlogHandler):
    def get(self):
        productseq = ['Computer', 'Bicycle', 'Book']
        if self.user:
           self.render("addwish.html", productseq = productseq)
        else:
            self.redirect("/")

    def post(self):
        productseq = ['Computer', 'Bicycle', 'Book']
        if not self.user:
            self.redirect('/')

        producttype = self.request.get('producttype')
        detail = self.request.get('detail')
        author = User.by_fid(self.user)
        
        if producttype and detail and author:
            w = Wish(parent = blog_key(), producttype = producttype, detail = detail, author = author)
            add_wish(w)
            self.redirect('/wish/%s' % str(w.key().id()))
        else:
            error = "fill in the details, please!"
            self.render("addwish.html", productseq = productseq, producttype = producttype, detail = detail, author = author, error=error) #add author here as well


class Interest(db.Model):
    user = db.ReferenceProperty(User)
    post = db.ReferenceProperty(Post)
    created = db.DateTimeProperty(auto_now_add = True)

    @classmethod
    def by_data(cls, user, post):
        i = Interest.all().filter(' user =', user).filter('post = ', post).get()
        return i

class Interested(BlogHandler):
    def get(self):
        self.redirect('/')

    def post(self):
        postkey = self.request.get("postkey")
        post = db.get(postkey)
        u = User.by_fid(self.user)
        i = Interest.by_data(u, post)
        if not i:
            i = Interest(user = u, post = post)
            i.put()
            self.write('<p>Interest sent</p>')
        else:
            self.write('<p>Had already sent</p>')

class Feed(db.Model):
    contact = db.StringProperty(required = False)
    text = db.TextProperty(required = False)
    created = db.DateTimeProperty(auto_now_add = True)


class Feedback(BlogHandler):
    def get(self):
        self.redirect('/')

    def post(self):
        contact = self.request.get("email")
        text = self.request.get("feedtext")
        f = Feed(contact = contact, text = text)
        f.put()
        print "received feedback"
        self.write('<p>Feedback Sent</p>')
        self.redirect('/')

class ShowInterested(BlogHandler):
    def get(self):
        postkey = self.request.get('postkey')
        post = db.get(postkey)
        interests = db.GqlQuery("SELECT * FROM Interest " +
                "WHERE post = :1",post)
        self.render("showinterested.html", interests = interests)

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
                               ('/post/([0-9]+)(?:.json)?', PostPage),
                               ('/books', Books),
                               ('/computers', Computers),
                               ('/bicycles', Bicycles),
                               ('/myitems', MyItems),
                               ('/mywishes', MyWishes),
                               ('/wish/([0-9]+)(?:.json)?', WishPage),
                               ('/wishlist',WishFront),
                               ('/showinterested', ShowInterested),
                               #('/user',UserPage),
                               ('/sellitem', SellItem),
                               ('/addwish', AddWish),
                               ('/feedback', Feedback),
		                       ('/logout', Logout),
			                   ('/login', Login),
                               ('/interested', Interested),
                               ('/img', Image),
                               ],
                              debug=True)
