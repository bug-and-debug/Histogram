import csv
import json
import os
import sys
import re
import math
from copy import deepcopy
import numpy as np
import matplotlib
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.offsetbox as offsetbox
from matplotlib.artist import Artist
from matplotlib.ticker import MultipleLocator, FormatStrFormatter
import argparse
import datetime
from power_common import *
import pdb
import codecs
import glob

# To append the contents to google spreadsheet
import httplib2
from apiclient import discovery
import oauth2client
from oauth2client import client
from oauth2client import tools

# To upload a file to google drive
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive

mpl.rcParams['agg.path.chunksize'] = 10000 
MIN_WAKE_CURRENT = 5 #mA
HYSTERESIS_CURRENT = 0.2#15 #mA
MIN_WAKE_TIME = 0#500 #500 ms
HOST_MIN_WAKE_TIME = 3 
IGNORED_ROWS = 1

PCAP_PATH = "/usr/local/google/home/shruthireddy/Comms-Power-Automation/Sniffer-Capture" 
SNIFFER_CAPTURE_FILE = ""

# If modifying these scopes, delete your previously saved credentials
# at ~/.credentials/sheets.googleapis.com-python-quickstart.json
SCOPES = 'https://www.googleapis.com/auth/spreadsheets'
CLIENT_SECRET_FILE = 'client_secrets.json'
APPLICATION_NAME = 'Update logs to spreadsheet'
SPREADSHEET_ID = 'YREUGFHASKGEFAYLSEFHABSEFABE'
SPREADSHEET_ID_NEW = "ERYGFHEAEKFFHUYREGHFSFAK"

GDRIVE_GRAPH_FOLDER_ID = 'ASNUIEFHKAJFFNUQRAEFHJENF'
GRAPH_FOLDER_LINK = "https://drive.google.com/drive/u/1/folders/" + GDRIVE_GRAPH_FOLDER_ID
GRAPHS_LIST = []
TEXT_TO_APPEND = {}
TEXT_TO_APPEND['values'] = []
channel_text = {}
channel_text['HOST'] = []
channel_text['WIFI'] = []
channel_text['NCP'] = []
#channel_text['BLE'] = []
channel_text['CELLULAR'] = []

FOLDER = ""
CSV_PATH = ""
START_TIME = datetime.datetime.now()
END_TIME = datetime.datetime.now()

APPEND = False


class TestStats:
	def __init__(self, 
				avg_wake_interval, 
				avg_wake_time, 
				avg_idle_time, 
				avg_wake_curr, 
				avg_idle_curr, 
				avg_current,
				num_wakes,
				total_wake_time,
				total_idle_time,
				total_test_time):
		self.avg_wake_interval = avg_wake_interval
		self.avg_wake_time = avg_wake_time
		self.avg_idle_time = avg_idle_time
		self.avg_wake_curr = avg_wake_curr
		self.avg_idle_curr = avg_idle_curr
		self.avg_current = avg_current
		self.num_wakes = num_wakes
		self.total_wake_time = total_wake_time
		self.total_idle_time = total_idle_time
		self.total_test_time = total_test_time

def drive_connection():
    gauth = GoogleAuth()
    gauth.LoadCredentialsFile("mycreds.txt")
    if gauth.credentials is None:
        gauth.LocalWebserverAuth()
    elif gauth.access_token_expired:
        gauth.Refresh()
    else:
        gauth.Authorize()
    gauth.SaveCredentialsFile("mycreds.txt")
    drive = GoogleDrive(gauth)
    
    folder_list = drive.ListFile({'q': "'{0}' in parents and trashed=false".format(GDRIVE_GRAPH_FOLDER_ID)}).GetList()
    sub_folder_id = ""
    for folder in folder_list:
        if folder['title'] == "Build":
            sub_folder_id = folder['id']
    fid = ""
    if sub_folder_id == "":
        folder_metadata = {'title' : FOLDER, 'mimeType' : 'application/vnd.google-apps.folder',
                           'parents': [{'kind': 'drive#fileLink', 'id': GDRIVE_GRAPH_FOLDER_ID}]}
        folder = drive.CreateFile(folder_metadata)
        folder.Upload()
        fid = folder['id']
    else:
        fid = sub_folder_id
    return drive, fid
		
def upload_file_to_gdrive(drive, fid, file_path):
    file_name = file_path.split('/')[-1]
    f = drive.CreateFile({"title":file_name, "parents": [{"kind": "drive#fileLink", "id": fid}]})
    f.SetContentFile(file_path)
    f.Upload()

    
def get_credentials():
    """Gets valid user credentials from storage.

    If nothing has been stored, or if the stored credentials are invalid,
    the OAuth2 flow is completed to obtain the new credentials.

    Returns:
        Credentials, the obtained credential.
    """
    home_dir = os.path.expanduser('~')
    credential_dir = os.path.join(home_dir, '.credentials')
    if not os.path.exists(credential_dir):
        os.makedirs(credential_dir)
    credential_path = os.path.join(credential_dir,
                                   'mail_to_g_app.json')

    store = oauth2client.file.Storage(credential_path)
    credentials = store.get()
    if not credentials or credentials.invalid:
        flow = client.flow_from_clientsecrets(CLIENT_SECRET_FILE, SCOPES)
        flow.user_agent = APPLICATION_NAME
        if flags:
            credentials = tools.run_flow(flow, store, flags)
        else: # Needed only for compatibility with Python 2.6
            credentials = tools.run(flow, store)
        print('Storing credentials to ' + credential_path)
    return credentials

def connect_to_spreadsheet():
    credentials = get_credentials()
    http = credentials.authorize(httplib2.Http())
    discoveryUrl = ('https://sheets.googleapis.com/$discovery/rest?'
                    'version=v4')
    service = discovery.build('sheets', 'v4', http=http,
                              discoveryServiceUrl=discoveryUrl)
    return service


def insert_emptyRow_in_1st_Worksheet (spreadsheetId, service):
    requests = []
    requests.append({
        "insertDimension": {
            "range": {
                "sheet_id": 0,
                "dimension": "ROWS",
                "startIndex": 0,
                "endIndex": 1
                }
            }
        })
    body = {
            'requests': requests
            }
    response = service.spreadsheets().batchUpdate(spreadsheetId=spreadsheetId,
            body=body).execute()


def append_to_spreadsheet_A1A(spreadsheetId, sheet_name, service, values):
    rangeName = sheet_name + '!A1:A'
    #insert_emptyRow_in_1st_Worksheet(spreadsheetId,service)
    # https://developers.google.com/sheets/guides/values#appending_values
    values = values #{'values':[['Hello',],]}
    result = service.spreadsheets().values().append(
        spreadsheetId=spreadsheetId, range=rangeName,
        valueInputOption='RAW',
        insertDataOption='INSERT_ROWS',
        body=values).execute()



def append_to_spreadsheet(spreadsheetId, sheet_name, service, values):
    rangeName = sheet_name + '!A1'
    #insert_emptyRow_in_1st_Worksheet(spreadsheetId,service)
    # https://developers.google.com/sheets/guides/values#appending_values
    values = values #{'values':[['Hello',],]}
    result = service.spreadsheets().values().append(
        spreadsheetId=spreadsheetId, range=rangeName,
        valueInputOption='RAW', insertDataOption='INSERT_ROWS',
        body=values).execute()

    
def findFirstIdleIndex(time_array, current_array, min_wake_current, start_time):
	for ii in range(0, len(current_array), 1):
		if current_array[ii] < min_wake_current and time_array[ii] >= start_time:
			return ii
	#print time_array[ii]
	#print current_array[ii]
	#print "Couldn't find first idle index"
	sys.exit()
			
def get_fulltime(timestamp, tm):
    real_time = timestamp + datetime.timedelta(seconds=int(tm))  # Careful to add just the integer part to the timestamp
                                                                 # Rollovers (new minute, hour, day, leapyear, handled gracefully by python)
    time_remainder = float(tm) % 1                               # Grab part after the decimal point - timestamp rounds to nearest second so we handle it
                                                                 # ourselves
    # "{%H:%M:}".format(today)
    # reformat time with floating point seconds
    fulltime = '{:%a %b %d %H:%M:}'.format(real_time) + str(float('{:%S}'.format(real_time)) + float(str(time_remainder)[:6]))
    str_to_dt = datetime.datetime.strptime(fulltime, "%a %b %d %H:%M:%S.%f")
    fulltime = datetime.datetime.strftime(str_to_dt, "%a %b %d %H:%M:%S.%f")
    return fulltime


def findStartEndIndices(time_array, start_time, end_time):
	start_index = 0
	end_index = len(time_array) - 1

	for ii in range(1, len(time_array), 1):
		if time_array[ii] < start_time:
			start_index = ii
		if time_array[ii] <= end_time:
			end_index = ii

	return (start_index, end_index)

def findTransitions(time_array, current_array, min_wake_time, min_wake_current, start_time, end_time, hysteresis):
	firstIdleIndex = findFirstIdleIndex(time_array, current_array, min_wake_current, start_time)
	curr_state = "Idle"
	rising_edge_time = 0
	start_index = 0

	wake_array = []

	for ii in range(firstIdleIndex, len(current_array), 1):
		if time_array[ii] > end_time: break
		if curr_state == "Idle" and current_array[ii] > min_wake_current:
			if min_wake_time != 0:
				curr_state = "Rising"
			else:
				curr_state = "Awake"
			rising_edge_time = time_array[ii]
			start_index = ii
		elif curr_state == "Rising":
			if current_array[ii] < min_wake_current:
				curr_state = "Idle"
			elif current_array[ii] > min_wake_current and (time_array[ii] - rising_edge_time) > float(min_wake_time)/1000:
				curr_state = "Awake"
		elif curr_state == "Awake":
			if current_array[ii] < (min_wake_current - hysteresis):
				end_index = ii
				awake_period = AwakePeriod(rising_edge_time, time_array[ii], start_index, end_index)
				wake_array.append(awake_period)
				curr_state = "Idle"

	return wake_array

def findValues(wake_array, time_array, current_array, min_wake_current, start_time, end_time):
	firstIdleIndex = findFirstIdleIndex(time_array, current_array, min_wake_current, start_time)
	firstIdleTime = time_array[firstIdleIndex]

	wakeIntervalSum = 0
	numWakeIntervals = 0

	wakeTimeSum = 0
	numWakeTimes = 0

	wakeCurrSum = 0
	numWakeCurrPoints = 0

	idleTimeSum = 0
	numIdleTimes = 0

	idleCurrSum = 0
	numIdleCurrPoints = 0

	for ii in range(0, len(wake_array), 1):
		# Wrap these in a try statement to prevent indexing outside of list
		try:
			wakeIntervalSum += wake_array[ii+1].start_time - wake_array[ii].start_time
			numWakeIntervals += 1

			idleTimeSum += wake_array[ii+1].start_time - wake_array[ii].end_time
			numIdleTimes += 1

			start_index = wake_array[ii].end_index
			end_index = wake_array[ii+1].start_index

			idleCurrSum += sum(current_array[start_index:end_index])
			numIdleCurrPoints += end_index - start_index
		except:
			pass

		wakeTimeSum += wake_array[ii].end_time - wake_array[ii].start_time
		numWakeTimes += 1 

		start_index = wake_array[ii].start_index
		end_index = wake_array[ii].end_index

		wakeCurrSum += sum(current_array[start_index:end_index+1])
		numWakeCurrPoints += end_index - start_index + 1

	runningSum = 0
	numEntries = 0
	for ii in range(0, len(current_array), 1):
		if time_array[ii] > start_time and time_array[ii] < end_time:
			runningSum += current_array[ii]
			numEntries += 1
		
	try:
		avgWakeInterval = wakeIntervalSum/numWakeIntervals
		avgWakeTime = wakeTimeSum/numWakeTimes
		avgWakeCurr = wakeCurrSum/numWakeCurrPoints
		avgIdleTime = idleTimeSum/numIdleTimes
		avgIdleCurr = idleCurrSum/numIdleCurrPoints
		avgCurrent = float(runningSum)/numEntries
		numWakes = len(wake_array)
	except ZeroDivisionError:
		print('Min wake current higher than set limit, consider running the script with plot-only on')
		exit()

	totalTestTime = wake_array[-1].end_time - wake_array[0].start_time

	#print avgWakeInterval
	#print avgWakeTime
	#print avgWakeCurr
	#print avgIdleTime
	#print avgIdleCurr
	#print avgCurrent

	return TestStats( avgWakeInterval,
						avgWakeTime,
						avgIdleTime,
						avgWakeCurr,
						avgIdleCurr,
						avgCurrent,
						numWakes,
						wakeTimeSum,
						idleTimeSum,
						totalTestTime)

def generateWakePeriodStats(wake_array, start_time, end_time):
	wake_times = []
	for time_slot in wake_array:
		if time_slot.start_time > start_time and time_slot.end_time < end_time:
			wake_times.append(time_slot.end_time - time_slot.start_time)

	return np.asarray(sorted(wake_times))

def getNumberOfWakes(wake_times_array, duration_limit_down, duration_limit_up):
    	num = 0
    	for wake_time in wake_times_array:
			if duration_limit_up != -1:
				if wake_time > duration_limit_down and wake_time <= duration_limit_up:
    					num += 1
			elif duration_limit_up == -1:
    				if wake_time > duration_limit_down:
    						num += 1
	return num

def generateTransitionArrays(wake_array):
	time_array = []
	current_array = []
	for wake in wake_array:
		time_array.append(wake.start_time)
		current_array.append(0)
		time_array.append(wake.start_time)
		current_array.append(300)

		time_array.append(wake.end_time)
		current_array.append(300)
		time_array.append(wake.end_time)
		current_array.append(0)

	return (np.asarray(time_array), np.asarray(current_array))

def formatTestStatsString(TestResults):
	#formattedString = "Averages : \n"
	formattedString = ""
	formattedString += "Wake Interval:   %.3f s\n" %(TestResults.avg_wake_interval) 
	formattedString += "Wake Time:       %.3f s\n" %(TestResults.avg_wake_time)
	formattedString += "Idle Time:       %.3f s\n" %(TestResults.avg_idle_time)
	formattedString += "Wake Current:    %.3f mA\n" %(TestResults.avg_wake_curr)
	formattedString += "Idle Current:    %.3f mA\n" %(TestResults.avg_idle_curr)
	formattedString += "Overall Current: %.3f mA\n" %(TestResults.avg_current)
	formattedString += "Total Wakes:     %s\n" %(TestResults.num_wakes)
	formattedString += "Total Wake Time: %.3f s\n" %(TestResults.total_wake_time)
	formattedString += "Total Idle Time: %.3f s\n" %(TestResults.total_idle_time)
	formattedString += "Total Test Time: %.3f s\n" %(TestResults.total_test_time) 

	return formattedString

def formatTestStatsDict(TestResults):
	return_dict = {}
	return_dict["WakeInterval"] = TestResults.avg_wake_interval
	return_dict["WakeTime"] = TestResults.avg_wake_time
	return_dict["IdleTime"] = TestResults.avg_idle_time
	return_dict["WakeCurrent"] = TestResults.avg_wake_curr
	return_dict["IdleCurrent"] = TestResults.avg_idle_curr
	return_dict["OverallCurrent"] = TestResults.avg_current
	return_dict["TotalWakes"] = TestResults.num_wakes
	return_dict["TotalWakeTime"] = TestResults.total_wake_time
	return_dict["TotalIdleTime"] = TestResults.total_idle_time
	return_dict["TotalTestTime"] = TestResults.total_test_tim
	return return_dict
			

def main():
	######################################## Ingest User Arguments ########################################

	parser = argparse.ArgumentParser(description="Analyze current vs time logs.")
	parser.add_argument("--file"             , help="input log file")
	parser.add_argument("--key-channel"      , help="primary equipment CHANNEL #", type=int)
	parser.add_argument("--start"            , help="start time for zooming (in s)", type=float)
	parser.add_argument("--end"              , help="end time for zooming (in s)", type=float)
	parser.add_argument("--hysteresis"       , type=float, help="current (I in mA) below MIN_WAKE_CURRENT at which platform will be considered idle/sleep")
	parser.add_argument("--min-wake-current" , type=float, help="current (I in mA) over which platform will be considered awake")
	parser.add_argument("--min_wake_time"    , type=float, help="time (in s) platform current must remain above min-wake-current to be considered as awake")
	parser.add_argument("--histogram"        , help="[on | off] enable plotting of distribution of wake times.")
	parser.add_argument("--additional-series", help="additional (comma-separated) keysight data columns to plot. eg: 1,2,3,4")
	parser.add_argument("--plot-only"        , help="[on | off] when \"on\", no current calculations are performed, just outputs a plot.")
	parser.add_argument("--ignored-rows"	 , help="Number of rows to ignore from the bottom of the file (default=15)")
	parser.add_argument("--time"  			 , help="Format: <year>-<month>-<day>T<hour>:<minute>:<second>.  Start time (GMT) of the test.  If no start time is provided, the output will be listed from time 0.")
	parser.add_argument("--output"       	 , help="Path to output CSV.  If file exists, append to it.  Else, create it.")
	parser.add_argument("--build" 			 , help="Label to be used if --output-csv is specified.")
	parser.add_argument("--rail"        	 , help="Label to be used if --output-csv is specified.")
	parser.add_argument("--channel1"         , help="Channel 1 should be HOST")
	parser.add_argument("--channel2"         , help="Channel 2 should be WIFI/BLE/NCP/CELLULAR")
	parser.add_argument("--channel3"         , help="Channel 3 should be BLE/NCP")
	parser.add_argument("--channel4"         , help="Channel 4 should be CELLULAR")
	parser.add_argument("--HOST_idle_current",help="Channel 1 idle current limit")
	#parser.add_argument("--OMAP_avg_wake_time"	 ,help="Channel 1 wake time limit")
	parser.add_argument("--WIFI_overall_current",help="Channel 2 overall current limit")
	parser.add_argument("--c2_wake_time"	 ,help="Channel 2 wake time limit")
	parser.add_argument("--NCP_idle_current",help="Channel 3 idle current limit")
	#parser.add_argument("--NCP_avg_wake_time"	 ,help="Channel 3 wake time limit")
	parser.add_argument("--CELLULAR_idle_current",help="Channel 4 idle current limit")
	parser.add_argument("--c4_wake_time"	 ,help="Channel 4 wake time limit")
	parser.add_argument("--HOST_min_wake_current",help="HOST minimum wake current")
	parser.add_argument("--WIFI_min_wake_current",help="WIFI minimum wake current")
	parser.add_argument("--NCP_min_wake_current",help="NCP minimum wake current")
        #parser.add_argument("--BLE_min_wake_current",help="BLE minimum wake current")
        parser.add_argument("--CELLULAR_min_wake_current",help="CELLULAR minimum wake current")
        parser.add_argument("--append",help="enable appending content to google drive")
	#parser.add_argument("--sniffer-capture", help="pcap file name")
        


	args = vars(parser.parse_args())
	global flags
	path = os.path.abspath(args["file"])
	start = None
	end = None
	keystone_column = 0
	
	global FOLDER
	global START_TIME
	global END_TIME
	global CSV_PATH
	global APPEND
	CSV_PATH = path
	
        if args["append"] != None:
		if args["append"] == "on" or args["append"] == "ON":
			APPEND = True
	
        #global SNIFFER_CAPTURE_FILE
        #if args["sniffer_capture"] != None:
		#SNIFFER_CAPTURE_FILE = args["sniffer_capture"]



	min_wake_time = MIN_WAKE_TIME
	min_wake_current = MIN_WAKE_CURRENT
	hysteresis = HYSTERESIS_CURRENT

	directory = os.path.dirname(path)
	filename = os.path.splitext(os.path.basename(path))[0]
	filetype = os.path.splitext(os.path.basename(path))[1].lower()

	# Output CSV defaults
	output_csv_path = None
	software_version = None
	rail_name = None

	should_plot_histogram = True
	should_perform_computations = True

	additional_series = []


	######################################## Import Data ########################################

	time_array = []
	current_array = []

	time_units = ""
	current_units = ""

	time = None

	shouldPlotZoomed = False

	start_index = None
	end_index = None

	if args["ignored_rows"] != None:
		global IGNORED_ROWS
		IGNORED_ROWS = int(args["ignored_rows"])

	if filetype == ".txt":
		time_array, current_array, time_units, current_units = importTXT(path)
	elif filetype == ".csv":
		time_array, current_array, time_units, current_units = importCSV(path)
	else:
		print "Script only accepts .txt and .csv"
		sys.exit(0)
		
	channels_in_file = []
	with open(path) as fl:
		lines = fl.readlines()
		for line in lines:
			if 'Time' in line:
				if 'Channel 1' in line:
					channels_in_file.append("Channel1")
				if 'Channel 2' in line:
					channels_in_file.append("Channel2")
				if 'Channel 3' in line:
					channels_in_file.append("Channel3")
				if 'Channel 4' in line:
					channels_in_file.append("Channel4")
			if 'Date' in line:
				tm = (line.split('Date:')[1]).strip()
				time = datetime.datetime.strptime(tm, '%a %b %d %H:%M:%S %Y')
				print time

	if args["start"] != None: 
		start = args["start"]
		shouldPlotZoomed = True
	else:
		if type(time_array) == list:
			start = time_array[0]
		else:
			start = time_array.data[0]

	if args["end"] != None: 
		end = args["end"]
		shouldPlotZoomed = True
	else:
		if type(time_array) == list:
			end = time_array[-1]
		else:
			end = time_array.data[-1]

	if args["min_wake_time"] != None:
		min_wake_time = args["min_wake_time"]
	if args["min_wake_current"] != None: 
		min_wake_current = args["min_wake_current"]
	if args["key_channel"] != None:
		keystone_column = args["key_channel"]
	else:
		if type(time_array) != list:
			keystone_tag_to_use = current_array[0].tag_name
			keystone_column = keystone_tag_to_use.split()[2]
	keystone_column = 1
	if args["hysteresis"] != None:
		hysteresis = args["hysteresis"]
	if args["histogram"] != None:
		if args["histogram"].lower() == "on":
			should_plot_histogram = True
	if args["plot_only"] != None:
		if args["plot_only"].lower() == "on":
			should_perform_computations = False
	#if args["additional_series"] != None:
		#additional_series = args["additional_series"].split(',')
	#if args["time"] != None:
		#time = datetime.datetime.strptime(args["time"], "%Y-%m-%dT%H:%M:%S")

	if args["output"] != None:
		output_csv_path = args["output"]
	if args["build"] != None:
		software_version = args["build"]
		FOLDER = args["build"]
	if args["rail"] != None:
		rail_name = args["rail"]

	TEXT_TO_APPEND['values'].append(["BUILD NUMBER : ", software_version])
	TEXT_TO_APPEND['values'].append(["INPUT FILE : ", path.split('/')[-1]])
	TEXT_TO_APPEND['values'].append(["TIME : ", str(time)])
	TEXT_TO_APPEND['values'].append(["Graphs : ", GRAPH_FOLDER_LINK])
	TEXT_TO_APPEND['values'].append([""])
	
	HOST_idle_current = 23 
       	WIFI_overall_current = 1 
	NCP_idle_current = 20.6 
        CELLULAR_idle_current= 1.7 
	
	HOST_min_wake_current = 27

        WIFI_min_wake_current = 1
        NCP_min_wake_current = 21
     	CELLULAR_min_wake_current = 2
            
        HOST_wake_time = 30
        CELLULAR_wake_time = 40
            
          		
	if args['HOST_min_wake_current'] != None:
		HOST_min_wake_current = float(args['HOST_min_wake_current'])
	if args['WIFI_min_wake_current'] != None:
		WIFI_min_wake_current = float(args['WIFI_min_wake_current'])
	if args['NCP_min_wake_current'] != None:
		NCP_min_wake_current = float(args['NCP_min_wake_current'])
        #if args['BLE_min_wake_current'] != None:
		#BLE_min_wake_current = float(args['BLE_min_wake_current'])
        if args['CELLULAR_min_wake_current'] != None:
		CELLULAR_min_wake_current = float(args['CELLULAR_min_wake_current'])


        if args['HOST_idle_current'] != None:
		HOST_idle_current = float(args['HOST_idle_current'])
	if args['WIFI_overall_current'] != None:
		WIFI_overall_current = float(args['WIFI_overall_current'])    
	if args['NCP_idle_current'] != None:
		NCP_idle_current = float(args['NCP_idle_current'])
        if args['CELLULAR_idle_current'] != None:
		CELLULAR_idle_current = float(args['CELLULAR_idle_current'])

		
	channel1 = args['channel1']
	channel2 = args['channel2']
	channel3 = args['channel3']
	channel4 = args['channel4']
	lst_channel = [channel1, channel2, channel3, channel4]
	
	channel_len = len(current_array)
	
	if channel1 is not None and 'Channel1' not in channels_in_file:
		print "The input file does not contain measurements on channel 1"
		sys.exit()
	if channel2 is not None and 'Channel2' not in channels_in_file:
		print "The input file does not contain measurements on channel 2"
		sys.exit()
	if channel3 is not None and 'Channel3' not in channels_in_file:
		print "The input file does not contain measurements on channel 3"
		sys.exit()
	if channel4 is not None and 'Channel4' not in channels_in_file:
		print "The input file does not contain measurements on channel 4"
		sys.exit()
	
	lst = []
	#if channel1 is None and channel_len >= 1:
	#	print 'Please pass channel1 in arguments!'
	#	sys.exit()
	if channel1 is not None and channel_len >= 1:
		lst.append({"channel":"C1 - HOST", "logic":channel1, "column":1, "data":current_array[0].data})
	elif channel1 is not None and channel_len < 1:
		print 'channel 1 does not exist in the input file'
		
	#if channel2 is None and channel_len >= 2:
	#	print 'Please pass channel2 in arguments!'
	#	sys.exit()
	if channel2 is not None and channel_len >= 2:
		lst.append({"channel":"C2 - WIFI", "logic":channel2, "column":2, "data":current_array[1].data})
	elif channel2 is not None and channel_len == 1:
		lst.append({"channel":"C2", "logic":channel2, "column":2, "data":current_array[0].data})
	elif channel2 is not None and channel_len < 2:
		print 'channel 2 does not exist in the input file'
		
	#if channel3 is None and channel_len >= 3:
	#	print 'Please pass channel3 in arguments!'
	#	sys.exit()
	if channel3 is not None and channel_len >= 3:
		lst.append({"channel":"C3 - NCP", "logic":channel3, "column":3, "data":current_array[2].data})
	elif channel3 is not None and channel_len == 2:
		lst.append({"channel":"C3", "logic":channel3, "column":3, "data":current_array[1].data})
	elif channel3 is not None and channel_len == 1:
		lst.append({"channel":"C3", "logic":channel3, "column":3, "data":current_array[0].data})
	elif channel3 is not None and channel_len < 3:
		print 'channel 3 does not exist in the input file'
		
	#if channel4 is None and channel_len >= 4:
	#	print 'Please pass channel4 in arguments!'
	#	sys.exit()
	if channel4 is not None and channel_len >= 4:
		lst.append({"channel":"C4 - CELLULAR", "logic":channel4, "column":4, "data":current_array[3].data})
	elif channel4 is not None and channel_len == 3:
		lst.append({"channel":"C4", "logic":channel4, "column":4, "data":current_array[2].data})
	elif channel4 is not None and channel_len == 2:
		lst.append({"channel":"C4", "logic":channel4, "column":4, "data":current_array[1].data})
	elif channel4 is not None and channel_len == 1:
		lst.append({"channel":"C4", "logic":channel4, "column":4, "data":current_array[0].data})
	elif channel4 is not None and channel_len < 4:
		print 'channel 4 does not exist in the input file'

	######################################## Crunch Numbers ########################################
        wake_periods = None
	TestStats = None

	time_array_new = deepcopy(time_array)
	
	new_file_name = filename
	results = []
	result_pass = True
	graphs = []
        if time != None:
            if type(time_array) != list:
                time_array.data = convertTimeArrayToDateTime(time_array.data, time)
	    else:
		time_array = convertTimeArrayToDateTime(time_array, time)

	for l in lst:
		user_specified_series = l['data']
		logic_name = l['logic']
		channel_name = l['channel']
		if logic_name != "HOST":
			should_plot_histogram = False
			min_wake_time = MIN_WAKE_TIME
		if logic_name == "HOST":
			should_plot_histogram = True
			min_wake_current = HOST_min_wake_current
			min_wake_time = HOST_MIN_WAKE_TIME
		elif logic_name == "WIFI":
			min_wake_current = WIFI_min_wake_current
		elif logic_name == "NCP":
			min_wake_current = NCP_min_wake_current
		elif logic_name == "CELLULAR":
    			min_wake_current = CELLULAR_min_wake_current

		filename = new_file_name + "_" + channel_name
		keystone_column = l['column']
		C_idle_current = HOST_idle_current
                C_overall_current = WIFI_overall_current
		#c_wake_time = OMAP_avg_wake_time

		print "========================================="
		if should_perform_computations:
			wake_periods = findTransitions(time_array_new.data, user_specified_series, min_wake_time, min_wake_current, start, end, hysteresis)
			TestStats = findValues(wake_periods, time_array_new.data, user_specified_series, min_wake_current, start, end)
			annotation = formatTestStatsString(TestStats)
                        params_to_append = [software_version, 'host', TestStats.avg_idle_curr, TestStats.avg_idle_time,\
			                    TestStats.avg_current, TestStats.total_idle_time, TestStats.total_test_time,\
			                    TestStats.total_wake_time, TestStats.num_wakes,	TestStats.avg_wake_curr,\
			                    TestStats.avg_wake_interval, TestStats.avg_wake_time]

			#if channel_name != "C3":
			txt = "Averages of Channel {0}".format(channel_name)
			print txt
			TEXT_TO_APPEND['values'].append([""])
			TEXT_TO_APPEND['values'].append([txt])
			TEXT_TO_APPEND['values'].append([""])
			print annotation
			TEXT_TO_APPEND['values'].append([annotation])
                        #else:
                        
                        if logic_name == "HOST":
                                channel_text['HOST'].append(params_to_append)
                               	C_idle_current = HOST_idle_current
				if TestStats.avg_idle_curr > C_idle_current:
					print '--- BUG ---'
					TEXT_TO_APPEND['values'].append(['--- BUG ---'])
					txt = 'HOST : Measured Avg HOST idle current {0} mA is higher than the set HOST idle current limit ({1} mA) --- FAIL'\
						  .format(str(TestStats.avg_idle_curr), str(C_idle_current))
					#print txt
					#TEXT_TO_APPEND['values'].append([txt])
					results.append(txt)
					result_pass = False
				else:
					txt = 'HOST : Measured Avg HOST idle current {0} mA is lesser than the set HOST idle current limit ({1} mA) --- PASS'\
						  .format(str(TestStats.avg_idle_curr), str(C_idle_current))
					#print txt
					#TEXT_TO_APPEND['values'].append([txt])
					results.append(txt)



                        if logic_name == "WIFI":
                                params_to_append[1]= 'wifi'
                                channel_text['WIFI'].append(params_to_append)
				C_overall_current = WIFI_overall_current
				if TestStats.avg_current > C_overall_current:
					print '--- BUG ---'
					TEXT_TO_APPEND['values'].append(['--- BUG ---'])
					txt = 'WIFI :Measured Overall Wifi current {0} mA is higher than the set Wifi overall current limit ({1} mA) --- FAIL'\
						  .format(str(TestStats.avg_current), str(C_overall_current))
					#print txt
					#TEXT_TO_APPEND['values'].append([txt])
					results.append(txt)
					result_pass = False
				else:
					txt = 'WIFI :Measured overall Wifi current {0} mA is lesser than the set Wifi overall current limit ({1} mA) --- PASS'\
						  .format(str(TestStats.avg_current), str(C_overall_current))
					#print txt
					#TEXT_TO_APPEND['values'].append([txt])
					results.append(txt)


                        if logic_name == "NCP":
                                params_to_append[1]= 'ncp'
                                channel_text['NCP'].append(params_to_append) 
				C_idle_current = NCP_idle_current
				if TestStats.avg_idle_curr > C_idle_current:
					print '--- BUG ---'
					TEXT_TO_APPEND['values'].append(['--- BUG ---'])
					txt = 'NCP : Measured Avg NCP idle current {0} mA is higher than the set NCP idle current limit ({1} mA) --- FAIL'\
						  .format(str(TestStats.avg_idle_curr), str(C_idle_current))
					#print txt
					#TEXT_TO_APPEND['values'].append([txt])
					results.append(txt)
					result_pass = False
				else:
					txt = 'NCP : Measured Avg NCP idle current {0} mA is lesser than the set NCP idle current limit ({1} mA) --- PASS'\
						  .format(str(TestStats.avg_idle_curr), str(C_idle_current))
					#print txt
					#TEXT_TO_APPEND['values'].append([txt])
					results.append(txt)




                        if logic_name == "BLE":
                            params_to_append[1]= 'ble'
                            channel_text['BLE'].append(params_to_append) 

                        if logic_name == "CELLULAR":
                            params_to_append[1]= 'cellular'
                            channel_text['CELLULAR'].append(params_to_append)
                            C_idle_current = CELLULAR_idle_current
			    if TestStats.avg_idle_curr > C_idle_current:
                                   print '--- BUG ---'
				   TEXT_TO_APPEND['values'].append(['--- BUG ---'])
				   txt = 'CELLULAR : Measured Avg Cellular idle current {0} mA is higher than the set Cellular idle current limit ({1} mA) ---FAIL'\
						  .format(str(TestStats.avg_idle_curr), str(C_idle_current))
				   #print txt
				   #TEXT_TO_APPEND['values'].append([txt])
				   results.append(txt)
				   result_pass = False
			    else:
				   txt = 'CELLULAR : Measured Avg Cellular idle current {0} mA is lesser than the set Cellular idle current limit({1} mA) --- PASS'\
						  .format(str(TestStats.avg_idle_curr), str(C_idle_current))
				   #print txt
				   #TEXT_TO_APPEND['values'].append([txt])
			           results.append(txt)


                        
                        # Report bug for current range
			c_bug_num_of_samples = 0
			c_min_wake_current = HOST_min_wake_current
                        c_wake_time = HOST_wake_time
                        if logic_name == "CELLULAR":
				c_min_wake_current = CELLULAR_min_wake_current
				c_wake_time = CELLULAR_wake_time
			c_calculating_bug = False
			c_starttime_bug = 0.0
			for index, current in enumerate(l['data']):
				tm = time_array_new.data[index]
				if current > c_min_wake_current:
					if c_calculating_bug == False:
						c_calculating_bug = True
						c_starttime_bug = float(tm)
						c_bug_num_of_samples = 0
					else:
						c_bug_num_of_samples += 1
				elif current < c_min_wake_current:
					if c_calculating_bug == True:
						c_endtime_bug = float(tm)
						c_waketime_bug = c_bug_num_of_samples * 0.1
						if c_waketime_bug > c_wake_time:
							message = '%s : BUG when device is awake for %s seconds. Start time: %s .'\
							% (logic_name, str(c_waketime_bug), str(get_fulltime(time, c_starttime_bug)))
							print message

							TEXT_TO_APPEND['values'].append([message])
						c_bug_num_of_samples = 0
						c_calculating_bug = False
						c_starttime_bug = 0.0


			if output_csv_path is not None:
				dict_contents = formatTestStatsDict(TestStats)
				headers = ["Build", "Rail"] + sorted(dict_contents.keys())
				dict_contents["Build"] = software_version
				dict_contents["Rail"] = rail_name

				if not os.path.exists(output_csv_path):
					outfile = open(output_csv_path, "w")
					writer = csv.DictWriter(outfile, headers)
					writer.writeheader()
					writer.writerow(dict_contents)
					outfile.close()
				else:
					outfile = open(output_csv_path, "a")
					writer = csv.DictWriter(outfile, headers)
					writer.writerow(dict_contents)
					outfile.close()

				# Write out JSON file for spreasheet upload
				dest_dir = os.path.dirname(output_csv_path)
				json_file_name = os.path.splitext(os.path.basename(output_csv_path))[0]
				json_file = open(os.path.join(dest_dir, json_file_name + ".json"), "w")
				json.dump(dict_contents, json_file)
				json_file.close()
		
		if shouldPlotZoomed:
			if type(time_array) == list:
				start_index, end_index = findStartEndIndices(time_array, start, end)
			else:
				start_index, end_index = findStartEndIndices(time_array.data, start, end)
		#import pdb
                #pdb.set_trace()
		#if time != None:
			#if type(time_array) != list:
				#time_array.data = convertTimeArrayToDateTime(time_array.data, time)
			#else:
				#time_array = convertTimeArrayToDateTime(time_array, time)
		######################################## Plot Data Series ########################################
		additional_series = [keystone_column]
		
		fig, ax = plt.subplots(1, figsize=(34, 20))
		fig.canvas.set_window_title(l['channel'])
		# For non-Keystone test data

                if type(time_array) == list:
			if time == None:
				ax.plot(np.asarray(time_array)/60,
					np.asarray(current_array))
				ax.set_xlabel("Time (min)")
				major_locator = MultipleLocator(20)
				major_formatter = FormatStrFormatter('%d')
				minor_locator = MultipleLocator(10)
				#ax.xaxis.set_major_locator(major_locator)
				ax.xaxis.set_major_formatter(major_formatter)
				#ax.xaxis.set_minor_locator(minor_locator)
			else:
				ax.plot(np.asarray(time_array),np.asarray(current_array))
		# For Keystone data, overplot each series
		else:
			for data_set in current_array:
				for column in additional_series:
					if str(column) in data_set.tag_name:
						if time == None:
							ax.plot(np.asarray(time_array.data)/60,
								np.asarray(data_set.data))
							ax.set_xlabel("Time (min)")
							major_locator = MultipleLocator(20)
							major_formatter = FormatStrFormatter('%d')
							minor_locator = MultipleLocator(10)
							#ax.xaxis.set_major_locator(major_locator)
							ax.xaxis.set_major_formatter(major_formatter)
							#ax.xaxis.set_minor_locator(minor_locator)
						else:   
							ax.plot(np.asarray(time_array.data), np.asarray(data_set.data))

							#ax.xaxis.set_minor_locator(mdates.MinuteLocator(interval=15))
							#ax.xaxis.set_minor_formatter(mdates.DateFormatter('%H:%M:%S'))
							#ax.xaxis.set_major_locator(mdates.HourLocator())
							ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%dT%H:%M:%S.%f'))

		ax.axhline(min_wake_current, color="red")

		if args["start"] != None:
			if time == None:
				ax.axvline(start/60, color="red")
			else:
				start_datetime = time + datetime.timedelta(seconds=start)
				ax.axvline(start_datetime, color="red")
		if args["end"] != None:
			if time == None:
				ax.axvline(end/60, color="red")
			else:
				end_datetime = time + datetime.timedelta(seconds=end)
				ax.axvline(end_datetime, color="red")

		ax.set_title("Current vs Time")
		ax.set_ylabel("Current (mA)")

		if should_perform_computations:
			txt = ax.text(0, 1, annotation, transform=ax.transAxes, fontsize=20, verticalalignment='top', family='monospace')
			plt.setp(ax.get_xticklabels(), rotation=30)
			plt.savefig(os.path.join(directory, filename + ".png"))
			txt.remove()
			ax.text(0, 1, annotation, transform=ax.transAxes, fontsize=12, verticalalignment='top', family='monospace')
		else:
			plt.setp(ax.get_xticklabels(), rotation=30)
			plt.savefig(os.path.join(directory, filename + ".png"))
		GRAPHS_LIST.append(os.path.join(directory, filename + ".png"))
		#graphs.append(plt)
		#plt.show()

		######################################## Plot Zoomed Data Series ########################################

		# This start/end value comparison is no longer valid since I am converting the time_array to datetime objects
		if type(time_array) == list:
			if shouldPlotZoomed:
				fig, ax = plt.subplots(1, figsize=(24, 15))
		
				if time == None:
					ax.plot(np.asarray(time_array[start_index:end_index])/60,
						np.asarray(current_array[start_index:end_index]))

					major_locator = MultipleLocator(20)
					major_formatter = FormatStrFormatter('%d')
					minor_locator = MultipleLocator(10)
					#minor_formatter = FormatStrFormatter("%d")
					#ax.xaxis.set_major_locator(major_locator)
					ax.xaxis.set_major_formatter(major_formatter)
					#ax.xaxis.set_minor_locator(minor_locator)
					#ax.xaxis.set_minor_formatter(minor_formatter)
					ax.set_xlabel("Time (min)")
				else:
					ax.plot(np.asarray(time_array[start_index:end_index]),
						np.asarray(current_array[start_index:end_index]))

					#ax.xaxis.set_minor_locator(mdates.MinuteLocator(interval=15))
					ax.xaxis.set_minor_formatter(mdates.DateFormatter('%H:%M:%S'))
					#ax.xaxis.set_major_locator(mdates.HourLocator())
					ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%dT%H:%M:%S.%f'))

				ax.axhline(min_wake_current, color="red")

				ax.set_title("Current vs Time")
				ax.set_ylabel("Current (mA)")

				if should_perform_computations:
					ax.text(0, 1, annotation, transform=ax.transAxes, fontsize=12, verticalalignment='top', family='monospace')

				plt.savefig(os.path.join(directory, filename + "_zoom.png"))
				GRAPHS_LIST.append(os.path.join(directory, filename + "_zoom.png"))
		else:
			if shouldPlotZoomed:
				fig, ax = plt.subplots(1, figsize=(24, 15))

				for data_set in current_array:
					for column in additional_series:
						if str(column) in data_set.tag_name:
							if time == None:
								ax.plot(np.asarray(time_array.data[start_index:end_index]),
									np.asarray(data_set.data[start_index:end_index]))
								ax.set_xlabel("Time (min)")
								major_locator = MultipleLocator(20)
								major_formatter = FormatStrFormatter('%d')
								minor_locator   = MultipleLocator(10)
								#minor_formatter = FormatStrFormatter('%d')
								#ax.xaxis.set_major_locator(major_locator)
								ax.xaxis.set_major_formatter(major_formatter)
								#ax.xaxis.set_minor_locator(minor_locator)
								#ax.xaxis.set_minor_formatter(minor_formatter)
                                                        else:
								ax.plot(np.asarray(time_array.data[start_index:end_index]),
									np.asarray(data_set.data[start_index:end_index]))

								#ax.xaxis.set_minor_locator(mdates.MinuteLocator(interval=15))
								ax.xaxis.set_minor_formatter(mdates.DateFormatter('%H:%M:%S'))
								#ax.xaxis.set_major_locator(mdates.HourLocator())
								ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%dT%H:%M:%S.%f'))
				ax.axhline(min_wake_current, color="red")

				ax.set_title("Current vs Time")
				ax.set_ylabel("Current (mA)")
				if should_perform_computations:
					ax.text(0, 1, annotation, transform=ax.transAxes, fontsize=12, verticalalignment='top', family='monospace')
				plt.savefig(os.path.join(directory, filename + "_zoom.png"))
				GRAPHS_LIST.append(os.path.join(directory, filename + "_zoom.png"))
		#graphs.append(plt)
		#plt.show()

		if should_plot_histogram and should_perform_computations:
			fig, axis = plt.subplots(1, figsize=(24, 15))
			fig.canvas.set_window_title(l['channel']+"_histogram")
			wake_times = generateWakePeriodStats(wake_periods, start, end)

			#print wake_times

			# plt.clf()
			# plt.cla()
			max_bin = int((math.ceil(wake_times[-1]/10)+1)*10)

			bin_arr = [0, 5, 10, 20, 30]
			xnames = ["5", "10", "20", "30", ""]
			xvals = [0,1,2,3,4]
			yvals = [getNumberOfWakes(wake_times, 0, 5), 
					getNumberOfWakes(wake_times, 5, 10),
					getNumberOfWakes(wake_times, 10, 20),
					getNumberOfWakes(wake_times, 20, 30),
					getNumberOfWakes(wake_times, 30, -1) ]


			histogram_width = 1.0
			#yinterval = 5 * 10 ** (len(str(int(max(yvals)/5)))-1)

			max_max = max(yvals);
			max_top = max_max
			max_standard = 5* 10 ** (len(str(max_max))-1)
			if max_max > max_standard:
				if max_max <= max_standard + max_standard/2:
					max_top = max_standard + max_standard/2
				else:
					max_top = max_standard * 2
			else:
    				max_top = (max_max / (max_standard/5) + 1) * (max_standard/5)

			yinterval = max_top / 5	
			
			if yinterval == 0:
    				yinterval = 1

			plt.grid(True)
			plt.bar(xvals, yvals, width=1.0, color='g')
			plt.xticks([ x+(histogram_width/2) for x in  xvals],[x for x in xnames])
			plt.yticks(range(0,max(yvals),yinterval))
			plt.xlim([-0.5,len(xvals)-0.5])
			#n, bins, patches = plt.hist(wake_times, bins=bin_arr, facecolor='g', alpha=0.75)

			plt.xlabel('Wake Time (s)')
			plt.ylabel('Occurances')
			plt.title('Histogram of Wake Time')
			#print "Mean: %s\nSt. Dev.: %s\nMedian: %s" %(np.mean(wake_times), np.std(wake_times), np.median(wake_times))

			no_wakes_5 = "No of wakes < 5s = %d" % getNumberOfWakes(wake_times, 0, 5)
			no_wakes_5_10 = "No of wakes > 5s & < 10s = %d" % getNumberOfWakes(wake_times, 5, 10)
			no_wakes_10_20 = "No of wakes > 10s  & < 20s = %d" % getNumberOfWakes(wake_times, 10, 20)
			no_wakes_20_30 = "No of wakes > 20s  & < 30s = %d" % getNumberOfWakes(wake_times, 20, 30)
			no_wakes_30 = "No of wakes > 30 s = %d" % getNumberOfWakes(wake_times, 30, -1)

			no_wakes = "%s\n%s\n%s\n%s\n%s\n" % (no_wakes_5, no_wakes_5_10, no_wakes_10_20, no_wakes_20_30, no_wakes_30)
			str_histogram = "%s\nMean= %s\nStd deviation: %s\nMedian: %s" %  (no_wakes, np.mean(wake_times), np.std(wake_times), np.median(wake_times))

			ymin, ymax = plt.ylim()
			xmin, xmax = plt.xlim()

			#plt.text(xmax, ymax-1, str_histogram, verticalalignment='top', horizontalalignment='right')
			# plt.annotate(str_histogram, xy=(1, 1), xytext=(-15, -15), fontsize=10,
			# 	xycoords='axes fraction', textcoords='offset points',
			# 	bbox=dict(facecolor='white', alpha=1.0),
			# 	horizontalalignment='right', verticalalignment='top')

			ob = offsetbox.AnchoredText(str_histogram, loc=1)
			axis.add_artist(ob)

			plt.savefig(os.path.join(directory, filename + "_histogram.png"))
			GRAPHS_LIST.append(os.path.join(directory, filename + "_histogram.png"))

			print "\nHistogram Statistics\n"
			print str_histogram

			#graphs.append(plt)
			
		#graphs.append(plt)
			
	print "========================================================================="
	print ""		
	print "--- RESULTS ---"
	TEXT_TO_APPEND['values'].append([""])
	TEXT_TO_APPEND['values'].append(["--- RESULTS ---"])
		
	for rslt in results:
		print rslt
		TEXT_TO_APPEND['values'].append([rslt])
		
	TEXT_TO_APPEND['values'].append([""])

	TEXT_TO_APPEND['values'].append(["Histogram Statistics\n"])
	TEXT_TO_APPEND['values'].append([str_histogram])

	return plt



if __name__ == "__main__":
  graph = main()
  if APPEND:
      TEXT_TO_APPEND['values'].append(["========================================================="])
      service = connect_to_spreadsheet()
      #print "Appending contents to spreadsheet..."
      #spreadsheetId = SPREADSHEET_ID
      #insert_emptyRow_in_1st_Worksheet (spreadsheetId, service)
      #append_to_spreadsheet(spreadsheetId, 'F1', service, TEXT_TO_APPEND)
      #append_to_spreadsheet_A1A (spreadsheetId, 'F1', service, TEXT_TO_APPEND)
      tmp_var = ""
      with codecs.open('Results.txt', 'w+', 'utf-8') as fl:
		print "Writing console text into text file..."
		temp_list = TEXT_TO_APPEND['values']
		for temp in temp_list:
			for i in temp:
				tmp_var += i + " "
			fl.write("{0}\n".format(tmp_var))
			tmp_var = ""
      
      print "Appending channel wise contents to sheets..."
      spreadsheetId = SPREADSHEET_ID_NEW
      TEXT_TO_APPEND = {}
      TEXT_TO_APPEND['values'] = channel_text['HOST']
      append_to_spreadsheet(spreadsheetId, 'X1-HOST', service, TEXT_TO_APPEND)
      TEXT_TO_APPEND['values'] = channel_text['WIFI']
      append_to_spreadsheet(spreadsheetId, 'X1-WIFI', service, TEXT_TO_APPEND)
      TEXT_TO_APPEND['values'] = channel_text['NCP']
      append_to_spreadsheet(spreadsheetId, 'X1-NCP', service, TEXT_TO_APPEND)
      #TEXT_TO_APPEND['values'] = channel_text['BLE']
      #append_to_spreadsheet(spreadsheetId, 'F1-BLE', service, TEXT_TO_APPEND)
      TEXT_TO_APPEND['values'] = channel_text['CELLULAR']
      append_to_spreadsheet(spreadsheetId, 'X1-CELLULAR', service, TEXT_TO_APPEND)
			
      drive, fid = drive_connection()
      for path in GRAPHS_LIST:
          print "Uploading {0}...".format(path.split('/')[-1])
          upload_file_to_gdrive(drive, fid, path)
          os.remove(path)
      
      print "Uploading Results.txt file to google drive..."
      upload_file_to_gdrive(drive, fid, 'Results.txt')
      os.remove('Results.txt')
      
      #print "Uploading pcap file to google drive..."
      #latest_file = PCAP_PATH +"/"+ SNIFFER_CAPTURE_FILE
      #if SNIFFER_CAPTURE_FILE == "":
          #list_of_files = glob.glob(PCAP_PATH + "/*.pcap")
          #latest_file = max(list_of_files, key=os.path.getctime)
      #upload_file_to_gdrive(drive, fid, latest_file)

      print "Uploading csv file to google drive..."
      upload_file_to_gdrive(drive, fid, CSV_PATH)
  graph.show()


