import time
import board
import adafruit_sht4x
import argparse
from datetime import datetime
import os
from dotenv import load_dotenv
import requests
import base64
from tinydb import TinyDB

load_dotenv()

HONEYWELL_KEY = os.getenv("HONEYWELL_KEY")
HONEYWELL_SECRET = os.getenv("HONEYWELL_SECRET")
HONEYWELL_REFRESH = os.getenv("HONEYWELL_REFRESH")
TINYDB_DIR = os.getenv("TINYDB_DIR")
HOME_LATITUDE = os.getenv("HOME_LATITUDE")
HOME_LONGITUDE = os.getenv("HOME_LONGITUDE")
OPENWEATHER_KEY = os.getenv("OPENWEATHER_KEY")
ROOM_TEMP_MINIMUM = float(os.getenv("ROOM_TEMP_MINIMUM"))
EHEAT_SETPOINT = float(os.getenv("EHEAT_SETPOINT"))

logs_db = TinyDB(f"{TINYDB_DIR}/logs.json")

encoded_token = base64.b64encode((HONEYWELL_KEY + ":" + HONEYWELL_SECRET).encode("utf-8"))

def honeywell_request(type, endpoint, authorization, *, content_type: str = "", params: dict = {}, data = "", json = {}):
    headers = {
        "authorization": authorization,
        "cache-control": "no-cache"
        }
    if not content_type.isspace():
        headers["content-type"] = content_type
    response = requests.request(type, f"https://api.honeywell.com{endpoint}", data=data,headers=headers, params=params, json=json)
    try:
        response_content = response.json()
    except:
        response_content = response.content
    return response_content

def get_auth_token():
    response = honeywell_request("POST", "/oauth2/token", encoded_token, content_type="application/x-www-form-urlencoded", data=f"grant_type=refresh_token&refresh_token={HONEYWELL_REFRESH}")
    return response["access_token"]

def set_thermostat(update_settings, old_settings):
    new_settings = {k: old_settings[k] for k in old_settings.keys() & {"mode", "heatSetpoint", "coolSetpoint", "thermostatSetpointStatus", "nextPeriodTime"}}
    new_settings.update(update_settings)
    honeywell_request("POST", f"/v2/devices/thermostats/{device_id}", f"Bearer {auth_token}", params={"apikey": HONEYWELL_KEY, "locationId": location_id}, json=new_settings, content_type="application/json")


auth_token = get_auth_token()
locations = honeywell_request("GET", "/v2/locations", f"Bearer {auth_token}", params={"apikey": HONEYWELL_KEY})
location_id = locations[0]["locationID"]
device_id = locations[0]["devices"][0]["deviceID"]

thermostat_info = honeywell_request("GET", f"/v2/devices/thermostats/{device_id}", f"Bearer {auth_token}", params={"apikey": HONEYWELL_KEY, "locationId": location_id})

# Try to implement if/when openweathermap API key is actually activated
# weather_response = requests.request("GET", f"https://api.openweathermap.org/data/2.5/weather?lat={HOME_LATITUDE}&lon={HOME_LONGITUDE}&appid={OPENWEATHER_KEY}")
# weather_info = weather_response.json()

outdoor_temp = thermostat_info["outdoorTemperature"]
current_thermostat_status = thermostat_info["changeableValues"]


i2c = board.I2C()   # uses board.SCL and board.SDA
sht = adafruit_sht4x.SHT4x(i2c)
sht.mode = adafruit_sht4x.Mode.NOHEAT_HIGHPRECISION
# Can also set the mode to enable heater
# sht.mode = adafruit_sht4x.Mode.LOWHEAT_100MS

tempc, relative_humidity = sht.measurements
tempf = tempc * 9/5 + 32
thermostat_change = "None"

if tempf < ROOM_TEMP_MINIMUM:
    set_thermostat({"mode":"EmergencyHeat","heatSetpoint":80,"thermostatSetpointStatus":"PermanentHold"})
    thermostat_change = "RoomHeatBegin"
else:
    if current_thermostat_status["thermostatSetpointStatus"] == "PermanentHold":
        set_thermostat({"thermostatSetpointStatus": "NoHold"}, current_thermostat_status)
        thermostat_change = "RoomHeatEnd"
    should_emergency_activate = outdoor_temp < EHEAT_SETPOINT
    if should_emergency_activate != current_thermostat_status["emergencyHeatActive"]:
        new_mode = "EmergencyHeat" if should_emergency_activate else "Heat"
        set_thermostat({"mode":new_mode}, current_thermostat_status)
        thermostat_change = f"ToggleEHeat: {should_emergency_activate}"

current_time = datetime.now();
logs_db.insert({"thermostatChange": thermostat_change, "outdoorTemperature": outdoor_temp, "roomTemperature": tempf, "roomHumidity": relative_humidity, "thermostatStatus": current_thermostat_status, "createdAt": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")})
