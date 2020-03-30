#!/usr/bin/python

# purpose: query the HyperFlex API for runtime statistics and health

from __future__ import division
import requests
import json
import logging
import argparse
import sys

# ignore warnings when using a self-signed certificate
requests.packages.urllib3.disable_warnings()

# default values
server = '10.6.160.180'
username = 'admin'
verbose = False
query = 'about'

# parsing the argument list
parser = argparse.ArgumentParser()
parser.add_argument('-H', '--host')
parser.add_argument('-u', '--username', '--user')
parser.add_argument('-p', '--password', '--pass')
parser.add_argument('-q', '--query')
parser.add_argument('-w', '--warn', '--warning', type=int, help="warning level in percent")
parser.add_argument('-c', '--crit', '--critical', type=int, help="critical level in percent")
parser.add_argument('-v', '--verbose', action='store_true', help="increase output verbosity")
parser.add_argument('-d', '--debug', action='store_true')
parser.add_argument('--version', action='version', version='0.1')
args = parser.parse_args()

if args.host:
	server=args.host
if args.username:
	username=args.username
if args.query:
	query=args.query
if args.verbose:
	logging.basicConfig(level=logging.INFO)
elif args.debug:
	logging.basicConfig(level=logging.DEBUG)
if args.password:
	password=args.password
else:
	print "specify password"
	sys.exit(3)

logging.info("Server: " + server)
logging.debug("User: " + username)
logging.debug("Pass: " + password)


def get_auth_token():
	url = 'https://'+server+'/aaa/v1/auth?grant_type=password'
	headers={'content-type':'application/json'}

	payload = {
		"username": username,
		"password": password,
		"client_id": "HxGuiClient",
		"client_secret": "Sunnyvale",
		"redirect_uri": "http://localhost:8080/aaa/redirect"
	}

	try:
		response = requests.post(url, headers=headers,
			data=json.dumps(payload), verify=False, timeout=4)
		if response.status_code == 201:
			if response.json().get('access_token'):
				logging.info("Got token ok")
				return response.json()
			logging.error("Failed get a token " + response.content)
			return None
	except Exception as e:
		logging.error("Post for token failed \n"+str(e))
		return None


def query_hx_api(authdata,url):
	logging.debug("called query_hx_api()")

	try:
		headers = { 'Authorization':
			authdata['token_type'] + ' ' + authdata['access_token'],
			'Connection':'close' }
		logging.debug("url: "+url)
		response = requests.get( url, headers=headers, verify=False, timeout=10 )
		if response.status_code == 200:
			logging.debug("Got data ok")
			return response.json()
		logging.error("Failed to get data "+response.content)
		return None

	except Exception as e:
		logging.error("Post for data failed \n"+str(e))
		print "UNKNOWN - API query failed for server "+server
		sys.exit(3)


if __name__ == '__main__':
	token = get_auth_token()
	if token:
		#print json.dumps(token)
		logging.info("Token: "+token['access_token'])

		if query=='about':
			about = query_hx_api(token, 'https://'+server+'/rest/about')
			print about['fullName']
			print about['modelNumber']
		elif 'datastore_' in query:
			datastore = query_hx_api(token, 'https://'+server+'/rest/summary')

			if query=='datastore_health':
				if datastore['resiliencyInfo']['state']=='HEALTHY':
					print "OK - Cluster is healthy"
					sys.exit(0)
				else:
					print "WARN - Cluster is "+datastore['resiliencyInfo']['state']
					sys.exit(1)

			elif query=='datastore_freeCapacity':
				totalCapacity = datastore['totalCapacity']
				freeCapacity  = datastore['freeCapacity']
				inUseCapacityPercent = ( 1 - freeCapacity / totalCapacity ) * 100

				if args.crit and inUseCapacityPercent > args.crit:
					nagios_text='CRIT'
					nagios_exit=2
				elif args.warn and inUseCapacityPercent > args.warn:
					nagios_text='WARN'
					nagios_exit=1
				else:
					nagios_text='OK'
					nagios_exit=0

				print("%s - Free capacity is %0.2f TB (%d%% in use) | free_storage=%d"
					% (nagios_text, freeCapacity /1000/1000/1000/1000, 
					   inUseCapacityPercent, totalCapacity-freeCapacity)
				)
				sys.exit( nagios_exit )

		elif query=='failed_disks':
			failed_disks = query_hx_api(token, 
				'https://'+server+'/coreapi/v1/hypervisor/disks?state=OFFLINE')
			# dictionary 'failed_disks' contains a list of failed/removed disks
			# It is empty if all disks are working properly

			if len(failed_disks) >= 2:
				print "CRIT - "+str(len(failed_disks))+" failed disks"
				sys.exit(2)
			elif len(failed_disks):
				print "WARN - 1 failed disk"
				sys.exit(1)
			else:
				print "OK - All disk healthy"
				sys.exit(0)

		elif query=='failed_nodes':
			failed_nodes = query_hx_api(token, 
				'https://'+server+'/coreapi/v1/hypervisor/hosts?state=OFFLINE')
			# dictionary 'failed_disks' contains a list of failed/removed disks
			# It is empty if all disks are working properly

			if len(failed_nodes):
				print "CRIT - One or more nodes are offline"
				sys.exit(2)
			else:
				print "OK - All nodes healthy"
				sys.exit(0)

		else:
			print "unknown query"
			sys.exit(3)

	sys.exit(0)
