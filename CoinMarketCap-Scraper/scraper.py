# This script saves screenshots of the configured website by opening it in Chrome.
# 
# Complete the required parameters in config.ini
#
# Script will use the Selenium library, open Chrome, navigate to coinmarketcap.com, scroll down until BTC price is at the top of the page and take a screenshot.
# The script saves images to the file defined in config.ini, and also creates a zipped file for easy automated upload if required.
#
# INSTALLATION
# 1. Install selenium (pip install selenium)
#
# 2. Chrome should be installed on the box as ChromeDriver needs the Chrome binary.
#    On Linux, follow the steps below:
#    -> Download the .deb file with wget:   wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
#    -> Install Chrome with:                sudo apt install ./google-chrome*.deb
# 
# 3. Download Chrome webdriver from https://chromedriver.chromium.org/downloads
#    Version you downloaded should match the version of Chrome installed on your device
#    Place the exe/binary file you downloaded into the project root folder, and update the CHROMEDRIVER_PATH in config.ini with the name of the file
#    Note: Need to add the executable permission on Linux:  sudo chmod +x chromedriver_104_linux64
# 
# 4. Pillow (PIL) needs the external libwebp library to be able to convert png images to webp format, 
#    which is a smaller file than png and better if the image will be used on a website.
#    -> On Ubutnu, install with:    sudo apt-get install -y libwebp-dev
#    -> On Windows, download and execute webpmux.exe from https://developers.google.com/speed/webp/download
#    Note: Install Pillow AFTER libwep-dev is installed, otherwise, you might need to reinstall pillow after the above library has been installed
#           python3 -m pip uninstall Pillow
#           python3 -m pip install Pillow
# 
# 5. Run saveScreenshots.py to execute the script:    python saveScreenshots.py

import configparser
import os, platform, csv, shutil
from PIL import Image
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
# from selenium.webdriver.common.keys import Keys
# from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException

# Get config from config.ini
config = configparser.RawConfigParser() # RawConfigParser sets interpolation to none so any % characters in the URLs can work
config.read(os.path.join(os.path.dirname(os.path.abspath(__file__)),'config.ini'))
CHROMEDRIVER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), config.get('config','CHROMEDRIVER_PATH'))
TIMEOUT = config.getint('config','TIMEOUT') # Maximum time to wait for the dashboard to load
POLLING_FREQUENCY = config.getfloat('config','POLLING_FREQUENCY') # Frequency at which the scrpt will check the dashboard DOM for html elements to appear/disappear
OUTPUTFOLDER_PATH = config.get('config','OUTPUTFOLDER_PATH') # Path to the directory where dashboard screenshots will be saved in
BROWSER_SIZE = config.get('config','BROWSER_SIZE')
IMAGE_WIDTH = config.getint('config','IMAGE_WIDTH') # Width of the image to be saved
IMAGE_HEIGHT = config.getint('config','IMAGE_HEIGHT') # Height of the image to be saved
TOTAL_TABLE_ROWS_PER_PAGE = config.getint('config','TOTAL_TABLE_ROWS_PER_PAGE')
SCROLL_WHEN_INDEX = config.getint('config','SCROLL_WHEN_INDEX')
WEBSITE_URL = config.get('config','WEBSITE_URL')
CONSENT_PAGE_ID = config.get('config', 'CONSENT_PAGE_ID')
CONSENT_CLOSE_XPATH= config.get('config','CONSENT_CLOSE_XPATH')
ADS_CONTAINER = config.get('config', 'ADS_CONTAINER')
ADS_CONTAINER_CLOSE = config.get('config', 'ADS_CONTAINER_CLOSE')
FIRST_LOAD_XPATH = config.get('config', 'FIRST_LOAD_XPATH') # Xpath that will be awaited before proceeding to the next step
SCROLL_TO_ELEMENT = config.get('config','SCROLL_TO_ELEMENT') # Xpath of the main table to which Selenium will scroll down to

# Initialize Chrome
options = webdriver.ChromeOptions()
options.add_experimental_option('excludeSwitches', ['enable-logging']) # This will silence "USB Device not functioning" errors Chrome might return
options.add_argument(BROWSER_SIZE)
if (platform.system() != 'Windows'): # Hide Chrome browser if the script is run on a Linux server, which most porbably does not have a display
    options.add_argument('headless') # 'headless' will keep Chrome browser hidden
chrome_service = Service(CHROMEDRIVER_PATH)
driver = webdriver.Chrome(service=chrome_service, options=options)

def saveTableToCsv():
    """
    Saves the table on crypto prices on CoinMarketCap's first page to a csv file. Scrapes rows in batches and keeps scrolling down the page to get table rows fetched as 
    virtual scrolling is used (a table with 100 empty rows gets rendered on DOM but only the visible ~20 rows have data).
    """
    global driver
    print('Saving table contents row by row to csv:')
    
    data = []
    noOfIterations = 0
    lastRow = ''
    iterations_count = TOTAL_TABLE_ROWS_PER_PAGE / (SCROLL_WHEN_INDEX-1)

    while noOfIterations < iterations_count:
        if lastRow:
            driver.execute_script("arguments[0].scrollIntoView();", lastRow) # If lastRow is set, scroll to it using JavaScript so Coinmarketcap retrieves the table contents for the next set of rows
        table = driver.find_element(By.CSS_SELECTOR, '.cmc-table') # Find the table and iterate over its rows to extract data

        rows = table.find_elements(By.CSS_SELECTOR, 'tr')
        topRows = rows[noOfIterations*SCROLL_WHEN_INDEX:SCROLL_WHEN_INDEX*(noOfIterations+1)] # Get the first 10 rows. Set SCROLL_WHEN_INDEX to +1 of the desired row number, i.e. to 11.
        for row in topRows:
            try: # contents of the table get updated frequently, so guard the script against stale element reference and re-capture the missed element
                cells = row.find_elements(By.CSS_SELECTOR, 'td')
                if cells:
                    row_data = [cell.text for cell in cells]
                    print(row_data) # Display the contents of the row copied over
                    data.append(row_data)
            except Exception as e:
                print(" * ERROR - Error while parsing table, contents probably got changed")
                print(e)
                driver.quit() # Quit Chrome driver, otherwise the process will remain running
        lastRow = row
        noOfIterations = noOfIterations + 1
        
    # Save the data to a CSV file
    with open(OUTPUTFOLDER_PATH+'/table_data.csv', 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerows(data)

def takeScreenshot():
    """
    Gets workbook name and dashboard name, opens the dashoard in Chrome, waits for it to fully load and saves a 200x150 pixel screnshot in png & webp formats
    Saves the screenshot as {workbookname}+{dashboardname} with alphanumkerical characters escaped:
    e.g. "ClientProfiler" -> "Top/Bottom Traders" screenshot will be saved as "ClientProfiler-TopBottomTraders.webp" with "/" and spaces removed
    """
    global driver
    print('Taking the screenshot of the page')
    fileName = 'screenshot'
    pngImage = OUTPUTFOLDER_PATH + '/' + fileName + '.png'
    webpImage = OUTPUTFOLDER_PATH + '/' + fileName + '.webp'


    driver.save_screenshot(pngImage) # Save png format as fallback image as well in case customer's browser does not support webp format
    image = Image.open(open(pngImage, 'rb'))
    image.thumbnail((IMAGE_WIDTH, IMAGE_HEIGHT))  # .thumbnail() method changes the Image object in place and doesn’t return a new object. Expects a tuple for size (width, height)
    image.save(pngImage, format='png')
    image = image.convert('RGB')
    image.save(webpImage, format='webp')
    image.close() # Close the image
    image = None # Clear the image variable

# START
# ==================================================================
if __name__ == "__main__":
    # Prepare the directory screenshots will be placed in. This will make sure there is an empty folder at script start.
    if not os.path.exists(OUTPUTFOLDER_PATH): # check if target folder to save the images in is present. If not, create it
        os.makedirs(OUTPUTFOLDER_PATH)
    else:  # If the folder exists, delete and create and empty one, so any previous screenshots get deleted and replaced when script is re-run
        try:
            shutil.rmtree(OUTPUTFOLDER_PATH)
            os.makedirs(OUTPUTFOLDER_PATH)
        except OSError as e:
            print ("Error: %s - %s." % (e.filename, e.strerror))
            driver.quit() # Quit Chrome driver, otherwise the process will remain running

    # Visit the website
    print('Navigating to: ' + WEBSITE_URL)
    driver.get(WEBSITE_URL)

    try:
        # Wait for page to get rendered in DOM until TIMEOUT in config.ini 
        watchlist = WebDriverWait(driver, TIMEOUT).until( EC.presence_of_element_located((By.XPATH, FIRST_LOAD_XPATH)) ) # Wait until the element defined in FIRST_LOAD_XPATH gets loaded
        print("Page loaded")

        # Check if consent banner appeared CONSENT_PAGE_ID
        consent = driver.find_elements(By.XPATH, CONSENT_PAGE_ID)
        if consent:
            print("Consent banner is displayed")
            WebDriverWait(driver, TIMEOUT).until( EC.presence_of_element_located((By.XPATH, CONSENT_CLOSE_XPATH)) ).click()
            print("Closed the consent banner")

        # Check if consent banner appeared CONSENT_PAGE_ID
        adsWindow = driver.find_elements(By.XPATH, ADS_CONTAINER)
        if adsWindow:
            print("There is an ads window")
            WebDriverWait(driver, TIMEOUT).until( EC.presence_of_element_located((By.XPATH, ADS_CONTAINER_CLOSE)) ).click()
            print("Closed the ads container")

        # Wait for Dealers folder to get rendered in DOM
        try:
            element = WebDriverWait(driver, TIMEOUT).until( EC.presence_of_element_located((By.XPATH, SCROLL_TO_ELEMENT)) ) # Wait until the SCROLL_TO_ELEMENT is loaded successfully
            driver.execute_script("arguments[0].scrollIntoView();", element) # Scroll to the element using JavaScript
            takeScreenshot()
            saveTableToCsv()
        except Exception as e:
            print(" * ERROR - Could not locate the SCROLL_TO_ELEMENT element")
            print(e)
            driver.quit() # Quit Chrome driver, otherwise the process will remain running
    except Exception as e:
            print(" * ERROR - Failed to locate the FIRST_LOAD_XPATH element")
            print(e)
            driver.quit() # Quit Chrome driver, otherwise the process will remain running

    print('Creating a zip file of the images folder')
    # Uncomment hte line below to have the output folder zipped
    #shutil.make_archive('output', 'zip', OUTPUTFOLDER_PATH)
    print('Done')
    driver.quit() # Quit Chrome driver