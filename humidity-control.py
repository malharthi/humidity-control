# -*- coding: utf-8 -*-

import sys
import re
import feedparser
import time
import logging
import Adafruit_DHT
from HTMLParser import HTMLParser
from tplink_smartplug import discoverPlugs, SmartPlug

def fetchOutdoorTemp():
    atomfeed = 'https://weather.gc.ca/rss/city/on-69_e.xml'
    feeddata = feedparser.parse(atomfeed)
    if not feeddata.entries:
        logging.error('Failed to retreive outdoor weather feed.')
        return None

    summary = HTMLParser().unescape(feeddata.entries[1].summary)
    for line in summary.splitlines():
        if 'Temperature' in line:
            result = re.findall(r"[-+]?\d*\.\d+|\d+", line)
            if not result:
                logging.error('Failed to parse outdoor temerature.')
                return None
            else:
                return float(result[0])

def readIndoorHumidityTemp():
    """Returns a temperature, humidity tupple as read from the sensor."""
    return 0, 0

def findIndoorRelativeHumidity(outdoorTemp, indoorRH):
    return 0

def controlRH(config):
    aliasToFind = config['plug_name']
    RH_adjustment = config['RH_adjustment']
    
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

    outdoorTemp = fetchOutdoorTemp()

    # Try to grab a sensor reading. Use the read_retry method which will retry up
    # to 15 times to get a sensor reading (waiting 2 seconds between each retry).
    sensor, pin = Adafruit_DHT.AM2302, 4
    humidity, temperature = Adafruit_DHT.read_retry(sensor, pin)
    if humidity is None or temperature is None:
        logging.error('Could not read humidity/temperature from the sensor. Waiting to the next round.')
        return
    humidity += RH_adjustment

    goalRH = config['max_RH']
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

    logging.info('Outdoor temp: %3.2f °C, Indoor temp: %3.2f °C, Goal RH: %2.0f %%, Indoor RH: %2.1f %%', 
                 outdoorTemp, temperature, goalRH, humidity)
    logging.info('Action: %s', action)
    
def loop(config):
    interval = config['interval']
    logging.info('Starting the control loop with a %d minute interval', interval)
    while True:
        controlRH(config)
        time.sleep(interval * 60)

def readConfig():
    # The default configuration
    config = {'plug_name': 'My Smart Plug',
              'interval': 5,
              'RH_adjustment': 0,
              'max_RH': 35
              }

    with open('humidity-control.config') as f:
        lines = f.readlines()

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
            elif key in ['RH_adjustment', 'max_RH']: config[key] = float(value)
        except ValueError:
            logging.error('Malformed value in humidity_control.config. Ignored. Line: %s', line)

    logging.info('Config: %s', config)
    return config

def main():
    logging.basicConfig( # filename='humidity-control.log', 
        level=logging.DEBUG,
        format='%(asctime)s %(levelname)s: %(message)s',
        datefmt='%b %d %H:%M:%S')
    loop(readConfig())

if __name__ == "__main__":
    main()