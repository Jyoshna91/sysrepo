import time
import os
import re
import io
import traceback
import pandas as pd
from datetime import datetime
from reportlab.platypus import SimpleDocTemplate, Image, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
import json
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
from pathlib import Path
from tejas_utils import *
from common_libs.logger import logger
from ne_level_adrs_deletion import NeLevelDeletion
from pathlib import Path
from datetime import datetime
import sys

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

# Detect base path for both CLI and PyInstaller EXE
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
    print("M4 Base_Dir = {BASE_DIR}")
else:
    BASE_DIR = Path(__file__).resolve().parent
    print("M4 Base_Dir = {BASE_DIR}")

SS_DIR = BASE_DIR / "screenshots"
EXPORT_DIR = BASE_DIR / "exports"

# Assets folder beside exe/script
ASSETS_DIR = BASE_DIR / "assets" / "non_live_circuit_deletion"

RUN_DIR = ASSETS_DIR / timestamp
RUN_DIR.mkdir(parents=True, exist_ok=True)

class NonLiveCircuitDeletion:

    def __init__(self, driver, db_query, diag_username, diag_passwords):
        logger.info("#### NonLiveCircuitDeletion initialized successfully ###########")
        self.driver = driver
        self.db_query = db_query
        self.diag_username = diag_username
        self.diag_passwords = diag_passwords
        self.processed_vcgs = set()
        self.login_manager = None
        self.elements = []
        self.styles = getSampleStyleSheet()
        self.current_pdf = str(RUN_DIR / f"node_deletion_screenshots_{timestamp}.pdf")

    def home_page(self):
        wait = WebDriverWait(self.driver, 10)
        configuration = wait.until(EC.visibility_of_element_located((By.XPATH, "//span[text()='Configuration']")))
        act = ActionChains(self.driver)
        act.move_to_element(configuration).perform()
        circuits = wait.until(EC.visibility_of_element_located((By.XPATH, "//span[text()='Circuits']")))
        act.move_to_element(circuits).perform()
        manage = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[text()='Manage Circuits']")))
        act.key_down(Keys.CONTROL).click(manage).key_up(Keys.CONTROL).perform()
        tabs = self.driver.window_handles
        self.driver.switch_to.window(tabs[-1])
        time.sleep(0.2)

    def collect_packet_flow(self, port_number):
        logger.info("collect packet flow started")
        time.sleep(1)
        wait = WebDriverWait(self.driver, 10)
        logger.info(f"checking packet flow status")
        self.driver.switch_to.default_content()
        WebDriverWait(self.driver, 20).until(EC.frame_to_be_available_and_switch_to_it((By.NAME, "nodeTocFrame")))
        time.sleep(1)
        performance_btn = wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//a[contains(@id,'itemText') and contains(normalize-space(.),'Performance')]")))
        performance_btn.click()
        time.sleep(1)
        cur_inter_btn = wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//a[contains(@id,'itemText') and contains(normalize-space(.),'Current interval')]")))
        cur_inter_btn.click()
        time.sleep(1)
        # -------- CLICK VCG --------
        vcg_btn = wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//a[contains(@id,'itemText') and contains(normalize-space(.),'VCG')]")))
        vcg_btn.click()
        time.sleep(1)
        self.driver.switch_to.default_content()
        WebDriverWait(self.driver, 20).until(
            EC.frame_to_be_available_and_switch_to_it((By.NAME, "nodeBodyFrame"))
        )
        port_ptn = f"//a[contains(@href,'Interface') and b[contains(normalize-space(),'{port_number}')]]"
        port_ptn = wait.until(EC.element_to_be_clickable((By.XPATH, port_ptn)))
        port_ptn.click()

        logger.info(f"clicked on respective port successfully")

        metrics = [
            "Valid Frames Transmitted",
            "Valid Frames Received",
            "Valid Bytes Transmitted",
            "Valid Bytes Received"
        ]

        for attempt in range(3):
            try:
                self.driver.switch_to.default_content()
                WebDriverWait(self.driver, 20).until(
                    EC.frame_to_be_available_and_switch_to_it((By.NAME, "nodeBodyFrame"))
                )
                table_xpath = f"//table[caption/b[contains(normalize-space(),'{port_number}')]]"
                table = wait.until(
                    EC.presence_of_element_located((By.XPATH, table_xpath))
                )
                values_list = []
                logger.info(f"Capturing packet flow status for port {port_number}")
                for metric in metrics:
                    row = table.find_element(By.XPATH, f".//tr[td/b[normalize-space()='{metric}']]")
                    columns = row.find_elements(By.TAG_NAME, "td")
                    values_list.extend([col.text.strip() for col in columns[1:5]])

                logger.info(f"packet_flow for {port_number}: {values_list}")

                flow = sum(int(x) for x in values_list)
                if flow != 0:
                    return "available"
                else:
                    return "unavailable"
            except StaleElementReferenceException:
                time.sleep(1)
                continue
        return "Unknown"

    def switch_to_frames(self, driver, *frames, timeout=60):
        driver.switch_to.default_content()
        for frame in frames:
            WebDriverWait(driver, timeout).until(
                EC.frame_to_be_available_and_switch_to_it((By.NAME, frame)))

    def open_shelf_port(self, port_number):
        wait = WebDriverWait(self.driver, 20)
        try:
            pattern = r'^(E1|VCG|ETH|STM1|STM4|STM16|STM64)-([1-9]|[1-5][0-9]|6[0-4])-([1-9]|[1-9][0-9]|1[0-9]{2}|200)-([1-9]|[1-9][0-9]|[1-9][0-9]{2}|500)$'
            match = re.match(pattern, port_number)
            if not match:
                raise Exception(f"Invalid port format: {port_number}")
            port = match.group(3)
            # port = port_number.split(" - ")[2]
            logger.info(f"regex result port number is: {port}")
            logger.info(f"clicking on slot(Shelf)")
            self.driver.switch_to.default_content()
            frame_element = WebDriverWait(self.driver, 30).until(
                EC.visibility_of_element_located((By.NAME, "nodeTocFrame")))
            self.driver.switch_to.frame(frame_element)
            inventory_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[normalize-space()='Inventory']")))
            inventory_btn.click()
            logger.info("clicked on inventory btn successfully")

            # click on Shelf btn
            shelf_btn = wait.until(
                EC.element_to_be_clickable((By.XPATH, "//a[starts-with(normalize-space(), 'SHELF-')]")))
            shelf_btn.click()
            logger.info("clicked on shelf btn successfully")

            # click on respective port
            port_ele = f"//a[contains(@href,'Slot={port}') and contains(@id,'itemTextLink')]"
            port_btn = wait.until(EC.element_to_be_clickable((By.XPATH, port_ele)))
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", port_btn)
            time.sleep(1)
            self.driver.execute_script("arguments[0].click();",port_btn)
            logger.info(f"clicked on port {port_btn.text} successfully")

            # click on Ports
            # Manage frames to enter "nodeBodyFrame --> ticTopFrame"
            self.driver.switch_to.default_content()
            self.switch_to_frames(self.driver, "nodeBodyFrame", "ticTopFrame")
            # Click Ports btn
            logger.info("clicking on ports")
            port_ele = f"//a[contains(@href,'CardPorts') and contains(@href,'Slot={port}')]"
            port_btn = wait.until(EC.element_to_be_clickable((By.XPATH, port_ele)))
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", port_btn)
            time.sleep(1)
            self.driver.execute_script("arguments[0].click();",port_btn)
            logger.info(f"clicked on ports successfully")

            # identify that "Ports" table loaded
            table = wait.until(EC.presence_of_element_located(
                (By.XPATH, "//table[caption/b[normalize-space()='Ports']]")))
            try:
                target_port = wait.until(EC.presence_of_element_located((By.XPATH, f"//table[caption/b[contains(text(),'Ports')]]//a[normalize-space()='{port_number}']")))
                self.driver.execute_script("arguments[0].scrollIntoView({behavior:'smooth', block:'center'});", target_port)
                time.sleep(2)
                logger.info(f"Scrolled to port:{port_number}")
                # self.take_screenshot(f"Port_{port}")
            except Exception as e:
                logger.warning(f"Port scrooling failed:{e}")
            if table:
                logger.info(f"port status table found successfully")
            else:
                logger.warning("port status table not found")

            return True
        except Exception as e:
            logger.error(f"Select port failed due to {e}")
            return False

    def convert_port(self, full_port, port_new):
        parts = full_port.split("-")
        if len(parts) == 4:
            parts[2] = port_new
            return "-".join(parts)
        else:
            raise ValueError("Port string format is invalid")
    def clear_manage_circuit_filters(self):
        try:
            node_field = self.driver.find_element(By.XPATH, "(//input[@class='dhx_combo_input'])[1]")
            node_field.send_keys(Keys.CONTROL + "a")
            node_field.send_keys(Keys.DELETE)
        except:
            pass
        try:
            timeslot_field = self.driver.find_element(By.XPATH, "//*[@id='timeslot']")
            timeslot_field.send_keys(Keys.CONTROL + "a")
            timeslot_field.send_keys(Keys.DELETE)
        except:
            pass
        try:
            self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        except:
            pass
        try:
            id_input = WebDriverWait(self.driver, 5).until(EC.visibility_of_element_located((By.ID, "cktid")))
            id_input.clear()
        except:
            pass
        try:
            circuit_label_input = WebDriverWait(self.driver, 5).until(EC.visibility_of_element_located((By.ID, "userLabel")))
            circuit_label_input.clear()
        except:
            pass
        logger.info("Manage circuits filters cleared")


    def nms_level_deletion(self, row, index, processed_db_ids, connection_id, tjs_id, service_name):
        time.sleep(5)
        try:
            WebDriverWait(self.driver, 10).until(EC.visibility_of_element_located((By.ID, "userLabel")))
        except:
            self.home_page()
            WebDriverWait(self.driver, 10).until(EC.visibility_of_element_located((By.ID, "userLabel")))
        circuit_id = str(row.get("connection_id", "")).strip().rstrip("_")
        selected_node = str(row.get("selected_node", "")).strip().upper()
        selected_port = str(row.get("selected_port", "")).strip().upper()
        logger.info(f"[NMS INPUT] {selected_node} {selected_port}")
        label = row.get("label")
        node, port, other_node, other_port = self.get_vcg_node_and_port(row)
        has_vcg_e1 = bool(node and port)
        if not tjs_id or tjs_id.lower() in ["", "none", "nan"]:
            if has_vcg_e1:
                logger.info("VCG/E1/STM found -> checking traffic before ADRS")
                if "STM" in str(port).upper():
                    logger.info("STM detected -> cross connection")
                    source_status = self.check_stm_traffic_status(node, port)
                    logger.info(f"First end status = {source_status}")
                    if source_status == "available":
                        logger.info("checking other end stm")
                        other_status = self.check_stm_traffic_status(other_node, other_port)
                        logger.info(f"Second end status = {other_status}")
                        if other_status == "available":
                            flow_status = "available"
                        else:
                            flow_status = "unavailable"
                    else:
                        flow_status = "unavailable"
                else:
                    logger.info("E1/VCG detected -> current interval")
                    flow_status = self.check_traffic_flow(node, port, other_node, other_port)
                    logger.info(f"flow status: {flow_status}")
                if flow_status == "failed":
                    logger.error("Traffic check failed")
                    return
                if flow_status != "unavailable":
                    logger.info("Live traffic present")
                logger.info("Non-live VCG/E1 -> continue ADRS flow")
            logger.info(f"[SKIP NMS] tjs_id NULL -> Direct ADRS")
            return{"status":"ADRS","service_name":service_name,"zone":row.get("zone"),"connection_id":circuit_id, "a_end":row.get("a_end"), "a_end_port":row.get("a_end_port"),
                    "b_end":row.get("b_end"), "b_end_port":row.get("b_end_port"), "selected_node":row.get("selected_node"), "selected_port":row.get("selected_port") }

        self.current_connection_id = circuit_id
        a_node = str(row.get("a_end", "")).strip().upper()
        b_node = str(row.get("b_end", "")).strip().upper()
        is_unknown_node = "UNKNOWN" in [a_node, b_node]
        if is_unknown_node:
            logger.info(f"UNKNOWN node detected(A={a_node}, B={b_node}) - direct deletion")
            WebDriverWait(self.driver, 5).until(EC.visibility_of_element_located((By.ID, "userLabel")))
        else:
            node, port, other_node, other_port = self.get_vcg_node_and_port(row)
            is_duplicate_vcg = False
            if node and port and "STM" not in str(port).upper():
                vcg = port.strip().upper()
                if vcg in self.processed_vcgs:
                    logger.info(f"skipping duplicates VCG {vcg}, but performing deletion operation in manage circuits")
                    is_duplicate_vcg = True
                else:
                    self.processed_vcgs.add(vcg)
            if node and port and not is_duplicate_vcg:
                logger.info(f"VCG/E1/STM found -> Node: {node}, Port: {port}")
                time.sleep(1)
                if "STM" in str(port).upper():
                    logger.info("STM detected -> cross connection")
                    source_status = self.check_stm_traffic_status(node, port)
                    logger.info(f"First end status = {source_status}")
                    if source_status == "available":
                        logger.info("checking other end stm")
                        other_status = self.check_stm_traffic_status(other_node, other_port)
                        logger.info(f"Second end status = {other_status}")
                        if other_status == "available":
                            flow_status = "available"
                        else:
                            flow_status = "unavailable"
                    else:
                        flow_status = "unavailable"
                else:
                    logger.info("VCG/E1 detected -> CURRENT INTERVAL")
                    flow_status = self.check_traffic_flow(node,port,other_node,other_port)
                logger.info(f"FLOW STATUS = {flow_status}")
                if flow_status == "failed":
                    logger.error("Traffic check failed")
                    return
                if flow_status != "unavailable":
                    logger.info("LIVE TRAFFIC PRESENT")
                    self.db_query.update_deletion_status(
                        connection_id=circuit_id,
                        status=False,
                        remarks="Circuit is Active - deletion skipped"
                    )
                    processed_db_ids.append(row.get("id"))
                    return
            else:
                logger.info("No VCG -> normal deletion")

        SPECIAL_CIRCUITS = ["TEJAS"]
        is_tejas = False

        if circuit_id and any(circuit_id.strip().upper().startswith(x) for x in SPECIAL_CIRCUITS):
            time.sleep(1)
            id_input =  WebDriverWait(self.driver, 5).until(
                EC.visibility_of_element_located((By.XPATH, "//input[@name='cktId']")))
            id_input.clear()
            time.sleep(1)
            self.search_tejas_network(row)
            is_tejas = True

        logger.info(f"Circuit {circuit_id}")

        try:
            if not is_tejas:
                self.clear_manage_circuit_filters()
                time.sleep(1)
                id_input =  WebDriverWait(self.driver, 5).until(EC.visibility_of_element_located((By.XPATH, "//input[@name='cktId']")))
                id_input.click()
                time.sleep(1)
                id_input.clear()
                if tjs_id and tjs_id.lower() not in ["none", "nan"]:
                    id_input.send_keys(tjs_id)
                logger.info(f"Entered tjs_id in ID field: {tjs_id}")

                WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable(
                        (By.XPATH, "(//img[@title='Search' and contains(@src,'search_image')])[1]"))).click()

            WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.XPATH, "//div[contains(@class,'objbox')]//tr"))
            )
            if is_unknown_node:
                self.take_screenshot(f"Unknown circuit-{label}")

            try:
                time.sleep(1)
                ok_btn = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.XPATH, '//*[@id="dialog_butt_ok"]'))
                )
                ok_btn.click()
                time.sleep(1)
                self.db_query.update_deletion_status(
                    connection_id=str(circuit_id).strip(),
                    status=False,
                    remarks="Circuit not found in Tejas Manage Circuits"
                )
                processed_db_ids.append(row.get("id"))
                return

            except TimeoutException:
                logger.info(f"Clicked Search for circuit_id: {circuit_id}")

                rows = WebDriverWait(self.driver, 5).until(EC.presence_of_all_elements_located((By.XPATH, "//div[contains(@class,'objbox')]//tr")))

                logger.info(f"Found {len(rows)} rows for circuit {circuit_id}")
                allowed_states = ["PENDING", "PARTIAL", "ORPHAN", "CONFLICT"]
                delete_flag = True
                valid_rows = []
                for r in rows:
                    cells = r.find_elements(By.TAG_NAME, "td")
                    if len(cells) < 7:
                        continue

                    label = cells[2].text.strip()
                    state = cells[6].text.strip().upper()

                    logger.info(f"Row label: {label}, State: {state}")
                    if state in ["PENDING", "PARTIAL", "ORPHAN", "CONFLICT"]:
                        logger.info(f"Special state detected:{state}")
                        self.take_screenshot(f"Direct state-{label}")

                    if state not in allowed_states:
                        if not has_vcg_e1:
                            logger.info("Skipping state validation for ADRS flow")
                            continue
                        delete_flag = False
                        logger.info(f"State {state} not eligible for deletion")
                        continue

                    valid_rows.append(r)

                if not delete_flag:
                    if has_vcg_e1:
                        self.db_query.update_deletion_status(
                            connection_id=circuit_id,
                            status=False,
                            remarks="State not eligible"
                        )
                        processed_db_ids.append(row.get("id"))
                        return
                    else:
                        logger.info("ADRS flow detected. Skipping state validation.")

                if delete_flag and valid_rows:
                    logger.info("All circuits eligible. Selecting rows")

                    for r in valid_rows[1:]:
                        select_cell = r.find_elements(By.TAG_NAME, "td")[1]

                        self.driver.execute_script("""
                            var evt = new MouseEvent('click', {
                                bubbles: true,
                                ctrlKey: true
                            });
                            arguments[0].dispatchEvent(evt);
                        """, select_cell)
                    time.sleep(1)
                    first_cell = valid_rows[0].find_elements(By.TAG_NAME, "td")[1]
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});",
                        first_cell
                    )
                    time.sleep(1)
                    ActionChains(self.driver).context_click(first_cell).perform()
                    delete_btn = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable(
                            (By.XPATH, "//div[normalize-space()='Delete']")
                        )
                    )
                    delete_btn.click()

                    delete_deactivate_btn = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable(
                            (By.XPATH, "(//div[normalize-space()='Delete And Deactivate'])[1]")
                        )
                    )

                    self.driver.execute_script("arguments[0].click();", delete_deactivate_btn)
                    time.sleep(2)
                    WebDriverWait(self.driver, 10).until(EC.alert_is_present())
                    alert = self.driver.switch_to.alert
                    print(alert.text)
                    alert.dismiss()
                    # alert.accept()
                    # close_btn = WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//input[@id='ajaxResponseWindow_close_']")))
                    # close_btn.click()
                    time.sleep(1)
                    logger.info(f"Deletion triggered for circuit {circuit_id}")
                    self.db_query.update_deletion_status(
                        connection_id=circuit_id.strip(),
                        status=True,
                        remarks="Deleted NMS Level"
                    )
                    processed_db_ids.append(row.get("id"))
                    return "DONE"
                else:
                    logger.info(f"Circuit {circuit_id} skipped due to state mismatch")
                    return "DONE"

        except Exception as e:
            logger.warning(f"Failed for circuit_id {circuit_id}: {e}")
            self.db_query.update_deletion_status(
                connection_id=circuit_id.strip(),
                status=False,
                remarks=str(e)
            )
            processed_db_ids.append(row.get("id"))
            return "DONE"
        
    def take_screenshot(self, title="Screenshot"):
        try:
            screenshot_bytes = self.driver.get_screenshot_as_png()
            img_stream = io.BytesIO(screenshot_bytes)
            img = Image(img_stream)
            img.drawWidth = 500
            img.drawHeight = img.drawWidth * img.imageHeight / img.imageWidth
            content = [
                Paragraph(title, self.styles["Heading3"]),
                Spacer(1, 10),
                img,
                Spacer(1, 20)
            ]
            self.elements.extend(content)
            logger.info("Screenshot added to PDF")
        except Exception as e:
            logger.warning(f"Screenshot failed: {e}")
        
    def finalize_pdf(self):
        try:
            if not self.elements:
                return
            doc = SimpleDocTemplate(self.current_pdf, pagesize=A4)
            doc.build(self.elements)
            logger.info(f"PDF saved: {self.current_pdf}")
        except Exception as e:
            logger.exception(f"PDF build failed: {e}")

    def ne_level_deletion(self, node, card=None, port=None, stm=None, jklm=None, 
                          circuit_type="OPTICAL", mode="delete", connection_id="None", 
                          full_port=None, is_priority=False):

        wait = WebDriverWait(self.driver, 10)
        time.sleep(8)
        node_input = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[@class='dhx_combo_input']")))
        node_input.click()
        time.sleep(0.2)
        # character_typing(node_input, node)
        # node_input.send_keys(Keys.ENTER)
        # node_input.click()
        # time.sleep(0.2)
        node_input.send_keys(Keys.CONTROL + "a")
        node_input.send_keys(Keys.BACKSPACE)
        time.sleep(0.2)
        node_input.send_keys(node)
        time.sleep(0.3)
        node_input.send_keys(Keys.ENTER)
        logger.info(f"Node entered: {node}")
        time.sleep(1)
        search_node = WebDriverWait(self.driver, 5).until(EC.element_to_be_clickable(
            (By.XPATH, "(//img[@title='Search Nodes'])[1]")))
        search_node.click()
        time.sleep(1)
        try:
            WebDriverWait(self.driver, 5).until(EC.visibility_of_element_located((By.ID, "dialog_butt_ok")))
            self.driver.find_element(By.ID, "dialog_butt_ok").click()
            logger.info("Popup handled -> No results")
            return "not found"
        except:
            logger.info("No popup appeared")
        parent_window = self.driver.current_window_handle
        ip_element = wait.until(EC.element_to_be_clickable(
        (By.XPATH, "//*[@id='gridbox']/table/tbody/tr[2]/td/div/div/table/tbody/tr[2]/td[1]/a")))
        node_ip = ip_element.text.strip()
        self.global_node_ip = node_ip
        logger.info(f"Global Node IP: {node_ip}")
        ip_element.click()
        wait.until(lambda d: len(d.window_handles) > 1)
        self.driver.switch_to.window(self.driver.window_handles[-1])
        try:
            WebDriverWait(self.driver, 10).until(EC.alert_is_present())
            alert = self.driver.switch_to.alert
            alert.accept()
            logger.info("Alert accepted")
        except:
            logger.info("No alert present")
        time.sleep(0.2)
        # try:
        #     time.sleep(5)
        #     # WebDriverWait(self.driver, 20).until(EC.visibility_of_element_located((By.NAME, "Username")))
        #     WebDriverWait(self.driver, 20).until(lambda d:
        #                                          d.find_elements(By.NAME, "Username") or 
        #                                          d.find_elements(By.ID, "Uptime"))
        #     if self.driver.find_elements(By.NAME, "Username"):
        #         logger.info("Login page loaded normally")
        #     elif self.driver.find_elements(By.ID, "Uptime"):
        #         logger.inf("Node page already loaded (uptime detecetd)")
        # except:
        #     logger.warning("Username not found -> using open node ne fallback")
        #     status = self.open_node_ne(self.global_node_ip, parent_window, node)
        #     if status == "failed":
        #         logger.error(f"Skipping node:{node}")
        #         return "failed"
        
        self.handle_unexpected_alert()
        ensure_write_mode(self.driver, self.diag_username, self.diag_passwords)
        logger.info("Login handeled via ensure_write_mode")
        logger.info(f"MODE VALUE: {mode}")
        if mode == "flow_check":
            self.driver.switch_to.window(self.driver.window_handles[-1])
            self.driver.switch_to.default_content()
            return "success"
        self.driver.switch_to.window(self.driver.window_handles[-1])
        self.driver.switch_to.default_content()
        time.sleep(1)
        self.tejas_node_manager()
        result = self.apply_cross_connect_filter(node,
            card,
            port,
            stm if circuit_type == "OPTICAL" else None,
            jklm if circuit_type == "OPTICAL" else None,
            connection_id,
            full_port,
            is_priority=is_priority,
            mode=mode
        )
        if result == "LIVE":
            self.driver.close()
            return "LIVE"
        self.driver.close()
        self.driver.switch_to.window(parent_window)
        self.driver.switch_to.default_content()
        WebDriverWait(self.driver, 5).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(1)
        return "success"
    
    def open_node_ne(self, node_ip, parent_window, node):

        def is_error_page():
            try:
                page = self.driver.page_source.lower()
                return "no route to host" in page or "requested url could not be retrieved" in page
            except:
                return True

        def safe_close_tab():
            try:
                handles = self.driver.window_handles
                if len(handles) > 1:
                    self.driver.switch_to.window(handles[-1])

                    try:
                        self.driver.execute_script("window.stop();")
                    except:
                        pass

                    self.driver.close()
                    self.driver.switch_to.window(parent_window)
            except:
                pass

        try:
            logger.info("Opening node via click")

            WebDriverWait(self.driver, 5).until(lambda d: len(d.window_handles) > 1)
            self.driver.switch_to.window(self.driver.window_handles[-1])

            time.sleep(15)

            if is_error_page():
                raise Exception("Error page after click")

            try:
                ensure_write_mode()
            except:
                pass

            frame_element = WebDriverWait(self.driver, 10).until(
                EC.visibility_of_element_located((By.NAME, "commonHeader"))
            )
            self.driver.switch_to.frame(frame_element)

            WebDriverWait(self.driver, 5).until(
                EC.visibility_of_element_located((By.XPATH, "//b[contains(text(),'Uptime')]"))
            )

            self.driver.switch_to.default_content()

            logger.info("Node opened successfully via click")
            return "success"

        except Exception:
            try:
                logger.info("Click failed → trying URL")

                safe_close_tab()

                self.driver.execute_script("window.open('');")
                self.driver.switch_to.window(self.driver.window_handles[-1])
                self.driver.set_page_load_timeout(15)

                try:
                    self.driver.get(f"http://{node_ip}:20080")
                except:
                    try:
                        self.driver.execute_script("window.stop();")
                    except:
                        pass

                time.sleep(15)

                if is_error_page():
                    raise Exception("Error page after URL")

                try:
                    ensure_write_mode()
                except:
                    pass

                frame_element = WebDriverWait(self.driver, 10).until(
                    EC.visibility_of_element_located((By.NAME, "commonHeader"))
                )
                self.driver.switch_to.frame(frame_element)

                WebDriverWait(self.driver, 5).until(
                    EC.visibility_of_element_located((By.XPATH, "//b[contains(text(),'Uptime')]"))
                )

                self.driver.switch_to.default_content()

                logger.info("Node opened successfully via URL")
                return "success"

            except Exception:
                logger.error(f"Node {node} failed to open completely")

                safe_close_tab()
                return "failed"

    def handle_unexpected_alert(self):
        try:
            WebDriverWait(self.driver, 3).until(EC.alert_is_present())
            alert = self.driver.switch_to.alert
            text = alert.text
            logger.warning(f"Unexpected alert detected: {text}")
            alert.accept()
            time.sleep(1)
            return True
        except:
            return False

    def check_traffic_flow(self, node, port, other_node, other_port, is_opposite=False):
        main_tab = self.driver.current_window_handle
        self.open_manage_nodes()
        time.sleep(2)
        WebDriverWait(self.driver, 5).until(EC.presence_of_element_located((By.XPATH, "//input[@class='dhx_combo_input']")))
        manage_nodes_tab = self.driver.current_window_handle
        open_status = self.ne_level_deletion(node=node, mode="flow_check")
        if open_status == "failed":
            logger.error(f"node failed")
            return "failed"
        
        WebDriverWait(self.driver, 10).until(lambda d: len(d.window_handles) > 1)
        node_tab = self.driver.window_handles[-1]
        self.driver.switch_to.window(node_tab)
        try:
            if "E1" in port:
                logger.info(f"E1 detected for port: {port}")
                self.open_shelf_port(port)
                time.sleep(2)
                self.take_screenshot(f"E1 - {node} - {port}")
                status = self.admin_oper_alarm(port)
                oper = str(status.get("operational", "")).lower()
                cir = str(status.get("cir_status", "")).lower()
                logger.info(f"DEBUG -> cir_status: {cir}, operational:{oper}")
                if "non" in cir:
                    return "unavailable"
                elif "live" in cir:
                    logger.info(f"{port} is LIVE")
                    if is_opposite:
                        return "available"
                    opposite_status = self.check_opposite_side(other_node, other_port)
                    return opposite_status
                elif "down" in oper:
                    return "unavailable"
                else:
                    return "available"
            # ---------------- VCG FLOW ----------------
            vcg_flow = self.collect_packet_flow(port)
            self.take_screenshot(f"VCG_PACKET_FLOW - {node} - {port}")
            logger.info(f"VCG Flow: {vcg_flow}")
            self.open_shelf_port(port)
            time.sleep(2)
            self.take_screenshot(f"VCG - {node} - {port}")
            self.switch_to_frames(self.driver, "nodeTocFrame")
            l2_elements = self.driver.find_elements(By.XPATH, "//a[contains(text(), 'L2 Services')]")
            # l2_elements = WebDriverWait(self.driver, 20).until(
            #     EC.presence_of_all_elements_located((By.XPATH, "//a[contains(text(), 'L2 Services')]")))
            if l2_elements:
                eth_status = self.l2_eth_card(port, node, vcg_flow)
            else:
                eth_status = self.l1_eth_card(port, vcg_flow)
            logger.info(f"ETH status: {eth_status}")
            packet_flow = eth_status.get("packet_flow")
            cir_status = eth_status.get("cir_status")
            logger.info(
                f"VCG: {vcg_flow}, ETH: {packet_flow}, STATUS: {cir_status}"
            )
            if (
                    vcg_flow in ["unavailable", "NA"] and
                    packet_flow in ["unavailable", "NA"] and
                    cir_status == "non-live"
            ):
                logger.info("SAFE TO DELETE")
                return "unavailable"
            else:
                logger.info(f"{port} is LIVE")
                if is_opposite:
                    return "available"
                opposite_status = self.check_opposite_side(other_node, other_port)
                return opposite_status

            # logger.info("TEST MODE: Forcing deletion")
            # return "unavailable"

        finally:
            self.driver.close()
            self.driver.switch_to.window(manage_nodes_tab)
            self.driver.close()
            self.driver.switch_to.window(main_tab)
    
    # def check_opposite_side(self,node,port):
    #     logger.info(f"Checking opposite side: {node} | {port}")
    #     port_upper = str(port).upper()
    #     if "STM" in port_upper:
    #         return self.check_stm_traffic_status(node,port)
    #     elif "E1" in port_upper:
    #         cir = self.l1_e1_card(node,port)
    #         if "non" in str(cir).lower():
    #             return "unavailable"
    #         return "available"
    #     elif ("VCG" in port_upper or "ETH" in port_upper):
    #         cir = self.l1_eth_card(node,port)
    #         if "non" in str(cir).lower():
    #             return "unavailable"
    #         return "available"
    #     return "available"
    def check_opposite_side(self, node, port):
        logger.info(f"checking opposite side: {node}")
        port_upper = str(port).upper()
        if "STM" in port_upper:
            return self.check_stm_traffic_status(node, port)
        else:
            return self.check_traffic_status_flow(node, port, None, None)
    
    def check_stm_traffic_status(self,node,port):
        logger.info(f"Checking STM traffic: {node} | {port}")
        try:
            parts = port.split("-")
            card = "-".join(parts[1:3])
            port_no = parts[3]
            stm = parts[4]
            jklm = "-".join(parts[4:])
            logger.info(
                f"CARD={card}, "
                f"PORT={port_no}, "
                f"STM={stm}, "
                f"JKLM={jklm}"
            )

            main_tab = self.driver.current_window_handle
            self.open_manage_nodes()
            manage_nodes_tab = self.driver.current_window_handle
            open_status = self.ne_level_deletion(
                node=node,
                mode="flow_check"
            )
            if open_status == "failed":
                return "failed"
            WebDriverWait(self.driver, 10).until(
                lambda d: len(d.window_handles) > 1
            )
            node_tab = self.driver.window_handles[-1]
            self.driver.switch_to.window(node_tab)
            self.driver.switch_to.default_content()
            self.tejas_node_manager()
            result = self.apply_cross_connect_filter(
                node=node,
                card=card,
                port=port_no,
                stm=stm,
                jklm=jklm,
                connection_id=None,
                full_port=port,
                mode="traffic_check"
            )
            self.driver.close()
            self.driver.switch_to.window(manage_nodes_tab)
            self.driver.close()
            self.driver.switch_to.window(main_tab)
            return result
        except Exception as e:
            logger.error(f"STM traffic check failed:\n" f"{traceback.format_exc()}")
            return "failed"

    def get_vcg_node_and_port(self, row):

        a_node = str(row.get("a_end", "")).strip().upper()
        b_node = str(row.get("b_end", "")).strip().upper()

        a_port = str(row.get("a_end_port", "")).strip().upper()
        b_port = str(row.get("b_end_port", "")).strip().upper()

        logger.info(f"A-END = {a_node} | {a_port}")
        logger.info(f"B-END = {b_node} | {b_port}")

        # PRIORITY 1 -> E1

        if "E1" in a_port:
            logger.info("E1 found in A-END")
            return a_node, a_port, b_node, b_port

        if "E1" in b_port:
            logger.info("E1 found in B-END")
            return b_node, b_port, a_node, a_port

        # PRIORITY 2 -> VCG

        if "VCG" in a_port:
            logger.info("VCG found in A-END")
            return a_node, a_port, b_node, b_port

        if "VCG" in b_port:
            logger.info("VCG found in B-END")
            return b_node, b_port, a_node, a_port

        # PRIORITY 3 -> STM

        if "STM" in a_port:
            logger.info("STM found in A-END")
            return a_node, a_port, b_node, b_port

        if "STM" in b_port:
            logger.info("STM found in B-END")
            return b_node, b_port, a_node, a_port

        logger.info("No E1/VCG/STM found")

        return None, None, None, None

    def search_tejas_network(self, row):
        circuit_id = str(row.get("connection_id", "")).strip()
        a_node = str(row.get("a_end", "")).strip()
        b_node = str(row.get("b_end", "")).strip()
        a_port_value = str(row.get("a_end_port", "")).strip()
        b_port_value = str(row.get("b_end_port", "")).strip()
        if "E1" in a_port_value or "VCG" in a_port_value:
            node = a_node
            port_value = a_port_value
        elif "E1" in b_port_value or "VCG" in b_port_value:
            node = b_node
            port_value = b_port_value
        else:
            if a_port_value:
                node = a_node
                port_value = a_port_value
            else:
                node = a_node
                port_value = a_port_value
        parts = port_value.split("-")

        port = "-".join(parts[:4])
        if port_value.startswith("STM") and len(parts) > 4:
            timeslot = "-".join(parts[4:])
        else:
            timeslot = None

        logger.info(f"Tejas search -> Node:{node}, Port:{port}, TimeSlot:{timeslot}")
        time.sleep(3)
        wait = WebDriverWait(self.driver, 5)
        node_input = wait.until(
            EC.element_to_be_clickable((By.XPATH, "(//input[@class='dhx_combo_input'])[1]"))
        )
        node_input.send_keys(node)
        time.sleep(2)
        node_input.send_keys(Keys.ENTER)
        time.sleep(2)

        port_input = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[@id='tpBrowser']")))
        port_input.click()
        time.sleep(1)

        search_box = WebDriverWait(self.driver, 5).until(
            EC.visibility_of_element_located((By.XPATH, "//div[contains(text(),'TejNms')]/following::input[1]"))
        )
        search_box.send_keys(port)
        time.sleep(0.5)
        search_box.send_keys(Keys.ENTER)
        time.sleep(1)
        port = port.strip()
        stm_element = WebDriverWait(self.driver, 20).until(
            EC.element_to_be_clickable((By.XPATH, f"//div[@class='objbox']//span[text()='{port}']")))
        self.driver.execute_script("arguments[0].click();", stm_element)

        ok_btn = WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//*[@id='win_ok']")))
        ok_btn.click()
        time.sleep(2)
        if timeslot:
            timeslot_input = WebDriverWait(self.driver, 10).until(
                EC.visibility_of_element_located((By.XPATH, "//*[@id='timeslot']")))
            timeslot_input.send_keys(timeslot)
            time.sleep(0.5)
            timeslot_input.send_keys(Keys.ENTER)
        else:
            logger.info(f"Skipping timeslot input(E1/VCG")
        time.sleep(1)
        search_button = WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "(//img[@title='Search'])[1]")))
        search_button.click()
        time.sleep(2)

    def open_manage_nodes(self):
        self.driver.switch_to.default_content()
        wait = WebDriverWait(self.driver, 10)
        act = ActionChains(self.driver)
        topology = wait.until(EC.visibility_of_element_located((By.XPATH, "(//span[contains(text(), 'Topology')])[1]")))
        act.move_to_element(topology).perform()
        manage_nodes = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Manage Nodes')]")))
        act.key_down(Keys.CONTROL).click(manage_nodes).key_up(Keys.CONTROL).perform()
        self.driver.switch_to.window(self.driver.window_handles[-1])
        # time.sleep(2)

    def tejas_node_manager(self):
        print("*********************************")
        # time.sleep(1)
        self.driver.switch_to.default_content()
        try:
            WebDriverWait(self.driver, 10).until(EC.frame_to_be_available_and_switch_to_it((By.NAME,"commonhandler")))
        except:
            self.driver.switch_to.default_content()
        WebDriverWait(self.driver, 10).until(
            EC.frame_to_be_available_and_switch_to_it((By.NAME, "nodeTocFrame")))
        click(self.driver, (By.XPATH, "//a[contains(text(),'Configuration')]"))
        click(self.driver, (By.XPATH, "//a[contains(text(),'Cross-connect')]"))
        # time.sleep(1)

    def node_body_frame(self):
        WebDriverWait(self.driver, 10).until(lambda d: len(d.window_handles) > 1)
        self.driver.switch_to.window(self.driver.window_handles[-1])
        self.driver.switch_to.default_content()
        WebDriverWait(self.driver, 10).until(EC.frame_to_be_available_and_switch_to_it((By.NAME, "nodeBodyFrame")))

    def apply_cross_connect_filter(self, node, card, port, stm, jklm, connection_id, full_port, is_priority=False, mode="delete"):
        time.sleep(3)
        wait = WebDriverWait(self.driver, 10)
        self.node_body_frame()
        card = str(card).strip()
        if not card or card.lower == "none":
            logger.info("skipping card selection")
            return
        table = wait.until(EC.visibility_of_element_located(
            (By.XPATH, "//caption[contains(.,'Filter Cross-connects')]/ancestor::table")))
        card_dropdown = table.find_element(By.XPATH, ".//select[contains(@name,'Card')]")
        select = Select(card_dropdown)
        found = False
        for option in select.options:
            option_text = option.text.strip()
            if option_text.replace(" ", "").endswith(card):
                select.select_by_visible_text(option_text)
                found = True
                logger.info(f"selected card: {option.text}")
                break
        if not found:
            raise Exception(f"card not found: {card}")
        # ------------------PORT---------------------
        time.sleep(0.2)
        port = str(int(float(port))).strip()
        # logger.info(f"CSV port value: {repr(port)}")
        port_dropdown = table.find_element(By.XPATH, ".//select[contains(@name,'PN')]")
        select_port = Select(port_dropdown)
        wait.until(lambda d: len(select_port.options) > 1)
        found = False
        for option in select_port.options:
            option_text = option.text.strip()
            if option_text == port or port in option_text:
                select_port.select_by_visible_text(option_text)
                found = True
                logger.info(f"selected port: {option.text}")
                break
        if not found:
            raise Exception(f"port not found: {port}")
        time.sleep(0.2)

        # -------- STMNo, K, L, M SELECTION (XPATH VERSION) --------
        if not jklm or str(jklm).lower() in ["none", "nan", "<null>"]:
            logger.info("VCG / No JKLM -> Skipping STM, K, L, M selection")

        else:
            # -------- SPLIT JKLM --------
            j, k, l, m = str(jklm).strip().split("-")

            logger.info(f"J value (for STMNo): {j}")
            logger.info(f"K value: {k}")
            logger.info(f"L value: {l}")
            logger.info(f"M value: {m}")

            # -------- STMNo (J) --------
            stmno_dropdown = table.find_element(By.XPATH, ".//select[contains(@name,'STM')]")
            select_stmno = Select(stmno_dropdown)

            wait.until(lambda d: len(select_stmno.options) > 1)

            found = False
            for option in select_stmno.options:
                option_text = option.text.strip()

                if option_text == j:
                    select_stmno.select_by_visible_text(option_text)
                    found = True
                    break

            if not found:
                raise Exception(f"STMNo not found: {j}")

            time.sleep(0.2)

            # -------- K --------
            k_dropdown = table.find_element(By.XPATH, ".//select[contains(@name,'SearchK')]")
            select_k = Select(k_dropdown)

            wait.until(lambda d: len(select_k.options) > 1)
            select_k.select_by_visible_text(k)
            time.sleep(0.2)

            # -------- L --------
            l_dropdown = table.find_element(By.XPATH, ".//select[contains(@name,'SearchL')]")
            select_l = Select(l_dropdown)

            wait.until(lambda d: len(select_l.options) > 1)
            select_l.select_by_visible_text(l)
            time.sleep(0.2)

            # -------- M --------
            m_dropdown = table.find_element(By.XPATH, ".//select[contains(@name,'SearchM')]")
            select_m = Select(m_dropdown)

            wait.until(lambda d: len(select_m.options) > 1)
            select_m.select_by_visible_text(m)
            time.sleep(0.2)

        # ----------- FILTER BUTTON (COMMON FOR BOTH) -----------
        filter_button = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//input[@type='button' and @value='Filter']"))
        )

        self.driver.execute_script("arguments[0].click();", filter_button)
        logger.info("Filter button clicked")
        # ==========================================
        # STM TRAFFIC CHECK
        # ==========================================
        if mode == "traffic_check":
            rows = wait.until(EC.presence_of_all_elements_located((By.XPATH,"//table[@width='95%' and @border='1']//tr[position()>1]")))
            for row in rows:
                cols = row.find_elements(By.TAG_NAME, "td")
                self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});",row)
                time.sleep(1)
                self.take_screenshot(f"STM_STATUS_{node}_{port}")
                if len(cols) < 9:
                    continue
                source_status = cols[3].text.strip().upper()
                dest_status = cols[8].text.strip().upper()
                if (source_status == "UP" and dest_status == "UP"):
                    logger.info("STM LIVE")
                    return "available"
            logger.info("STM NON-LIVE")
            return "unavailable"
        time.sleep(1)
        # -----------------select checkbox-----------------
        try:
            checkbox = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "(//table//input[@type='CHECKBOX'])[1]")))
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", checkbox)
            time.sleep(1)
            self.driver.execute_script("arguments[0].click();", checkbox)
            logger.info("Checkbox clicked")
            self.take_screenshot(f"NE Level Deletion - {node} - {full_port}")
            time.sleep(1)
            if is_priority:
                logger.info(f"LIVE circuit found in AIS injected node {node}")
                self.take_screenshot(f"LIVE CIRCUIT - {node} - {full_port}")
                return "LIVE"
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", checkbox)
            # ------------------Click delete selected connections-----------
            delete_button = wait.until(EC.element_to_be_clickable(
                (By.XPATH, "//input[@type='SUBMIT' and @value='Delete selected connection(s)']")))
            delete_button.click()
            logger.info("Delete selected connection clicked")
            time.sleep(1)
            yes_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//input[@type='BUTTON' and @value='No']")))
            yes_button.click()
            # yes_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//input[@type='SUBMIT' and @value='Yes']")))
            # yes_button.click()
            # self.db_query.update_deletion_status(connection_id=connection_id, status=True, remarks="Tejas side nodes deleted, pending with other NMS")
        except TimeoutException:
            logger.warning("No circuits found for this node. Proceeding to next node.")
            return

    def process_csv_nodes(self, processed_rows, connection_id, processed_db_ids):
        time.sleep(5)
        overall_status = False
        main_tab = self.driver.current_window_handle
        self.open_manage_nodes()
        WebDriverWait(self.driver, 5).until(EC.presence_of_element_located((By.XPATH, "//input[@class='dhx_combo_input']")))
        manage_nodes_tab = self.driver.current_window_handle
        processed_keys = set()
        processed_rows = sorted(processed_rows, key=lambda x : x.get("priority", False), reverse=True)
        for row in processed_rows:
            key = f"{row['node']}_{row['card']}_{row['port']}_{row['jklm']}"
            if key in processed_keys:
                logger.info(f"skipping duplicates execution:{key}")
                continue
            processed_keys.add(key)
            node = row["node"]
            card = row["card"]
            port = row["port"]
            jklm = row["jklm"]
            full_port = row["full_port"]
            logical_resource = row["logical_resource"]
            port_upper = str(full_port).upper()
            node_data = self.db_query.get_device_manufacturer(node)

            if not node_data:
                logger.info(f"[FILTER] {node} -> UNKNOWN")
                continue
            manufacturer = node_data["manufacturer"]
            zone = node_data["zone"]
            if manufacturer.upper() != "TEJAS":
                logger.info(f"[FILTER] {node} -> {node_data} (no login)")
                continue
            self.login_manager.current_zone = zone
            logger.info(f"[FILTER] {node} -> TEJAS (processing) | {zone}")
            status = None
            remarks = None
            is_priority = row.get("priority", False)
            try:
                time.sleep(2)
                if jklm:
                    result = self.ne_level_deletion(node=node,card=card,port=port,stm=str(jklm).split("-")[0],jklm=jklm,
                                                    full_port=full_port,circuit_type="OPTICAL",is_priority=is_priority
                    )
                else:
                    time.sleep(2)
                    result = self.ne_level_deletion(node=node,card=card,port=port,stm=None,jklm=None,full_port=full_port,
                        circuit_type="ETH",is_priority=is_priority
                    )
                logger.info(f"[NE RESULT] {result}")
                if result == "LIVE":
                    overall_status = False
                    break
                elif result == "success":
                    overall_status = True
                else:
                    overall_status = False
           
            except Exception as e:
                logger.info(f"Error in deletion for {node}:{e}")
                overall_status = False
               
            finally:
                try:
                   self.driver.switch_to.window(manage_nodes_tab)
                   self.driver.switch_to.default_content()
                except Exception as e:
                    logger.warning(f"Tab switch failed:{e}")
        try:
            self.driver.switch_to.window(manage_nodes_tab)
            self.driver.close()
            self.driver.switch_to.window(main_tab)
        except Exception as e:
            logger.warning(f"Final tab cleanup failed:{e}")
        # final_remark = " | ".join(remarks_list) if remarks_list else "Tejas nodes deleted successfully"
        if overall_status:
            final_remark = "Deleted Successfully"
        else:
            final_remark = "Live circuit found"
        self.db_query.update_deletion_status(connection_id=str(connection_id.strip()),
                                                               status=overall_status,
                                                               remarks=final_remark)
        processed_db_ids.append(row.get("id"))
        return

    def l2_eth_card(self, port_number, node, vcg_flow):
        # eth_status  = {"cir_status":"live/non-live","alarm_info":[],"packet_flow": "available/unavailable"}
        eth_status = {}
        eth_status_9 = {}
        # collect VCG status and packet flow for port 5
        # Manage frames to enter "ticTopFrame"
        self.switch_to_frames(self.driver, "nodeBodyFrame", "ticTopFrame")
        status_5 = self.admin_oper_alarm(port_number)
        # logger.info(f"L2 ETH| port {port_number} status: {status_5}")
        eth_status["cir_status"] = status_5["cir_status"]
        eth_status["alarm_info"] = status_5["alarm_info"]
        # capture the packet flow status
        # packet_flow = self.collect_packet_flow(port_number)
        eth_status["packet_flow"] = vcg_flow
        logger.info(f"L2 ETH|packet flow of port 5: {vcg_flow}")
        if status_5["cir_status"] != "live":  # "Inactive":
            # collect VCG status and packet flow for port 9
            # click on port 9
            l2_port = self.convert_port(port_number, "9")  # L2 port conversion
            logger.info(f"L2_ETH: checking status for {l2_port}")
            self.open_shelf_port(l2_port)
            current_node = node
            self.take_screenshot(f"VCG - {current_node} - {port_number}")
            logger.info(f"L2_ETH: Clicked on port 9 successfully")
            status_9 = self.admin_oper_alarm(l2_port)
            logger.info(f"L2 ETH| port {port_number} status: {status_9}")
            eth_status_9["cir_status"] = status_9["cir_status"]
            eth_status_9["alarm_info"] = status_9["alarm_info"]
            logger.info(f"L2_ETH: collected status for {l2_port} successfully")
            packet_flow = self.collect_packet_flow(l2_port)
            self.take_screenshot(f"VCG_PACKET_FLOW - {current_node} - {port_number}")
            logger.info(f"L2_ETH| packet flow of port 9: {packet_flow}")
            eth_status_9["packet_flow"] = packet_flow
        elif status_5["cir_status"] == "live":
            logger.info(f"Circuit is active in main port, hence protection port skipped")
            return eth_status
        else:
            logger.info(f"L2_ETH: port 5 packet flow unknown")

        if eth_status_9["cir_status"] == "live":
            return eth_status_9
        else:
            return eth_status

    def l1_eth_card(self, port_number, vcg_flow):
        # result  = {"cir_status":"live/non-live","alarm_info":[],"packet_flow": "available/unavailable"}
        wait = WebDriverWait(self.driver, 30)
        result = {}
        alarm_info = None

        # Manage frames to enter "ticTopFrame"
        self.switch_to_frames(self.driver, "nodeBodyFrame", "ticTopFrame")
        table = wait.until(EC.presence_of_element_located(
            (By.XPATH, "//table[caption/b[normalize-space()='Ports']]")))
        # Get only data rows (rows that contain anchor inside <th>)
        rows = table.find_elements(By.XPATH, ".//tr[th/a]")

        eth_ports = []
        vcg_ports = []
        for row in rows:
            try:
                port_name = row.find_element(By.TAG_NAME, "a").text.strip()
                columns = row.find_elements(By.TAG_NAME, "td")

                admin_status = columns[0].text.strip()
                oper_status = columns[1].text.strip()

                port_info = {
                    "port_name": port_name,
                    "admin_status": admin_status,
                    "oper_status": oper_status
                }

                if port_name.startswith("ETH"):
                    eth_ports.append(port_info)

                elif port_name.startswith("VCG"):
                    vcg_ports.append(port_info)

            except Exception as e:
                logger.error(f"L1 ETH port status failed to capture due to {e} [dynamic DOM]")
                continue

        # find admin and operational status
        if len(eth_ports) == len(vcg_ports):
            for i in range(len(eth_ports)):
                if port_number in eth_ports[i]["port_name"] or port_number in vcg_ports[i]["port_name"]:
                    l1_eth_port = eth_ports[i]["port_name"]
                    l1_vcg_port = vcg_ports[i]["port_name"]
                    eth_ad_status = eth_ports[i]["admin_status"]
                    eth_oper_status = eth_ports[i]["oper_status"]
                    logger.info(f"ETH port: admin:{eth_ad_status},operation:{eth_oper_status}")
                    vcg_ad_status = vcg_ports[i]["admin_status"]
                    vcg_oper_status = vcg_ports[i]["oper_status"]
                    logger.info(f"VCG port: admin:{vcg_ad_status},operation:{vcg_oper_status}")
                    break
        else:
            logger.error(
                f"length of eth_ports:{len(eth_ports)} does not match length of vcg_ports:{len(vcg_ports)}")

        # Collect alarm info
        if eth_ad_status == 'UP' and eth_oper_status == 'DOWN':
            cir_st = "non-live"
            result["cir_status"] = cir_st
            logger.info(f"L1_ETH: ETH admin {eth_ad_status} Operation {eth_oper_status} | Nonlive")
            alarm_info = self.collect_alarm_info(l1_eth_port)
            if alarm_info:
                if not alarm_info["alarms"]:
                    logger.info(f"operation is down, however no alarm : {alarm_info["alarms"]}")
                logger.info(f"L1 ETH port {l1_eth_port} alarm: {alarm_info}")
            result["alarm_info"] = alarm_info
            alarm_type, occur_list = self.format_alarm_info(alarm_info)
            self.db_query.update_deletion_status(connection_id=self.current_connection_id, alarm_type=alarm_type, alarm_last_occured=occur_list)
                # Need to capture alarm info into database

        elif eth_ad_status == 'DOWN' and eth_oper_status == 'DOWN':
            cir_st = "non-live"
            result["cir_status"] = cir_st
            logger.info(f"L1_ETH: ETH admin {eth_ad_status} Operation {eth_oper_status} | Nonlive")
            result["alarm_info"] = "NA"

        elif eth_ad_status == 'UP' and eth_oper_status == 'UP':
            if vcg_ad_status == 'UP' and vcg_oper_status == 'DOWN':
                cir_st = "non-live"
                result["cir_status"] = cir_st
                logger.info(
                    f"L1_ETH: ETH: {eth_ad_status}|{eth_oper_status} VCG: {vcg_ad_status}|{vcg_oper_status} | Non-live")
                alarm_info = self.collect_alarm_info(l1_vcg_port)
                if alarm_info:
                    logger.info(f"L1 VCG port {l1_vcg_port} alarm: {alarm_info}")
                result["alarm_info"] = alarm_info
                alarm_type, occur_list = self.format_alarm_info(alarm_info)
                self.db_query.update_deletion_status(connection_id=self.current_connection_id, alarm_type=alarm_type, alarm_last_occured=occur_list)

            elif vcg_ad_status == 'DOWN' and vcg_oper_status == 'DOWN':
                cir_st = "non-live"
                logger.info(
                    f"L1_ETH: ETH: {eth_ad_status}|{eth_oper_status} VCG: {vcg_ad_status}|{vcg_oper_status} | Non-live")
                result["cir_status"] = cir_st
                result["alarm_info"] = "NA"
                # return result

            elif eth_ad_status == "UP" and eth_oper_status == "UP":
                logger.info(f"L1_ETH:ETH:{eth_ad_status} | {eth_oper_status}"
                            f"VCG:{vcg_ad_status}|{vcg_oper_status}")
                result = self.admin_oper_alarm(port_name=l1_vcg_port,
                                               admin_status=vcg_ad_status,
                                               operational_status=vcg_oper_status,
                                               port_number=l1_vcg_port)
                return result
                # return result
        else:
            logger.error(f"Unexpected port status found")

        # get packet flow status (for default)
        # packet_flow = self.collect_packet_flow(l1_vcg_port)
        # result["packet_flow"] = vcg_flow
        # print(f"packet flow: {packet_flow}")
        # if packet_flow:
        result["packet_flow"] = vcg_flow
        # update to the database
        logger.info(f"L1 ETH port {port_number} packet_flow: {vcg_flow}")
        return result
    
    def format_alarm_info(self, alarm_info):
        if alarm_info:
            if alarm_info != "Not Applicable":
                alarm_type = str(alarm_info.get("alarms", [])) \
        .replace("[", "{") \
        .replace("]", "}")
                occur_list = json.dumps(alarm_info.get("occurrence", []))
            else:
                alarm_type = "Not Applicable"
                occur_list = "NA"
        else:
            alarm_type = "Not Applicable"
            occur_list = "NA"
        return alarm_type, occur_list
    

    def collect_alarm_info(self, port_number):
        wait = WebDriverWait(self.driver, 30)
        alarm_data = {}
        alarm_info = None
        # Manage frames to enter "nodeBodyFrame --> cardAlarmsFrame"
        self.driver.switch_to.default_content()
        self.switch_to_frames(self.driver, "nodeBodyFrame", "cardAlarmsFrame")
        # click on stop refresh button
        # locate the Stop Refreshing button
        submit_btn = wait.until(EC.presence_of_element_located(
            (By.XPATH, "//input[@type='SUBMIT' and @value='Stop Refresh']")))
        # JavaScript click
        self.driver.execute_script("arguments[0].click();", submit_btn)
        # print("Alarm-Frame: clicked on stop refresh btn successfully")
        all_alarms = f"//tr[td[5][normalize-space()='{port_number}']]/td[3]"
        elements = self.driver.find_elements(By.XPATH, all_alarms)
        alarm_list = [el.text.strip() for el in elements if el.text.strip()]
        alarm_info = ", ".join(alarm_list)
        all_occur = f"//tr[td[5][normalize-space()='{port_number}']]/td[2]"
        elements = self.driver.find_elements(By.XPATH, all_occur)
        occur_list = [el.text.strip() for el in elements if el.text.strip()]
        occur_info = ", ".join(occur_list)

        if alarm_info == "":
            logger.info(f"No alarm found for port {port_number}")
            alarm_data["occurrence"] = []
            alarm_data["alarms"] = []
            # return alarm_list  # "No alarm"
            return alarm_data
        else:
            logger.info(f"Alarm info collected successfully for port {port_number}")
            alarm_data["occurrence"] = occur_list
            alarm_data["alarms"] = alarm_list
            # return alarm_list
            return alarm_data

    def admin_oper_alarm(self, port_name):
        wait = WebDriverWait(self.driver, 60)
        # result  = {"cir_status":"live/non-live","alarm_info":[],"packet_flow": "available/unavailable"}
        result = {}
        result["packet_flow"] = "NA"
        alarm_info = None
        port_number = port_name
        logger.info(f"Collecting admin & Operational status for {port_number}")
        # Manage frames to enter "ticTopFrame"
        self.switch_to_frames(self.driver, "nodeBodyFrame", "ticTopFrame")
        # Fetch Admin and Operational Status for given ports
        admin_st_ele = f"//a[normalize-space(.)='{port_number}']/ancestor::tr/td[1]"
        oper_st_ele = f"//a[normalize-space(.)='{port_number}']/ancestor::tr/td[2]"
        admin_status = wait.until(EC.presence_of_element_located((By.XPATH, admin_st_ele))).text
        operational_status = wait.until(EC.presence_of_element_located((By.XPATH, oper_st_ele))).text
        if admin_status.strip().upper() == "UP" and operational_status.strip().upper() == "DOWN":
            # print(f"admin_status: {admin_status}\noperational status: {operational_status}| Non-live circuit")
            cir_st = "non-live"
            result["cir_status"] = cir_st
            # collect alarm information
            alarm_info = self.collect_alarm_info(port_name)
            logger.info(f"E1 port {port_number} alarm info: {alarm_info}")
            logger.info(f"E1 port {port_number} admin:{admin_status},operational:{operational_status}|Non-live")
            result["alarm_info"] = alarm_info
            alarm_type, occur_list = self.format_alarm_info(alarm_info)
            self.db_query.update_deletion_status(connection_id=self.current_connection_id, alarm_type=alarm_type, alarm_last_occured=occur_list)
            return result
        elif admin_status.strip().upper() == "DOWN" and operational_status.strip().upper() == "DOWN":
            logger.info(f"E1 port {port_number} admin:{admin_status},operational:{operational_status}|Non-live")
            cir_st = "non-live"
            result["cir_status"] = cir_st
            result["alarm_info"] = "NA"
            return result
        elif admin_status.strip().upper() == "UP" and operational_status.strip().upper() == "UP":
            alarm_info = self.collect_alarm_info(port_name)
            logger.info(f"E1 port {port_number} alarm info: {alarm_info}")
            alarms = [a.upper() for a in alarm_info.get("alarms", [])]
            if any("ALARM INDICATION SIGNAL" in a or "LOSS OF SIGNAL" in a
                for a in alarms):
                logger.info(f"E1 port {port_number} has AIS/LOS alarm -> NON-LIVE")
                cir_st = "non-live"
                result["cir_status"] = cir_st
                result["alarm_info"] = alarm_info
                alarm_type, occur_list = self.format_alarm_info(alarm_info)
                self.db_query.update_deletion_status_live(
                    connection_id=self.current_connection_id,
                    alarm_type=alarm_type,
                    alarm_last_occured=occur_list
                )
                return result
        else:
            logger.error(
                f"Unexpected status: E1 port {port_number} admin:{admin_status},operational:{operational_status}")
            cir_st = "unknown"
            result["cir_status"] = cir_st
            result["alarm_info"] = "unknown"
            return result

    def main_process(self, filepath):
        logger.info("Starting Circuit Processing")
        self.devices_df = self.db_query.get_ais_circuit_data(filepath)
        self.devices_df['status'] = ''
        self.devices_df['remarks'] = ''
        total_records = len(self.devices_df)
        print("Total nodes:", total_records)
        csv_processor = NeLevelDeletion(self.db_query)
        processed_db_ids = []
        for index, row in self.devices_df.iterrows():
            label = row.get("label")
            connection_id = row.get("connection_id")
            db_id = self.db_query.get_non_live_row(connection_id, row.get("a_end_port"), row.get("b_end_port"))
            processed_db_ids.extend([str(x) for x in db_id])
            tjs_id = str(row.get("tjs_id", "")).strip()
            service_name = str(row.get("service_name", "")).strip()
            zone = row.get("zone")
            start_time = time.time()
            logger.info(f"Processing node: {label} | {connection_id} | {tjs_id} | {service_name} | {zone}")
            logger.info("_" * 80)
            logger.info(f"START: {connection_id}")
            logger.info("_" * 80)
            try:
                if self.driver is None:
                    self.driver = self.login_manager.process_node(row)
                result = self.nms_level_deletion(row=row, index=index, processed_db_ids=processed_db_ids, connection_id = connection_id, tjs_id = tjs_id, service_name=service_name)
                if isinstance(result, dict) and result.get("status", "").strip().upper() == "ADRS":
                    logger.info(f"[ADRS FLOW] Processing {connection_id}")
                    csv_path = csv_processor.run(input_data=result, task_type="non_live")
                    if csv_path:
                        self.process_csv_nodes(csv_path, connection_id, processed_db_ids)
                    else:
                        logger.warning(f"[ADRS] No search results for {connection_id}")
                        self.db_query.update_deletion_status(connection_id=str(connection_id).strip(), status=False,
                                                                               remarks='No search results in ADRS')
                        processed_db_ids.append(row.get("id"))
                        continue
            except Exception as e:
                logger.exception(f"Node failed: {label} due to {e}")
            logger.info("_" * 80)
            logger.info(f"END: {connection_id}")
            logger.info("_" * 80 + "\n")
            end_time = time.time()
            total_time = round(end_time - start_time, 2)
            logger.info(f"Circuit {connection_id} took {total_time} seconds")
        logger.info("Tejas Automation run completed")
        output_path = RUN_DIR / f"node_deletion_results_{timestamp}.csv"
        final_df = self.db_query.get_final_non_live_data(processed_db_ids)
        if final_df is not None and not final_df.empty:
            final_df.to_csv(output_path, index=False)
        else:
            logger.warning("NO DATA FOUND")
        self.finalize_pdf()
        if self.driver:
            self.driver.quit()
