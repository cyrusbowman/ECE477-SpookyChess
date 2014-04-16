#!/usr/bin/env python
# -*- coding: utf-8 -*-
############################################################
# (c) Marcin Kasperski, 2008
############################################################
# Example FICS bot code
############################################################

############################################################
# Configuration
############################################################


from twisted.internet import stdio, reactor
from twisted.protocols import basic
from twisted.web import client


"""    def lineReceived(self, line):
        # Ignore blank lines
        if not line: return

        # Parse the command
        commandParts = line.split()
        command = commandParts[0].lower()
        args = commandParts[1:]

        # Dispatch the command to the appropriate method.  Note that all you
        # need to do to implement a new command is add another do_* method.
        try:
            method = getattr(self, 'do_' + command)
        except AttributeError, e:
            self.sendLine('Error: no such command.')
        else:
            try:
                method(*args)
            except Exception, e:
                self.sendLine('Error: ' + str(e))

    def do_help(self, command=None):
        #help [command]: List commands, or show help on the given command
        if command:
            self.sendLine(getattr(self, 'do_' + command).__doc__)
        else:
            commands = [cmd[3:] for cmd in dir(self) if cmd.startswith('do_')]
            self.sendLine("Valid commands: " +" ".join(commands))

    def do_quit(self):
        #quit: Quit this session
        self.sendLine('Goodbye.')
        self.transport.loseConnection()
        
    def do_check(self, url):
        #check <url>: Attempt to download the given web page
        client.getPage(url).addCallback(
            self.__checkSuccess).addErrback(
            self.__checkFailure)

    def do_send(self):
        print "Ready to play!"
	self.handler.protocol.runCommand("players")

    def __checkSuccess(self, pageData):
        self.sendLine("Success: got %i bytes." % len(pageData))

    def __checkFailure(self, failure):
        self.sendLine("Failure: " + failure.getErrorMessage())

    def connectionLost(self, reason):
        # stop the reactor, only because this is meant to be run in Stdio.
        reactor.stop()
"""

FICS_HOST = 'freechess.org'
FICS_PORT = 5000

FICS_USERNAME = 'RaspiChessbot'
FICS_PASSWORD = 'udrbod'

# Automatically stop after that many minutes (don't leave
# the testing code running forever)
STOP_AFTER = 15

CONTACT_USER = 'RaspiChessbot'

FINGER_TEXT = """
Early implementation of a physical chessboard playable through the FICS system. This is a work in progress, so be patient with us!
""" % locals()

PROTECT_LOGOUT_FREQ = 45

SAVE_FILE = "registered.players"

IGNORED_PLAYERS = ['RoboAdmin', 'Mamer', 'Relay']

LOG_COMMUNICATION = True

READY_TO_PLAY = False

############################################################
# Imports
############################################################

from twisted.internet import reactor, defer, protocol, task
from twisted.protocols import basic
from twisted.python import log as twisted_log
import re, sys, sets

############################################################
# Logging setup
############################################################

# Initialise Twisted logging. Here - to the console
twisted_log.startLogging(sys.stdout)

############################################################
# Small helper functions
############################################################

re_empty = re.compile("^[\s\r\n]*$")
def is_empty(text):
    """
    """
    return re_empty.match(text) and True or False

IGNORED_PLAYERS_SET = sets.Set([ x.lower() for x in IGNORED_PLAYERS])

def is_player_ignored(who):
    return who.lower() in IGNORED_PLAYERS_SET

############################################################
# Saving registration info
############################################################

def register_player(who, rating):
    """
    Saving info that player who of rating rating registered.
    Here - oversimplistic procedure, we just append a line
    to the file.
    """
    twisted_log.msg("Registering player %(who)s with rating %(rating)d"
                    % locals())
    # Note no race condition which could happen in multithreaded
    # apps
    f = file(SAVE_FILE, "a")
    f.write("%(who)s: %(rating)d\n" % locals())
    f.close()

############################################################
# Regexp gallery.
############################################################

# Command(s) the bot is handling

re_cmd_join = re.compile("^\s*join\s*$")

# Login process support

re_login = re.compile(
    '([Uu]ser|[Ll]ogin):')
re_password = re.compile(
    '[Pp]assword:')
re_guestlogin = re.compile(
    r"Press return to enter the (?:server|FICS) as \"([^\"]*)\"")
re_normallogin = re.compile(
    r"Starting FICS session as ([a-zA-Z0-9]+)")

# Block mode support

BLOCK_START = chr(21)        # \U
BLOCK_SEPARATOR = chr(22)    # \V
BLOCK_END = chr(23)          # \W

re_block_reply_start = re.compile(
    BLOCK_START + r"(\d+)" + BLOCK_SEPARATOR + r"(\d+)" + BLOCK_SEPARATOR)
re_block_reply_end = re.compile(BLOCK_END)

# FICS notifications we care about

re_tell = re.compile(r"""
^
(?P<who>[^\s()]+)    # Johny
(?:\(\S+\))*         # (TD)(TM)(SR) etc
\stells\syou:\s      #  tells you:
(?P<what>.*)         # blah blah
$
""", re.VERBOSE)

# Extracting info from finger command reply

re_finger_not_played = re.compile(
    "has not played any rated games")
re_finger_std_rating = re.compile(
    "^Standard\s+(\d+)", re.MULTILINE + re.IGNORECASE)

############################################################
# Handler (hooks for true code)
############################################################

class MyHandler(object):
    """
    The class where we put the actual bot code (our functions)
    """

    def __init__(self):
        self._bad_tells = {}
        # We will set this variable in FicsFactory, while
        # making association between handler and protocol
        self.protocol = None

    ########################################################
    # Protocol callbacks
    ########################################################

    def onTell(self, who, what):
         """
         Called whenever we obtain a tell
         """
         if is_player_ignored(who):
             return

         if re_cmd_join.match(what):
             self.processJoin(who)
             return

         # Bad command handling
         c = self._bad_tells.get(who, 0) + 1
         self._bad_tells[who] = c
         if c <= 3:
             self.protocol.runCommand(
                 "tell %(who)s I do not understand your command" % locals())
             return
         else:
             twisted_log.err("More than 3 mistakes from %(who)s, ignoring his wrong command" % locals())

    ########################################################
    # Utility functions
    ########################################################

    @defer.inlineCallbacks
    def processJoin(self, who):
        """
        Called when we receive join request. We use
        finger to grab the user rating, then save
        his or her data.
        """
        finger_data = yield self.protocol.runCommand(
            "finger %(who)s /s r" % dict(who=who),
            )
        rating = None
        m = re_finger_std_rating.search(finger_data)
        if m:
            rating = int(m.group(1))
        elif re_finger_not_played.search(finger_data):
            rating = 0
        else:
            twisted_log.err("Can't detect rating of %(who)s" % locals())
            rating = 0
        register_player(who, rating)
        yield self.protocol.runCommand(
            "tell %(who)s You are registered with rating %(rating)d" % locals())


############################################################
# Protocol (technical details of FICS connection)
############################################################

class FicsProtocol(basic.LineReceiver): # overloading the basic.LineReceiver class
    """
    Wrapper for technical details of FICS connection.
    LineReceiver handles telnet for us, in this class
    we handle login process, issue commands and grab
    their results, interpret FICS notifications.
    """

    prompt = 'fics%'

    def __init__(self):
        # To be set later
        self.handler = None

    ##################################################
    # Login and post-login initialization
    ##################################################

    def connectionMade(self):
        twisted_log.msg("TCP connection made to the server")
        self.delimiter = "\n\r"
        self._inReply = None
        self._keepAlive = None
        self.setRawMode()

    def connectionLost(self, reason):
        twisted_log.msg("Connection lost " + str(reason))
        if self._keepAlive:
            self._keepAlive.stop()
            self._keepAlive = None

    def rawDataReceived(self, data):
        """
        Raw telnet data obtained. We use this mode only while
        logging in, later on we switch to the line mode.
        """
        if LOG_COMMUNICATION:
            twisted_log.msg("Raw data received: %s" % data)
        if re_login.search(data):
            self.sendLine(FICS_USERNAME)
            return
        if re_password.search(data):
            self.sendLine(FICS_PASSWORD)
            return
        name = self.checkIfLogged(data)
        if name:
            self.user = name
            self.setLineMode()
            twisted_log.msg("Logged in as %s" % name)
            self.loggedIn()

    def checkIfLogged(self, data):
        if FICS_PASSWORD:
            m = re_normallogin.search(data)
            if m:
                return m.group(1)
        else:
            m = re_guestlogin.search(data)
            if m:
                self.sendLine("")
                return m.group(1)
        return None

    def loggedIn(self):
        """
        Just logged in. Initialization
        """
        # Internal list of callbacks for future commands
        self._reply_deferreds = []

        self.sendLine("iset defprompt 1")
        self.sendLine("iset nowrap 1")

        self.sendLine("set interface PythonCodeFollowingMekkTutorial")
        self.sendLine("set open 0")
        self.sendLine("set shout 0")
        self.sendLine("set cshout 0")
        self.sendLine("set seek 0")
        # self.sendLine("tell 0")  # guest tells
        self.sendLine("set gin 0")
        self.sendLine("set pin 0")
        self.sendLine("- channel 53")

        # finger
        finger = FINGER_TEXT.split("\n")[1:]
        for no in range(0, 10):
            text = (no < len(finger)) and finger[no] or ""
            self.sendLine("set %d %s" % (no+1, text))

        # Enable block mode
        self.sendLine("iset block 1")

        # Setup 
        if PROTECT_LOGOUT_FREQ:
            def _keep_alive_fun():
                self.runCommand("date")
            self._keep_alive = task.LoopingCall(_keep_alive_fun)
            self._keep_alive.start(PROTECT_LOGOUT_FREQ * 60)
        else:
            self._keep_alive = None

	# Enable external commands
	READY_TO_PLAY = True
	

    ##################################################
    # Normal works
    ##################################################

    def lineReceived(self, line):
        """
        Called whenever we obtain a line of text from FICS
        """
        if LOG_COMMUNICATION:
            twisted_log.msg("Received line: %s" % line)

        if self._inReply:
            n = re_block_reply_end.search(line)
            if n:
                (id, code, text) = self._inReply
                self._inReply = None
                self.handleCommandReply(id, code,
                                        text + "\n" + line[:n.start()])
            else:
                self._inReply = (self._inReply[0], self._inReply[1],
                                 self._inReply[2] + "\n" + line)
            return

        if line.startswith(self.prompt+' '):
            line = line[len(self.prompt)+1:]
        if is_empty(line):
            return

        m = re_block_reply_start.match(line)
        if m:
            id = m.group(1)
            code = m.group(2)
            text = line[m.end():]
            n = re_block_reply_end.search(text)
            if n:
                self.handleCommandReply(id, code, text[:n.start()])
            else:
                self._inReply = (id, code, text)
            return

        self.parseNormalLine(line)

    def parseNormalLine(self, line):
        """
        Here we parse the normal FICS-initiated notification.
        """

        m  = re_tell.match(line)
        if m:
            return self.handler.onTell(who = m.group('who'), what = m.group('what'))
        # Good place to add other events handling

    def runCommand(self, command):
        """
        Sends given command to FICS.

        Returns deferred which will be fired with the command result
        (given as text) - once it is obtained.
        """
        # Allocate spare command id
        l = len(self._reply_deferreds)
        id = l
        for i in range(0, l):
            if not self._reply_deferreds[i]:
                id = i
                break

        # Issue the command 
        self.sendLine('%d %s' % (id+1, command))

        # Crate the resulting deferred and save it. We will
        # fire it from handleCommandReply.
        d = defer.Deferred()
        if id == l:
            self._reply_deferreds.append(d)
        else:
            self._reply_deferreds[id] = d

        twisted_log.msg("CommandSend(%d, %s)" % (id+1, command))
        return d

    def handleCommandReply(self, id, code, text):
        """
        We just obtained reply to the command identified by id.
        So we locate the callback registered to handle it, and call it.
        """
        # code is a command code, we don't use it currently
        reply_deferred = None
        pos = int(id) - 1
        if pos >= 0:
            reply_deferred = self._reply_deferreds[pos]
            self._reply_deferreds[pos]=None
        twisted_log.msg("CommandReply(%s, %s)" % (id, text))
        if not reply_deferred is None:
            return reply_deferred.callback(text)


############################################################
# Factory (connection management)
############################################################

class FicsFactory(protocol.ReconnectingClientFactory): # overloading the protocol.ReconnectingClientFactory class
    """
    By using ReconnectingClientFactory we re-connect
    every time we get disconnected from FICS.
    """
    def __init__(self, handler):
        self.handler = handler
        # ReconettingClientFactory settings
        self.maxDelay = 180
        self.noisy = True
    def buildProtocol(self, addr):
        twisted_log.msg("Connected to the server")
        self.resetDelay()  # reconnection delay
        self.protocol = FicsProtocol()
        self.protocol.handler = self.handler
        self.handler.protocol = self.protocol
        return self.protocol

############################################################
# Main
############################################################

# check connectivity
handler = MyHandler()
stdio.StandardIO(IOHandler(handler))

reactor.connectTCP(FICS_HOST, FICS_PORT, 
                   FicsFactory(handler))
if STOP_AFTER:
    reactor.callLater(STOP_AFTER * 60, reactor.stop)

reactor.run()
	



