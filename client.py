import socket
import threading
import tkinter as tk
from tkinter import messagebox


class QuizClient:
    def __init__(self, root):
        self.root = root
        self.root.title("SUquid Quiz Games - Client")
        self.root.geometry("550x550")
        self.root.resizable(True, True)
        self.client_socket = None
        self.is_connected = False
        self.selected_answer = tk.StringVar()
        self._create_widgets()
    
    def _create_widgets(self):
        config_frame = tk.Frame(self.root, padx=10, pady=10)
        config_frame.pack(fill=tk.X)
        ip_label = tk.Label(config_frame, text="Server IP:")
        ip_label.pack(side=tk.LEFT)
        self.ip_entry = tk.Entry(config_frame, width=12)
        self.ip_entry.pack(side=tk.LEFT, padx=(5, 10))
        self.ip_entry.insert(0, "127.0.0.1")
        port_label = tk.Label(config_frame, text="Port:")
        port_label.pack(side=tk.LEFT)
        self.port_entry = tk.Entry(config_frame, width=7)
        self.port_entry.pack(side=tk.LEFT, padx=(5, 10))
        self.port_entry.insert(0, "12345")
        username_label = tk.Label(config_frame, text="Username:")
        username_label.pack(side=tk.LEFT)
        self.username_entry = tk.Entry(config_frame, width=12)
        self.username_entry.pack(side=tk.LEFT, padx=(5, 10))
        self.connect_button = tk.Button(
            config_frame, 
            text="Connect", 
            command=self._connect_to_server
        )
        self.connect_button.pack(side=tk.LEFT)
        log_frame = tk.Frame(self.root, padx=10, pady=5)
        log_frame.pack(fill=tk.BOTH, expand=True)
        log_label = tk.Label(log_frame, text="Client Log:")
        log_label.pack(anchor=tk.W)
        scrollbar = tk.Scrollbar(log_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_listbox = tk.Listbox(
            log_frame, 
            height=10, 
            width=60,
            yscrollcommand=scrollbar.set
        )
        self.log_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.log_listbox.yview)
        self.game_frame = tk.LabelFrame(self.root, text="Game Area", padx=10, pady=10)
        self.game_frame.pack(fill=tk.X, padx=10, pady=10)
        self.question_label = tk.Label(
            self.game_frame,
            text="Waiting for game to start...",
            font=("Arial", 12, "bold"),
            wraplength=500,
            justify=tk.LEFT
        )
        self.question_label.pack(anchor=tk.W, pady=(0, 10))
        options_frame = tk.Frame(self.game_frame)
        options_frame.pack(anchor=tk.W, fill=tk.X)
        self.option_a_radio = tk.Radiobutton(
            options_frame,
            text="A) Option A",
            variable=self.selected_answer,
            value="A",
            font=("Arial", 10),
            state=tk.DISABLED
        )
        self.option_a_radio.pack(anchor=tk.W, pady=2)
        self.option_b_radio = tk.Radiobutton(
            options_frame,
            text="B) Option B",
            variable=self.selected_answer,
            value="B",
            font=("Arial", 10),
            state=tk.DISABLED
        )
        self.option_b_radio.pack(anchor=tk.W, pady=2)
        self.option_c_radio = tk.Radiobutton(
            options_frame,
            text="C) Option C",
            variable=self.selected_answer,
            value="C",
            font=("Arial", 10),
            state=tk.DISABLED
        )
        self.option_c_radio.pack(anchor=tk.W, pady=2)
        self.submit_button = tk.Button(
            self.game_frame,
            text="Submit Answer",
            command=self._submit_answer,
            state=tk.DISABLED
        )
        self.submit_button.pack(anchor=tk.W, pady=(10, 0))
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
    
    def _log(self, message):
        self.root.after(0, lambda: self._append_log(message))
    
    def _append_log(self, message):
        self.log_listbox.insert(tk.END, message)
        self.log_listbox.see(tk.END)
    
    def _show_error(self, title, message):
        self.root.after(0, lambda: messagebox.showerror(title, message))
    
    def _validate_ip(self, ip_string):
        parts = ip_string.split('.')
        if len(parts) != 4:
            return False
        
        for part in parts:
            try:
                num = int(part)
                if num < 0 or num > 255:
                    return False
            except ValueError:
                return False
        
        return True
    
    def _enable_game_area(self):
        self.option_a_radio.config(state=tk.NORMAL)
        self.option_b_radio.config(state=tk.NORMAL)
        self.option_c_radio.config(state=tk.NORMAL)
        self.submit_button.config(state=tk.NORMAL)
        self.question_label.config(text="Get ready! First question coming...")
        self.selected_answer.set("")
    
    def _disable_game_area(self):
        self.option_a_radio.config(state=tk.DISABLED)
        self.option_b_radio.config(state=tk.DISABLED)
        self.option_c_radio.config(state=tk.DISABLED)
        self.submit_button.config(state=tk.DISABLED)
        self.question_label.config(text="Waiting for game to start...")
        self.option_a_radio.config(text="A) Option A")
        self.option_b_radio.config(text="B) Option B")
        self.option_c_radio.config(text="C) Option C")
        self.selected_answer.set("")
    
    def _update_question_ui(self, question, opt_a, opt_b, opt_c):
        self.question_label.config(text=question)
        self.option_a_radio.config(text=f"A) {opt_a}", state=tk.NORMAL)
        self.option_b_radio.config(text=f"B) {opt_b}", state=tk.NORMAL)
        self.option_c_radio.config(text=f"C) {opt_c}", state=tk.NORMAL)
        self.submit_button.config(state=tk.NORMAL)
        self.selected_answer.set("")
    
    def _disable_answer_ui(self):
        self.option_a_radio.config(state=tk.DISABLED)
        self.option_b_radio.config(state=tk.DISABLED)
        self.option_c_radio.config(state=tk.DISABLED)
        self.submit_button.config(state=tk.DISABLED)
        self.question_label.config(text="Waiting for other players...")
    
    def _submit_answer(self):
        answer = self.selected_answer.get()
        if not answer:
            messagebox.showwarning("No Selection", "Please select an answer before submitting.")
            return
        try:
            answer_message = f"ANS:{answer}"
            self.client_socket.send(answer_message.encode('utf-8'))
            self._log(f"Sent answer: {answer}")
        except socket.error as e:
            self._log(f"Error sending answer: {e}")
            return
        self._disable_answer_ui()
    
    def _connect_to_server(self):
        ip_str = self.ip_entry.get().strip()
        port_str = self.port_entry.get().strip()
        username = self.username_entry.get().strip()
        if not self._validate_ip(ip_str):
            messagebox.showerror("Invalid IP", "Please enter a valid IP address (e.g., 127.0.0.1).")
            return
        try:
            port = int(port_str)
            if port < 1 or port > 65535:
                raise ValueError("Port out of range")
        except ValueError:
            messagebox.showerror("Invalid Port", "Please enter a valid port number (1-65535).")
            return
        if not username:
            messagebox.showerror("Invalid Username", "Please enter a username.")
            return
        self.connect_button.config(state=tk.DISABLED)
        self.ip_entry.config(state=tk.DISABLED)
        self.port_entry.config(state=tk.DISABLED)
        self.username_entry.config(state=tk.DISABLED)
        self._log(f"Connecting to {ip_str}:{port} as '{username}'...")
        connection_thread = threading.Thread(
            target=self._handle_connection, 
            args=(ip_str, port, username),
            daemon=True
        )
        connection_thread.start()
    
    def _handle_connection(self, ip, port, username):
        try:
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.connect((ip, port))
            self._log(f"Connected to server at {ip}:{port}")
            self._log(f"Sending username: '{username}'")
            self.client_socket.send(username.encode('utf-8'))
            auth_response = self.client_socket.recv(1024).decode('utf-8')
            if auth_response == "REJECT":
                self._log("Connection rejected: Username taken.")
                self._show_error("Authentication Failed", "Username is already taken. Please choose a different username.")
                return
            elif auth_response == "OK":
                self._log("Successfully connected to the lobby.")
                self.is_connected = True
            else:
                self._log(f"Unexpected server response: {auth_response}")
                return
            while self.is_connected:
                data = self.client_socket.recv(1024)
                if data:
                    message = data.decode('utf-8')
                    if message == "GAME_START":
                        self._log("Game is starting!")
                        self.root.after(0, self._enable_game_area)
                    elif message.startswith("QUES|"):
                        parts = message.split("|")
                        if len(parts) >= 5:
                            question = parts[1]
                            opt_a = parts[2]
                            opt_b = parts[3]
                            opt_c = parts[4]
                            self._log(f"Question: {question}")
                            self.root.after(0, lambda q=question, a=opt_a, b=opt_b, c=opt_c: 
                                           self._update_question_ui(q, a, b, c))
                        else:
                            self._log(f"Invalid question format: {message}")
                    elif message.startswith("SCORE|"):
                        parts = message.split("|")
                        if len(parts) >= 5:
                            result = parts[1]
                            points_earned = parts[2]
                            total_score = parts[3]
                            scoreboard = parts[4]
                            self._log("=" * 30)
                            self._log(f"You answered: {result}")
                            self._log(f"Points earned: +{points_earned}")
                            self._log(f"Your total score: {total_score}")
                            self._log("--- Current Standings ---")
                            for line in scoreboard.split("\n"):
                                self._log(f"  {line}")
                            self._log("=" * 30)
                        else:
                            self._log(f"Invalid score format: {message}")
                    elif message.startswith("DISCONNECT|"):
                        parts = message.split("|")
                        if len(parts) >= 2:
                            disconnected_user = parts[1]
                            self._log(f"Player '{disconnected_user}' has disconnected.")
                    elif message == "GAME_OVER":
                        self._log("=" * 30)
                        self._log("GAME OVER!")
                        self._log("=" * 30)
                        self._log("Waiting for next game...")
                        self.root.after(0, self._disable_game_area)
                    else:
                        self._log(f"Received: {message}")
                else:
                    self._log("Server closed the connection")
                    break
            
        except socket.error as e:
            self._log(f"Connection error: {e}")
        
        finally:
            self.is_connected = False
            if self.client_socket:
                try:
                    self.client_socket.close()
                except socket.error:
                    pass
            self._log("Disconnected from server")
            self._log("-" * 40)
            self.root.after(0, self._reset_ui)
    
    def _reset_ui(self):
        self.connect_button.config(state=tk.NORMAL)
        self.ip_entry.config(state=tk.NORMAL)
        self.port_entry.config(state=tk.NORMAL)
        self.username_entry.config(state=tk.NORMAL)
        self._disable_game_area()
    
    def _on_closing(self):
        self.is_connected = False
        if self.client_socket:
            try:
                self.client_socket.close()
            except socket.error:
                pass
        self.root.destroy()


def main():
    root = tk.Tk()
    app = QuizClient(root)
    root.mainloop()


if __name__ == "__main__":
    main()
