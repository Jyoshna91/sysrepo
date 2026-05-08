import os, sys
import ast
import time
import logging
import pandas as pd

from tejas_utils import *
from db_querys import DbQuery

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.proxy import Proxy, ProxyType
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from common_libs.logger import logger, BASE_DIR
from ui.get_cred_data import load_credentials

class TejasAutomation:

    def __init__(self, label):
        # logger.info("Initializing Tejas Automation")
        self.label= label
        self.db_query = DbQuery()
        self.diag_cred = self.db_query.get_daig_credentials()

        self.driver = None
        self.previous_zone = None

    # Config & Zone
    def get_config_data(self):
        logger.info("Loading configuration file")
        config = load_config(self)


        ###### Zone Based Password Logic ######
        ## Get Credentials from CSV file
        cred_json_path = os.path.join(BASE_DIR, "ui", "creds.json")
        cred = load_credentials(cred_json_path)

        self.username = cred["OLM_ID"]

        zone_password_map = {
                            "south": cred["south_password"],
                            "north": cred["north_password"],
                            "west": cred["west_password"]
                        }
        
        Node_df=self.db_query.get_node_data(self.label)

        # Filter row based on label
        filtered_df = Node_df[Node_df['label'] == self.label]

        if not filtered_df.empty:
            zone = str(filtered_df['zone'].iloc[0]).strip().lower()
            self.password = zone_password_map.get(zone)

        logger.info(f" OLM ID: {self.username} South :{zone_password_map['south']} North :{zone_password_map['north']} West :{zone_password_map['west']}")




        # ================= USERNAME =================
        raw_user = self.diag_cred.get("user_name", "")
 
        # Case 1: Pandas Series → convert to list
        if hasattr(raw_user, "tolist"):
            self.diag_username = [str(x).strip() for x in raw_user.tolist()]
 
        # Case 2: String (single value)
        elif isinstance(raw_user, str):
            self.diag_username = [raw_user.strip()]
 
        # Case 3: Already list
        elif isinstance(raw_user, list):
            self.diag_username = [str(x).strip() for x in raw_user]
 
        # Fallback
        else:
            self.diag_username = []
 
        # ================= PASSWORD =================
        raw_passwords = self.diag_cred.get("password", "")
 
        # Case 1: Pandas Series → convert to list
        if hasattr(raw_passwords, "tolist"):
            self.diag_passwords = [str(x).strip() for x in raw_passwords.tolist()]
 
        # Case 2: String → try to evaluate list string
        elif isinstance(raw_passwords, str):
            try:
                parsed = ast.literal_eval(raw_passwords)
 
                if isinstance(parsed, list):
                    self.diag_passwords = [str(x).strip() for x in parsed]
                else:
                    self.diag_passwords = [str(parsed).strip()]
 
            except Exception:
                self.diag_passwords = [raw_passwords.strip()]
 
        # Case 3: Already list
        elif isinstance(raw_passwords, list):
            self.diag_passwords = [str(x).strip() for x in raw_passwords]
 
        # Fallback
        else:
            self.diag_passwords = []
 
        self.zones_list = config["zones_list"]
 
        logger.debug(f"Configured zones: {list(self.zones_list.keys())}")
        logger.info("Configuration loaded successfully")

    def get_zone(self, row):
 
        try:
            logger.debug(f"Resolving zone for node: {row['label']}")
 
            for zone, data in self.zones_list.items():
 
                if make_lower(row["zone"]) == make_lower(zone):
 
                    self.tejas_zone = zone
                    self.tejas_url = str(data["url"])
                    self.tejas_proxy_ip = str(data["proxy_ip"])
                    self.tejas_proxy_port = int(data["proxy_port"])
 
                    logger.info(
                        f"Node {row['label']} mapped to zone {self.tejas_zone}"
                    )
                    return
 
            logger.error(f"Zone not found for node {row['label']} with circle {row['zone']}")
            raise Exception("Zone not found")
 
        except Exception as e:
            logger.exception("Zone resolution failed")
            raise Exception("Zone resolution failed")

    # initialize driver
    def driver_initialize(self):
        logger.info(
            f"Launching Firefox for zone={self.tejas_zone}, "
            f"proxy={self.tejas_proxy_ip}:{self.tejas_proxy_port}"
        )

        for var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
            os.environ.pop(var, None)

        proxy = Proxy()
        proxy.proxy_type = ProxyType.MANUAL
        proxy.http_proxy = f"{self.tejas_proxy_ip}:{self.tejas_proxy_port}"
        proxy.ssl_proxy = f"{self.tejas_proxy_ip}:{self.tejas_proxy_port}"

        options = Options()
        options.set_preference("network.proxy.type", 1)
        options.set_preference("network.proxy.http", self.tejas_proxy_ip)
        options.set_preference("network.proxy.http_port", self.tejas_proxy_port)
        options.set_preference("network.proxy.ssl", self.tejas_proxy_ip)
        options.set_preference("network.proxy.ssl_port", self.tejas_proxy_port)
    
        # OpenS while connecing the VPN also 
        options.set_preference("network.proxy.no_proxies_on", "localhost, 127.0.0.1")

        self.driver = webdriver.Firefox(options=options)
        self.driver.maximize_window()
        self.driver.get(self.tejas_url)
    
    #main login Part
    def tejas_login(self, max_retries=3):
        logger.info("Logging into Tejas UI")

        for attempt in range(max_retries):
            
            # Wait until username field is present (fresh DOM)
            Wait = WebDriverWait(self.driver, 15)
            Wait.until(EC.presence_of_element_located((By.XPATH, "//td[contains(text(),'Login Name:')]//following::input[1]")))

            # Always re-locate elements (VERY IMPORTANT)
            username_field = self.driver.find_element(By.XPATH, "//td[contains(text(),'Login Name:')]//following::input[1]")
            password_field = self.driver.find_element(By.XPATH, "//td[contains(text(),'Password:')]//following::input[1]")

            username_field.clear()
            password_field.clear()

            username_field.send_keys(self.username)
            password_field.send_keys(self.password)

            click(self.driver, (By.XPATH, "//input[@name='login']"))
            time.sleep(5)

            error = self.driver.find_elements(By.XPATH, "//td[contains(@class,'errormsg') and contains(text(),'Naming Server')]")
            if error:
                logger.warning("Naming Server issue detected. Retrying...")
                time.sleep(5)   # wait for server to stabilize
                continue

            logger.info("Login successful")
            return

        raise Exception("Login failed after retries")
    
    # ---------------- MAIN METHOD (PER NODE) ---------------- #
    def process_node(self, row):
        """ Call this method from another file """

        self.node_name = row["label"]
        logger.info(f"Processing node: {self.node_name}")

        self.get_zone(row)

        # First time
        if self.driver is None:
            self.driver_initialize()
            self.driver.get(self.tejas_url)
            self.tejas_login()

        # Zone changed → re-login
        elif self.previous_zone != self.tejas_zone:
            logger.info(f"Zone changed → {self.tejas_zone}")

            self.driver.delete_all_cookies()
            time.sleep(2)

            self.driver.get(self.tejas_url)
            self.tejas_login()

        else:
            logger.info(f"Reusing session for {self.tejas_zone}")

        self.previous_zone = self.tejas_zone

        return self.driver
    
    # ---------------- CLOSE ---------------- #
    def close_browser(self):
        if self.driver:
            logger.info("Closing browser")
            self.driver.quit()
            self.driver = None
