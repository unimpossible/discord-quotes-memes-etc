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
!quote          A random quote from any user from this channel
!quote <user>   A quote from the specified user
                Username is case sensitive
!quote <userid> A quote from the specified user ID
!quote channel  A quote from this channel
!quote all      A quote from any channel and any user
!quote count    Number of quotes we have
!quote save     Save the last message from this channel, regardless of length.

Billy Madison:
!billypic       Picture
!billy          Quote

!help     This Message

notoriousrip for compliments
v. 3.6 (002) Not Great, Not Terrible
```
"""

with open("billy.txt") as f:
    quotes = f.read().splitlines()

class BotResponse(object):
    """BotResponse."""

    def __init__(self, resp=None):
        """__init__.

        :param resp: data to send back. If this is a string, we will respond
        with this string, If it is a discord File object we will send it as an
        attachment
        """
        self.discord_file = None
        self.content = None
        if type(resp) == discord.File:
            self.discord_file = resp
        else:
            self.content = resp

    async def send_response(self, client, message):
        """send_response.

        :param client: discord client
        :param message: message which we are responding to
        """
        await message.channel.send(self.content, file=self.discord_file)

client = discord.Client()

# Helper functions

# hash() is randomized, override it
def _hash(s):
    """_hash.

    :param s:
    """
    return hashlib.md5(s.encode('utf-8')).hexdigest()[:12]

def _shlex(cmd):
    """_shlex.

    :param cmd:
    """
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
    Use this to update the database
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
    """Return a single quote string."""
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
    """quote_get_random_channel.

    :param channel: channel to select a quote from

    Return:
        String of a random quote from this channel
    """
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
    """Get a quote string from the specified user.

    :param username:
    """
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
    """Get a string of a quote from a specified user.

    :param userid: integer user id to select quote from
    """
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
    """Returns a string of the leaderboard."""
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
    """quote_save.

    :param message:
    :param skip_checks:
    """
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
    """download_file.

    :param url: URL to download or the pre-baked name to use

    Returns:
        IO Bytes of the file downloaded or a BotResponse on error
    """
    err = "Sorry. No."

    if url.lower() in memes:
        return io.open("memes/" + url.lower() + ".jpg", "rb")

    o = urlparse(url)
    invalid = ["localhost", "127.0", "192.", "pi.net", "routerlogin", "::1", "::2", "loopback", "raspberrypi"]
    if o == None:
        return BotResponse(err + " Bad URL")

    if any(x in o.hostname for x in invalid):
        logger.log(logging.ERROR, "Tried receive " + url)
        print("do not " + url)
        return BotResponse(err)

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                print("got " + str(resp))
                return BotResponse(err + " " + (str(resp.status)))

            data = io.BytesIO(await resp.read())
            return data

async def meme_attached(message, top, bottom):
    if not message.attachments:
        logger.log(logging.ERROR, message)
        logger.log(logging.ERROR, message.embeds)
        return BotResponse("No image to meme!")

    img_exts = ["jpg", "jpeg", "png"]
    for attachment in message.attachments:
        if not any(attachment.proxy_url.endswith(x) for x in img_exts):
            return BotResponse("I am dumb")
        return await meme_response(attachment.proxy_url, top, bottom)

    return BotResponse("how did i get here?")


async def meme_previous(message, top, bottom):
    """Finds the previous message in the channel and uses that to create a meme.

    :param message: previous discord message
    :param top: top text
    :param bottom: bottom text

    Returns:
        BotResponse object
    """
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

    return BotResponse("Could not find one")


async def meme_response(url, topText, bottomText):
    """meme_response.

    :param url:
    :param topText:
    :param bottomText:
    """
    data = await download_file(url)
    if type(data) == BotResponse:
        return data

    try:
        meme = meme_top_bottom_image(topText, bottomText, data)
    except Exception as e:
        logger.log(logging.ERROR, e)
        return BotResponse("I suck :(")


    data = io.BytesIO()
    meme.save(data, format="jpeg")
    #meme.save("test.jpg")
    data.seek(0)
    return BotResponse(discord.File(data, "meme.jpg"))

### Command Processor ###
async def early_out_response(lower, message):
    """
    Parameters
    lower: message content, lowercased
    message: discord message structure

    Return
    BotResponse to send back or None if no response available
    """
    if lower.find("fuck adam sandler") >= 0:
        return BotResponse("Do not insult the greatest comedian of all time")

    if lower.find("adam sandler sucks") >= 0:
        return BotResponse("Do not insult the greatest comedian of all time")

    if lower.startswith("!billypic"):
        pic = random.choice(pics)
        return BotResponse(discord.File(pic))

    if lower.startswith("!memelist"):
        return BotResponse(", ".join(memes))

    if lower.startswith("!billy help") or lower.startswith("!help"):
        return BotResponse(usage)

    if lower.startswith("!meme"):
        # so we do not auto lowercase everything use the original
        cmd = _shlex(message.content)

        # did the user reply to a message with an image? if so, use that image
        if message.reference:
            ref = message.reference
            try:
                ref = await message.channel.fetch_message(message.reference.message_id)
                if len(cmd) < 2:
                    return BotResponse("!meme <top text> [bottom text]")
                top = cmd[1]
                bottom = None
                if len(cmd) > 2:
                    bottom = cmd[2]
                return await meme_attached(ref, top, bottom)
            except Exception:
                return BotResponse("Could not get attached message")
        if (len(cmd) != 3 and len(cmd) != 4):
            return BotResponse("syntax: !meme <image url> <top text> [bottom text]")

        url = cmd[1]
        top = cmd[2]
        bottom = None
        if len(cmd) > 3:
            bottom = cmd[3]

        logger.log(logging.INFO, cmd)
        if url == "last":
            resp = await meme_previous(message, top, bottom)
        else:
            resp = await meme_response(url, top, bottom)
            # remove the old image only if an image existed and we weren't
            # meme-ing a previous
            if resp.discord_file:
                # remove the old image
                await message.edit(suppress=True)
        return resp

    if lower.startswith("!quote"):
        argv = _shlex(lower)

        if len(argv) == 1:
            return BotResponse(quote_get_random_channel(message.channel))

        if argv[1] == 'channel':
            return BotResponse(quote_get_random_channel(message.channel))

        if argv[1] == 'all':
            return BotResponse(quote_get_random())

        if argv[1] == 'count':
            return BotResponse(quote_get_leaderboard())
        if argv[1] == 'save':
            prev_message = message.channel.last_message_id
            prev_message = await message.channel.history(limit=2).flatten()
            prev_message = prev_message[1]
            quote_save(prev_message, True)
            return BotResponse("ok")

        if len(message.mentions) > 0:
            userid = message.mentions[0].id
            return BotResponse(quote_get_userid(userid))

        # is this a user ID?
        try:
            userid = message.content[7:]
            return BotResponse(quote_get_userid(int(userid)))
        except ValueError:
            pass

        # chop off quote, treat rest of command as username
        return BotResponse(quote_get_user(message.content[7:]))

    return None


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
        return None

    quote = random.choice(quotes)
    quote = quote.replace("[[name]]", message.author.name)
    return BotResponse(quote)

### Client Events ###
@client.event
async def on_ready():
    """Ready callback."""
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
async def on_guild_channel_update(before, after):
    print("Updated guild {0} {1}".format(str(before.id), str(after.id)))

@client.event
async def on_message(message):
    """on_message.

    :param message: incoming message discord object
    """
    if message.author == client.user:
        return

    lower = message.content.lower()
    resp = await early_out_response(lower, message)
    if resp:
        await resp.send_response(client, message)
        return

    resp = get_sandler_quote(message)
    if resp:
        await resp.send_response(client, message)

    drinks = ["what ok", "wen drink", "when drink", "beer"]
    if any(x in lower for x in drinks):
        await message.add_reaction("🍺")

    church = ["church", "heavenly father", "pray"]
    if any(x in lower for x in church):
        await message.add_reaction("\N{CHURCH}")

    crown = ["bezos", "elon"]
    if any(x in lower for x in crown):
        await message.add_reaction("👑")

    quote_save(message)

client.run(TOKEN)
