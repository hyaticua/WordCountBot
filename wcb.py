import discord

# TODO
# - store last read message timestamps so bot can more intelligently scan for missed messages
# - issue rescan on shutdown/restart
# - save state to JSON on shutdown, look for saved state on startup and reinit


root_user = 'hyaticua#1259'
version = '1.0.0_alpha'
bot_invocation_str = '!wcb'
default_watch_words = []

client = discord.Client()
guild_data_dict = {}

# =======================================
#   class defs
# =======================================

class AccessLevel:
    NONE = 0
    SERVER_MANAGER = 1
    ROOT = 2

class ScanState:
    NEEDS_SCAN = 0
    SCANNING = 1
    SCAN_COMPLETE = 2

class WatchWord:
    def __init__(self, word):
        self.word = word
        self.scan_state = ScanState.NEEDS_SCAN
        self.first_scanned = None
        self.last_scanned = None

class GuildData:
    def __init__(self, guild):
        self.guild = guild
        self.watch_words = {word: WatchWord(word) for word in default_watch_words}
        self.user_word_data = {}
    
    def add_word(self, word):
        if word not in self.watch_words:
            self.watch_words[word] = WatchWord(word)
        
    def remove_word(self, word):
        if word in self.watch_words:
            self.watch_words.remove(word)

    def get_watch_words(self):
        return self.watch_words.keys()

    async def scan_message_history(self):
        words_to_scan = []

        for _, word_data in self.watch_words.items():
            if word_data.scan_state == ScanState.NEEDS_SCAN:
                word_data.scan_state = ScanState.SCANNING
                words_to_scan.append(word_data)

        for channel in self.guild.text_channels:
            async for message in channel.history(limit=None, oldest_first=True):
                check_for_watch_words(message, self.guild, words_to_scan)

        for word_data in words_to_scan:
            word_data.scan_state = ScanState.SCAN_COMPLETE

class UserWordData:
    def __init__(self, word):
        self.word = word
        self.msgs = []
        self.count = 0

    def add(self, message_id, num_instances):
        if message_id not in self.msgs:
            self.msgs.append(message_id)
            self.count = self.count + num_instances

class Command:
    def __init__(self, name, description, func, additional_syntax=None, num_args=0, minimum_access_level=AccessLevel.NONE):
        self.name = name
        self.description = description
        self.additional_syntax = additional_syntax
        self.func = func
        self.num_args = num_args
        self.minimum_access_level = minimum_access_level
        self.help_str = None

    async def execute(self, message, tokens):
        if self.minimum_access_level > AccessLevel.NONE:
            user_level = get_user_access_level(message.author)
            if self.minimum_access_level > user_level:
                await message.channel.send('Error: user does not have permission to execute command')
                return False
        return await self.func(message, tokens)
    
    @property
    def help(self):
        # lazy construct help_str
        if self.help_str is None:
            cmd_example = f'{bot_invocation_str} {self.name}'
            if self.additional_syntax:
                cmd_example = cmd_example + f' *{self.additional_syntax}*'
            self.help_str = f'**{self.name}** - {self.description}\n{cmd_example}\n\n'
        return self.help_str


# =======================================
#   util functions
# =======================================

def check_for_watch_words(message, guild, watch_words):
    if message.content.startswith(bot_invocation_str):
        return

    if message.author == client.user:
        return

    guild_data = guild_data_dict[guild]
    user_word_data = guild_data.user_word_data

    normalized_str = message.content.replace(' ', '').lower()

    for word_data in watch_words:
        word = word_data.word
        if word in normalized_str:
            if message.author not in user_word_data:
                user_word_data[message.author] = {}
            if word not in user_word_data[message.author]:
                user_word_data[message.author][word] = UserWordData(word)
            
            count = normalized_str.count(word)
            user_word_data[message.author][word].add(message.id, count)

async def send_status(channel, user, word):
    count = 0
    guild_data = guild_data_dict[channel.guild]
    user_word_data = guild_data.user_word_data

    if user in user_word_data:
        if word in user_word_data[user]:
            word_data = user_word_data[user][word]
            count = word_data.count
    await channel.send(f'{user.display_name} has said {word} {count} times!')

def parse_user_from_msg(guild, msg):
    if '<@!' in msg:
        start = msg.find('<@!') + 3
        end = msg.find('>', start)
        member = guild.get_member(int(msg[start:end]))
        return member
    return None

def get_user_fullname(user):
    return f'{user.name}#{user.discriminator}'

def is_server_manager(user):
    print(user.guild_permissions.manage_guild)

def is_root_user(user):
    return root_user == get_user_fullname(user)
    
def get_user_access_level(user):
    if is_root_user(user):
        return AccessLevel.ROOT
    elif is_server_manager(user):
        return AccessLevel.SERVER_MANAGER
    else:
        return AccessLevel.NONE


# =======================================
#   bot commands
# =======================================

async def count_func(message, tokens):
    word = tokens[2]
    mention = tokens[3]

    guild = message.guild
    guild_data = guild_data_dict[guild]

    if word not in guild_data.watch_words:
        await message.channel.send(f'Error: not indexing word "{word}"')
        return False

    user = parse_user_from_msg(guild, mention)
    if user:
        await send_status(message.channel, user, word)

    return True


async def add_word_func(message, tokens):
    word = tokens[2]

    guild = message.guild
    guild_data = guild_data_dict[guild]

    if word in guild_data.watch_words:
        await message.channel.send(f'Error: already indexing *{word}*')
        return False

    await message.channel.send(f'Adding watch word *{word}*')
    guild_data.add_word(word)
    await guild_data.scan_message_history()

    return True


async def remove_word_func(message, tokens):
    word = tokens[2]

    guild = message.guild
    guild_data = guild_data_dict[guild]

    if word not in guild_data.watch_words:
        await message.channel.send(f'Error: not indexing "{word}"')
        return False

    guild_data.remove_word(word)
    await message.channel.send(f'Removed watch word *{word}*')
    return True

async def list_words_func(message, tokens):
    guild = message.guild
    guild_data = guild_data_dict[guild]

    word_list = ['Watch words:']
    for word in guild_data.watch_words.keys():
        word_list.append(word)

    word_list_str = '\n'.join(word_list)
    await message.channel.send(word_list_str)
    return True

async def help_func(message, tokens):
    msg_to_send = None

    if len(tokens) == 3:
        requested_cmd = tokens[2]
        if requested_cmd in commands:
            msg_to_send = commands[requested_cmd].help
        else:
            msg_to_send = 'Error: command not found'
    else:
        # display generic help message
        lines = []
        lines.append(f'Word Count Bot v{version}\nAvailable Commands:\n\n')
        for _, cmd in commands.items():
            lines.append(cmd.help)
        msg_to_send = ''.join(lines)
    
    if msg_to_send:
        await message.channel.send(msg_to_send)

async def about_func(message, tokens):
    about_str = f'Word Count Bot v{version} by hyaticua'
    await message.channel.send(about_str)

commands = {
    'count' : Command(name='count',
                      description='Display a count of how many times user has said a watch word',
                      func=count_func,
                      additional_syntax='word @user',
                      num_args=2),
    'add'   : Command(name='add',
                      description='Add a watch word to be indexed by the bot', 
                      func=add_word_func,
                      additional_syntax='word',
                      num_args=1,
                      minimum_access_level=AccessLevel.SERVER_MANAGER),
    'remove': Command(name='remove',
                      description='Remove a watch word from the bot', 
                      func=remove_word_func,
                      additional_syntax='word',
                      num_args=1,
                      minimum_access_level=AccessLevel.SERVER_MANAGER),
    'list'  : Command(name='list',
                      description='List all words that are watched by the bot',
                      func=list_words_func),
    'help'  : Command(name='help',
                      description='Get help for a command',
                      additional_syntax='command',
                      func=help_func),
    'about' : Command(name='about',
                      description='About this bot',
                      func=about_func),
}


# =======================================
#   discord events
# =======================================

@client.event
async def on_ready():
    print('We have logged in as {0.user}'.format(client))

    for guild in client.guilds:
        if guild not in guild_data_dict:
            guild_data_dict[guild] = GuildData(guild)

    for guild, guild_data in guild_data_dict.items():
        await guild_data.scan_message_history()

@client.event
async def on_guild_join(guild):
    if guild not in guild_data_dict:
        guild_data_dict[guild] = GuildData(guild)
    await guild_data_dict[guild].scan_message_history()

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    is_bot_msg = False

    if message.content.startswith(bot_invocation_str):
        is_bot_msg = True
        tokens = message.content.split(' ')

        if len(tokens) < 2: return
        
        cmd_str = tokens[1]

        if cmd_str not in commands:
            # send error about bad command
            return
            
        cmd = commands[cmd_str]

        if cmd.num_args > 0 and cmd.num_args != len(tokens) - 2:  # account for '!wcb' and 'cmd'
            # send error about bad args
            return

        await cmd.execute(message, tokens)

    if is_bot_msg:
        return

    guild_data = guild_data_dict[message.guild]
    check_for_watch_words(message, message.guild, guild_data.watch_words)



client.run('secret_key_goes_here')
