import requests,json
r = requests.get('https://opendata.cwb.gov.tw/api/v1/rest/datastore/E-A0015-001?Authorization=CWB-68A93663-BED9-4D7E-9305-E42BC130F02D&limit=1&format=JSON')
data = json.loads(r.text)

class EarthquakeReport:
    def __init__(self,data):
        self.data = data
        self.earthquakeNo = data['records']['earthquake'][0]['earthquakeNo']
        self.reportImageURI = data['records']['earthquake'][0]['reportImageURI']
        self.originTime = data['records']['earthquake'][0]['earthquakeInfo']['originTime']
        self.depth = data['records']['earthquake'][0]['earthquakeInfo']['depth']['value']
        self.location = data['records']['earthquake'][0]['earthquakeInfo']['epiCenter']['location']

    def get(self):
        return self.earthquakeNo , self.reportImageURI,self.originTime, self.depth,self.location

output = EarthquakeReport(data).get()
print(output)