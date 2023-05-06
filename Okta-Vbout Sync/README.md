<h3>PROJECT NAME</h3>
VBout - Okta Sync
     
<h3>Author</h3>
Cagan Cerkez, 2023
     
<h3>DESCRIPTION</h3>
Vbout is a marketing automation tool.

Okta is an Identity-as-a-Service (IDaaS) platform.

This Python script can be scheduled to run daily and it will check your active users on Okta and will copy them to a contact list on Vbout, so you can target marketing campaigns against your active user base.

The bat file can be used to schedule the script to run periodically.

<h3>WHAT IT DOES</h3>    

* Get the list of all existing groups from Okta using their API 
* Get the list of users in each Okta group, excluding groups specified in the config.ini file (e.g. exclude those used for authorization so only authentication groups are fetched), so only unique accounts that belong to a single customer groups are fetched
* Get the list of all “Contact Lists” from VBout using their api
* Find the ID of the target list on VBout where the Okta contacts should be uploaded to & the ID’s of it’s fields (e.g. ID’s of the “First Name”, “Last Name”, “Activated”, etc fields)
* Fetch the “contacts” that you currently have under the target list on VBout using their API
* Compare the lists of active users fetched from Okta vs the list of contacts on VBout
* Add those accounts that exists in the Okta users list that do not exist on VBout to the target VBout contact list
* Remove those accounts which exist in the target VBout contact list that do not exist in the active Okta user list (e.g. users that got deactivated)
* Send a SUCCESS or an ERROR email to the recipients in config.ini file depending on how the script got executed, listing both the accounts added & deleted or any error message received
* Write execution logs to file in the /logs directory for troubleshooting in case of an error
