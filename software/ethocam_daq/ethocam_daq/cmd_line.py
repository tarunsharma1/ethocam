import os
import time
import argparse
from . import utility
from .config import Config
from .display import Display
from .status import StatusLogger
from .light import LightSensor
from .temp_humid import TempHumidSensor
from .wittypi import VoltageMonitor
from .wittypi import CurrentMonitor
from .video import VideoRecorder
#from .file_transfer import TransferAgent
#from .gps import GPS
from pprint import pprint
import board
import sparkfun_qwiicrelay
import digitalio

def cmd_reset_status():
    description_str = 'Reset ethocam acquistion status'
    parser = argparse.ArgumentParser(description=description_str)
    parser.parse_args()
    config = Config()
    utility.check_base_data_dir(config)
    status_logger = StatusLogger(config)
    status_logger.reset()

def cmd_display_info():
    description_str = 'display information case when nohalt file exists'
    parser = argparse.ArgumentParser(description=description_str)
    parser.parse_args()
    sensor_data = {}

    # Load configuration and check data directory (create if required)
    config = Config()
    sensor_data['config'] = config.dict()

    # Update status file
    utility.debug_print('updating status file',config)
    status_logger = StatusLogger(config)
    status = status_logger.read()
    sensor_data['status'] = status

    # Get network information infomation
    if config['Network']['enabled'] == 'yes':
        utility.debug_print('getting network information',config)
        host_data = utility.get_ip_and_hostname(config)

    # Get temperature and humidity
    utility.debug_print('get temperature and humidity',config)
    th_sensor = TempHumidSensor()
    sensor_data['temperature'] = th_sensor.temperature
    sensor_data['humidity'] = th_sensor.humidity

    # Get light sensor reading
    utility.debug_print('get light sensor reading',config)
    light_sensor = LightSensor(config)
    sensor_data['light'] = light_sensor.data 

    # Get battery and regulator voltages 
    utility.debug_print('get voltages',config)
    volt_monitor = VoltageMonitor(config)
    sensor_data['power'] = {}
    sensor_data['power']['input_voltage'] = volt_monitor.input_voltage
    sensor_data['power']['output_voltage'] = volt_monitor.output_voltage

    # Update Display to show acquiring message
    utility.debug_print('display acquiring message',config)
    display = Display(config)
    if config['Network']['enabled'] == 'yes':
        msg = [
                f"{status['datetime']}",
                f"{host_data['hostname']} {host_data['ip']}",
                f"mode = nohalt", 
                f"battery = {sensor_data['power']['input_voltage']}",
                ]
    else:
        msg = [
                f"{status['datetime']}",
                f"mode = nohalt", 
                f"battery = {sensor_data['power']['input_voltage']}",
                ]
    display.show(msg)


def cmd_acquire_data():
    description_str = 'acquire data from camera + other sensors and save/send data'
    parser = argparse.ArgumentParser(description=description_str)
    parser.parse_args()
    sensor_data = {}

    # Load configuration and check data directory (create if required)
    config = Config()
    sensor_data['config'] = config.dict()
    utility.check_base_data_dir(config)

    # Update status file
    utility.debug_print('updating status file',config)
    status_logger = StatusLogger(config)
    status = status_logger.update()
    sensor_data['status'] = status

    # Get network information infomation
    if config['Network']['enabled'] == 'yes':
        utility.debug_print('getting network information',config)
        host_data = utility.get_ip_and_hostname(config)


    # Get current data directory name and create directory
    utility.debug_print('get/create current data dir',config)
    data_dir = utility.get_current_data_dir(config,status['datetime'])
    os.makedirs(data_dir)

    # Change owner of data file from root from pi user 
    utility.chown(data_dir, 'pi', recursive=True) 

    # Get temperature and humidity
    utility.debug_print('get temperature and humidity',config)
    th_sensor = TempHumidSensor()
    sensor_data['temperature'] = th_sensor.temperature
    sensor_data['humidity'] = th_sensor.humidity

    # Get light sensor reading
    utility.debug_print('get light sensor reading',config)
    light_sensor = LightSensor(config)
    sensor_data['light'] = light_sensor.data 

    # Get battery and regulator voltages 
    utility.debug_print('get voltages',config)
    volt_monitor = VoltageMonitor(config)
    sensor_data['power'] = {}
    sensor_data['power']['input_voltage'] = volt_monitor.input_voltage
    sensor_data['power']['output_voltage'] = volt_monitor.output_voltage

    # Update Display to show acquiring message
    utility.debug_print('display acquiring message',config)
    display = Display(config)
    if config['Network']['enabled'] == 'yes':
        msg = [
                f"{status['datetime']}",
                f"{host_data['hostname']} {host_data['ip']}",
                f"mode = acquiring", 
                f"count = {status['count']}", 
                f"battery = {sensor_data['power']['input_voltage']}",
                ]
    else:
        msg = [
                f"{status['datetime']}",
                f"mode = acquiring", 
                f"count = {status['count']}", 
                f"battery = {sensor_data['power']['input_voltage']}",
                ]
    display.show(msg)

    #if sensor_data['light']['lux'] >= config['Video'].getfloat('lux_threshold'):

    # Start current monitor
    utility.debug_print('start current monitor',config)
    curr_monitor = CurrentMonitor(config)
    curr_monitor.start()

    # Record video
    utility.debug_print('start video recording',config)
    vid_rec = VideoRecorder(config, data_dir)
    pin = digitalio.DigitalInOut(board.D21)
    pin.direction = digitalio.Direction.OUTPUT
    # Turn on infrared lights if dark outside
    if sensor_data['light']['lux'] < config['Video'].getfloat('lux_threshold'):
        # code to turn on relay
        utility.debug_print('turning on relay', config)
        i2c = board.I2C()
        relay = sparkfun_qwiicrelay.Sparkfun_QwiicRelay(i2c)
        if relay.connected:
            utility.debug_print('ON time', config)
            relay.relay_on()
        # Start video recording for night time
        # also turn the IR filter using gpio
        # pin.value = False turns off the IR filter in the camera (night), pin.value=True turns on the IR filter in the camera (day)
        pin.value = False
        vid_rec.run(tuning='night')
        if relay.connected:
             relay.relay_off()
        pin.value = True
    else:
        # Start video recording for day time
        pin.value = True
        vid_rec.run(tuning='day')
    utility.debug_print('video recording done',config)


    # Send video data to remote host vis scp
    if config['Network']['enabled'] == 'yes':
        utility.debug_print('begin video file transfer',config)
        transfer_agent = TransferAgent(config, data_dir)
        transfer_agent.send_data_directory()
        utility.debug_print('video file transfer done',config)

    # Get GPS reading
    if config['GPS']['enabled'] == 'yes':        
        utility.debug_print('get gps reading',config)
        gps = GPS(config)
        gps_data = gps.read()
        sensor_data['gps'] = gps_data

    # Stop current monitor, get data and save sensor data to file
    utility.debug_print('stop current monitor',config)
    curr_monitor.stop()
    utility.debug_print('get current',config)
    sensor_data['power']['output_current'] = curr_monitor.data

    utility.save_sensor_data(config, data_dir, sensor_data)

    # Send sensor data to remote host vis scp
    if config['Network']['enabled'] == 'yes':
        utility.debug_print('send sensor data',config)
        transfer_agent.send_sensor_file()
        transfer_agent.close()

    # Change owner of data file from root from pi user 
    utility.chown(data_dir, 'pi', recursive=True) 

    # Update Display to show sleeping message
    utility.debug_print('dislplay sleeping message',config)
    if config['Network']['enabled'] == 'yes':
        msg = [
            f"{status['datetime']}",
            f"{host_data['hostname']} {host_data['ip']}",
            f"mode = sleeping", 
            f"count = {status['count']}",
            f"battery = {sensor_data['power']['input_voltage']}",
            ]
    else:
        msg = [
            f"{status['datetime']}",
            f"mode = sleeping", 
            f"count = {status['count']}",
            f"battery = {sensor_data['power']['input_voltage']}",
            ]
    display.show(msg)
    time.sleep(config['Display'].getfloat('shutdown_dt'))
    
    utility.debug_print('done',config)

