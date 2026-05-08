import os
import re
import sys
import json
import uuid
import shutil
import base64
import hashlib
import multiprocessing

from tkinter import *
from PIL import Image, ImageTk
from cryptography.fernet import Fernet
from datetime import datetime, timedelta
from tkinter import filedialog, messagebox
from multiprocessing import Process, Queue


def debug_log(msg):
    try:
        with open("debug.log", "a") as f:
            f.write(f"{datetime.now()} | PID={os.getpid()} | {msg}\n")
    except:
        pass

debug_log(f"START | __name__={__name__} | frozen={getattr(sys,'frozen',False)}")

if getattr(sys, 'frozen', False):
    multiprocessing.set_executable(sys.executable)
    debug_log("Multiprocessing executable set")

def generate_machine_key():
    unique_id = str(uuid.getnode())  # MAC address
    hash_value = hashlib.sha256(unique_id.encode()).digest()
    return base64.urlsafe_b64encode(hash_value)

SECRET_KEY = generate_machine_key()
cipher = Fernet(SECRET_KEY)

def encrypt_data(data: str) -> str:
    return cipher.encrypt(data.encode()).decode()

def decrypt_data(data: str) -> str:
    return cipher.decrypt(data.encode()).decode()

# ================= SAFE PATH SETUP =================
def get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)   # IMPORTANT: not _MEIPASS
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

BASE_DIR = get_base_dir()

def run_pipeline_process(node_string, queue):
    debug_log(f"CHILD PROCESS ENTERED | nodes={node_string}")

    if __name__ != "__mp_main__":
        debug_log("Running in child process context")
    try:
        import sys, os, traceback

        def get_runtime_base():
            if getattr(sys, 'frozen', False):
                return os.path.dirname(sys.executable)
            return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

        base_dir = get_runtime_base()
        if getattr(sys, "frozen", False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

        sys.path.insert(0, base_dir)

        from project_pipeline import ProjectPipeline

        nodes = [n.strip() for n in node_string.split(",") if n.strip()]
        results = []

        for node in nodes:
            try:
                pipeline = ProjectPipeline(node)
                result = pipeline.m1_module(node)
                # result = "Node is done"
                results.append(f"{node}: {result}")

            except Exception:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))

                with open("mp_error.log", "a") as f:
                    f.write(tb_str + "\n\n")

                results.append(f"{node}: ERROR\n{tb_str}")
        debug_log("Sending result to queue")
        queue.put(("success", "\n\n".join(results)))

    except Exception:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))

        with open("mp_error.log", "a") as f:
            f.write(tb_str + "\n\n")

        queue.put(("error", tb_str))

def resource_path(*paths):
    """
    Works for both:
    - Running in IDE
    - PyInstaller (.exe)
    """
    if hasattr(sys, "_MEIPASS"):
        base = sys._MEIPASS  # PyInstaller temp folder
    else:
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    return os.path.join(base, *paths)

#img_path = os.path.join(BASE_DIR, "task_libs", "ui", "images")
img_path=BASE_DIR
# print(img_path)
def get_runtime_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)  # EXE folder
    return os.path.dirname(os.path.abspath(__file__))

RUNTIME_DIR = get_runtime_dir()

creds_file = os.path.join(RUNTIME_DIR, "creds.json")
attachments_dir = os.path.join(BASE_DIR,"attachments")

# def resource_path(relative_path):
#     if hasattr(sys, '_MEIPASS'):
#         return os.path.join(sys._MEIPASS, relative_path)
#     return os.path.join(BASE_DIR, relative_path)


# ============================================================
# =================== MAIN FORM CLASS ========================
# ============================================================

class NetworkCredentialsForm:

    def __init__(self, window, on_complete=None):
        self.window = window
        self.on_complete = on_complete

        self.window.title("Tejas Live/Non-Live Circuit Segregation")
        self.window.state("zoomed")
        self.window.configure(bg="#0b1a31")

        self.screen_w = self.window.winfo_screenwidth()
        self.screen_h = self.window.winfo_screenheight()

        # ================= BACKGROUND =================
        bg_img = Image.open(resource_path("ui", "images", "test_blue.png"))
        bg_img = bg_img.resize((self.screen_w, self.screen_h))
        self.bg_photo = ImageTk.PhotoImage(bg_img)

        self.canvas = Canvas(self.window, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_image(0, 0, image=self.bg_photo, anchor="nw")

        # ================= LOGOS =================
        left_logo = Image.open(resource_path("ui", "images", "tctslogo.png")).resize((260, 70))
        self.left_logo_photo = ImageTk.PhotoImage(left_logo)
        self.canvas.create_image(30, 20, image=self.left_logo_photo, anchor="nw")

        right_logo = Image.open(resource_path("ui", "images", "Tata-Group-Logo-White.png")).resize((60, 50))
        self.right_logo_photo = ImageTk.PhotoImage(right_logo)
        self.canvas.create_image(self.screen_w - 90, 25, image=self.right_logo_photo, anchor="nw")

        neo_img = Image.open(resource_path("ui", "images", "neu_automation.png")).resize((260, 85))
        self.neo_photo = ImageTk.PhotoImage(neo_img)
        self.canvas.create_image(self.screen_w // 2, 90, image=self.neo_photo, anchor="center")

        # ================= TITLE =================
        self.canvas.create_text(
            self.screen_w // 2,
            180,
            text="Web-Q Automation - Tejas Live/Non-Live Circuit Segregation",
            fill="white",
            font=("Segoe UI", 16, "bold"),
            anchor="center"
        )

        # ================= BACK BUTTON =================
        back_text = self.canvas.create_text(
            40,
            155,
            text="← Back",
            fill="#c6f7ff",
            font=("Segoe UI", 11, "bold"),
            anchor="w"
        )

        self.canvas.tag_bind(back_text, "<Enter>", lambda e: self.canvas.config(cursor="hand2"))
        self.canvas.tag_bind(back_text, "<Leave>", lambda e: self.canvas.config(cursor=""))
        self.canvas.tag_bind(back_text, "<Button-1>", lambda e: self.go_back())

        # ================= FOOTER =================
        current_year = datetime.now().year
        footer_text = f"© 2020 - {current_year} Tata Communications Transformation Services. All rights reserved."

        self.canvas.create_text(
            self.screen_w - 30,
            self.screen_h - 100,
            text=footer_text,
            fill="white",
            font=("Segoe UI", 9),
            anchor="se"
        )

        # ================= SETTINGS =================
        self.box_width = 380
        self.box_height = 34
        self.box_padding_x = 18
        self.box_padding_y = 6
        self.gap = 55
        self.left_x = (self.screen_w - self.box_width) // 2
        self.glass_bg = "#2f5373"

        eye_img = Image.open(resource_path("ui", "images","show.png")).resize((18, 18))
        self.eye_icon = ImageTk.PhotoImage(eye_img)

        # folder_img = Image.open(resource_path("task_libs", "ui", "images","folder.png")).resize((18, 18))
        # self.folder_icon = ImageTk.PhotoImage(folder_img)

        self.entries = {}
        self.borders = {}

        self.required_fields = {
            "OLM ID",
            "Tejas South Password",
            "Tejas North Password",
            "Tejas West Password",
        }

        y = 200
        self.create_field("OLM ID", y); y += self.gap
        self.create_password("Chitragupt Password", y); y += self.gap
        self.create_password("Tejas South Password", y); y += self.gap
        self.create_password("Tejas North Password", y); y += self.gap
        self.create_password("Tejas West Password", y); y += self.gap
        self.create_field("Node Name", y); y += self.gap

        Button(self.window, text="SUBMIT",
               font=("Segoe UI", 11, "bold"),
               fg="white", bg="#2d5fd3",
               bd=0, cursor="hand2",
               command=self.validate).place(
            x=self.screen_w // 2 - 130,
            y=y + 15, width=120, height=34)

        Button(self.window, text="RESET",
               font=("Segoe UI", 11, "bold"),
               fg="white", bg="#6c757d",
               bd=0, cursor="hand2",
               command=self.reset_fields).place(
            x=self.screen_w // 2 + 20,
            y=y + 15, width=120, height=34)

        self.load_from_json()

    # ================= ROUNDED RECT =================
    def rounded_rect(self, x1, y1, x2, y2, r=18, **kwargs):
        points = [
            x1+r,y1, x2-r,y1, x2,y1, x2,y1+r,
            x2,y2-r, x2,y2, x2-r,y2,
            x1+r,y2, x1,y2, x1,y2-r,
            x1,y1+r, x1,y1
        ]
        return self.canvas.create_polygon(points, smooth=True, **kwargs)

    # ================= OLM CLEAN INPUT =================
    def clean_olm_input(self, event):
        entry = self.entries["OLM ID"]

        value = entry.get()

        # ONLY letters and numbers (STRICT)
        cleaned = re.sub(r'[^A-Za-z0-9]', '', value)

        # Uppercase
        cleaned = cleaned.upper()

        if value != cleaned:
            entry.delete(0, "end")
            entry.insert(0, cleaned)

    # ================= NODE CLEAN INPUT =================
    def clean_node_input(self, event):
        entry = self.entries["Node Name"]

        value = entry.get()

        # Allow A-Z, 0-9, underscore, comma
        cleaned = re.sub(r'[^A-Za-z0-9_,]', '', value)

        cleaned = cleaned.upper()

        # Remove multiple commas
        cleaned = re.sub(r',+', ',', cleaned)

        if value != cleaned:
            entry.delete(0, "end")
            entry.insert(0, cleaned)
        
    # ================= FIELD CREATION =================
    def create_field(self, label, y):

        label_id = self.canvas.create_text(
            self.left_x, y,
            text=label,
            anchor="nw",
            fill="white",
            font=("Segoe UI", 10, "bold")
        )

        if label in self.required_fields:
            bbox = self.canvas.bbox(label_id)
            self.canvas.create_text(
                bbox[2] + 2, y,
                text="*",
                anchor="nw",
                fill="red",
                font=("Segoe UI", 12, "bold")
            )

        box_y = y + 18

        border = self.rounded_rect(
            self.left_x, box_y,
            self.left_x + self.box_width,
            box_y + self.box_height,
            r=18,
            fill=self.glass_bg,
            outline="#3b6b8f", width=1
        )

        entry_width = self.box_width - (self.box_padding_x * 2) - 4
        if label == "Node Name":
            entry_width -= 35
        
        entry = Entry(
            self.window,
            font=("Segoe UI", 11),
            bg=self.glass_bg,
            fg="white",
            bd=0,
            insertbackground="white",
            relief="flat"
        )
        entry.config(highlightthickness=0)

        entry_height = 22
        entry.place(
            x=self.left_x + self.box_padding_x,
            y=box_y + (self.box_height - entry_height) // 2,
            width=entry_width,
            height=entry_height
        )

        self.entries[label] = entry
        self.borders[label] = border

        # ================= APPLY VALIDATION =================
        if label == "OLM ID":
            entry.bind("<KeyRelease>", self.clean_olm_input)

        if label == "Node Name":
            entry.bind("<KeyRelease>", self.clean_node_input)

        # if label == "Node Name":
        #     Button(self.window,
        #            image=self.folder_icon,
        #            bg=self.glass_bg,
        #            bd=0,
        #            cursor="hand2",
        #            command=self.attach_file).place(
        #         x=self.left_x + self.box_width - 38,
        #         y=box_y + 7)

    def create_password(self, label, y):
        self.create_field(label, y)
        self.entries[label].config(show="*")

        box_y = y + 18

        Button(self.window,
               image=self.eye_icon,
               bg=self.glass_bg,
               bd=0,
               cursor="hand2",
               command=lambda e=self.entries[label]: self.toggle_password(e)
               ).place(
            x=self.left_x + self.box_width - 38,
            y=box_y + 7)

    def toggle_password(self, entry):
        entry.config(show="" if entry.cget("show") == "*" else "*")

    # ================= FILE ATTACH =================
    def attach_file(self):
        file_path = filedialog.askopenfilename()
        if not file_path:
            return

        if not os.path.exists(attachments_dir):
            os.makedirs(attachments_dir)

        destination = os.path.join(
            attachments_dir,
            os.path.basename(file_path)
        )

        shutil.copy(file_path, destination)

        self.entries["Node Name"].delete(0, END)
        self.entries["Node Name"].insert(0, destination)

    # ================= VALIDATION =================
    def validate(self):
        debug_log("VALIDATE CALLED")
        missing = []

        for label, entry in self.entries.items():

            # Skip optional field
            if label == "Chitragupt Password":
                continue

            value = entry.get().strip()

            if not value:
                missing.append(label)
                self.canvas.itemconfig(self.borders[label],
                                    outline="#ff4d4d", width=2)
            else:
                self.canvas.itemconfig(self.borders[label],
                                    outline="#3b6b8f", width=1)

        if missing:
            self.show_popup("Validation Error",
                            ["Please fill the following fields:"] + missing)
            return

        # ================= OLM ID VALIDATION =================
        olm_value = self.entries["OLM ID"].get().strip()

        if not re.match(r'^[A-Za-z0-9_]+$', olm_value):
            self.canvas.itemconfig(self.borders["OLM ID"],
                                outline="#ff4d4d", width=2)

            self.show_popup(
                "Validation Error",
                [
                    "Invalid OLM ID",
                    "Only letters, numbers are allowed",
                    "Example: USER123"
                ]
            )
            return
        else:
            self.canvas.itemconfig(self.borders["OLM ID"],
                                outline="#3b6b8f", width=1)

        # ================= NODE VALIDATION =================
        node_value = self.entries["Node Name"].get().strip()

        node_list = [n.strip() for n in node_value.split(",")]

        if not node_list or any(n == "" for n in node_list):
            messagebox.showerror(
                "Invalid Node Name",
                "Node Name must be comma-separated values.\n\n"
                "Example:\nNODE1,NODE2,NODE3"
            )
            self.canvas.itemconfig(self.borders["Node Name"],
                                outline="#ff4d4d", width=2)
            return

        # Normalize spacing
        cleaned_nodes = ",".join(node_list)
        self.entries["Node Name"].delete(0, END)
        self.entries["Node Name"].insert(0, cleaned_nodes)

        self.save_to_json()

        messagebox.showinfo(
            "Success ✔",
            "All required fields submitted successfully\n\n"
            "Automation is running in the background...\n"
            "This may take a few minutes.\n"
            "Please do not close the application."
        )

        self.after_submit(cleaned_nodes)

    # ================= SAVE JSON (ENCRYPTED) =================
    def save_to_json(self):

        encrypted_data = {}

        for label, entry in self.entries.items():
            value = entry.get().strip()
            if value:
                encrypted_data[label] = encrypt_data(value)

        data = {
            "timestamp": datetime.now().isoformat(),
            "data": encrypted_data
        }

        with open(creds_file, "w") as file:
            json.dump(data, file, indent=4)

    # ================= LOAD JSON =================
    def load_from_json(self):

        if not os.path.exists(creds_file):
            return

        try:
            with open(creds_file, "r") as file:
                content = json.load(file)

            if not content:
                return

            timestamp = datetime.fromisoformat(content.get("timestamp"))
            if datetime.now() >= timestamp + timedelta(hours=24):
                with open(creds_file, "w") as file:
                    json.dump({}, file)
                return

            saved_data = content.get("data", {})

            for label, entry in self.entries.items():
                if label == "Node Name":
                    continue

                encrypted_value = saved_data.get(label)
                if encrypted_value:
                    try:
                        decrypted_value = decrypt_data(encrypted_value)
                        entry.insert(0, decrypted_value)
                    except:
                        pass

        except Exception as e:
            print("Load error:", e)

    # ================= AUTOMATION FLOW =================
    def after_submit(self, node_name):
        # self.reset_fields()
        self.window.iconify()
        self.start_automation(node_name)

    # def start_automation(self, node_name):
    #     try:
    #         sys.path.append(os.path.abspath(os.path.join(BASE_DIR, "..")))
    #         from task_libs.project_pipeline import ProjectPipeline
    #         pipeline = ProjectPipeline(node_name)
    #         result = pipeline.M1_pipeline(node_name)
    #         # result = "UNKNOWN"
    #         self.window.after(0, self.on_automation_success, result)
    #     except Exception as e:
    #         self.window.after(0, self.on_automation_failure, str(e))

    def start_automation(self, node_name):
        debug_log(f"START_AUTOMATION called with nodes={node_name}")

        self.queue = Queue()

        self.process = Process(
            target=run_pipeline_process,
            args=(node_name, self.queue)
        )

        debug_log("Starting child process")
        self.process.start()
        debug_log(f"Child process started PID={self.process.pid}")

        self.check_process_result()

    def check_process_result(self):
        debug_log("Checking process result...")
        if not self.queue.empty():
            debug_log("Queue has data")
        if not self.queue.empty():
            status, message = self.queue.get()
        elif not self.process.is_alive():
            debug_log("Process died unexpectedly")

            # process died without sending data
            self.on_automation_failure("Process terminated unexpectedly. Check mp_error.log")
            return
        else:
            self.window.after(500, self.check_process_result)
            return

        # restore window
        self.window.deiconify()
        self.window.state("zoomed")
        self.window.lift()
        self.window.focus_force()

        if status == "success":
            self.on_automation_success(message)
        else:
            self.on_automation_failure(message)

    def on_automation_success(self, result):
        # Restore window
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()

        # Decide popup message
        if result is None or result == "" or isinstance(result, str) and result.lower() == "unknown":
            message = (
                "Automation Failed.\n\n"
                "Status: Unknown.\n"
                "Please verify the inputs."
            )
            msgflg = 0

        elif isinstance(result, str) and result.lower() == "success":
            message = (
                "Automation completed ✔\n\n"
                f"Results:\n{result}"
            )
            msgflg = 1
        elif isinstance(result, str) and result.endswith((".csv", ".xlsx")):
            message = (
                "Automation completed successfully ✔\n\n"
                f"Output file generated:\n{result}"
            )
            msgflg = 1
        else:
            message = (
                "Automation completed.\n\n"
                f"Result: {result}"
            )
            msgflg = 1

        if msgflg:
            messagebox.showinfo("Automation Success", message)
        else:
            messagebox.showerror("Automation Failed", message)

        if self.on_complete:
            self.on_complete(success=True)

    # def on_automation_failure(self, error):
    #     self.window.deiconify()
    #     self.window.lift()
    #     self.window.focus_force()
    #     messagebox.showerror("Automation Failed", error)
    def on_automation_failure(self, error_traceback):
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()

        # ------------------ Log the error ------------------
        from common_libs.logger import logger
        logger.error("Automation Failed:\n" + error_traceback)

        # ------------------ Show full traceback in the popup ------------------
        messagebox.showerror(
            "Automation Failed",
            f"An error occurred during automation:\n\n{error_traceback}"
        )
    def go_back(self):
        self.window.destroy()
        if self.on_complete:
            self.on_complete(success=False)

    def reset_fields(self):
        for label, entry in self.entries.items():
            entry.delete(0, END)
            self.canvas.itemconfig(self.borders[label],
                                   outline="#3b6b8f", width=1)

    def show_popup(self, title, lines, success=False):

        popup = Toplevel(self.window)
        popup.overrideredirect(True)
        popup.grab_set()

        width = 400
        height = 170 + len(lines) * 20

        x = (self.screen_w // 2) - (width // 2)
        y = (self.screen_h // 2) - (height // 2)

        popup.geometry(f"{width}x{height}+{x}+{y}")
        popup.configure(bg="#1e3d59")

        frame = Frame(
            popup,
            bg="#244a6a",
            highlightthickness=2,
            highlightbackground="#3e7db3"
        )
        frame.place(relwidth=1, relheight=1)

        Label(frame, text=title,
              font=("Segoe UI", 14, "bold"),
              bg="#244a6a", fg="white").pack(pady=(20, 8))

        msg = ""
        for line in lines:
            msg += f"• {line}\n"

        Label(frame, text=msg,
              font=("Segoe UI", 10),
              bg="#244a6a", fg="white",
              justify="center").pack()

        def close_popup():
            popup.destroy()
            if success:
                self.after_submit(self.entries["Node Name"].get().strip())

        Button(frame, text="OK",
               font=("Segoe UI", 10, "bold"),
               bg="#2d5fd3", fg="white",
               bd=0, width=10,
               command=close_popup).pack(pady=(15, 20))


# ================= MAIN =================
def main():
    debug_log(f"MAIN() STARTED | PID={os.getpid()}")

    if getattr(sys, 'frozen', False):
        import multiprocessing
        multiprocessing.set_executable(sys.executable)

    root = Tk()
    NetworkCredentialsForm(root)
    root.mainloop()

if __name__ == "__main__":
    main()
