#!/usr/bin/python3
# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
'''
Created on 19.12.2017

@author: mstoffel
'''

from configparser import RawConfigParser
import logging
import sys
import os
from threading import Thread
import threading
import shlex
from c8yMQTT import C8yMQTT
import time
import io
import psutil
from sense_hat import SenseHat


#import restServer
sense = SenseHat()
startUp = False
stopEvent = threading.Event()
config_file = 'pi.properties'
config = RawConfigParser()
config.read(config_file)
reset = 0
resetMax = 3



c8y = C8yMQTT(config.get('device','host'),
               int(config.get('device','port')),
               config.getboolean('device','tls'),
               config.get('device','cacert'),
               loglevel=logging.getLevelName(config.get('device', 'loglevel')))

def sendTemperature():
    tempString = "211," + str(sense.get_temperature())
    c8y.logger.debug("Sending Temperature  measurement: " + tempString)
    c8y.publish("s/us", tempString)


def sendHumidity():
    tempString = "992,," + str(sense.get_humidity())
    c8y.logger.debug("Sending Humidity  measurement: " + tempString)
    c8y.publish("s/uc/pi", tempString)


def sendPressure():
    tempString = "994,," + str(sense.get_pressure())
    c8y.logger.debug("Sending Pressure  measurement: " + tempString)
    c8y.publish("s/uc/pi", tempString)


def sendAcceleration():
    acceleration = sense.get_accelerometer_raw()
    x = acceleration['x']
    y = acceleration['y']
    z = acceleration['z']
    accString = "991,," + str(x) + "," + str(y) + "," + str(z)
    c8y.logger.debug("Sending Acceleration measurement: " + accString)
    c8y.publish("s/uc/pi", accString)


def sendGyroscope():
    o = sense.get_orientation()
    pitch = o["pitch"]
    roll = o["roll"]
    yaw = o["yaw"]
    gyString = "993,," + str(pitch) + "," + str(roll) + "," + str(yaw)
    c8y.logger.debug("Sending Gyroscope measurement: " + gyString)
    c8y.publish("s/uc/pi", gyString)

def sendConfiguration():
    with open(config_file, 'r') as configFile:
            configString=configFile.read()
    configString = '113,"' + configString + '"'
    c8y.logger.debug('Sending Config String:' + configString)
    c8y.publish("s/us",configString)

def getserial():
    # Extract serial from cpuinfo file
    cpuserial = "0000000000000000"
    try:
        f = open('/proc/cpuinfo', 'r')
        for line in f:
            if line[0:6] == 'Serial':
                cpuserial = line[10:26]
        f.close()
    except:
        cpuserial = "ERROR000000000"
    c8y.logger.debug('Found Serial: ' + cpuserial)
    return cpuserial

def getrevision():
    # Extract board revision from cpuinfo file
    myrevision = "0000"
    try:
        f = open('/proc/cpuinfo','r')
        for line in f:
            if line[0:8]=='Revision':
                length=len(line)
                myrevision = line[11:length-1]
        f.close()
    except:
        myrevision = "ERROR0000"
    c8y.logger.debug('Found HW Version: ' + myrevision)
    return myrevision

def gethardware():
    # Extract board revision from cpuinfo file
    myrevision = "0000"
    try:
        f = open('/proc/cpuinfo','r')
        for line in f:
            if line[0:8]=='Hardware':
                length=len(line)
                myrevision = line[11:length-1]
        f.close()
    except:
        myrevision = "ERROR0000"
    c8y.logger.debug('Found Hardware: ' + myrevision)
    return myrevision

       
def sendCPULoad():
    tempString = "995,," + str(psutil.cpu_percent())
    c8y.logger.debug("Sending CPULoad: " + tempString)
    c8y.publish("s/uc/pi", tempString)

def sendMemory():
    tempString = "996,," +  str(psutil.virtual_memory().total >> 20) + "," + str(psutil.virtual_memory().available >> 20) + "," + str(psutil.swap_memory().total >> 20)
    c8y.logger.debug("Sending Memory: " + tempString)
    c8y.publish("s/uc/pi", tempString)


def listenForJoystick():
    for event in sense.stick.get_events():
        c8y.logger.debug("The joystick was {} {}".format(event.action, event.direction))
        c8y.publish("s/us", "400,c8y_Joystick,{} {}".format(event.action, event.direction))
        if event.action == 'pressed' and event.direction == 'middle':
            global reset
            global resetMax
            reset += 1
            if reset >= resetMax:
                stopEvent.set()
                c8y.logger.info('Resetting c8y.properties initializing re-register device....')
                c8y.reset()
                runAgent()


def sendMeasurements(stopEvent, interval):
    try:
        while not stopEvent.wait(interval):
            listenForJoystick()
            sendTemperature()
            sendAcceleration()
            sendHumidity()
            sendPressure()
            sendGyroscope()
        c8y.logger.info('sendMeasurement was stopped..')
    except (KeyboardInterrupt, SystemExit):
        c8y.logger.info('Exiting sendMeasurement...')
        sys.exit()
# Can be used  to reset existing operations.
def on_message_startup(client, obj, msg):
    message = msg.payload.decode('utf-8')
    c8y.logger.info("On_Message_Startup Received: " + msg.topic + " " + str(msg.qos) + " " + message)


def on_message_default(client, obj, msg):
    message = msg.payload.decode('utf-8')
    c8y.logger.info("Message Received: " + msg.topic + " " + str(msg.qos) + " " + message)
    if message.startswith('1001'):
        setCommandExecuting('c8y_Message')
        messageArray =  shlex.shlex(message, posix=True)
        messageArray.whitespace =',' 
        messageArray.whitespace_split =True 
        sense.show_message(list(messageArray)[-1])
        sense.clear
        setCommandSuccessfull('c8y_Message')
    if message.startswith('510'):
        Thread(target=restart).start()
    if message.startswith('513'):
        updateConfig(message)
    if message.startswith('520'):
        c8y.logger.info('Received Config Upload. Sending config')
        sendConfiguration() 
    



def setCommandExecuting(command):
    c8y.logger.info('Setting command: '+ command + ' to executing')
    c8y.publish('s/us','501,'+command)

def setCommandSuccessfull(command):
    c8y.logger.info('Setting command: '+ command + ' to successful')
    c8y.publish('s/us','503,'+command)

def setCommandFailed(command,errorMessage):
    c8y.logger.info('Setting command: '+ command + ' to failed cause: ' +errorMessage)
    c8y.publish('s/us','502,'+command+','+errorMessage)

def restart():
        if config.get('device','reboot') != '1':
            c8y.logger.info('Rebooting')
            c8y.publish('s/us','501,c8y_Restart')
            config.set('device','reboot','1')
            with open(config_file, 'w') as configfile:
                config.write(configfile)
            c8y.disconnect()
            os.system('sudo reboot')
        else:
            c8y.logger.info('Received Reboot but already in progress')

def updateConfig(message):
        
        c8y.logger.info('UpdateConfig')
        if config.get('device','config_update') != '1':
            plain_message = c8y.getPayload(message).strip('\"')
            with open(config_file, 'w') as configFile:
                config.readfp(io.StringIO(plain_message))
                c8y.logger.info('Current config:' + str(config.sections()))
                config.set('device','config_update','1')
                config.write(configFile)
            c8y.logger.info('Sending Config Update executing')
            setCommandExecuting('c8y_Configuration')
            c8y.disconnect()
            c8y.logger.info('Restarting Service')
            os.system('sudo service c8y restart')
        else:
            c8y.logger.info('Received Config Update but already in progress')


def runAgent():
    # Enter Device specific values
    stopEvent.clear()

    global reset

    reset=0
    if c8y.initialized == False:
        serial = getserial()
        c8y.logger.info('Not initialized. Try to registering Device with serial: '+ serial)
        c8y.registerDevice(serial,
                           serial,
                           config.get('device','devicetype'),
                           getserial(),
                           gethardware(),
                           getrevision(),
                           config.get('device','operations'),
                           config.get('device','requiredinterval'),
                           config.get('device','bootstrap_pwd'))
    if c8y.initialized == False:
        c8y.logger.info('Could not register. Exiting.')
        exit()
    ## Connect Startup
    c8y.connect(on_message_startup,config.get('device', 'subscribe'))
    time.sleep(2)
    c8y.logger.info('Request Old Operations')
    # This wil get you all pending operations. Proceed in on_message_startup....
    c8y.publish('s/us','500')
    time.sleep(1)

    c8y.publish("s/us", "114,"+ config.get('device','operations'))
    if config.get('device','reboot') == '1':
        c8y.logger.info('reboot is active. Publishing Acknowledgement..')
        setCommandSuccessfull('c8y_Restart')
        config.set('device','reboot','0')
        with open(config_file, 'w') as configfile:
            config.write(configfile)
    if config.get('device','config_update') == '1':
        c8y.logger.info('Config Update is active. Publishing Acknowledgement..')
        setCommandSuccessfull('c8y_Configuration')
        config.set('device','config_update','0')
        with open(config_file, 'w') as configfile:
            config.write(configfile)
    sendConfiguration()
    time.sleep(2)
    c8y.disconnect()
    time.sleep(2)
    c8y.connect(on_message_default,config.get('device', 'subscribe'))



runAgent()
c8y.logger.info('Starting sendMeasurements.')
sendThread = Thread(target=sendMeasurements, args=(stopEvent, int(config.get('device','sendinterval'))))
sendThread.start()






