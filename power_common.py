import re
import datetime
import matplotlib.dates

IGNORED_ROWS = 15

class AwakePeriod:
	def __init__(self, start_time, end_time, start_index, end_index):
		self.start_time = start_time
		self.end_time = end_time
		self.start_index = start_index
		self.end_index = end_index

# For Keystone data storage
class DataSeries:
	def __init__(self, tag_name):
		self.tag_name = tag_name
		self.data = []
	def add_data(self, new_data):
		self.data.append(new_data)

def minutesToSeconds(minutes):
	return float(minutes)*60

def secondsToMinutes(seconds):
	return float(seconds)/60

def hoursToMinutes(hours):
	return float(hours)*60

def minutesToHours(minutes):
	return float(minutes)/60

def hoursToSeconds(hours):
	return minutesToSeconds(hoursToMinutes(float(hours)))

def determineUnits(header):
	header = header.lower()

	timeUnit = ""

	if "(sec)" in header or "(s)" in header:
		timeUnit = "sec"
	elif "(min)" in header:
		timeUnit =  "min"
	elif "(hr)" in  header:
		timeUnit =  "hr"
	else:
		print "Unable to determine time units."
		sys.exit(1)

	currentUnit = ""

	if "(ma)" in header or "(mA)" in header:
		currentUnit = "mA"
	elif "(ua)" in header or "(uA)" in header:
		currentUnit = "uA"
	elif "(a)" in header or "(A)" in header:
		currentUnit = "A"
	else:
		print "Unable to determine current units."
		sys.exit(1)

	return (timeUnit, currentUnit)

# Functions for importing various types of data files from different pieces of measurement equipment.
def DetectKeystoneData(WholeDocument):
	if("N6705B exported datalog" in WholeDocument[0]):
		print "Keystone test data detected"
		return True
	else:
		return False

def DetectKeystoneExportedData(WholeDocument):
	if "14585A Exported Waveform" in WholeDocument[0]:
		print "Exported Keystone data detected"
		return True
	else:
		return False

def ImportKeystoneData(WholeDocument):
	SampleInterval = None
	DataLists = []
	StartIndex = None

	for ii in range(0, len(WholeDocument)-IGNORED_ROWS, 1):
		line = WholeDocument[ii]

		if "Sample interval" in line:
			sample_interval_text = re.search("[0-9]+\.[0-9]+", line).group(0)
			SampleInterval = float(sample_interval_text)
			continue
		elif "Sample" in line and "Curr avg " in line:
			DataLists.append(DataSeries("time"))

			line = line.strip()
			labels = line.split(',')
			for label in labels:
				if "Sample" in label:
					pass
				else:
					DataLists.append(DataSeries(label))

			StartIndex = ii + 1
		else:
			try:
				line = line.strip()
				points = line.split(',')

				curr_time = float(points[0])*SampleInterval
				DataLists[0].add_data( curr_time )

				for jj in range(1, len(points), 1):
					if float(points[jj]) < 0:
						points[jj] = 0
					DataLists[jj].add_data(float(points[jj])*1000)
			except:
				pass

	return (DataLists[0], DataLists[1:], "sec", "mA")

def ImportExportedKeystoneData(WholeDocument):
	SampleInterval = None
	DataLists = []
	StartIndex = None

	for ii in range(0, len(WholeDocument)-IGNORED_ROWS, 1):
		line = WholeDocument[ii]

		if "Sampling Period:" in line:
			sample_interval_text = re.search("[0-9]+\.[0-9]+", line).group(0)
			SampleInterval = float(sample_interval_text)
			continue
		elif "Time" in line and "Current Avg" in line:
			DataLists.append(DataSeries("time"))

			line = line.strip()
			labels = line.split(',')
			for label in labels:
				if "Time" in label:
					pass
				else:
					DataLists.append(DataSeries(label))

			StartIndex = ii + 1
		else:
			try:
				line = line.strip()
				points = line.split(',')

				curr_time = float(points[0])
				DataLists[0].add_data( curr_time )

				for jj in range(1, len(points), 1):
					if float(points[jj]) < 0:
						points[jj] = 0
					DataLists[jj].add_data(float(points[jj])*1000)
			except:
				pass

	return (DataLists[0], DataLists[1:], "sec", "mA")

def ImportGenericCSV(WholeDocument):
	time_array = []
	current_array = []

	timeUnits, currentUnits = determineUnits(WholeDocument[0])

	for ii in range(0, len(WholeDocument)-IGNORED_ROWS, 1):
		line = WholeDocument[ii]
		try:
			line = line.strip()
			values = line.split(",")

			rawTime = float(values[0])

			if timeUnits == "hr":
				seconds = hoursToSeconds(rawTime)
				time_array.append(seconds)
			elif timeUnits == "min":
				seconds = minutesToSeconds(rawTime)
				time_array.append(seconds)
			elif timeUnits == "sec":
				time_array.append(rawTime)
			else:
				print "Unknown time units."
				sys.exit(1)

			if float(values[1]) < 0:
				values[1] = 0
			rawCurrent = float(values[1])

			if currentUnits == "mA":
				current_array.append(rawCurrent)
			elif currentUnits == "A":
				current_array.append(rawCurrent*1000)
			elif currentUnits == "uA":
				current_array.append(rawCurrent/1000.0)
			else:
				print "Unknown current units."
				sys.exit(1)
		except:
			pass

	return (time_array, current_array, timeUnits, currentUnits)

def importCSV(path):
	File = open(path)
	WholeDocument = File.readlines()
	File.close()

	print(len(WholeDocument))

	if len(WholeDocument) == 1:
		WholeDocument = WholeDocument[0].split('\r')

	if DetectKeystoneData(WholeDocument):
		return ImportKeystoneData(WholeDocument)
	elif DetectKeystoneExportedData(WholeDocument):
		return ImportExportedKeystoneData(WholeDocument)
	else:
		return ImportGenericCSV(WholeDocument)

def importTXT(path):
	File = open(path)
	WholeDocument = File.readlines()
	File.close()

	time_array = []
	current_array = []

	timeUnits, currentUnits = determineUnits(WholeDocument[0])

	for ii in range(0, len(WholeDocument)-IGNORED_ROWS, 1):
		line = WholeDocument[ii]
		try:
			line = line.strip()
			values = line.split()

			rawTime = float(values[0])

			if timeUnits == "hr":
				seconds = hoursToSeconds(rawTime)
				time_array.append(seconds)
			elif timeUnits == "min":
				seconds = minutesToSeconds(rawTime)
				time_array.append(seconds)
			elif timeUnits == "sec":
				time_array.append(rawTime)
			else:
				print "Unknown time units."
				sys.exit(1)

			if float(values[2]) < 0:
				values[2] = 0
			rawCurrent = float(values[2])

			if currentUnits == "mA":
				current_array.append(rawCurrent)
			elif currentUnits == "A":
				current_array.append(rawCurrent*1000)
			elif currentUnits == "uA":
				current_array.append(rawCurrent/1000.0)
			else:
				print "Unknown current units."
				sys.exit(1)
		except:
			pass

	return (time_array, current_array, timeUnits, currentUnits)

def convertTimeArrayToDateTime(time_array, start_time):
	output_list = []
	for elem in time_array:
		curr_time = start_time + datetime.timedelta(seconds=elem)
		output_list.append(curr_time)

	return matplotlib.dates.date2num(output_list)
