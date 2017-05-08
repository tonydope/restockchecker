import requests
import re
import time
import random
import json
import telebot
from bs4 import BeautifulSoup
import sqlite3

url = 'http://www.supremenewyork.com/shop/all'
main_url = 'http://www.supremenewyork.com'
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.3; Win64; x64; rv:51.0) Gecko/20100101 Firefox/51.0'}
proxy = ''
proxy_login = 'tonydaup'
proxy_pass = 'zrt9lu'
channel = '@sometelegramchannelwhereisthebotadmin'
token = '' # Telegram bot token
tb = telebot.TeleBot(token)
con = sqlite3.connect('monitor.db')
cur = con.cursor()

# droptime in UTC
drop_day = 3 # Thu
drop_h = 10
drop_m = 3

def GetProxies():
    # Open config
    with open('proxy.json', 'r') as f:
        proxys = json.load(f)
    return proxys

def GetSoup(link):
    soup = ''
    retries = 0
    while not soup:
        retries += 1
        if retries > 5:
            break
        proxies = {'http': 'http://%s:%s@%s' % (proxy_login,proxy_pass,proxy),
                'https': 'http://%s:%s@%s' % (proxy_login,proxy_pass,proxy),}
        try:
            r = requests.get(link, headers = headers, \
                                proxies = proxies)
            soup = BeautifulSoup(r.text, "html.parser")
        except:
            print 'Connection Error. Retry: %s' % retries
            time.sleep(1)
    return soup

def GetItems():
    soup = GetSoup(url)
    if soup:
        scroller = soup.find('div', {'class': 'turbolink_scroller'})
        items = scroller.find_all('a')
        return items
    else:
        print 'Connection is failed'
        return

def GetItemInfo(item):
    link = main_url+item.get('href')
    #print link
    image = item.img.get('src')
    soup = GetSoup(link)
    if soup:
        details = soup.find('div', {'id': 'details'})
        name = details.h1.string
        style = details.p.string
        buttons = str(details.div.find('fieldset',{'id':'add-remove-buttons'}))
        sizes = []
        if not re.search(r'sold out', buttons):
            status = 1 #instock
            # Available sizes
            filter(lambda size: sizes.append(size.renderContents()), \
                details.fieldset.find_all('option'))
        else:
            status = 0 #soldout
        return {'link': link, 'image': image, 'name': name, 'style': style, 'status': status, 'sizes': sizes}
    else:
        print 'GetItemInfo error'
        return

''' Make some shit with database '''
def AddItemToDb(item):
    cur.execute('INSERT INTO items (link, image, name, style, status, time) \
                 VALUES (?,?,?,?,?,?)', \
                (item['link'], item['image'], item['name'], \
                 item['style'], item['status'], time.time()))
    con.commit()

def GetItemFromDbByLink(link):
    try:
        cur.execute('SELECT item_id, status FROM items WHERE link = ?', (link,))
        data = cur.fetchone()
    except:
        print "[DB ERROR]"
    else:
        try:
            return {'id': data[0], 'status': data[1]}
        except:
            return

def AddInstockEventToDb(item_id, sizes):
    cur.execute('INSERT INTO instock (item_id, time, sizes) VALUES (?,?,?)', \
                (item_id, time.time(), sizes))
    con.commit()

def GetLastInstockEventFromDb(item_id):
    cur.execute('SELECT event_id FROM instock \
                 WHERE item_id = ? ORDER BY time DESC', \
                (item_id,))
    try:
        event_id = cur.fetchone()[0]
    except:
        return
    else:
        return event_id

def AddSoldoutEventToDb(item_id):
    event_id = GetLastInstockEventFromDb(item_id)
    if event_id:
        cur.execute('INSERT INTO soldout (event_id, item_id, time) VALUES (?,?,?)', (event_id, item_id, time.time()))
        con.commit()

def GetInstockEventTimeFromDb(event_id):
    cur.execute('SELECT time FROM instock \
                 WHERE event_id = ?', \
                (event_id,))
    try:
        time = float(cur.fetchone()[0])
    except:
        return
    else:
        return time

def GetSoldoutEventTimeFromDb(event_id):
    cur.execute('SELECT time FROM soldout \
                 WHERE event_id = ?', \
                (event_id,))
    try:
        time = float(cur.fetchone()[0])
    except:
        return
    else:
        return time

def GetSelloutTimeFromDb(event_id):
    soldouttime = GetSoldoutEventTimeFromDb(event_id)
    instocktime = GetInstockEventTimeFromDb(event_id)
    if soldouttime and instocktime:
        return round(soldouttime - instocktime, 2)

'''Output'''
def SendAndGetDbInfo(info):
    dbitem = GetItemFromDbByLink(info['link'])
    if dbitem is None:
        AddItemToDb(info)
    if dbitem is None or \
       dbitem['status'] is not info['status']: #check that some shit rly happened
        dbitem = GetItemFromDbByLink(info['link'])
        cur.execute('UPDATE items SET status = ? where item_id = ?', \
                    (info['status'], dbitem['id']))
        con.commit()
        if info['status']:
            AddInstockEventToDb(dbitem['id'], str(info['sizes']))
            info['sellout'] = ''
        else:
            AddSoldoutEventToDb(dbitem['id'])
            event_id = GetLastInstockEventFromDb(dbitem['id'])
            info['sellout'] = GetSelloutTimeFromDb(event_id)
        return info

def SendInfoToTelegram(info):
    retries = 0
    if info:
        if info['status']:
            status = 'InStock'
        else:
            status = 'SoldOut'
        msg = u''
        msg = msg+'[%s]\n' % status
        msg = msg+'Name: [%s]\n' % info['name']
        msg = msg+'Color: [%s]\n' % info['style']
        msg = msg+'%s' % info['link']
        if info['sizes']:
            msg = msg+'\nAvailable sizes: %s' % info['sizes']
        if info['sellout']:
            if info['sellout'] > 60:
                msg = msg+'\nSellOut time: ~%.1f min' % (info['sellout']/60)
            else:
                msg = msg+'\nSellOut time: ~%.2f sec' % info['sellout']
        while True:
            retries += 1
            if retries > 10:
                break
            try:
                tb.send_photo(channel,'http:'+info['image'] , msg)
            except:
                print 'Telegram eror rertry: %s' % retries
                time.sleep(1)
            else:
                break

def PrintItemInfo(info):
    if info:
        print '-'*60
        print '[%s]' % info['status']
        print 'Name: %s' % info['name'].encode('utf-8')
        print 'Color: %s' % info['style'].encode('utf-8')
        print 'Link: %s' % info['link'].encode('utf-8')
        if info['sizes']:
            print 'Available sizes: %s' % info['sizes']
        print '-'*60

def Monitor():
    global proxy
    global tb
    proxys = GetProxies()
    proxy = proxys[0]
    olditems = GetItems()
    if olditems:
        while True:
            for proxy in proxys:
                #print time.asctime()
                #print proxy
                items = GetItems()
                if items:
                    newitems = list(set(items).difference(olditems))
                    if newitems:
                        olditems = GetItems()
                        print '+'*60
                        print time.asctime()
                        print '+'*60
                        info = map(GetItemInfo, newitems)
                        info = map(SendAndGetDbInfo,info)
                        if info:
                            map(SendInfoToTelegram,info)
                            map(PrintItemInfo,info)
                if time.gmtime().tm_wday == drop_day and \
                   time.gmtime().tm_hour == drop_h and \
                   time.gmtime().tm_min <= drop_m:
                    time.sleep(1)
                else:
                    time.sleep(random.randint(10,20))

Monitor()
