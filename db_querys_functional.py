import logging
import traceback
import pandas as pd
from common_libs.db import db_connect, db_close
from psycopg2.extras import execute_values, DictCursor
import psycopg2.extras
import json
from common_libs.logger import logger

class DbQuery:
    def __init__(self):
        self.conn = db_connect()
        self.cursor = self.conn.cursor()
        self.adrs_scope = 'ADRS_SCOPE'
        self.adrs_scope_updated = 'COMPLETED'

    def get_daig_credentials(self):
        try:
            query = """
                        SELECT ID, USER_NAME, PASSWORD FROM TJS_DIAG_CREDENTIALS WHERE TYPE = 'write' ORDER BY ID
            """
            df = pd.read_sql(query, self.conn)
            return df

        except Exception as e:
            logger.error(f"Failed to fetch diag CRED")
            print(f'Exception:{e}')

    def get_node_data(self,label):
        query = f"SELECT * FROM Public.tjs_xc_dump where label='{label}';"
        # query = "SELECT * FROM Public.tjs_xc_dump where label='CHN_SAN_906_T1408_T';" #290 Circuits
        # query = "SELECT * FROM Public.tjs_xc_dump where label='CHN_DLF_947_T1201_F';" #6 Circuits
        df = pd.read_sql(query, self.conn)
        return df

    def update_node_data(self, row_id, status):
        try:
            cur = self.conn.cursor()
            update_query = """
                UPDATE Public.tjs_xc_dump
                SET tejas_status = %s
                WHERE id = %s;
            """
            cur.execute(update_query, (status, row_id))
            self.conn.commit()
            cur.close()
            print("Successfully excuted update query")
        except Exception as e:
            print("Error occured while excuted update query", e)
            raise Exception(e)

    def insert_circuit_info(self, df):
        if df.empty:
            print("DataFrame is empty. Nothing to insert.")
            return

        cur = self.conn.cursor()
        df = df.drop(columns=['id'], errors='ignore')

        columns = list(df.columns)
        column_str = ",".join(columns)

        insert_query = f""" INSERT INTO public.tjs_circuit_info ({column_str}) VALUES %s """

        data = [ tuple(None if pd.isna(val) else val for val in row) for row in df.to_numpy() ]

        try:
            execute_values(cur, insert_query, data)
            self.conn.commit()
            print(f"{len(data)} rows inserted successfully.")

        except Exception as e:
            self.conn.rollback()
            print("Error inserting data:", e)

        finally:
            cur.close()

    # Verify End Points Nms status
    def VerifynmsStatus(self):
        try:
            cur = self.conn.cursor()

            query = """
                SELECT *
                FROM public.tjs_circuit_info
                WHERE circuit_category in ('DROP','PASSTHRU');
            """
            cur.execute(query)

            # Get column names
            colnames = [desc[0] for desc in cur.description]
            print(colnames)

            rows = cur.fetchall()
            print(f"Total circuits fetched: {len(rows)}")

            update_sql = """
                UPDATE public.tjs_circuit_info
                SET endpoint_nms_status = %s
                WHERE rtrim(connection_id) = %s;
                """

            for row in rows:
                row_dict = dict(zip(colnames, row))

                i_label = row_dict.get("label")
                i_connection_id = row_dict.get("connection_id")
                i_a_end = row_dict.get("a_end")
                i_b_end = row_dict.get("b_end")

                print(f"Checking: Connection={i_connection_id}, Label={i_label}")

                if i_a_end and i_b_end:
                    epA = str(i_a_end).lower().strip()
                    epB = str(i_b_end).lower().strip()

                    tejas = ('t', 'me', 'mc', 'cp')

                    def get_nms(ep):
                        parts = ep.split('_')
                        if len(parts) > 3:
                            part = parts[3]   # 4th section
                            for t in tejas:
                                if part.startswith(t):
                                    return True
                            return False
                        return None

                    nmsA = get_nms(epA)
                    nmsB = get_nms(epB)

                    if nmsA == nmsB:
                        endpoint_nms_status = "same"
                    else:
                        endpoint_nms_status = "different"
                else:
                    endpoint_nms_status = "unknown"

                try:
                    cur.execute(update_sql, (endpoint_nms_status, i_connection_id.strip()))
                except Exception as e:
                    print(f"Update failed for Connection={i_connection_id} - {e}")

            self.conn.commit()
            print("All endpoint NMS status updates committed successfully.")

        except Exception as e:
            self.conn.rollback()
            print("Error in VerifynmsStatus:", e)
            traceback.print_exc()

        finally:
            cur.close()
            print("Cursor closed.")

    def update_circuit_data(self, status, connection_id, label):
        try:
            cur = self.conn.cursor()
            update_query = """
                UPDATE public.tjs_circuit_info
                SET status = %s
                WHERE connection_id = %s and label = %s;
            """
            cur.execute(update_query, (status, connection_id, label))
            self.conn.commit()
            cur.close()
            print("Successfully excuted update query")
        except Exception as e:
            print("Error occured while excuted update query", e)
            raise Exception(e)
        
    def get_circuit_data(self):
        query = "SELECT * FROM public.tjs_circuit_info;"
        df = pd.read_sql(query, self.conn)
        return df

    def update_product_types(
            self, order_num, lsi_num, row_id
    ):
        try:
            cur = self.conn.cursor()
            update_query = """
                UPDATE Public.tjs_circuit_info
                SET ra = %s,
                    lsi = %s
                    WHERE id = %s;
            """
           
            cur.execute(
                update_query,
                (order_num, lsi_num, row_id)
            )
            self.conn.commit()
            cur.close()
            print("Successfully executed update query")
        except Exception as e:
            print("Error occurred while executing update query", e)
            raise
    
    # AIS Input Data
    def get_ais_injected_data(self):
        query = """SELECT 
                    DISTINCT INFO.LABEL,
                    INFO.CONNECTION_ID,
                    INFO.SOURCE,

                    -- FIRST 4 PARTS
                    CONCAT_WS('-',
                        split_part(INFO.SOURCE, '-', 1),
                        split_part(INFO.SOURCE, '-', 2),
                        split_part(INFO.SOURCE, '-', 3),
                        split_part(INFO.SOURCE, '-', 4)
                    ) AS SOURCE_CARD,

                    -- FIXED REMAINING PART
                    CASE 
                        WHEN array_length(string_to_array(INFO.SOURCE, '-'), 1) > 4 THEN
                            TRIM(BOTH '-' FROM
                                regexp_replace(
                                    INFO.SOURCE,
                                    '^(([^-]+-){4})',
                                    ''
                                )
                            )
                        ELSE NULL
                    END AS SOURCE_JKLM,
                    INFO.DROP_CIRCUIT_TYPE,
                    DEV.ZONE

                FROM 
                    PUBLIC.TJS_CIRCUIT_INFO AS INFO

                JOIN 
                    PUBLIC.TJS_NON_LIVE_CIRCUIT_MIG_DET AS NON_LIVE
                    ON INFO.LABEL = NON_LIVE.LABEL

                JOIN
                    PUBLIC.TJS_XC_DUMP AS DEV
                    ON INFO.LABEL = DEV.LABEL

                WHERE 
                    INFO.CIRCUIT_STATUS = 'non-live';"""
        
        df = pd.read_sql(query, self.conn)
        return df
    
    # Update AIS Status
    def update_ais_status(self, label, status):
        try:
            query = """
                UPDATE public.tjs_non_live_circuit_mig_det
                SET ais_injected_status = %s,
                    ais_injected_date = NOW()
                WHERE label = %s
            """

            with self.conn.cursor() as cur:
                cur.execute(query, (status, label))
                self.conn.commit()

            self.logger.info(f"AIS status updated for {label} → {status}")

        except Exception as e:
            self.logger.error(f"Failed to update AIS status for {label}: {e}")
            print(f'Exception:{e}')

###### ------------------- TASK 10 Utils Starts Here ------------------- ######

    def get_cir_endpoints_data(self, node_name):
        query = f""" 
        SELECT 
            ci.id,
            ci.label,
            ci.connection_id,
            ci.a_end,
            ci.a_end_port,
            ci.b_end,
            ci.b_end_port,
            ci.circuit_category,
            ci.drop_circuit_type,
            ci.status,
            xd.zone 
        FROM public.tjs_circuit_info ci 
        LEFT JOIN public.tjs_xc_dump xd 
            ON ci.label = xd.label 
        WHERE ci.label = %s
            AND ci.circuit_status is NULL
            AND ci.status = 'COMPLETED'
            ;"""    #AND TRIM(ci.connection_id) = %s
        # AND ci.circuit_status = NULL;"""
        # Use parameterized query to avoid SQL injection
        df = pd.read_sql(query, self.conn, params=[node_name])
        # Sort by a_end
        df = df.sort_values(by="a_end")
        return df

    def db_new_update_cir_live_nonlive(self, cir_status, processed_node, processed_port):
        """
        Update circuit_info and insert into live/non-live migration tables
        for all rows where the given node/port combination appears on either side.

        """
        # logger.info("processed_node=%r, processed_port=%r", processed_node, processed_port)

        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:

                # Handle alarm info
                if cir_status["alarm_info"] != "Not Applicable":
                    alarm_list = cir_status["alarm_info"]["alarms"]
                    occur_list = json.dumps(cir_status["alarm_info"]["occurrence"])
                else:
                    alarm_list = "Not Applicable"
                    occur_list = "NA"

                # Update all rows that match node/port on either side
                update_query = """
                    UPDATE public.tjs_circuit_info ci
                    SET circuit_status = %s,
                        alaram = %s,
                        packet_status = %s
                    WHERE (ci.a_end = %s AND ci.a_end_port = %s)
                       OR (ci.b_end = %s AND ci.b_end_port = %s);
                """
                cur.execute(update_query, (
                    cir_status["cir_status"], alarm_list, cir_status["packet_flow"],
                    processed_node, processed_port, processed_node, processed_port
                ))
                logger.info("Rows updated: %s", cur.rowcount)

                # Collect all affected rows
                select_query = """
                    SELECT *
                    FROM public.tjs_circuit_info
                    WHERE (a_end = %s AND a_end_port = %s)
                       OR (b_end = %s AND b_end_port = %s);
                """
                cur.execute(select_query, (processed_node, processed_port,
                                           processed_node, processed_port))
                affected_rows = cur.fetchall()
                logger.info("Rows selected: %s", len(affected_rows))

                # Insert into migration tables
                for row in affected_rows:
                    if cir_status["cir_status"] == "live":
                        insert_live_query = """
                            INSERT INTO public.tjs_live_circuit_mig_det
                                (label, connection_id, existing_a_end, existing_a_end_port,
                                 existing_b_end, existing_b_end_port,alarm_remarks,packet_status)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT DO NOTHING;
                        """
                        cur.execute(insert_live_query, (
                            row["label"], row["connection_id"], row["a_end"], row["a_end_port"],
                            row["b_end"], row["b_end_port"], alarm_list, cir_status["packet_flow"]
                        ))
                    elif cir_status["cir_status"] == "non-live":
                        insert_nonlive_query = """
                            INSERT INTO public.tjs_non_live_circuit_mig_det
                                (label, connection_id, a_end, a_end_port, b_end, b_end_port,
                                 alarm_type, alarm_last_occured,packet_status)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT DO NOTHING;
                        """
                        cur.execute(insert_nonlive_query, (
                            row["label"], row["connection_id"], row["a_end"], row["a_end_port"],
                            row["b_end"], row["b_end_port"], alarm_list, occur_list, cir_status["packet_flow"]
                        ))

                # Commit once after all updates/inserts
                self.conn.commit()
                logger.info("Committed updates and inserts successfully")

        except Exception as e:
            self.conn.rollback()
            logger.error("Error occurred while executing update/insert queries", exc_info=True)
            raise

    def db_update_ume_manual_cir(self,processed_node_a,a_port,processed_node_b,b_port,status):

        try:

            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if status in ["UME_Manual"]:
                    # Update all rows that match node/port on either side
                    update_query = """
                        UPDATE public.tjs_circuit_info ci
                        SET circuit_status = %s
                        WHERE (ci.a_end = %s AND ci.b_end = %s)
                            OR (ci.a_end = %s AND ci.b_end = %s);
                    """
                    cur.execute(update_query, (
                        status,
                        processed_node_a, processed_node_b,
                        processed_node_b, processed_node_a
                    ))
                    logger.info("Rows updated: %s", cur.rowcount)
                    logger.info("Committed updates and inserts successfully for UME Manual case")
                elif status in ["unmanaged","no endpoints","no_drop_end"]:
                    update_query = """
                        UPDATE public.tjs_circuit_info ci
                        SET circuit_status = %s
                        WHERE (ci.a_end = %s AND ci.a_end_port = %s)
                            AND (ci.b_end = %s AND ci.b_end_port = %s);
                    """
                    cur.execute(update_query, (
                        status,
                        processed_node_a, a_port,
                        processed_node_b, b_port
                    ))
                    logger.info("Rows updated: %s", cur.rowcount)
                    logger.info("Committed updates and inserts successfully for Unmanaged case")


                # Commit once after all updates/inserts
                self.conn.commit()

        except Exception as e:
            self.conn.rollback()
            logger.error("Error occurred while executing update/insert queries", exc_info=True)
            raise

    def db_update_hanging_cir(self,cir_status):
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:

                # Handle alarm info
                if cir_status["alarm_info"] != "Not Applicable":
                    alarm_list = cir_status["alarm_info"]["alarms"]
                    occur_list = json.dumps(cir_status["alarm_info"]["occurrence"])
                else:
                    alarm_list = "Not Applicable"
                    occur_list = "NA"

                # Update all rows that match node/port on either side
                update_query = """
                    UPDATE public.tjs_circuit_info ci
                SET circuit_status = %s,
                    alaram = %s,
                    packet_status = %s
                WHERE UPPER(TRIM(ci.a_end)) = 'UNKNOWN'
                   OR UPPER(TRIM(ci.b_end)) = 'UNKNOWN';
                """
                cur.execute(update_query, (
                    cir_status["cir_status"], alarm_list, cir_status["packet_flow"]
                ))
                logger.info("Rows updated: %s", cur.rowcount)

                # Collect all affected rows
                select_query = """
                    SELECT *
                    FROM public.tjs_circuit_info ci
                    WHERE UPPER(TRIM(ci.a_end)) = 'UNKNOWN'
                        OR UPPER(TRIM(ci.b_end)) = 'UNKNOWN';
                """
                cur.execute(select_query)
                affected_rows = cur.fetchall()
                logger.info("Rows selected: %s", len(affected_rows))

                # Insert into migration table if non-live
                if cir_status["cir_status"].lower() == "non-live":
                    for row in affected_rows:
                        insert_nonlive_query = """
                                    INSERT INTO public.tjs_non_live_circuit_mig_det
                                        (label, connection_id, a_end, a_end_port, b_end, b_end_port,
                                         alarm_type, alarm_last_occured, packet_status)
                                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                                    ON CONFLICT DO NOTHING;
                                    """
                        cur.execute(insert_nonlive_query, (
                            row["label"], row["connection_id"], row["a_end"], row["a_end_port"],
                            row["b_end"], row["b_end_port"], alarm_list, occur_list, cir_status["packet_flow"]
                        ))
                else:
                    logger.error("Hanging circuit cannot be live")

                # Commit once after all updates/inserts
                self.conn.commit()
                logger.info("Committed updates and inserts successfully")

        except Exception as e:
            self.conn.rollback()
            logger.error("Error occurred while executing update/insert queries", exc_info=True)
            raise

    def db_update_cir_category_and_type(self, df):
        try:
            with self.conn.cursor() as cur:
                # Create a temporary table
                cur.execute("""
                    CREATE TEMP TABLE tmp_circuit_updates (
                        id BIGINT,
                        circuit_category TEXT,
                        drop_circuit_type TEXT
                    ) ON COMMIT DROP;
                """)

                # Insert all updated rows into temp table
                rows = df[['id', 'circuit_category', 'drop_circuit_type']].values.tolist()
                psycopg2.extras.execute_values(
                    cur,
                    "INSERT INTO tmp_circuit_updates (id, circuit_category, drop_circuit_type) VALUES %s",
                    rows
                )

                # Bulk update in one shot
                cur.execute("""
                    UPDATE public.tjs_circuit_info ci
                    SET circuit_category = tmp.circuit_category,
                        drop_circuit_type = tmp.drop_circuit_type
                    FROM tmp_circuit_updates tmp
                    WHERE ci.id = tmp.id;
                """)

                self.conn.commit()
                logger.info(f"Updated cir_info with circuit category and type successfully") #, {len(df)}
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Failed to update cir_info with circuit category and type" ) #exc_info=True
            raise

###### ------------------- TASK 10 Utils Ends Here ------------------- ######
    def get_unmatched_circuits(self):
        query = """
        SELECT connection_id, status
        From tjs_circuit_info 
        WHERE LOWER(COALESCE(status, '')) IN (
            'circuit match not found check in adrs',
            'zero search results in manage circuit')"""
        df = pd.read_sql(query, self.conn)
        logger.info(f"Fetched {len(df)} circuits from tjs_circuit_info")
        return df
#----------------------------------------------------------------------------------------

## TASK 18 Utils here
    # def get_ais_circuit_data(self, filepath):
    #     try:
    #         df_csv = pd.read_csv(filepath)
    #         self.cursor.execute("""
    #             DROP TABLE IF EXISTS temp_input;

    #             CREATE TEMP TABLE temp_input (
    #                 connection_id TEXT,
    #                 label TEXT
    #             );
    #         """)
    #         self.conn.commit()
    #         data = list(df_csv[['connection_id', 'label']].itertuples(index=False, name=None))
    #         insert_query = """
    #             INSERT INTO temp_input (connection_id, label)
    #             VALUES %s
    #         """
    #         execute_values(self.cursor, insert_query, data)
    #         self.conn.commit()
    #         query = """
    #         SELECT
    #             mig.label,
    #             mig.connection_id,
    #             ci.service_name,
    #             ci.tjs_id,
    #             mig.a_end,
    #             mig.b_end,
    #             mig.a_end_port,
    #             mig.b_end_port,
    #             xc.zone

    #         FROM temp_input inp

    #         JOIN public.tjs_non_live_circuit_mig_det mig
    #         ON inp.connection_id = mig.connection_id

    #         JOIN public.tjs_xc_dump xc
    #         ON inp.label = xc.label

    #         LEFT JOIN (
    #             SELECT DISTINCT ON (connection_id)
    #                 connection_id,
    #                 tjs_id,
    #                 service_name
    #             FROM public.tjs_circuit_info
    #             ORDER BY connection_id, tjs_id DESC
    #         ) ci
    #         ON mig.connection_id = ci.connection_id

    #         WHERE mig.ais_injected_status = TRUE
    #         """

    #         df = pd.read_sql(query, self.conn)

    #         return df

    #     except Exception as e:
    #         logger.error(f"Error in get_ais_circuit_data: {e}")
    #         raise

    def get_ais_circuit_data(self, filepath):
        try:
            df_csv = pd.read_csv(filepath)
            a_df = df_csv[df_csv["a_end_status"].astype(str).str.strip().str.upper().eq("SUCCESS")].copy()
            a_df["selected_node"] = a_df["a_end"]
            a_df["selected_port"] = a_df["a_end_port"]
            b_df = df_csv[df_csv["b_end_status"].astype(str).str.strip().str.upper().eq("SUCCESS")].copy()
            b_df["selected_node"] = b_df["b_end"]
            b_df["selected_port"] = b_df["b_end_port"]
            final_df = pd.concat([a_df, b_df], ignore_index=True)
            self.cursor.execute("""
                DROP TABLE IF EXISTS temp_input;
                CREATE TEMP TABLE temp_input (
                    connection_id TEXT,
                    label TEXT,
                    tjs_id TEXT,
                    selected_node TEXT,
                    selected_port TEXT
                );
            """)
            self.conn.commit()
            data = list(
                final_df[
                    [
                        'connection_id',
                        'label',
                        'tjs_id',
                        'selected_node',
                        'selected_port'
                    ]
                ].itertuples(index=False, name=None)

            )
            insert_query = """
                INSERT INTO temp_input (
                    connection_id,
                    label,
                    tjs_id,
                    selected_node,
                    selected_port
                )
                VALUES %s
            """
            execute_values(
                self.cursor,
                insert_query,
                data
            )
            self.conn.commit()
            query = """
                SELECT DISTINCT
                    inp.connection_id,
                    inp.label,
                    CASE WHEN inp.tjs_id IS NULL
                    OR TRIM(inp.tjs_id) = ''
                    OR LOWER(TRIM(inp.tjs_id)) = 'nan'
                    THEN NULL
                    ELSE SPLIT_PART(inp.tjs_id, '.', 1)
                    END AS tjs_id,
                    inp.selected_node,
                    inp.selected_port,
                    ci.service_name,
                    ci.a_end,
                    ci.a_end_port,
                    ci.b_end,
                    ci.b_end_port,
                    xc.zone,
                    CASE
                        WHEN UPPER(inp.selected_port) LIKE '%E1%'
                        THEN 'E1'
                        WHEN UPPER(inp.selected_port) LIKE '%VCG%'
                        THEN 'VCG'
                        ELSE 'UNKNOWN'
                    END AS port_type
                FROM temp_input inp
                -- CASE 1 -> TJS ID MATCH
                LEFT JOIN public.tjs_circuit_info ci
                ON (
                    inp.tjs_id IS NOT NULL
                    AND inp.tjs_id <> ''
                    AND inp.tjs_id = ci.tjs_id
                )
                OR
                -- CASE 2 -> A/B END MATCH
                (
                    (
                        inp.selected_node = ci.a_end
                        AND inp.selected_port = ci.a_end_port
                    )
                    OR
                    (
                        inp.selected_node = ci.b_end
                        AND inp.selected_port = ci.b_end_port
                    )
                )
                LEFT JOIN public.tjs_xc_dump xc
                ON inp.label = xc.label
            """
            df = pd.read_sql(query, self.conn)
            return df
        except Exception as e:
            logger.error(f"Error in get_ais_circuit_data: {e}")
            raise

    def update_deletion_status(self, connection_id, status=True, remarks=None, alarm_type=None, alarm_last_occured=None):
        conn = db_connect()
        try:
            cur = conn.cursor()
            query = """
                UPDATE public.tjs_non_live_circuit_mig_det
                SET circuit_deletion_status = COALESCE(%s, circuit_deletion_status),
                    circuit_deletion_remarks = COALESCE(%s, circuit_deletion_remarks),
                    alarm_type = COALESCE(%s, alarm_type),
                    alarm_last_occured = COALESCE(%s, alarm_last_occured)
                WHERE connection_id = %s;
            """
            cur.execute(query, (status, remarks, alarm_type, alarm_last_occured, connection_id))
            conn.commit()
            cur.close()
            print(f"Updated deletion status for {connection_id}")
        finally:
            db_close(conn)
    
    def get_device_manufacturer(self, node):
        try:
            query = f"""
            SELECT 
            d.label,
            d.manufacturer,
            x.zone
            FROM tbl_device_dump d
            JOIN public.tjs_xc_dump x
            ON TRIM(d.label) = TRIM(x.label)
            WHERE TRIM(d.label) = TRIM('{node}')
            LIMIT 1
            """
            df = pd.read_sql(query, self.conn)
            if not df.empty:
                return {
            "manufacturer":str(df.iloc[0]["manufacturer"]).strip().upper(),
            "zone":str(df.iloc[0]["zone"]).strip().lower()}
            return None
        except Exception as e:
            logger.error(f"Error fetching manufacturer for {node}:{e}")
            return None
        
    def get_non_live_row(self, connection_id):
        query = f"""
            SELECT id
            FROM public.tjs_non_live_circuit_mig_det
            WHERE TRIM(connection_id) = TRIM('{connection_id}')
            LIMIT 1
        """
        df = pd.read_sql(query, self.conn)
        if not df.empty:
            return df.iloc[0]["id"]
        return None


    def get_final_non_live_data(self, processed_db_ids):
        clean_ids = [str(x) for x in processed_db_ids if x is not None]
        ids = ",".join(clean_ids)
        query = f"""
            SELECT 
            id, 
            label,
            connection_id,
            a_end,
            a_end_port,
            b_end,
            b_end_port,
            alarm_type,
            alarm_last_occured,
            ais_injected_status,
            ais_injected_date,
            packet_status,
            circuit_deletion_status,
            circuit_deletion_remarks
        FROM public.tjs_non_live_circuit_mig_det
        WHERE id IN ({ids})
        ORDER BY id ASC
        """
        df = pd.read_sql(query, self.conn)
        return df
    

    def get_adrs_circuit_full_data(self):
        try:
            query = """
            SELECT
                mig.connection_id,
                mig.label,
                mig.a_end,
                mig.a_end_port,
                mig.b_end,
                mig.b_end_port,
                xc.zone
            FROM public.tjs_non_live_circuit_mig_det mig
            LEFT JOIN public.tjs_xc_dump xc
             ON TRIM(mig.label) = TRIM(xc.label)
            WHERE LOWER(COALESCE(mig.circuit_deletion_remarks, '')) 
                  = 'circuit not found in tejas manage circuits'
            """

            df = pd.read_sql(query, self.conn)
            logger.info(f"Fetched {len(df)} circuits for ADRS processing")
            return df

        except Exception as e:
            logger.error(f"Error fetching ADRS circuit data: {str(e)}")
            return pd.DataFrame()

    ##-----------------------------------------------------------##


    def update_circuit_info(self, df, row):
        if df.empty:
            logger.info("No match found, skipping update")
            return
        rec = df.iloc[0]
        print(rec)
        query = """
               UPDATE tjs_circuit_info
               SET 
                   a_end = %s,
                   a_end_port = %s,
                   b_end = %s,
                   b_end_port = %s
               WHERE 
                   label = %s
                   AND connection_id = %s
                   AND source = %s
                   AND destination = %s
           """
        values = (
            rec["a_end"],
            rec["a_end_port"],
            rec["b_end"],
            rec["b_end_port"],
            row["label"],
            row["connection_id"],
            row["source"],
            row["destination"]
        )
        success = self.execute_update(query, values)
        if success:
            logger.info(f"DB updated | label={row['label']} | conn_id={row['connection_id']}")
        else:
            logger.error(f"DB update failed | label={row['label']} | conn_id={row['connection_id']}")
        return success

    def update_circuit_info_single(self, rec, row):
        # ✅ Normalize rec to dict-like
        if isinstance(rec, tuple):
            rec = dict(zip(
                ["a_end", "a_end_port", "b_end", "b_end_port", "service_name"],
                rec
            ))
        query = """
            UPDATE tjs_circuit_info
            SET 
                a_end = %s,
                a_end_port = %s,
                b_end = %s,
                b_end_port = %s,
                service_name = %s,
                status = %s
            WHERE 
                label = %s
                AND connection_id = %s
                AND source = %s
                AND destination = %s
        """

        values = (
            rec.get("a_end"),
            rec.get("a_end_port"),
            rec.get("b_end"),
            rec.get("b_end_port"),
            rec.get("service_name"),
            self.adrs_scope_updated,
            row.label if hasattr(row, "label") else row["label"],
            row.connection_id if hasattr(row, "connection_id") else row["connection_id"],
            row.source if hasattr(row, "source") else row["source"],
            row.destination if hasattr(row, "destination") else row["destination"],
        )

        # return self.execute_update(query, values)
        success = self.execute_update(query, values)
        if success:
            logger.info(f"DB updated")
        else:
            logger.error(f"DB update failed")
        return success

    def insert_circuit_info_bulk(self, df, row):
        if df is None or df.empty:
            return 0
        required_cols = ["service_name", "a_end", "a_end_port", "b_end", "b_end_port"]
        # ✅ Validate columns
        for col in required_cols:
            if col not in df.columns:
                logger.error(f"Missing column {col} in insert_df")
                return 0

        records = []
        for idx, r in df.iterrows():
            try:
                # ✅ Skip bad rows
                if pd.isna(r["a_end"]) or pd.isna(r["b_end"]):
                    logger.warning(f"Skipping row due to NULL values at index {idx}")
                    continue

                records.append((
                    row["connection_id"],
                    row["label"],
                    row["source"],
                    row["destination"],
                    str(r["a_end"]).strip(),
                    str(r["a_end_port"]).strip(),
                    str(r["b_end"]).strip(),
                    str(r["b_end_port"]).strip(),
                    str(r["service_name"]).strip(),
                    self.adrs_scope_updated,
                ))
            except Exception as e:
                logger.error(f"Row conversion failed at index {idx}: {e}")
                continue
        # ✅ Nothing valid
        if not records:
            logger.warning("No valid records to insert")
            return 0
        # query = """
        #     INSERT INTO tjs_circuit_info
        #     (connection_id, label, source, destination,
        #      a_end, a_end_port, b_end, b_end_port)
        #     VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        # """
        query = """
        INSERT INTO tjs_circuit_info (
            connection_id, label, source, destination,
            a_end, a_end_port, b_end, b_end_port, service_name, status
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (label, connection_id, source, destination, a_end, a_end_port, b_end, b_end_port)
        DO UPDATE SET
        a_end = EXCLUDED.a_end,
        a_end_port = EXCLUDED.a_end_port,
        b_end = EXCLUDED.b_end,
        b_end_port = EXCLUDED.b_end_port,
        service_name = EXCLUDED.service_name,
        status = EXCLUDED.status
        """
        cursor = self.conn.cursor()
        raw_queries = [cursor.mogrify(query, record) for record in records]
        clean_queries = [q.decode("utf-8") for q in raw_queries]
        for q in clean_queries:
            print(q)
        try:
            cursor.executemany(query, records)
            self.conn.commit()

            logger.info(f"{len(records)} rows inserted successfully")
            return len(records)
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Bulk insert failed: {e}")
            return 0
        finally:
            cursor.close()

    def execute_update(self, query, values):
        try:
            with self.conn.cursor() as cursor:
                cursor.execute(query, values)
            self.conn.commit()
            return True
        except Exception as e:
            self.conn.rollback()
            print(f"DB Update Error: {e}")
            return False

    def commit(self):
        self.conn.commit()

    def close(self):
        if self.conn:
            self.conn.close()

    def get_circuit_adrs_data_tu_au(self):
        query = """
            SELECT connection_id,label,source,destination
            FROM public.tjs_circuit_info
            WHERE TRIM(status) = 'ADRS_SCOPE'
            and connection_id = 'Tejas Networks.' 
            and source like 'TU%'
            and destination like 'TU%'
        """
        adrs_df = pd.read_sql(query, self.conn)
        adrs_df.columns = adrs_df.columns.str.strip()

        return adrs_df

    def get_zone_by_node(self, node_name):
        query = f""" SELECT label, zone FROM public.tjs_xc_dump WHERE label = %s limit 1"""
        zone_df = pd.read_sql(query, self.conn, params=[node_name])
        zone_df.columns = zone_df.columns.str.strip()
        return zone_df
##-----------------------ADRS SCOPE Data Extraction Queries Here-----------------------##
    
    def get_circuit_summary_by_label(self, label):
        query = f"""
        SELECT
            COUNT(*) AS total_count,
            COUNT(*) FILTER (WHERE TRIM(status) = 'COMPLETED') AS completed_count,
            COUNT(*) FILTER (WHERE LOWER(TRIM(circuit_status)) = 'live') AS live_count,
            COUNT(*) FILTER (WHERE LOWER(TRIM(circuit_status)) = 'non-live') AS non_live_count,
            COUNT(*) FILTER (WHERE LOWER(TRIM(circuit_status)) = 'unmanaged') AS unmanaged_count,
            COUNT(*) FILTER (WHERE TRIM(circuit_status) = 'UME_Manual') AS ume_manual_count
        FROM public.tjs_circuit_info
        WHERE TRIM(label) = '{label}'
        """
        df = pd.read_sql(query, self.conn)
        # Clean column names
        df.columns = df.columns.str.strip()
        return df
    
    def update_adrs_scope_for_ume_vne_endpoints(self, label):
        try:
            query = """
            UPDATE public.tjs_circuit_info
            SET status = 'ADRS_SCOPE'
            WHERE TRIM(label) = %s
            AND (
                    LOWER(TRIM(a_end)) LIKE 'ume%%'
                    OR LOWER(TRIM(a_end)) LIKE 'vne%%'
                )
            OR (
                    LOWER(TRIM(b_end)) LIKE 'ume%%'
                    OR LOWER(TRIM(b_end)) LIKE 'vne%%'
                )
            """

            cursor = self.conn.cursor()
            cursor.execute(query, (label,))
            self.conn.commit()
            updated_count = cursor.rowcount
            logger.info(f"Rows updated to ADRS_SCOPE (UME/VNE both ends): {updated_count}")

            cursor.close()

        except Exception:
            self.conn.rollback()
            logger.exception(f"Error updating ADRS_SCOPE for label: {label}")
 
        
