import tweepy

# == OAuth Authentication ==
#
# This mode of authentication is the new preferred way
# of authenticating with Twitter.

# The consumer keys can be found on your application's Details
# page located at https://dev.twitter.com/apps (under "OAuth settings")
consumer_key="dvqvInt4e3qpM9miNGQZRQ"
consumer_secret="5UoPJLF7KPxqtvtgFuSySKVd8jBxI0Jj0mZ5NpKY"

# The access tokens can be found on your applications's Details
# page located at https://dev.twitter.com/apps (located 
# under "Your access token")
access_token="1670725717-4zs2VrJcgFz8AeNrTfIz0hxuGwBd6N2GPHCvW4E"
access_token_secret="igeVH3rgJr9v2DyoMRFyyu5YuHY2k2sv4XClxUu3w"

auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
auth.set_access_token(access_token, access_token_secret)

api = tweepy.API(auth)

# If the authentication was successful, you should
# see the name of the account print out
print api.me().name

# If the application settings are set for "Read and Write" then
# this line should tweet out the message to your account's 
# timeline. The "Read and Write" setting is on https://dev.twitter.com/apps
api.update_status('Updating using OAuth authentication via Tweepy!')
