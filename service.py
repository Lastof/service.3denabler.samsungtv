'''
    3D Enabler [for] Samsung TV - addon for XBMC to enable 3D mode
    Copyright (C) 2014  Pavel Kuzub

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
'''

import os
import sys
import xbmc
import xbmcgui
import xbmcaddon
import simplejson
import socket
import re
import urllib2
from xml.dom.minidom import parseString
import base64
import uuid
import select
import requests

__addon__   = xbmcaddon.Addon()
libs = os.path.join(__addon__.getAddonInfo('path'), 'lib')
sys.path.append(libs)

import ssdp

ssdpModeMap = [
        'ssdp:all',
        'urn:schemas-sony-com:service:IRCC:1',
        'urn:schemas-sony-com:service:ScalarWebAPI:1'
    ]

def xbmclog(text, level=0):
    xbmc.log("SonyTVEnabler: "+text, level)

class Settings(object):
    def __init__(self):
        self.enabled        = True
        self.discover       = True
        self.ipaddress      = ''
        self.port           = 52323
        self.commands       = {}
        self.tvname         = ''
        self.authCookie     = ''
        self.pause          = True
        self.black          = True
        self.notifications  = True
        self.notifymessage  = ''
        self.sock           = False
        self.authCount      = 0
        self.pollCount      = 0
        self.curTVmode      = 0
        self.newTVmode      = 0
        self.ssdpmode       = 1
        self.detectmode     = 0
        self.pollsec        = 5
        self.idlesec        = 5
        self.inProgress     = False
        self.inScreensaver  = False
        self.skipInScreensaver  = True
        self.addonname      = __addon__.getAddonInfo('name')
        self.icon           = __addon__.getAddonInfo('icon')
        self.positionOff    = 1
        self.positionSBS    = 2
        self.positionOU     = 3
        self.sequenceBegin  = 'BLACKON,PAUSE,MODE3D,P1000'
        self.sequenceEnd    = 'CONFIRM,P1000,BLACKOFF,PLAY'
        self.remotename     = '3D Enabler'
        self.checkOnKey     = 'Mute'
        self.checkOffKey    = 'Mute'
        self.check          = True
        self.load()

    def getSetting(self, name, dataType = str):
        value = __addon__.getSetting(name)
        if dataType == bool:
            if value.lower() == 'true':
                value = True
            else:
                value = False
        elif dataType == int:
            try:
                value = int(value)
            except:
                value = 0
        elif dataType == dict:
            try:
                value = simplejson.loads(value)
            except:
                value = {}
        else:
            value = str(value)
        xbmclog('getSetting:' + str(name) + '=' + str(value), xbmc.LOGDEBUG)
        return value

    def setSetting(self, name, value):
        if type(value) == bool:
            if value:
                value = 'true'
            else:
                value = 'false'
        elif type(value) == dict:
            value = simplejson.dumps(value)
        else:
            value = str(value)
        xbmclog('setSetting:' + str(name) + '=' + str(value), xbmc.LOGDEBUG)
        __addon__.setSetting(name, value)

    def getLocalizedString(self, stringid):
        return __addon__.getLocalizedString(stringid)

    def load(self):
        xbmclog('loading Settings', xbmc.LOGINFO)
        self.enabled            = self.getSetting('enabled', bool)
        self.discover           = self.getSetting('discover', bool)
        self.ipaddress          = self.getSetting('ipaddress', str)
        self.tvname             = self.getSetting('tvname', str)
        self.port               = self.getSetting('port', int)
        self.authCookie         = self.getSetting('authCookie', str)
        self.pause              = self.getSetting('pause', bool)
        self.black              = self.getSetting('black', bool)
        self.notifications      = self.getSetting('notifications', bool)
        self.curTVmode          = self.getSetting('curTVmode', int)
        self.ssdpmode           = self.getSetting('ssdpmode', int)
        self.detectmode         = self.getSetting('detectmode', int)
        self.pollsec            = self.getSetting('pollsec', int)
        self.idlesec            = self.getSetting('idlesec', int)
        self.skipInScreensaver  = self.getSetting('skipInScreensaver', bool)
        self.sequence3DTAB      = self.getSetting('sequence3DTAB', str)
        self.sequence3DSBS      = self.getSetting('sequence3DSBS', str)
        self.sequence3Dnone     = self.getSetting('sequence3Dnone', str)
        self.commands           = self.getSetting('commands', dict)
        self.checkOnKey         = self.getSetting('checkOnKey', str)
        self.checkOffKey        = self.getSetting('checkOffKey', str)
        self.positionOff        = self.getSetting('positionOff', int)
        self.positionSBS        = self.getSetting('positionSBS', int)
        self.positionOU         = self.getSetting('positionOU', int)

def toNotify(message):
    if len(settings.notifymessage) == 0:
        settings.notifymessage = message
    else:
        settings.notifymessage += '. ' + message

def notify(timeout = 5000):
    if len(settings.notifymessage) == 0:
        return
    if settings.notifications:
        xbmc.executebuiltin('Notification(%s, %s, %d, %s)'%(settings.addonname, settings.notifymessage, timeout, settings.icon))
    xbmclog('NOTIFY: ' + settings.notifymessage, xbmc.LOGINFO)
    settings.notifymessage = ''

def getStereoscopicMode():
    query = '{"jsonrpc": "2.0", "method": "GUI.GetProperties", "params": {"properties": ["stereoscopicmode"]}, "id": 1}'
    result = xbmc.executeJSONRPC(query)
    json = simplejson.loads(result)
    xbmclog('Received JSON response: ' + str(json), xbmc.LOGDEBUG)
    ret = 'unknown'
    if json.has_key('result'):
        if json['result'].has_key('stereoscopicmode'):
            if json['result']['stereoscopicmode'].has_key('mode'):
                ret = json['result']['stereoscopicmode']['mode'].encode('utf-8')
    # "off", "split_vertical", "split_horizontal", "row_interleaved"
    # "hardware_based", "anaglyph_cyan_red", "anaglyph_green_magenta", "monoscopic"
    return ret

def getTranslatedStereoscopicMode():
    mode = getStereoscopicMode()
    xbmclog(mode)
    if mode == 'split_horizontal': return 1
    elif mode == 'split_vertical': return 2
    else: return 0

def stereoModeHasChanged():
    if settings.curTVmode != settings.newTVmode:
        return True
    else:
        return False

def getIPfromString(string):
    try:
        return re.search("(\d{1,3}\.){3}\d{1,3}", string).group()
    except:
        return ''

def getPortFromString(string):
    try:
        return int(re.search("(?<=\:)(\d{2,5})", string).group())
    except:
        return ''

# Discover Sony TV. If more than one detected - choose one from the list 
# To match all devices use ssdp.discover('ssdp:all')
def discoverTVip():
    tvdevices = []
    tvdevicesIPs = []
    tvdevicesNames = []
    discoverCount = 0
    while True:
        discoverCount += 1
        dicovered = ssdp.discover(ssdpModeMap[settings.ssdpmode])
        if xbmc.abortRequested: break
        if len(dicovered) > 0: break
        if discoverCount > 2: break
        
    for tvdevice in dicovered:
        tvXMLloc = tvdevice.location
        xbmclog('tvXMLloc: ' + str(tvXMLloc), xbmc.LOGDEBUG)
        tvip = getIPfromString(tvXMLloc)
        port = getPortFromString(tvXMLloc)
        if tvip:
            xbmclog('tvip: ' + str(tvip), xbmc.LOGDEBUG)
            tvFriendlyName = settings.getLocalizedString(30503) #Unknown
            try:
                tvXML = urllib2.urlopen(tvXMLloc).read()
                xbmclog('tvXML: ' + str(tvXML), xbmc.LOGDEBUG)
                tvXMLdom = parseString(tvXML)
                tvFriendlyName = tvXMLdom.getElementsByTagName('friendlyName')[0].childNodes[0].toxml()
            except urllib2.HTTPError as e:
                if e.code == 401:
                    # If Remote Access has been denied - we cannot even read the description
                    tvFriendlyName = settings.getLocalizedString(30501) #Access Denied. Check Permissions
                else:
                    toNotify(settings.getLocalizedString(30502) + ' ' + str(e))
                    xbmclog('HTTP Error ' + str(e), xbmc.LOGERROR)
            except:
                xbmclog('Exception getting friendly name', xbmc.LOGERROR)
            if tvip not in tvdevicesIPs:
                tvdevicesIPs.append(tvip)
                tvdevicesNames.append(tvFriendlyName + ' @ ' + tvip)
                tvdevices.append([tvip, tvFriendlyName, port])
    
    xbmclog('Discovered devices count: ' + str(len(tvdevices)), xbmc.LOGINFO)
        
    if len(tvdevices) > 1:
        myselect = dialog.select(settings.getLocalizedString(30514), tvdevicesNames) #Select your TV device
        toNotify(settings.getLocalizedString(30504) + ': ' + str(tvdevices[myselect][1])) #Discovered TV
        return tvdevices[myselect]
    elif len(tvdevices) == 1:
        toNotify(settings.getLocalizedString(30504) + ': ' + str(tvdevices[0][1])) #Discovered TV
        return tvdevices[0]
    else:
        toNotify(settings.getLocalizedString(30505)) #Samsung TV is not detected
        return []

def getRemoteSignals(tvip):
    if bool(tvip):
        try:
            returnedCommands = jsonRequest("http://"+settings.ipaddress+"/sony/system", {"id":1,"method":"getRemoteControllerInfo","version":"1.0","params":[]}).json()['result'][1]
            commands = {}
            for command in returnedCommands:
                commands[command['name'].upper()] = command['value']
            settings.commands = commands
            settings.setSetting('commands', settings.commands)
            return True
        except:
            return False
    return False

# Function to send keys
def sendKey(key, ipaddress):
    if (settings.commands < 1):
        return False
    headers = {'Content-type' :'text/xml'}
    data = '<?xml version="1.0" encoding="utf-8"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:X_SendIRCC xmlns:u="urn:schemas-sony-com:service:IRCC:1"><IRCCCode>'+settings.commands[key.upper()]+'</IRCCCode></u:X_SendIRCC></s:Body></s:Envelope>'
    send = requests.post('http://'+ipaddress+'/sony/IRCC?', data=data, headers=headers, cookies=dict(auth=settings.authCookie))
    if send.status_code == 200:
        return True
    else:
        return False

def jsonRequest(url, data, cookie={}, auth=('','')):
    headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}
    xbmclog('JSON Request submitted to tv. URL: '+str(url)+', data: '+str(data), xbmc.LOGDEBUG)
    return requests.post(url, data=simplejson.dumps(data), headers=headers, cookies=cookie, auth=auth)

def checkAuth():
    if not bool(settings.authCookie):
        return False
    elif (settings.commands > 1) or (getRemoteSignals(settings.ipaddress)):
        if sendKey('Mute', settings.ipaddress):
            sendKey('Mute', settings.ipaddress)
            return True
    return False

def authenticate():
    if not settings.sock: return False
    # Are we already AUTHed?
    if bool(settings.authCookie) and checkAuth():
        xbmclog('Already AUTHed', xbmc.LOGDEBUG)
        return True
    # Submit auth request to TV
    if dialog.ok('Autenticating with '+settings.tvname, 'In a moment a PIN will appear on the TV screen. Enter this pin into the dialogue that appears here to authenticate. (The dialogue may be behind the PIN)'):
        startAuth = jsonRequest("http://"+settings.ipaddress+"/sony/accessControl", {"id":13,"method":"actRegister","version":"1.0","params":[{"clientid":xbmc.getInfoLabel('System.FriendlyName'),"nickname":xbmc.getInfoLabel('System.FriendlyName')},[{"clientid":xbmc.getInfoLabel('System.FriendlyName'),"value":"yes","nickname":xbmc.getInfoLabel('System.FriendlyName'),"function":"WOL"}]]})
        pin = dialog.numeric(0, 'Enter Autentication PIN')
        finishAuth = jsonRequest("http://"+settings.ipaddress+"/sony/accessControl", {"id":13,"method":"actRegister","version":"1.0","params":[{"clientid":xbmc.getInfoLabel('System.FriendlyName'),"nickname":xbmc.getInfoLabel('System.FriendlyName')},[{"clientid":xbmc.getInfoLabel('System.FriendlyName'),"value":"yes","nickname":xbmc.getInfoLabel('System.FriendlyName'),"function":"WOL"}]]}, auth=('', str(pin)))
        try:
            settings.authCookie = finishAuth.cookies['auth']
            settings.setSetting('authCookie', settings.authCookie)
        except:
            xbmclog('PIN Rejected', xbmc.LOGDEBUG)
            return False
    if checkAuth():
        return True
    return False

def newSock():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3)
    return sock

def connectTV():
    settings.ipaddress = getIPfromString(settings.ipaddress)
    if bool(settings.ipaddress):
        settings.sock = newSock()
        try:
            xbmclog('Connecting to:' + str(settings.ipaddress) + ':' + str(settings.port), xbmc.LOGDEBUG)
            settings.sock.connect((settings.ipaddress, settings.port))
            return True
        except:
            xbmclog('TV is Off or IP is outdated', xbmc.LOGINFO)
    if settings.discover:
        tv = discoverTVip()
        if tv:
            settings.sock = newSock()
            try:
                #toNotify('TV Port: '+str(ipaddress)+":"+str(tv[2]))
                xbmclog('Connecting to:' + str(tv[0]) + ':' + str(tv[2]), xbmc.LOGDEBUG)
                settings.sock.connect((tv[0], tv[2]))
                settings.ipaddress = tv[0]
                settings.tvname = tv[1]
                settings.port = tv[2]
                settings.setSetting('ipaddress', settings.ipaddress)
                settings.setSetting('tvname', settings.tvname)
                settings.setSetting('port', settings.port)
                return True
            except Exception as inst:
                xbmclog('TV is Off or IP/Port is outdated', xbmc.LOGINFO)
                toNotify(settings.getLocalizedString(30508)) #Connection Failed
        else:
            xbmclog('TV has not been discovered', xbmc.LOGINFO)
            toNotify(settings.getLocalizedString(30506)) #TV has not been discovered
    else:
        xbmclog('Cannot connect. Discovery is turned off', xbmc.LOGINFO)
        toNotify(settings.getLocalizedString(30507)) #Discovery is turned off
    return False

def processSequence(commandSequence):
    putOnPause = False
    # Parse commands and execute them
    for x in commandSequence.split(','):
        thisKey = x.strip().upper()
        if thisKey in settings.commands:
            xbmclog('Sending ' + thisKey + ' as Key: ' + settings.commands[thisKey], xbmc.LOGDEBUG)
            sendKey(thisKey,settings.ipaddress)
        elif thisKey == 'PAUSE':
            if settings.pause:
                if xbmc.Player().isPlayingVideo():
                    if not xbmc.getCondVisibility('Player.Paused'):
                        xbmclog('Pause XBMC', xbmc.LOGDEBUG)
                        xbmc.Player().pause()
                        putOnPause = True
        elif thisKey == 'PLAY':
            if settings.pause:
                if xbmc.Player().isPlayingVideo():
                    if xbmc.getCondVisibility('Player.Paused'):
                        xbmclog('Resume XBMC', xbmc.LOGDEBUG)
                        if putOnPause: xbmc.Player().pause()
        elif thisKey[:1] == 'P':
            xbmclog('Waiting for ' + thisKey[1:] + ' milliseconds', xbmc.LOGDEBUG)
            xbmc.sleep(int(thisKey[1:]))
        elif thisKey == 'BLACKON':
            if settings.black:
                xbmclog('Screen to Black', xbmc.LOGDEBUG)
                blackScreen.show()
        elif thisKey == 'BLACKOFF':
            if settings.black:
                xbmclog('Screen from Black', xbmc.LOGDEBUG)
                blackScreen.close()
        else:
            xbmclog('Unknown command: ' + thisKey, xbmc.LOGWARNING)
            getRemoteSignals(settings.ipaddress)
    xbmclog('Done with sequence')

def change3Dsequence(start, end):
    sequence = settings.sequenceBegin
    options = {0:(settings.positionOff-1), 1:(settings.positionOU-1), 2:(settings.positionSBS-1)}
    change = options[end]-options[start]
    while change != 0:
        if change > 0:
            sequence = sequence + ',Down'
            change -= 1
        else:
            sequence = sequence + ',Up'
            change += 1
    sequence = sequence + ',' + settings.sequenceEnd
    return sequence

def mainStereoChange():
    if stereoModeHasChanged():
        if not connectTV():
            toNotify(settings.getLocalizedString(30508)) #Connection Failed
            # Authenticate and action
        elif authenticate():
            # Checking again as mode could have changed during long authentication process
            if settings.authCount > 1:
                settings.newTVmode = getTranslatedStereoscopicMode()
            if stereoModeHasChanged():
                xbmclog('Stereoscopic Mode changed: curTVmode:newTVmode = ' + str(settings.curTVmode) + ':' + str(settings.newTVmode), xbmc.LOGDEBUG)
                # Action Assignment
                commandSequence = change3Dsequence(settings.curTVmode, settings.newTVmode)
                processSequence(commandSequence)
                # Saving current 3D mode
                settings.curTVmode = settings.newTVmode
                settings.setSetting('curTVmode', settings.newTVmode)
            else:
                xbmclog('Stereoscopic Mode is the same', xbmc.LOGINFO)
        else:
            toNotify(settings.getLocalizedString(30509)) #Authentication Failed
        
        # Close the socket
        if settings.sock:
            settings.sock.close()
    else:
        xbmclog('Stereoscopic mode has not changed', xbmc.LOGDEBUG)
    # Notify of all messages
    notify()

def mainTrigger():
    if not settings.inProgress:
        settings.inProgress - True
        settings.newTVmode = getTranslatedStereoscopicMode()
        if stereoModeHasChanged():
            mainStereoChange()
        settings.inProgress - False

def onAbort():
    # On exit switch TV back to None 3D
    settings.newTVmode = 0
    if stereoModeHasChanged():
        xbmclog('Exit procedure: changing back to None 3D', xbmc.LOGINFO)
        mainStereoChange()

def checkAndDiscover():
    if not (settings.ipaddress and settings.authCookie) and settings.check:
        if settings.discover:
            if dialog.yesno(settings.addonname, settings.getLocalizedString(30515), settings.getLocalizedString(30518)):#, settings.getLocalizedString(30519)):    #Your Samsung TV is not defined yet    #If it is connected to your network - it can be discovered    #Do you want to discover TV now?
                if connectTV():
                    while not authenticate():
                        settings.authCount += 1
                        if (settings.authCount > 0) and not (dialog.yesno("Authentication Failed", "Authentication failed, would you like to try again?")):
                            toNotify("Authentication Failed")
                            settings.check = False
                            break
        else:
            if dialog.yesno(settings.addonname, settings.getLocalizedString(30515), settings.getLocalizedString(30516), settings.getLocalizedString(30517)):    #Your Samsung TV is not defined yet    #Auto Discovery is currently Disabled    #Do you want to enter your TV IP address now?
                __addon__.openSettings()
    notify()

class MyMonitor(xbmc.Monitor):
    def __init__(self, *args, **kwargs):
        xbmc.Monitor.__init__(self)
    
    def onSettingsChanged( self ):
        xbmclog('Settings changed', xbmc.LOGDEBUG)
        settings.load()
        checkAndDiscover()
        settings.check = True
    
    def onScreensaverDeactivated(self):
        # If detect mode is poll only - do not react on events
        if settings.detectmode == 2: return
        xbmclog('Screensaver Deactivated', xbmc.LOGDEBUG)
        settings.inScreensaver = False
    
    def onScreensaverActivated(self):
        # If detect mode is poll only - do not react on events
        if settings.detectmode == 2: return
        xbmclog('Screensaver Activated', xbmc.LOGDEBUG)
        if settings.skipInScreensaver:
            settings.inScreensaver = True
    
    def onNotification(self, sender, method, data):
        # If detect mode is poll only - do not react on events
        if settings.detectmode == 2: return
        xbmclog('Notification Received: ' + str(sender) + ': ' + str(method) + ': ' + str(data), xbmc.LOGDEBUG)
        if method == 'Player.OnPlay':
            if xbmc.Player().isPlayingVideo():
                xbmclog('Trigger: onNotification: ' + str(method), xbmc.LOGDEBUG)
                #Small delay to ensure Stereoscopic Manager completed changing mode
                xbmc.sleep(500)
                mainTrigger()
        elif method == 'Player.OnStop':
            xbmclog('Trigger: onNotification: ' + str(method), xbmc.LOGDEBUG)
            #Small delay to ensure Stereoscopic Manager completed changing mode
            xbmc.sleep(500)
            mainTrigger()

def main():
    global dialog, dialogprogress, blackScreen, settings, monitor
    dialog = xbmcgui.Dialog()
    dialogprogress = xbmcgui.DialogProgress()
    blackScreen = xbmcgui.Window(-1)
    settings = Settings()
    checkAndDiscover()
    monitor = MyMonitor()
    while not xbmc.abortRequested:
        if settings.detectmode != 1:
            if not settings.inScreensaver:
                settings.pollCount += 1
                if xbmc.getGlobalIdleTime() <= settings.idlesec:
                    if settings.pollCount > settings.pollsec:
                        mainTrigger()
                        settings.pollCount = 0
                        continue
        xbmc.sleep(1000)
    onAbort()

if __name__ == '__main__':
    main()
