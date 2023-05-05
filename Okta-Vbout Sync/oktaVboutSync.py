
import requests
import json
import configparser
import logging, logging.handlers
import smtplib, ssl
# from datetime import datetime

class oktaVboutSync():

    def __init__(self):

        # Read configuration parameters
        config = configparser.RawConfigParser() # RawConfigParser sets interpolation to none so any % characters in the URLs can work
        config.read('config.ini')
        self.oktaApiKey = config['general']['oktaApiKey']
        self.vboutApiKey = config['general']['vboutApiKey']
        self.vboutUrl = config['general']['vboutUrl']
        self.oktaUrl = config['general']['oktaUrl']
        self.oktaLimit = config['general']['oktaLimit']  # Number of users Okta API will return. Max allowed is 200. If there are more users, "link" header will include the URL to the next page
        self.excludedGroups = config['general']['excludedGroups']  # Okta groups that will not be added to VBout
        self.vboutListToSync = config['general']['vboutListToSync'] # Okta users will be added/deleted to/from this list on Vbout Contacts page

        self.groups = [] # Will be a list that holds a dictionary of groups. Each group dictionary will have an group id, name and group creation date

        # updateTime = "Last updated on: " + datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S.%f')[:-7]+' GMT' # record the GMT time the script was run at
        self.vboutApiLimit = 1000000 # api default is to return 100 results. Setting a high limit so all results are returned 
        self.oktaUsers = {} # Will hold user details in a dictionary, where email will be the main key
        self.vboutContacts = {} # Will hold user details in a dictionary, where email will be the main key
        self.vboutOktaListID = ''
        self.vboutOktaListFields = {}
        self.vboutFirstNameFieldID = ''
        self.vboutLastNameFieldID = ''
        self.vboutEmailFieldID = ''
        self.vboutCustomerFieldID = ''
        self.vboutActivatedFieldID = ''

        self.smtpHost = config.get("general", "smtpHost")
        self.smtpPort = config.getint("general", "smtpPort")
        self.smtpUser = config.get("general", "smtpUser")
        self.smtpPassword = config.get("general", "smtpAppPassword")
        self.recipients = config.get("general", "recipients").split(',') # Convert the emails into a list
        self.emailBody = ""
        self.all_success = True # Flag to monitor if any errors are received, initially set to True
        self.successfullyAddedUsers = 'USERS ADDED:\n'
        self.successfullyDeletedUsers = 'USERS DELETED:\n'

    # Setting up logger
    logger = logging.getLogger()
    logging.getLogger("chardet.charsetprober").disabled = True # Disable chardet encoding errors on the logs
    logger.setLevel(logging.DEBUG)
    handler = logging.handlers.TimedRotatingFileHandler(filename='logs/oktaVboutSync.log', when='midnight', interval=1, backupCount=0,encoding='utf-8', delay=False, utc=False) # Make sure encoding is set to utf-8 as axiory response is causing encoding errors
    handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s: %(message)s'))
    logger.addHandler(handler)
    logging.info('Starting oktaVboutSync.py')

    # Get All Groups in Okta
    def listGroups(self):
        '''
        Get all Okta Groups. 

        "link" header will include a "rel=next" parameter if there is a next page
        e.g. <https://${yourOktaDomain}/api/v1/users?after=00abcYZLMRWLUWIEDKK>; rel="next"
        If there are no other pages, link header will return "rel=self" 

        listGroups endpoint:   {{url}}/api/v1/groups
        '''
        link = '"next"' # Continue making requests if the "Link" header has ref="next"

        url = self.oktaUrl + "/api/v1/groups/"
        self.logger.info("listGroups request url: {}".format(url))

        payload = ""
        headers = {
            'Accept': "application/json",
            'Content-Type': "application/json",
            'Authorization': "SSWS " + self.oktaApiKey
            }

        while (link == '"next"'):
            self.logger.info("Link header ref={}".format(link))

            response = requests.request("GET", url, data=payload, headers=headers)
            responseJSON = json.loads(response.text)
            self.logger.info("listGroups response body: {}".format(responseJSON))

            for group in responseJSON:
                eachGroup = {}
                eachGroup['name'] = group['profile']['name']
                eachGroup['id'] = group['id']
                self.groups.append(eachGroup)   ## Add to the "groups" (list) attribute

            self.logger.info("listGroups response headers: {}".format(response.headers))
            link = response.headers['Link'].split('rel=') # <https://xxxxxxxxx.okta.com/api/v1/groups?limit=10000>; rel="self". link will be '"next"' if there is more data to be requested

    # Get Users in an Okta Group
    def getOktaGroupMembers(self, groupName, groupId):
        '''
        Get Okta group members

        "link" header will include a "rel=next" parameter if there is a next page
        e.g. <https://${yourOktaDomain}/api/v1/users?after=00abcYZLMRWLUWIEDKK>; rel="next"
        If there are no other pages, link header will return "rel=self" 
        
        listGroupMemmbers endpoint:  {{url}}/api/v1/groups/{{groupId}}/users
        '''
        link = '"next"' # Continue making requests if the "Link" header has ref="next"   

        url = self.oktaUrl + "/api/v1/groups/" + groupId + "/users"
        self.logger.info("listGroupMembers request url: {}".format(url))
        
        payload = ""
        headers = {
            'Accept': "application/json",
            'Content-Type': "application/json",
            'Authorization': "SSWS " + self.oktaApiKey
            }

        while (link == '"next"'):
            response = requests.request("GET", url, data=payload, headers=headers)
            responseJSON = json.loads(response.text)
            self.logger.info("listGroupMembers response body: {}".format(responseJSON))

            for user in responseJSON:
                if (user['status'] != "DEPROVISIONED"):                   
                    if (user['status'] != "DEPROVISIONED"): 
                        eachUser = {'firstName':user['profile']['firstName'], 'lastName':user['profile']['lastName'], 'created':user['created'].split('T')[0], 'group':groupName}
                        self.oktaUsers[user['profile']['login']] = eachUser
            self.logger.info("listGroups response headers: {}".format(response.headers))
            link = response.headers['Link'].split('rel=') # <https://xxxxxxxxxxxxx.okta.com/api/v1/groups?limit=10000>; rel="self". link will be '"next"' if there is more data to be requested

    # Get currnet lists on VBout
    def getVboutLists(self):
        '''
        Get VBout lists to find the id of OktaUsers list and fetch the ids of it's fields

        Lists endpoint:  https://api.vbout.com/1/emailmarketing/getlists.json?key=xxxxxxxxxxxxxx
        '''  

        url = self.vboutUrl + "emailmarketing/getlists.json?key=" + self.vboutApiKey + '&limit=' + str(self.vboutApiLimit)
        self.logger.info("vbout getlists request url: {}".format(url))
        
        payload = ""
        headers = {
            'Accept': "application/json",
            'Content-Type': "application/json"
            }

        response = requests.request("GET", url, data=payload, headers=headers)
        responseJSON = json.loads(response.text)['response']
        self.logger.info("VBout Lists response body: {}".format(responseJSON))

        if('data' in responseJSON and 'lists' in responseJSON['data'] and 'items' in responseJSON['data']['lists']):
            if(responseJSON['data']['lists']['count'] >= self.vboutApiLimit):
                print("ERROR there might be more lists that the API has not returned, check the limit parameter supplied")
                self.all_success = False # response is not in the expected structure
                self.emailBody = self.emailBody + 'Received lists count is equal to the limit parameter supplied to the getlists request, so script might have not received all VBout lists. Check the limit parameter used. \nVbout getlists request url: ' + url + ' \nReceived response: ' +  response.text
            else:
                vboutLists = responseJSON['data']['lists']['items']
                oktaListNotFound = True
                for eachList in vboutLists:
                    if (eachList['name'] == self.vboutListToSync):
                        oktaListNotFound = False # Clear the flag as the Okta list is found
                        self.vboutOktaListID = eachList['id']
                        self.vboutOktaListFields = eachList['fields']
                        key_list = list(self.vboutOktaListFields.keys())
                        val_list = list(self.vboutOktaListFields.values())
    
                        self.vboutFirstNameFieldID = key_list[val_list.index('First Name')]
                        self.vboutLastNameFieldID = key_list[val_list.index('Last Name')]
                        self.vboutEmailFieldID = key_list[val_list.index('Email Address')]
                        self.vboutCustomerFieldID = key_list[val_list.index('Customer')]
                        self.vboutActivatedFieldID = key_list[val_list.index('Activated')]
                        self.logger.info("vbout getlists response headers: {}".format(response.headers))
                        self.getVboutContacts(self.vboutOktaListID)
                if(oktaListNotFound):
                    self.all_success = False # Okta Users list is not found in the vbout getlists response
                    self.emailBody = self.emailBody + 'Response received from VBout getlists does not include the' + self.vboutListToSync + 'list. \nVBout getlists request url: ' + url + ' \nReceived response: ' +  response.text
        else:
            self.all_success = False # response is not in the expected structure
            self.emailBody = self.emailBody + 'Response received from VBout getlists request is not in the expected format. \nVbout getlists request url: ' + url + ' \nReceived response: ' +  response.text + ' \nExpected a "data" and then a "lists" attribute'

    # Get VBout Contacts in a List
    def getVboutContacts(self, id):
        '''
        Get VBout contacts that are in the Okta Users lists. API returns a max of 100 contacts. Check the count 

        getcontacts endpoint:  https://api.vbout.com/1/emailmarketing/getcontacts.json?key=xxxxxxxxxxxxx&listid=97396
        '''  

        url = self.vboutUrl + "emailmarketing/getcontacts.json?key=" + self.vboutApiKey + '&listid=' + id + '&limit=' + str(self.vboutApiLimit)
        self.logger.info("vbout getcontacts request url: {}".format(url))
        
        payload = ""
        headers = {
            'Accept': "application/json",
            'Content-Type': "application/json"
            }

        response = requests.request("GET", url, data=payload, headers=headers)
        responseJSON = json.loads(response.text)['response']
        self.logger.info("vbout getcontacts response body: {}".format(responseJSON))

        if('data' in responseJSON and 'items' in responseJSON['data']['contacts']):
            if(responseJSON['data']['contacts']['count'] >= self.vboutApiLimit):
                print("ERROR there might be more contacts that the API has not returned, check the limit parameter supplied")
                self.all_success = False # response is not in the expected structure
                self.emailBody = self.emailBody + 'Received contacts count is equal to the limit parameter supplied to the getcontacts request, so script might have not received all VBout contacts. Check the limit parameter used. \nVbout getcontacts request url: ' + url + ' \nReceived response: ' +  response.text
            else:
                contactsList = responseJSON['data']['contacts']['items']
                for eachUser in contactsList:
                    self.vboutContacts[eachUser['email']] = eachUser
                self.logger.info("vbout getcontacts response headers: {}".format(response.headers))
        else:
            self.all_success = False # response is not in the expected structure
            self.emailBody = self.emailBody + 'Response received from VBout getcontacts request is not in the expected format. \nVbout getcontacts request url: ' + url + ' \nReceived response: ' +  response.text + ' \nExpected a "data" and then a "contacts" attribute'

    # Add Contacts to VBout
    def addVboutContact(self, userEmail, userDetails, listID):
        '''
        Add a contact to the Vbout List with the received id
        Expected userDetails parameter format: {'user@company.com': {'firstName': 'User', 'lastName': 'User', 'group': 'oktaGroup1'}, 'user.second@acy.com': {'firstName': 'User', 'lastName': 'Second', 'group': 'oktaGroupX'}, ... }

        addcontact endpoint:  POST https://api.vbout.com/1/emailmarketing/addcontact.json?key={YOUR_API_ID} email=info@example.com status=active listid=24 fields[125]=John fields[1204]=Doe fields[325]=1983-9-1
        '''  

        url = self.vboutUrl + "emailmarketing/addcontact.json?key=" + self.vboutApiKey + '&email=' + userEmail + '&status=active&listid=' + listID + '&fields[' + str(self.vboutFirstNameFieldID) + ']=' + userDetails['firstName'] +'&fields[' + str(self.vboutLastNameFieldID) + ']=' + userDetails['lastName'] + '&fields[' + str(self.vboutCustomerFieldID) + ']=' + userDetails['group'] + '&fields[' + str(self.vboutActivatedFieldID) + ']=' + userDetails['created'] + '&fields[' + str(self.vboutEmailFieldID) + ']=' + userEmail
        print('addUser url',url)
        self.logger.info("vbout addcontact request url: {}".format(url))
        
        payload = ""
        headers = {
            'Accept': "application/json",
            'Content-Type': "application/json"
            }

        response = requests.request("POST", url, data=payload, headers=headers)
        responseJSON = json.loads(response.text)['response']
        self.logger.info("vbout addcontact {} response body: {}".format(userEmail, responseJSON))

        if('header' in responseJSON and 'status' in responseJSON['header'] and responseJSON['header']['status'] == 'ok'):
            self.logger.info("addcontact {} SUCCESS: {}".format(userEmail, responseJSON['data']))
            print('--SUCCESS addcontact ', userEmail)
            self.successfullyAddedUsers = self.successfullyAddedUsers + userEmail + '\n'
        else:
            self.logger.info("addcontact {} ERROR: {}".format(userEmail, responseJSON['data']))
            print('--ERROR addcontact ', userEmail)
            self.all_success = False # mark the error in the email
            self.emailBody = self.emailBody + 'Failed to add a contact to VBout. \nVbout addcontact request url: ' + url + ' \nReceived response: ' +  response.text

    def deleteVboutContact(self, userEmail, contactID, listID):
        '''
        Delete a contact from the Vbout List with the received id

        deletecontact endpoint:  POST https://api.vbout.com/1/emailmarketing/deletecontact.json?key={YOUR_API_ID} id=14523 listid=45678
        '''  

        url = self.vboutUrl + "emailmarketing/deletecontact.json?key=" + self.vboutApiKey + '&id=' + contactID + '&listid=' + listID
        self.logger.info("vbout deletecontact request url: {}".format(url))
        
        payload = ""
        headers = {
            'Accept': "application/json",
            'Content-Type': "application/json"
            }

        response = requests.request("POST", url, data=payload, headers=headers)
        responseJSON = json.loads(response.text)['response']
        self.logger.info("vbout deletecontact response body: {}".format(responseJSON))

        if('header' in responseJSON and 'status' in responseJSON['header'] and responseJSON['header']['status'] == 'ok'):
            self.logger.info("deletecontact {} SUCCESS: {}".format(userEmail, responseJSON['data']))
            print('--SUCCESS deletecontact ', userEmail)
            self.successfullyDeletedUsers = self.successfullyDeletedUsers + userEmail + '\n'
        else:
            self.logger.info("deletecontact {} ERROR: {}".format(userEmail, responseJSON['data']))
            print('--ERROR deletecontact ', userEmail)
            self.all_success = False # mark the error in the email
            self.emailBody = self.emailBody +'Failed to delete a contact from VBout. \nVbout deletecontact request url: ' + url + ' \nReceived response: ' +  response.text
    
    def send_email(self):
        print("\n\nSending email")
        
        if self.all_success:
            emailSubject = "Vbout-Okta SYNC - Success"
        else:
            emailSubject = "Vbout-Okta SYNC - ERROR"
        self.emailBody = self.emailBody + self.successfullyAddedUsers + '\n' + self.successfullyDeletedUsers
        message = 'Subject: {}\n\n{}'.format(emailSubject, self.emailBody)
        self.logger.info("Sending email: {}".format(message)) 
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(self.smtpHost, self.smtpPort, context=context) as server:
            server.login(self.smtpUser, self.smtpPassword)
            server.sendmail(self.smtpUser, self.recipients, message)

    
if __name__ == '__main__' :
    def syncOktaAndVbout():
        deleteDict = set(sync.vboutContacts) - set(sync.oktaUsers) # emails of users (derived from the keys of the dictionaries) in VBout that do not exist (or not active anymore) on Okta
        print("\n\n--to be deleted from vbout (total {})".format(len(deleteDict)))

        addDict = set(sync.oktaUsers) - set(sync.vboutContacts) # emails of active users (derived from the keys of the dictionaries) on Okta that do not exist in VBout
        print("\n++to be added from vbout (total {})".format(len(addDict)))
    
        for deleteUser in deleteDict:
            print('delete from vbout',deleteUser,sync.vboutContacts[deleteUser]['id'])
            sync.deleteVboutContact(deleteUser, sync.vboutContacts[deleteUser]['id'], sync.vboutOktaListID)
    
        for addUser in addDict:
            sync.addVboutContact(addUser, sync.oktaUsers[addUser], sync.vboutOktaListID)

    def deleteAllVBoutContacts():
        deleteDict = set(sync.vboutContacts)
        print("\n--DELETE ALL CONTACTS IN VBOUT {} LIST".format(sync.vboutListToSync))
        for deleteUser in deleteDict:
            print('delete from vbout',deleteUser,sync.vboutContacts[deleteUser]['id'])
            sync.deleteVboutContact(deleteUser, sync.vboutContacts[deleteUser]['id'], sync.vboutOktaListID)

    sync = oktaVboutSync()
    sync.listGroups() # Get Okta groups, store in "groups" attribute

    for group in sync.groups:
        internalGroups = sync.excludedGroups.split(",")
        if((group['name'] not in internalGroups)):     # Do not print internal test groups or groups that are used for functionality permissioning purposes
            print("Getting members of Okta group: {}".format(group['name']))
            sync.getOktaGroupMembers(group['name'], group['id'])

    sync.getVboutLists()
    
    print("\nOkta Users (total of {})".format(len(sync.oktaUsers)))
    print("\nVBout Contacts (total of {})",len(sync.vboutContacts))

    # SYNCH OKTA ACCOUNTS & VBOUT CONTACTS (COMMENT OUT syncOktaAndVbout() IF YOU WANT TO DELETE ALL VBOUT OKTA ACCOUNTS CONTACTS TO START FROM SCRATCH)
    syncOktaAndVbout()

    # UNCOMMENT FUNCTION BELOW (AND COMMENT THE syncOktaAndVbout CALL ABOVE) TO DELETE ALL USERS ON VBOUT OKTA ACCONUTS LIST
    #deleteAllVBoutContacts()

    sync.send_email()