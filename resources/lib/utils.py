import os, sys, urllib.request, urllib.parse, urllib.error, time
import xbmcvfs, xbmcaddon, xbmc

ADDON = xbmcaddon.Addon(id='plugin.dbmc')
LANGUAGE_STRING = ADDON.getLocalizedString
ADDON_NAME = xbmcaddon.Addon().getAddonInfo('id')
ADDON_PATH = xbmcaddon.Addon().getAddonInfo('path')
ICON = xbmcaddon.Addon().getAddonInfo('icon')
DATAPATH = xbmcvfs.translatePath(xbmcaddon.Addon().getAddonInfo('profile'))
DROPBOX_SEP = '/'



def log(txt):
    # if isinstance (txt,str):
    #     txt = txt
    message = '%s: %s' % (ADDON_NAME, txt)
    xbmc.log(msg=message, level=xbmc.LOGINFO)


def log_error(txt):
    # if isinstance (txt,str):
    #     txt = txt
    message = '%s: %s' % (ADDON_NAME, txt)
    xbmc.log(msg=message, level=xbmc.LOGERROR)


def log_debug(txt):
    # if isinstance (txt,str):
    #     txt = txt
    message = '%s: %s' % (ADDON_NAME, txt)
    xbmc.log(msg=message, level=xbmc.LOGWARNING)


def parse_argv():
    # parse argv
    try:
        # started as plugin
        params = {}
        paramstring = sys.argv[2]
        if paramstring:
            splitparams = paramstring.lstrip('?').split('&')
            for item in splitparams:
                item = urllib.parse.unquote_plus(item)
                keyval = item.split('=')
                params[keyval[0]] = keyval[1]
        return False, params
    except:
        # started as script
        params = dict(arg.split("=") for arg in sys.argv[1].split("&"))
        return True, params


def get_cache_path(account_name):
    datapath = ADDON.getSetting('cachepath')
    # Use user defined location?
    if datapath == '' or os.path.normpath(datapath) == '':
        # get the default path
        datapath = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
    return os.path.normpath(datapath + '/' + account_name)


def replaceFileExtension(path, extension):
    extension = '.' + extension
    if extension in path[-len(extension):]:
        # file extension is ok, nothing to do
        return path
    else:
        newPath = path.rsplit('.', 1)[0]
        return newPath + extension


def xor(w1, w2):
    from itertools import cycle
    '''xor two strings together with the lenght of the first string limiting'''
    try:
        result = ''.join(chr(ord(str(c1)) ^ ord(str(c2))) for c1, c2 in zip(w1, cycle(w2)))
        return result
    except TypeError as e:
        log_error(f"Word 1: {w1}")
        log_error(f"Word 2: {w2}")
        log_error(f"xor error: {e}")



def decode_key(word):
    from base64 import b64encode, b64decode
    '''decode the word which was encoded with the given secret key.
    '''
    try:
        base = xor(b64decode(word, '-_'), ADDON_NAME)
        return base[4 : int(base[:3], 10) + 4]
    except TypeError as e:
        log_error(f"Word input: {word}")
        log_error(f"decode_key error: {e}")



def utc2local(utc):
    offset = time.timezone
    if time.daylight:
        if time.altzone and time.localtime().tm_isdst == 1:  # using only if defined
            offset = time.altzone
    return utc - offset


def local2utc(local):
    offset = time.timezone
    if time.daylight:
        if time.altzone and time.localtime().tm_isdst == 1:  # using only if defined
            offset = time.altzone
    return local + offset
