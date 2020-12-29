import discord
import logging
import random
import glob
import aiohttp
import io
import shlex
import re
import sqlite3
import hashlib
from urllib.parse import urlparse
from memearoo import meme_top_bottom_image
TOKEN = open('token').read().strip()

# urls or things between square braces <>
QUOTE_SKIP_REGEX = r"(https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*))|(<.*>)"
# only keep quotes longer than this
QUOTE_MIN_LEN = 50

# logger
logger = logging.getLogger('discord')
logger.setLevel(logging.INFO)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

# billy globals
quotes = []
pics = glob.glob("pics/*")
memes = glob.glob("memes/*.jpg")
# chop off /memes/ and .jpg
memes = [x[6:-4] for x in memes]
memes.sort()

# quote database globals
quote_db = sqlite3.connect('quotes.db')
quote_db_cursor = quote_db.cursor()
quote_db_cursor.execute('CREATE TABLE IF NOT EXISTS quotes(hash TEXT primary key, user TEXT, message TEXT, date_added TEXT, userid INT, channelid INT)')
print('quote database loaded')

usage ="""
```
A Happy Hour Bot

Memes:
!memelist       list of meme templates, comma separated.
!meme <url or template name> <top text> [bottom text]
                Generate a meme from a URL or meme template.
                All parameters must be surrounded by quotes
                if they contain spaces.
                Bottom text is optional.

!meme last <top text> [bottom text]
                Use the previous image (not meme) in this channel

Quotes:
Note, only long messages (excl. URLs) are saved by default.
!quote          A random quote from any user
!quote <user>   A quote from the specified user
                Username is case sensitive
!quote <userid> A quote from the specified user ID
!quote channel  A quote from this channel
!quote count    Number of quotes we have
!quote save     Save the last message from this channel, regardless of length.

Billy Madison:
!billy help     This Message
!billypic       Picture
!billy          Quote


notoriousrip for compliments
v. 3.6 (002) Not Great, Not Terrible
```
"""

with open("billy.txt") as f:
    quotes = f.read().splitlines()

client = discord.Client()

# Helper functions

# hash() is randomized, override it
def _hash(s):
    return hashlib.md5(s.encode('utf-8')).hexdigest()[:12]

def _shlex(cmd):
    # unicode double quotes with ascii double quote
    # unicode single quote with ascii single quote
    cmd = re.sub(u"[\u201c\u201d\u201f]", '"', cmd)
    cmd = re.sub(u"[\u2018\u2019\u201b]", "'", cmd)
    argv = shlex.split(cmd)
    return argv

### Quote Database
async def quote_update():
    """
    Downloads old quotes into the database
    """
    print("Performing history quote gathering experience...")
    i = 0
    for channel in client.get_all_channels():
        if type(channel) == discord.channel.TextChannel:
            perms = channel.permissions_for(channel.guild.me)
            if not perms.read_message_history:
                continue

            async for message in channel.history(limit=1000):
                if message.author == client.user:
                    continue

                quote_save(message)

def quote_get_random():
    quote_db_cursor.execute("SELECT user, message, date_added, channelid FROM quotes ORDER BY RANDOM() limit 1")
    query = quote_db_cursor.fetchone()

    if not query:
        return "No quotes!"

    channel_name = client.get_channel(query[3]).name

    msg = """
    {user} @ {time} in {channel}:
    >>> {msg}
    """.format(user=query[0], time=query[2], msg=query[1], channel=channel_name)

    return msg

def quote_get_random_channel(channel):
    quote_db_cursor.execute("SELECT user, message, date_added FROM quotes WHERE channelid=(?) ORDER BY RANDOM() limit 1", (channel.id,))
    query = quote_db_cursor.fetchone()

    if not query:
        return "No quotes!"

    msg = """
    {user} @ {time} in {channel}:
    >>> {msg}
    """.format(user=query[0], time=query[2], msg=query[1], channel=channel.name)

    return msg

def quote_get_user(username):
    quote_db_cursor.execute("SELECT message, date_added,channelid FROM quotes WHERE user=(?) ORDER BY RANDOM() LIMIT 1", (username,))

    query = quote_db_cursor.fetchone()

    if not query:
        return "No quotes from {user}".format(user=username)

    channel_name = client.get_channel(query[2]).name

    msg = """
    {user} @ {time} in {channel}:
    >>> {msg}
    """.format(user=username, time=query[1], msg=query[0], channel=channel_name)

    return msg

def quote_get_userid(userid):
    quote_db_cursor.execute("SELECT message, date_added,channelid, user FROM quotes WHERE userid=(?) ORDER BY RANDOM() LIMIT 1", (userid,))

    query = quote_db_cursor.fetchone()

    if not query:
        return "No quotes from user"

    channel_name = client.get_channel(query[2]).name

    msg = """
    {user} @ {time} in {channel}:
    >>> {msg}
    """.format(user=query[3], time=query[1], msg=query[0], channel=channel_name)

    return msg

def quote_get_leaderboard():
    rows = quote_db_cursor.execute("SELECT count(*) from quotes")
    count = rows.fetchone()[0]

    users = quote_db_cursor.execute("SELECT distinct user from quotes")
    users = users.fetchall()
    resp = "```I have saved {count} quotes.\n".format(count=count)
    resp += "Quotes are counted only if >50 characters long.\n"
    resp += "{0:<25} {1:<10} {2:<10}\n".format("User", "# Quotes", "Avg Length")

    leaderboard = {}

    for user in users:
        user = user[0]
        q = quote_db_cursor.execute("SELECT count(*), AVG(LENGTH(message)) from quotes where user=(?)", (user,))
        data = q.fetchall()[0]
        leaderboard[user] = data

    # sort leaderboard by longest quotes average
    sorted_leaderboard = sorted(leaderboard.items(), key=lambda kv: kv[1][1])
    sorted_leaderboard.reverse()

    for user, data in sorted_leaderboard:
        avg = str(int(data[1]))
        resp += "{user: <25} {n:<10} {l}\n".format(user=user, n=data[0], l=avg)

    resp += "```"
    return resp

def quote_save(message, skip_checks=False):
    if not skip_checks:
        if len(message.content) < QUOTE_MIN_LEN:
            return

        if message.content.find("!meme") >= 0:
            return

        # strip urls from our calculation
        content_no_urls = re.sub(QUOTE_SKIP_REGEX, "", message.content)
        if len(content_no_urls) < QUOTE_MIN_LEN:
            return

    # kill off tagging others because that could be annoying
    content = message.content
    content = re.sub(r"<.*>", "", content)

    user = message.author.name
    uniqueID = str(_hash(user + content))

    quote_db_cursor.execute("SELECT count(*) FROM quotes WHERE hash = ?",(uniqueID,))
    find = quote_db_cursor.fetchone()[0]

    if find >0:
        return

    timestamp = message.created_at
    timestamp = str(timestamp.strftime("%d-%m-%Y %H:%M"))

    quote_db_cursor.execute("INSERT INTO quotes VALUES(?,?,?,?,?,?)",
                            (uniqueID, user, content, timestamp,
                             message.author.id, message.channel.id))
    quote_db.commit()

### File Processor ###
async def download_file(url):
    """
    Parameters
    url
      full url
    Returns
      error string or io bytes of the file downloaded
    """
    err = "Sorry. No."

    if url.lower() in memes:
        return io.open("memes/" + url.lower() + ".jpg", "rb")

    o = urlparse(url)
    invalid = ["localhost", "127.0", "192.", "pi.net", "routerlogin", "::1", "::2", "loopback", "raspberrypi"]
    if o == None:
        return err + " Bad URL", None

    if any(x in o.hostname for x in invalid):
        logger.log(logging.ERROR, "Tried receive " + url)
        print("do not " + url)
        return err

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                print("got " + str(resp))
                return err + " " + (str(resp.status))

            data = io.BytesIO(await resp.read())
            return data

async def meme_previous(message, top, bottom):
    # look for the previous image
    async for message in message.channel.history(limit=100):
        if message.author == client.user:
            continue
        if not message.attachments:
            continue

        img_exts = ["jpg", "jpeg", "png"]
        for attachment in message.attachments:
            if not any(attachment.proxy_url.endswith(x) for x in img_exts):
                continue
            return await meme_response(attachment.proxy_url, top, bottom)

    return "Could not find one", None


async def meme_response(url, topText, bottomText):
    data = await download_file(url)
    if type(data) == str:
        return data, None

    try:
        meme = meme_top_bottom_image(topText, bottomText, data)
    except Exception as e:
        logger.log(logging.ERROR, e)
        return "I suck :(", None


    data = io.BytesIO()
    meme.save(data, format="jpeg")
    #meme.save("test.jpg")
    data.seek(0)
    return None, discord.File(data, "meme.jpg")

### Command Processor ###
async def early_out_response(lower, message):
    """
    Parameters
    lower: message content, lowercased
    message: discord message structure

    Return
    Tuple of (Response String, Response Discord File)
    None for either indicates not to send a response of that type
    None for both indicates this is not a command
    If either is returned the caller should stop processing (hence 'early out')
    """
    if lower.find("fuck adam sandler") >= 0:
        return "Do not insult the greatest comedian of all time", None

    if lower.find("adam sandler sucks") >= 0:
        return "Do not insult the greatest comedian of all time", None

    if lower.startswith("!billypic"):
        pic = random.choice(pics)
        return None, discord.File(pic)

    if lower.startswith("!memelist"):
        return ", ".join(memes), None

    if lower.startswith("!billy help"):
        return usage, None

    if lower.startswith("!meme"):
        cmd = _shlex(lower)
        if (len(cmd) != 3 and len(cmd) != 4):
            return "syntax: !meme <image url> <top text> [bottom text]", None

        url = cmd[1]
        top = cmd[2]
        bottom = None
        if len(cmd) > 3:
            bottom = cmd[3]

        logger.log(logging.INFO, cmd)
        if url == "last":
            err, pic = await meme_previous(message, top, bottom)
        else:
            err, pic = await meme_response(url, top, bottom)
        if not err:
            await message.edit(suppress=True)
        return err, pic

    if lower.startswith("!quote"):
        argv = _shlex(lower)

        if len(argv) == 1:
            return quote_get_random(), None

        if argv[1] == 'channel':
            return quote_get_random_channel(message.channel), None

        if argv[1] == 'count':
            return quote_get_leaderboard(), None
        if argv[1] == 'save':
            prev_message = message.channel.last_message_id
            prev_message = await message.channel.history(limit=2).flatten()
            prev_message = prev_message[1]
            quote_save(prev_message, True)
            return "ok", None

        if len(message.mentions) > 0:
            userid = message.mentions[0].id
            return quote_get_userid(userid), None

        # is this a user ID?
        try:
            userid = message.content[7:]
            return quote_get_userid(userid), None
        except ValueError:
            pass

        # chop off quote, treat rest of command as username
        return quote_get_user(message.content[7:]), None

    return None, None


def need_respond(lower):
    """
    Decide whether to return a billy quote
    """
    if (lower.startswith("!billy") or
        lower.find('adam sandler') >= 0):
            return True
    else:
        return False

def get_sandler_quote(message):
    """
    Return a billy madison quote
    Parameters:
     message: discord message structure
    """
    lower = message.content.lower()

    if not need_respond(lower):
        return None, None

    quote = random.choice(quotes)
    quote = quote.replace("[[name]]", message.author.name)
    return quote, None

### Client Events ###
@client.event
async def on_ready():
    print('we have logged in as {0.user}'.format(client))

    # uncomment this to download the full database
    #await quote_update()

    # tests
    #for channel in client.get_all_channels():
    #    if type(channel) == discord.channel.TextChannel:
    #        perms = channel.permissions_for(channel.guild.me)
    #        if not perms.read_message_history:
    #            continue

    #        async for message in channel.history(limit=1):
    #            if message.author == client.user:
    #                continue

    #            print(await meme_previous(message, "howdy", "ok"))
    #            break
    print(quote_get_leaderboard())

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    print(message)
    lower = message.content.lower()
    command_response, discord_file = await early_out_response(lower, message)
    if (command_response or discord_file):
        await message.channel.send(command_response, file=discord_file)
        return

    response, discord_file = get_sandler_quote(message)
    if response:
        await message.channel.send(response, file=discord_file)

    drinks = ["what ok", "wen drink", "when drink", "beer"]
    if any(x in lower for x in drinks):
        await message.add_reaction("🍺")

    church = ["church", "heavenly father", "pray"]
    if any(x in lower for x in church):
        await message.add_reaction("\N{CHURCH}")

    quote_save(message)

client.run(TOKEN)
