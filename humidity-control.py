# -*- coding: utf-8 -*-

import re
import time
import socket
import logging
from HTMLParser import HTMLParser

import feedparser
import Adafruit_DHT

from tplink_smartplug import discoverPlugs, SmartPlug


class Context(object):
    def __init__(self):
        self.config = None
        self.lastKnownOutdoorTemp = None
        self.outdoorTempLastUpdate = None


def fetchOutdoorTemp():
    atomfeed = 'https://weather.gc.ca/rss/city/on-69_e.xml'
    socket.setdefaulttimeout(5)
    feeddata = feedparser.parse(atomfeed)
    if not feeddata.entries:
        logging.error('Failed to retreive outdoor weather feed.')
        return None
    
    # The 'Current Conditions' entry we are after
    entry = feeddata.entries[1]
    summary = HTMLParser().unescape(entry.summary)
    for line in summary.splitlines():
        if 'Temperature' in line:
            result = re.findall(r"[-+]?\d*\.\d+|\d+", line)
            if not result:
                logging.error('Failed to parse outdoor temperature.')
                return None
            # published = entry.published_parsed if not None else 
            return float(result[0])

    # We should not arrive here, but if we are, then..
    logging.error('No temperature value was found in the feed. The format might have changed.')
    return None

def controlcycle(context):
    aliasToFind = context.config['plug_name']
    RH_adjustment = context.config['RH_adjustment']
    
    humidifierPlug = None
    for ip, plug in discoverPlugs().iteritems():
        alias = plug.alias()
        if alias.lower() == aliasToFind.lower():
            humidifierPlug = plug
            _, state = humidifierPlug.state(str=True)
            logging.info('Found plug %s, IP: %s, State: %s', alias, ip, state)
            break

    if not humidifierPlug:
        logging.error('Could not find the plug \'%s\'. Waiting until the next round.', aliasToFind)
        return

    # Fetch outdoor temperature from weather service and set as the last known temp. 
    # If failed, use the last known reading. If also not available, use the 
    # fallback value from config.

    outdoorTemp = fetchOutdoorTemp()
    if outdoorTemp is not None:
        context.lastKnownOutdoorTemp = outdoorTemp
        context.outdoorTempLastUpdate = time.time()
    else:
        if context.lastKnownOutdoorTemp is not None:
            outdoorTemp = context.lastKnownOutdoorTemp
        else:
            fallbackTemp = context.config['fallback_temp']
            logging.info('No available outdoor temp reading. Assuming %0.1f°C', fallbackTemp)
            outdoorTemp = fallbackTemp

    # Try to grab a sensor reading. Use the read_retry method which will retry up
    # to 15 times to get a sensor reading (waiting 2 seconds between each retry).
    sensor, pin = Adafruit_DHT.AM2302, 4
    humidity, temperature = Adafruit_DHT.read_retry(sensor, pin)
    if humidity is None or temperature is None:
        logging.error('Could not read humidity/temperature from the sensor. Waiting until the next round.')
        return
    humidity += RH_adjustment

    goalRH = context.config['max_RH']
    roundedOutdoorTtemp = round(outdoorTemp)
    if roundedOutdoorTtemp >= 0: goalRH -= 2 # Keep it a bit below the max for safety
    elif -12 <= roundedOutdoorTtemp < 0: goalRH -= 5
    elif -18 <= roundedOutdoorTtemp < -12: goalRH -= 10
    elif -24 <= roundedOutdoorTtemp < -18: goalRH -= 15
    elif -30 <= roundedOutdoorTtemp < -24: goalRH -= 20
    else: goalRH -= 25

    action = None
    humidifierState = humidifierPlug.state()
    if round(humidity) >= goalRH:
        if humidifierState == SmartPlug.State.OFF:
            action = 'Keep off'
        else:
            success = humidifierPlug.turnOff()
            action = 'Turn off, ' + 'Succeeded' if success else 'Failed'
    else:
        if humidifierState == SmartPlug.State.ON:
            action = 'Keep on'
        else:
            success = humidifierPlug.turnOn()
            action = 'Turn on, ' + 'Succeeded' if success else 'Failed'

    logging.info('Outdoor temp: %0.1f°C, Indoor temp: %0.1f°C, Target RH: %0.0f%%, Indoor RH: %0.1f%%', 
                 outdoorTemp, temperature, goalRH, humidity)
    logging.info('Action: %s', action)
    
def loop(context):
    interval = context.config['interval']
    logging.info('Starting the control loop with a %d minute interval', interval)
    while True:
        controlcycle(context)
        time.sleep(interval * 60)

def readConfig():
    # The default configuration
    config = {'plug_name': 'My Smart Plug',
              'interval': 5,
              'RH_adjustment': 0,
              'max_RH': 35,
              'fallback_temp': -1
             }

    try:
        with open('humidity-control.config') as f:
            lines = f.readlines()
    except IOError as e:
        logging.error('Could not load the config file. Using a default configuration. Error: %s', e)
        return config

    for line in lines:
        # If line is empty or it is not empty but is comment, ignore
        if line in ['\r\n', '\n'] or (line and line[0] == '#'): continue

        parts = line.split('=')
        if len(parts) != 2:
            logging.error('Malformed line in humidity_control.config. Ignored. Line: %s', line)
            continue
        
        try:
            key, value = parts[0].strip(), parts[1].strip()
            if key == 'plug_name': config[key] = value
            elif key == 'interval': config[key] = int(value)
            elif key in ['RH_adjustment', 'max_RH', 'fallback_temp']: 
                config[key] = float(value)
        except ValueError:
            logging.error('Malformed value in humidity_control.config. Ignored. Line: %s', line)

    return config

def main():
    logging.basicConfig(#filename='humidity-control.log', 
        level=logging.DEBUG,
        format='%(asctime)s %(levelname)s: %(message)s',
        datefmt='%b %d %H:%M:%S')
        
    from logging.handlers import RotatingFileHandler
    handler = logging.handlers.RotatingFileHandler('humidity-control.log',
                                                   maxBytes=500000, backupCount=100)
    logging.getLogger('').addHandler(handler)
    
    context = Context()
    context.config = readConfig()
    logging.info('Config: %s', context.config)
    loop(context)

if __name__ == "__main__":
    main()
