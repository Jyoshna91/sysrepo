import os
import re

import pandas as pd
from db_querys import DbQuery
from tejas_utils import load_config
from common_libs.logger import logger
from pathlib import Path
import datetime
from datetime import datetime


timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
SS_DIR = Path(__file__).parent / "screenshots"
ASSETS_DIR = Path(__file__).parent / "assets" / "non_live_circuit_deletion" 
RUN_DIR = ASSETS_DIR / timestamp


class NeLevelDeletion:
    def __init__(self, db_query):
        self.db = db_query
        config = load_config(self)
        self.resource_files = config["paths"]["resource_files"]
        self.resource_cache = {}
        logger.info(f"[INIT] Loaded zones: {list(self.resource_files.keys())}")
        self.non_tejas_data = []

    # ---------------- LOAD CSV BASED ON ZONE ----------------
    def get_resource_df(self, zone):
        if not zone:
            logger.warning("[CSV] Zone is empty")
            return None
        zone = str(zone).strip().lower()
        logger.info(f"[CSV] Requested zone: {zone}")
        if zone not in self.resource_files:
            logger.error(f"[CSV] Zone not found in config: {zone}")
            return None
        if zone not in self.resource_cache:
            path = self.resource_files[zone]
            logger.info(f"[CSV] Loading CSV for zone '{zone}' → {path}")
            try:
                df = pd.read_csv(path)
                df.columns = df.columns.str.strip()
                logger.info(f"[CSV] Loaded rows: {len(df)} | Columns: {list(df.columns)}")
                self.resource_cache[zone] = df
            except Exception as e:
                logger.error(f"[CSV] Failed to load CSV: {e}")
                return None
        else:
            logger.info(f"[CSV] Using cached CSV for zone: {zone}")
        return self.resource_cache[zone]

    def extract_to_csv(self, input_data):
        connection_id = str(input_data.get("connection_id", "")).strip()
        service_name = str(input_data.get("service_name", "")).strip()
        zone = input_data.get("zone")

        df_res = self.get_resource_df(zone)
        if df_res is None:
            return None

        df_res["Circuit Name"] = df_res["Circuit Name"].astype(str).str.strip()
        df_match = df_res[
            df_res["Circuit Name"].str.contains(service_name, na=False)
        ]
        print("Total matched rows:", len(df_match))
        if df_match.empty:
            logger.warning(f"[CSV] No search results found | Service name: {service_name} | Connection ID: {connection_id}")
            return None
        df_match = df_match.copy()
        df_match["connection_id"] = connection_id
        df_match = df_match.drop_duplicates()
        return df_match
        

    def process_extracted_csv(self, df, input_data):

        processed_rows = []
        previous_keys = set()
        connection_id = input_data.get("connection_id")
        excel_node = str(input_data.get("selected_node", "")).strip().upper()
        excel_port = str(input_data.get("selected_port", "")).strip().upper()
        excel_port = "-".join(excel_port.split("-")[:4])

        for index in df.index:
            a_node = df.at[index, "A End Node(Label)"]
            a_port = str(df.at[index, "A End Port(Label)"]).strip()
            z_node = df.at[index, "Z End Node(Label)"]
            z_port = str(df.at[index, "Z End Port(Label)"]).strip()
            logical_resource = str(df.at[index, "Logical Resource"]).strip()
            end_ne = str(df.at[index, "End NE"]).strip()
            end_ctp = str(df.at[index, "End CTP"]).strip()
          
            nodes_to_process = []

            if a_node and a_node != "nan" and not a_node.upper().startswith("VNE"):
                nodes_to_process.append({
                    "node": a_node,
                    "port":a_port,
                    "logical_resource": logical_resource
                })
            
            if z_node and z_node != "nan" and not z_node.upper().startswith("VNE"):
                nodes_to_process.append({
                    "node": z_node,
                    "port":z_port,
                    "logical_resource": logical_resource
                })
            if end_ne and end_ne != "nan" and not end_ne.upper().startswith("VNE"):
                if end_ctp and end_ctp != "nan":
                    nodes_to_process.append({
                        "node": end_ne,
                        "port": end_ctp
                    })
            
            

            for item in nodes_to_process:
                item_node = str(item["node"]).strip().upper()
                item_port = str(item["port"]).strip().upper()
                item["priority"] = False
                logger.info(f"EXCEL: {excel_node} | {excel_port}")
                logger.info(f"ITEM: {item_node} | {item_port}")
                if item_node == excel_node and item_port == excel_port:
                    logger.info(f"MATCHED: {item_node} | {item_port}")
                    item["priority"] = True

                node = item["node"]
                port_val = item["port"]
                logical = item.get("logical_resource","")
                card = None
                port = None
                jklm = None
                upper_port = str(port_val).upper()
                upper_port = upper_port.replace(" ", "-")


                try:
                    if "J-KLM" in upper_port:
                        parts = upper_port.split(":")
                        stm_part = parts[0].strip()
                        m = re.search(r"STM\d+-(\d+)-(\d+)-(\d+)",stm_part)
                        if m:
                            card = f"{m.group(1)}-{m.group(2)}"
                            port = m.group(3)
                        if len(parts) >= 3:
                            jklm_part = parts[-1].strip()
                            nums = re.findall(r"\d+", jklm_part)
                            if len(nums) >= 4:
                                jklm = "-".join(nums[:4])
                    else:
                        if upper_port.startswith("STM"):
                            m = re.search(r"STM\d+-(\d+)-(\d+)-(\d+)", upper_port)
                            if m:
                                card = f"{m.group(1)}-{m.group(2)}"
                                port = m.group(3)

                            nums = re.findall(r"\d+", logical)
                            if len(nums) >= 4:
                                jklm = "-".join(nums[:4])

                        elif upper_port.startswith("VCG"):
                            m = re.search(r"VCG-(\d+)-(\d+)-(\d+)", upper_port)
                            if m:
                                card = f"{m.group(1)}-{m.group(2)}"
                                port = m.group(3)

                        elif upper_port.startswith("ETH"):
                            m = re.search(r"ETH-(\d+)-(\d+)-(\d+)", upper_port)
                            if m:
                                card = f"{m.group(1)}-{m.group(2)}"
                                port = m.group(3)

                        elif upper_port.startswith("E1"):
                            m = re.search(r"E1-(\d+)-(\d+)-(\d+)", upper_port)
                            if m:
                                card = f"{m.group(1)}-{m.group(2)}"
                                port = m.group(3)

                        else:
                            numbers = re.findall(r"\d+", upper_port)
                            if len(numbers) >= 3:
                                last_three = numbers[-3:]
                                card = f"{last_three[0]}-{last_three[1]}"
                                port = last_three[2]
                            elif len(numbers) == 2:
                                card = f"{numbers[0]}-{numbers[1]}"
                            elif len(numbers) == 1:
                                port = numbers[0]

                            if logical_resource:
                                nums = re.findall(r"\d+", logical_resource)
                                if len(nums) >= 4:
                                    jklm = "-".join(nums[:4])

                except Exception as e:
                    print(f"Error parsing row {index}: {e}")
                    continue
                node_key = str(node).strip().upper()
                if not item.get("priority"):
                    if node_key in previous_keys:
                        logger.info(f"[DUPLICATE NODE SKIPPED] {node_key}")
                        continue
                previous_keys.add(node_key)
                logger.info(f"[PRIORITY DEBUG] node={node}, full_port={port_val}, priority={item.get('priority')}")
                row_data = df.loc[index].to_dict()
                row_data.update({
                    "node":node,
                    "port":port,
                    "card":card,
                    "jklm":jklm,
                    "full_port":port_val,
                    "logical_resource":logical,
                    "priority":item.get("priority", False)
                })
                processed_rows.append(row_data)
        return processed_rows
    
    def run(self, input_data):
        try:
            df = self.extract_to_csv(input_data)
            if df is None or df.empty:
                return None
            # -------- SAVE DIRECT CSV HERE --------
            RUN_DIR.mkdir(parents=True, exist_ok=True)
            file_path = RUN_DIR / f"ne_level_deletion_adrsdump_ref_{timestamp}.csv"
            df.to_csv(file_path, index=False)
            logger.info(f"[CSV SAVED] {file_path}")
            # --------------------------------------
            processed_data = self.process_extracted_csv(
                df,
                input_data
            )
            return processed_data
        except Exception as e:
            logger.error(f"[PARSE ERROR] {e}")
            return None
