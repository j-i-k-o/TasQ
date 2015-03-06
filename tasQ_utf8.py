# -*- coding: utf-8 -*-

import tweepy
from tweepy.streaming import StreamListener
from tweepy.error import TweepError
import psycopg2
import urlparse
import os
import sys
import time
import re
import datetime
import threading

tweetlock = threading.Lock()

class TimeoutException(Exception):
    pass

class MyListener(StreamListener):
    def __init__(self, api, conn, cur):
        
        # call super method
        super(MyListener, self).__init__()

        # register regex
        self.rgx_add = re.compile(ur'(?:(\d+)年|)(?:(\d+)月|)(?:(\d+)日|)(?:(\d+)時|)(?:(\d+)分|)(?:(まで)|).*?、(.+)'.encode('utf-8'), re.U)
        # set api
        self.api = api
        self.conn = conn
        self.cur = cur

    def __del__(self):
        pass

    def on_status(self, status):
        if(status.in_reply_to_user_id == self.api.me().id):
            # parse status
            try:
                self.parse(status.text, status)
            except TweepError as e:
                print e.message
            except ValueError as e:
                print u"コマンドが正しくないです。".encode('utf-8')
                screennameWithAt = u'@'+self.api.me().screen_name
                reply_str = status.text.replace(screennameWithAt, u'')
                with tweetlock:
                    self.api.update_status(None, u"@"+status.author.screen_name+u" "+u"コマンドが正しくないです(ValueError)。「"+reply_str+u"」", in_reply_to_status_id=status.id)
                


    def on_error(self, status):
        print "an error occurred."
        print status

    def on_timeout(self):
        raise TimeoutException
    
    def getTimeDeltaLevel(self, td):
        if td > datetime.timedelta(31):
            return 5
        elif td > datetime.timedelta(7):
            return 4
        elif td > datetime.timedelta(1):
            return 3
        elif td > datetime.timedelta(days=0, hours=1):
            return 2
        elif td > datetime.timedelta(days=0, minutes=30):
            return 1
        else:
            return 0


    def parse(self, reply_str, reply_status):
        print "call parse"
        #parse reply string
        #delete @[screen_name]
        screennameWithAt = u'@'+self.api.me().screen_name
        reply_str = reply_str.replace(screennameWithAt, u'')
        reply_str = reply_str.replace(u' ', u'')
        reply_str = reply_str.replace(u'　', u'')
        print reply_str.encode('utf-8')
        date_now = datetime.datetime.now()
        date_to_add = datetime.datetime(date_now.year, date_now.month, date_now.day, date_now.hour, date_now.minute)
        print date_now
        print date_to_add
        if (self.rgx_add.match(reply_str.encode('utf-8')) != None): # add command accepted
            y, mo, d, h, mi = self.rgx_add.match(reply_str.encode('utf-8')).groups()[0:5]
            print self.rgx_add.match(reply_str.encode('utf-8')).groups()
            y = int(y) if y!=None else None
            mo = int(mo) if mo!=None else None
            d = int(d) if d!=None else None
            h = int(h) if h!=None else None
            mi = int(mi) if mi!=None else None
            if(y==None and mo==None and d==None and h!=None and mi==None):   #h時
                date_to_add = datetime.datetime(date_now.year, date_now.month, date_now.day, h)
            elif(y==None and mo==None and d==None and h!=None and mi!=None): #h時mi分
                date_to_add = datetime.datetime(date_now.year, date_now.month, date_now.day, h, mi)
            elif(y==None and mo!=None and d!=None and h==None and mi==None): #mo月d日
                date_to_add = datetime.datetime(date_now.year, mo, d)
            elif(y==None and mo!=None and d!=None and h!=None and mi==None): #mo月d日h時
                date_to_add = datetime.datetime(date_now.year, mo, d, h)
            elif(y==None and mo!=None and d!=None and h!=None and mi!=None): #mo月d日h時mi分
                date_to_add = datetime.datetime(date_now.year, mo, d, h, mi)
            elif(y!=None and mo!=None and d!=None and h==None and mi==None): #y年mo月d日
                date_to_add = datetime.datetime(y, mo, d)
            elif(y!=None and mo!=None and d!=None and h!=None and mi==None): #y年mo月d日h時
                date_to_add = datetime.datetime(y, mo, d, h)
            elif(y!=None and mo!=None and d!=None and h!=None and mi!=None): #y年mo月d日h時mi分
                date_to_add = datetime.datetime(y, mo, d, h, mi)
            else: #invalid data
                date_to_add = None

            isDeadline = self.rgx_add.match(reply_str.encode('utf-8')).groups()[5] != None

            print date_to_add

            #add to database
            if(date_to_add == None):
                raise ValueError
            
            self.cur.execute('insert into tasks values (%s, %s, %s, %s, %s)', (reply_status.author.id, date_to_add, self.rgx_add.match(reply_str.encode('utf-8')).groups()[6], isDeadline, self.getTimeDeltaLevel(date_to_add - date_now)))
            self.conn.commit()
            with tweetlock:
                self.api.update_status(None, u"@"+reply_status.author.screen_name+u" "+u"予定を追加「"+reply_str+u"」", in_reply_to_status_id=reply_status.id)

        elif (reply_str == u'予定'):
            pass
        else:
            with tweetlock:
                self.api.update_status(None, u"@"+reply_status.author.screen_name+u" "+u"コマンドが正しくないです。「"+reply_str+u"」", in_reply_to_status_id=reply_status.id)


#schedule

def checkSchedule(api,conn,cur):
    while True:
        time.sleep(60)
        print "scheduler wake"
    
        #get current date
        datenow = datetime.datetime.now()
        print datenow

        #send query
        cur.execute('select * from tasks')
        for t in cur.fetchall():
            #check date
            print t
            if(t[1] <= datenow):
                #delete
                print "delete"
                try:
                    cur.execute('delete from tasks where user_id=%s and date=%s and task=%s and is_deadline=%s', t[0:4])
                except psycopg2.Error:
                    pass
                
            elif (t[1] - datenow <= datetime.timedelta(31) and t[4] == 5):
                # last 1 month
                print "1 month"
                try:
                    with tweetlock:
                        api.update_status(None, u"@"+api.get_user(t[0]).screen_name+u" "+t[2].decode('utf-8')+u"まであと約1ヶ月です")
                except TweepError as e:
                    print e.message
                    
                try:
                    cur.execute('update tasks set report_level=%s where user_id=%s and date=%s and task=%s and is_deadline=%s', (t[4]-1, t[0], t[1], t[2], t[3]))
                except psycopg2.Error:
                    pass
    
            elif (t[1] - datenow <= datetime.timedelta(7) and t[4] == 4):
                # last 1 week
                print "1 week"
                try:
                    with tweetlock:
                        api.update_status(None, u"@"+api.get_user(t[0]).screen_name+u" "+t[2].decode('utf-8')+u"まであと1週間です")
                except TweepError as e:
                    print e.message

                try:
                    cur.execute('update tasks set report_level=%s where user_id=%s and date=%s and task=%s and is_deadline=%s', (t[4]-1, t[0], t[1], t[2], t[3]))
                except psycopg2.Error:
                    pass
    
            elif (t[1] - datenow <= datetime.timedelta(1) and t[4] == 3):
                # last 1 day 
                print "1 day"
                try:
                    with tweetlock:
                        api.update_status(None, u"@"+api.get_user(t[0]).screen_name+u" "+t[2].decode('utf-8')+u"まであと1日です")
                except TweepError as e:
                    print e.message
    
                try:
                    cur.execute('update tasks set report_level=%s where user_id=%s and date=%s and task=%s and is_deadline=%s', (t[4]-1, t[0], t[1], t[2], t[3]))
                except psycopg2.Error:
                    pass
    
            elif (t[1] - datenow <= datetime.timedelta(days=0, hours=1) and t[4] == 2):
                # last 1 hour
                print "1 hour"
                try:
                    with tweetlock:
                        api.update_status(None, u"@"+api.get_user(t[0]).screen_name+u" "+t[2].decode('utf-8')+u"まであと1時間です")
                except TweepError as e:
                    print e.message

                try:
                    cur.execute('update tasks set report_level=%s where user_id=%s and date=%s and task=%s and is_deadline=%s', (t[4]-1, t[0], t[1], t[2], t[3]))
                except psycopg2.Error:
                    pass
    
            elif (t[1] - datenow <= datetime.timedelta(days=0, minutes=30) and t[4] == 1):
                # last 1 month
                print "half hour"
                try:
                    with tweetlock:
                        api.update_status(None, u"@"+api.get_user(t[0]).screen_name+u" "+t[2].decode('utf-8')+u"まであと30分です")
                except TweepError as e:
                    print e.message
    
                try:
                    cur.execute('update tasks set report_level=%s where user_id=%s and date=%s and task=%s and is_deadline=%s', (t[4]-1, t[0], t[1], t[2], t[3]))
                except psycopg2.Error:
                    pass
    
    
        conn.commit()
        print "read to sleep"






if __name__ == '__main__':

    #authorization
    consumerKey = os.environ['CONSUMER_KEY'] 
    consumerSecret = os.environ['CONSUMER_SECRET']
    accessToken = os.environ['ACCESS_TOKEN']
    accessSecret = os.environ['ACCESS_SECRET']
    auth = tweepy.OAuthHandler(consumerKey, consumerSecret)
    auth.set_access_token(accessToken, accessSecret)
    api = tweepy.API(auth)
    urlparse.uses_netloc.append("postgres")
    url = urlparse.urlparse(os.environ["DATABASE_URL"])
    conn = psycopg2.connect(
            database=url.path[1:],
            user=url.username,
            password=url.password,
            host=url.hostname,
            port=url.port
            )
    cur = conn.cursor();
    print u"セット完了".encode('utf-8')

    thr = threading.Thread(target=checkSchedule, name="scheduler", args=(api,conn,cur))
    thr.setDaemon(True)
    thr.start()
    print "thread start"

    stream = tweepy.Stream(auth, MyListener(api, conn, cur), secure=True)
    while True:
        try:
            stream.userstream()
        except KeyboardInterrupt:
            print "KeyboardInterrpt occurred"
            print "terminate this program"
            cur.close()
            conn.close()
            break
        except TimeoutException:
            print "TimeoutException occurred"
            #wait 60 seconds
            time.sleep(60)
