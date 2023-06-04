import discord
from discord.ext import tasks
from discord.ext import commands
import re
import emoji
import os
from gtts import gTTS

prefix = "?"


class Help(commands.DefaultHelpCommand):
    def __init__(self):
        super().__init__()
        self.commands_heading = "Commands:"
        self.no_category = "Others"
        self.command_attrs["help"] = "コマンド一覧を表示"

    def get_ending_note(self):
        return f"各コマンドの説明: {prefix}help <コマンド名>\n" f"各カテゴリの説明: {prefix}help <カテゴリ名>\n"


intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=prefix, intents=intents, help_command=Help())

# 除外用の正規表現
url_pattern = re.compile("https?://[\w/:%#\$&\?\(\)~\.=\+\-]+")

emoji_pattern = re.compile(":[a-zA-Z0-9_]+:")

can_read = re.compile(
    "[a-zA-Zａ-ｚＡ-Ｚ0-9０-９\u3041-\u309F\u30A1-\u30FF\uFF66-\uFF9F\u2E80-\u2FDF\u3005-\u3007\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF\U00020000-\U0002EBEF]+"
)


# メッセージのクラス
# author, text
class MSG:
    def __init__(self, author, text):
        self.author = author
        self.text = text


# 読み上げ音声を作成
def create_audio(text):
    tts = gTTS(text, lang="ja")
    tts.save("out.mp3")


# 絵文字除去
def remove_emoji(text):
    return emoji.replace_emoji(text)


# 今いるvoice_channelのid
vc_id = -1

# 名前呼びの時間
timer = 0

# 前読んだ名前
pre_name = ""

# 読み上げるメッセージのリスト
msg_list = []


@bot.event
async def on_ready():
    # 起動したらターミナルにログイン通知が表示される
    print(f"ログインしました")

    await bot.add_cog(Cogs(bot))

    loop.start()


@tasks.loop(seconds=0.1)
async def loop():
    global vc_id
    global timer
    global pre_name

    # エラー回避もろもろ
    if not bot.is_ready():
        print("waiting...")

    await bot.wait_until_ready()

    guild = bot.get_guild(int(os.environ["guild_id"]))

    if guild is None:
        return
    if not msg_list:
        return
    if guild.voice_client is None:
        vc_id = -1
        return
    if guild.voice_client.is_playing():
        return

    if timer >= 0:
        timer -= 1

    # 時間が余っていてかつ前回の名前と同じなら省略
    if timer >= 0 and pre_name == msg_list[0].author:
        pass
    # システム系なら省略
    elif msg_list[0].author == "":
        pass
    # そうでないなら名前を読み上げて時間をリセットして名前を読み上げる
    else:
        timer = int(os.environ["default_waiting_time"])
        pre_name = msg_list[0].author
        msg_list[0].text = f"{msg_list[0].author}が発言,,,,{msg_list[0].text}"

    # 読むメッセージをターミナルへ
    print(f"[読み上げ]\n{msg_list[0].text}")

    create_audio(msg_list[0].text)
    del msg_list[0]
    guild.voice_client.play(discord.FFmpegPCMAudio("out.mp3"))


class Cogs(commands.Cog, name="Commands"):
    def __init__(self, bot):
        self.bot = bot

    # チャンネル入出時の通知
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.id == int(os.environ["bot_id"]):
            return

        if member.guild.voice_client is None:
            return

        # ミュートなどを無視
        if before.channel == after.channel:
            return

        if after.channel is None:
            if before.channel.id == vc_id:
                print("退出を検知")
                msg_list.append(MSG("", f"{member.display_name}が退出しました"))

        # 　入室時
        elif after.channel.id == vc_id:
            print("入室を検知")
            msg_list.append(MSG("", f"{member.display_name}が入室しました"))
            # タイマーリセット
            timer = int(os.environ["default_waiting_time"])

        elif before.channel is None:
            return

        elif before.channel.id == vc_id and after.channel.id != vc_id:
            print("移動を検知")
            msg_list.append(MSG("", f"{member.display_name}がチャンネルを移動しました"))

    # メッセージ受信時
    @commands.Cog.listener()
    async def on_message(self, message):
        global vc_id
        global msg_list

        # メッセージ送信者がBotだった場合は無視する
        if message.author.bot:
            return

        # コマンドを除外
        if message.content[0] == prefix:
            pass
        else:
            # 読むチャンネルでフィルタリング
            if message.channel.id == int(os.environ["read_channel_id"]):
                # ボイスチャンネルに入っていないなら読まない
                if message.guild.voice_client is None:
                    return

                msg = MSG(message.author.display_name, message.content)

                # 改行を消す
                msg.text = msg.text.replace("\n", ",,,,")

                # URLは省略
                msg.text = url_pattern.sub("", msg.text)

                # 絵文字は省略
                msg.text = remove_emoji(msg.text)

                # メッセージに読める文字が含まれていない場合は終了
                if can_read.search(msg.text) is None:
                    return

                msg_list.append(msg)

    # 各種コマンド
    @commands.command(name="join")
    async def _join(self, ctx):
        """ボイスチャンネルに参加"""
        global vc_id
        global msg_list

        # 送信者がボイスチャンネルに接続していない場合
        if ctx.author.voice is None:
            await ctx.channel.send("あなたはボイスチャンネルに接続していません")
            return

        # ボイスチャンネルに接続していない場合そのまま接続
        if ctx.guild.voice_client is None:
            await ctx.author.voice.channel.connect()

        # 同じチャンネルの場合
        elif ctx.author.voice.channel.id == vc_id:
            return

        # チャンネルの移動
        else:
            await ctx.channel.send("既に他のボイスチャンネルにいます")
            print("既に他のボイスチャンネルにいます")
            return

        print(f"ボイスチャンネル{ctx.author.voice.channel.name}に接続しました")

        vc_id = ctx.author.voice.channel.id
        # メッセージをリストに追加
        msg_list.append(MSG("", "こんにちは, 読み上げbotです"))

    @commands.command(name="bye")
    async def _bye(self, ctx):
        """ボイスチャンネルから切断"""
        global vc_id
        global msg_list
        if ctx.guild.voice_client is None:
            return

        # メッセージリストを消し音声再生中なら中断
        msg_list.clear()
        if ctx.guild.voice_client.is_playing():
            ctx.guild.voice_client.stop()

        await ctx.guild.voice_client.disconnect()

        await ctx.channel.send("ボイスチャンネルから退出しました")
        vc_id = -1
        print("ボイスチャンネルから退出しました")

    @commands.command(name="read")
    async def _read(self, ctx):
        """読むチャンネルを指定"""
        global vc_id
        global msg_list
        os.environ["read_channel_id"] = str(ctx.channel.id)
        print(f"読み上げるチャンネルが{ctx.channel.name}になりました")
        await ctx.channel.send("このチャンネルを読み上げます")

    @commands.command(name="where")
    async def _where(self, ctx):
        """読むチャンネルを取得"""
        global vc_id
        global msg_list
        channel = ctx.guild.get_channel(int(os.environ["read_channel_id"]))
        # チャンネルが見つからなかった場合
        if channel is None:
            await ctx.channel.send("今はどこも読み上げません")
        else:
            await ctx.channel.send(f"テキストチャンネル{channel.name}を読み上げます")


# Botの起動とDiscordサーバーへの接続
bot.run(os.environ["DISCORD_TOKEN"])
