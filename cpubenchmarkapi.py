#!/usr/bin/env python3
from requests import get
from bs4 import BeautifulSoup as bs
from multiprocessing import Process, Queue
import csv, os, argparse, time

# Add useragent to prevent 403 error
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0'}
baseURL = "https://www.cpubenchmark.net/cpu.php?cpu="
cpuListFileName = "cpus.txt"
csvFileName = "cpuData.csv"
numPhysicalCPUs = 1
numCPUs = os.cpu_count()
processes = []
cpuDataDict = {
    "Name": [],
    "CPU Class": [],
    "Socket": [],
    "Launched": [],
    "Overall Score": [],
    "Single Thread Rating": [],
    "Clockspeed": [],
    "Turbo Speed": [],
    "TDP": [],
    "Cores": [],
    "Threads": []
}

def getCPUName(soup, cpuDict):
    name = soup.find('div', {"class": "desc-header"}).text.strip()
    print(name)
    cpuDict["Name"].append(name)
    if "[Dual CPU]" in name:
        return 2
    elif "[Quad CPU]" in name:
        return 4
    else:
        return 1

def getSingleThreadedScore(soup, cpuDict):
    data = soup.find("div", {"class": "right-desc"}).text
    isNext = False
    for item in data.strip().split("\n"):
        if isNext:
            cpuDict["Single Thread Rating"].append(item.strip())
            return
        if "Single Thread Rating" in item:
            isNext = True
    cpuDict["Single Thread Rating"].append("N/A")

def getChipType(soup, cpuDict):
    data = soup.find("div", {"class": "left-desc-cpu"}).text
    for item in data.strip().split("\n"):
        if item.split(":")[0] == "Class" and item.split(":")[1].strip() != "":
            cpuDict["CPU Class"].append(item.split(":")[1].strip())
            return
    cpuDict["CPU Class"].append("N/A")

def getSocketType(soup, cpuDict):
    data = soup.find("div", {"class": "left-desc-cpu"}).text
    for item in data.strip().split("\n"):
        if item.split(":")[0] == "Socket" and item.split(":")[1].strip() != "":
            cpuDict["Socket"].append(item.split(":")[1].strip())
            return
    cpuDict["Socket"].append("N/A")

def getTimeOfRelease(soup, cpuDict):
    data = soup.find_all('p', {'class': 'alt'})
    for item in data:
        if "CPU First Seen on Charts:" in item.text:
            cpuDict["Launched"].append(item.text.split(":")[1].strip())
            return
    cpuDict["Launched"].append("N/A")

def getOverallScore(soup, cpuDict):
    data = soup.find("div", {"class": "right-desc"}).text
    isNext = False
    for item in data.strip().split("\n"):
        if isNext:
            cpuDict["Overall Score"].append(item.split()[0].strip())
            return
        if "Multithread Rating" in item:
            isNext = True

def getTDP(data, numPhysicalCPUs):
    for item in data:
        if "Typical TDP" in item.text:
            tdp = int(round(float(item.text.split(":")[1].strip().split(" ")[0]))) * numPhysicalCPUs
            if tdp < 0:
                tdp = "N/A"
            unit = item.text.split(":")[1].strip().split(" ")[1]
            return f"{tdp} {unit}"
    return "N/A"

def getCoresAndThreads(data, numPhysicalCPUs, cpuDict):
    threadsPresent = ("Threads" in data.text)
    if data.text.split(":")[0] == "Cores":
        coresAndThreads = data.text.replace(":", "").split(" ")
        cpuDict[coresAndThreads[0]].append(int(coresAndThreads[1]) * numPhysicalCPUs)
        if threadsPresent:
            cpuDict[coresAndThreads[2]].append(int(coresAndThreads[3]) * numPhysicalCPUs)
        else:
            cpuDict["Threads"].append(int(coresAndThreads[1]) * numPhysicalCPUs)
    else:
        coresAndThreads = data.text.split(":")[1].split(",")
        cores = coresAndThreads[0].strip().split(" ")
        threads = coresAndThreads[1].strip().split(" ")
        cpuDict[cores[1]].append(int(cores[0]) * numPhysicalCPUs)
        cpuDict[threads[1]].append(int(threads[0]) * numPhysicalCPUs)

def getClockspeedAndTurbo(data, cpuDict):
    component = data.text.split(":")[0]
    if component == "Clockspeed" or component == "Turbo Speed":
        speed = data.text.split(":")[1].strip().split()[0]
        if "," in speed:
            speed = float(speed.replace(".", "").replace(",", "."))
            speed = round(speed, 1)
        cpuDict[component].append(f"{speed} GHz")
    else:
        pivot = data.text.find("Threads")
        pivot += data.text[pivot:].find(",") + 1
        base = data.text[pivot:].split(",")[0].strip()
        turbo = data.text[pivot:].split(",")[1].strip()
        baseComponents = base.split(" ")
        turboComponents = turbo.split(" ")
        baseSpeed = baseComponents[0]
        turboSpeed = turboComponents[0]
        if "," in baseSpeed:
            baseSpeed = float(baseSpeed.replace(".", "").replace(",", "."))
            baseSpeed = round(baseSpeed, 1)
        if "," in turboSpeed:
            turboSpeed = float(turboComponents[0].replace(".", "").replace(",", "."))
            turboSpeed = round(turboSpeed, 1)
        if baseSpeed == 'NA':
            cpuDict["Clockspeed"].append("N/A")
        else:
            cpuDict["Clockspeed"].append(f"{baseSpeed} {baseComponents[1]}")
        if turboSpeed == 'NA':
            cpuDict["Turbo Speed"].append("N/A")
        else:
            cpuDict["Turbo Speed"].append(f"{turboSpeed} {turboComponents[1]}")

def getDetails(soup, numPhysicalCPUs, cpuDict):
    data = soup.find('div', {'class': 'desc-body'}).find_all('p')
    cpuDict["TDP"].append(getTDP(data, numPhysicalCPUs))
    for item in data:
        if item.text != "":
            component = item.text.split(":")[0]
            if component == "Cores" or component == "Total Cores":
                getCoresAndThreads(item, numPhysicalCPUs, cpuDict)
            if component in ["Performance Cores", "Primary Cores", "Clockspeed", "Turbo Speed"]:
                getClockspeedAndTurbo(item, cpuDict)
    if len(cpuDict["Name"]) > len(cpuDict["Turbo Speed"]):
        cpuDict["Turbo Speed"].append("N/A")
    if len(cpuDict["Name"]) > len(cpuDict["Clockspeed"]):
        cpuDict["Clockspeed"].append("N/A")

def validInputFile():
    if not os.path.exists(cpuListFileName):
        print("Error: Could not find the file specified.")
        print("File '" + cpuListFileName + "' does not exist")
        return False
    return True

def getCPUs():
    with open(cpuListFileName, 'r') as f:
        lines = f.readlines()
    cpus = []
    for line in lines:
        if line.find("#") != -1 or line.find("//") != -1:
            if min(line.find("#"), line.find("//")) != -1:
                line = line[:min(line.find("#"), line.find("//"))]
            else:
                line = line[:max(line.find("#"), line.find("//"))]
        if line.strip():
            cpus.append(line.strip())
    return cpus

def fillGaps(cpuDict):
    targetLen = len(cpuDict["Name"])
    for k, v in cpuDict.items():
        while targetLen > len(v):
            cpuDict[k].append("N/A")

def exportToCSV(cpuDict):
    print("Generating '" + csvFileName + "'...")
    try:
        with open(csvFileName, 'w') as f:
            writer = csv.writer(f)
            writer.writerow(cpuDict.keys())
            writer.writerows(zip(*cpuDict.values()))
    except:
        print("Error: unable to write to '" + csvFileName + "'. Make sure you have " +
              "permission to write to this file and it is not currently open and try again")

def addAuxData(currentData, cpuDict):
    for k, v in currentData.items():
        if k not in cpuDict:
            count = 0
            cpuDict[k] = [None] * len(cpuDict["Name"])
            for curName in cpuDict["Name"]:
                if curName in currentData["Name"]:
                    cpuDict[k][count] = currentData[k][currentData["Name"].index(curName)]
                else:
                    cpuDict[k][count] = "N/A"
                count += 1

def rankCPUs(cpuDict):
    overallScores = []
    singleThreadScores = []
    for x in range(len(cpuDict["Name"])):
        if cpuDict["Overall Score"][x] != "N/A":
            overallScores.append(int(cpuDict["Overall Score"][x]))
        else:
            overallScores.append(0)
        if cpuDict["Single Thread Rating"][x] != "N/A":
            singleThreadScores.append(int(cpuDict["Single Thread Rating"][x]))
        else:
            singleThreadScores.append(0)
    overallScores.sort(reverse=True)
    singleThreadScores.sort(reverse=True)
    cpuDict["Overall Rank"] = [None] * len(cpuDict["Name"])
    cpuDict["Single Threaded Rank"] = [None] * len(cpuDict["Name"])
    for x in range(len(cpuDict["Name"])):
        if cpuDict["Overall Score"][x] == "N/A":
            cpuDict["Overall Rank"][x] = "N/A"
        else:
            cpuDict["Overall Rank"][x] = overallScores.index(int(cpuDict["Overall Score"][x])) + 1
        if cpuDict["Single Thread Rating"][x] == "N/A":
            cpuDict["Single Threaded Rank"][x] = "N/A"
        else:
            cpuDict["Single Threaded Rank"][x] = singleThreadScores.index(int(cpuDict["Single Thread Rating"][x])) + 1

def readCSV():
    d = {}
    if os.path.exists(csvFileName):
        with open(csvFileName, 'r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                for k, v in row.items():
                    if k not in d:
                        d[k] = []
                    d[k].append(v)
    return d

def gatherResults(cpus, queue):
    cpuDict = {
        "Name": [],
        "CPU Class": [],
        "Socket": [],
        "Launched": [],
        "Overall Score": [],
        "Single Thread Rating": [],
        "Clockspeed": [],
        "Turbo Speed": [],
        "TDP": [],
        "Cores": [],
        "Threads": []
    }
    for cpu in cpus:
        currentCPU = cpu
        try:
            result = get(f'{baseURL}{cpu}', headers=headers)
            if result.status_code != 200:
                print(f"\nSkipping {currentCPU}: HTTP {result.status_code} error")
                continue
            soup = bs(result.content, "html.parser")
            sup = soup.find_all('sup')
            for x in sup:
                x.replaceWith('')
            numPhysicalCPUs = getCPUName(soup, cpuDict)
            getChipType(soup, cpuDict)
            getSocketType(soup, cpuDict)
            getTimeOfRelease(soup, cpuDict)
            getOverallScore(soup, cpuDict)
            getSingleThreadedScore(soup, cpuDict)
            getDetails(soup, numPhysicalCPUs, cpuDict)
            fillGaps(cpuDict)
        except Exception as e:
            print(f"\nSkipping {currentCPU}: Error occurred - {str(e)}")
            cpuDict["Name"].append(currentCPU)
            for key in cpuDict.keys():
                if key != "Name" and len(cpuDict[key]) < len(cpuDict["Name"]):
                    cpuDict[key].append("N/A")
            continue
    queue.put(cpuDict)
    return cpuDict

def multiProcess(cpus, processesToRun):
    cpuDict = {
        "Name": [],
        "CPU Class": [],
        "Socket": [],
        "Launched": [],
        "Overall Score": [],
        "Single Thread Rating": [],
        "Clockspeed": [],
        "Turbo Speed": [],
        "TDP": [],
        "Cores": [],
        "Threads": []
    }
    if processesToRun > numCPUs:
        processesToRun = numCPUs
    if processesToRun > len(cpus):
        processesToRun = len(cpus)
    queue = Queue(processesToRun)
    numCPUsPerProcess = len(cpus) // processesToRun
    extra = len(cpus) % processesToRun
    start = 0
    for x in range(processesToRun):
        cpusToGet = []
        end = start + numCPUsPerProcess
        if extra > 0:
            end += 1
            extra -= 1
        cpusToGet = cpus[start:end]
        start = end
        p = Process(target=gatherResults, args=(cpusToGet, queue))
        processes.append(p)
        p.start()
    while not queue.full():
        pass
    for x in range(processesToRun):
        d = queue.get()
        for k, v in d.items():
            for x in v:
                cpuDict[k].append(x)
    return cpuDict

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='API to pull CPU data from cpubenchmark.net')
    parser.add_argument('-i', nargs=1, metavar="file", help="input file containing a list of CPUs")
    parser.add_argument('-o', nargs=1, metavar="file", help="output file to save data to")
    parser.add_argument('-p', nargs='?', type=int, const=numCPUs, metavar="processes",
                        help="the number of processes you would like to run")
    parser.add_argument('-e', action='store_true', help="examples of how CPUs should be formatted")
    args = parser.parse_args()
    
    singleThreaded = True
    cpusToUse = 0
    
    if args.e:
        print("Example CPUs:")
        print("Intel Xeon X5650 @ 2.67GHz&cpuCount=2")
        print("Apple M1 Pro 10 Core")
        print("Intel Core i7-6920HQ @ 2.90GHz")
        print("Intel Core i9-9900K @ 3.60GHz")
        print("Intel Xeon E5-2670 v2 @ 2.50GHz")
        exit()
    if args.i:
        cpuListFileName = str(args.i[0])
    if args.o:
        csvFileName = str(args.o[0])
    if args.p:
        cpusToUse = args.p
        singleThreaded = False
    
    if not validInputFile():
        exit()
    
    try:
        start = time.time()
        cpus = getCPUs()
        currentData = readCSV()
        
        if singleThreaded:
            cpuDataDict = gatherResults(cpus, Queue(1))
        else:
            cpuDataDict = multiProcess(cpus, cpusToUse)
        
        rankCPUs(cpuDataDict)
        addAuxData(currentData, cpuDataDict)
        exportToCSV(cpuDataDict)
        finalTime = time.time() - start
        
        print("done.")
        print("Finished in: " + str(finalTime) + " seconds")
    except Exception as e:
        print(f"\nAn error occurred during processing: {str(e)}")
