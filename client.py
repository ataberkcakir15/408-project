"""
SUquid Quiz Games - Client Application (Phase 6)
CS408 Computer Networks Term Project

This module implements a TCP client with a Tkinter GUI.
Phase 6 adds disconnection handling - the client receives DISCONNECT| notifications
when other players leave, and properly resets UI on GAME_OVER to support multiple games.

Threading Model:
----------------
The GUI runs in the main thread via Tkinter's mainloop(). The socket.connect() and
socket.recv() calls are blocking - they wait until the operation completes. If we
ran these in the main thread, the entire GUI would freeze and become unresponsive.

Solution: We spawn a separate daemon thread to handle the connection and receiving.
This allows:
  - Main Thread: Handles all GUI events (button clicks, window updates, listbox logging)
  - Connection Thread: Handles blocking network operations independently

The daemon thread automatically terminates when the main window is closed.
"""

import socket
import threading
import tkinter as tk
from tkinter import messagebox


class QuizClient:
    """
    TCP Client class that manages socket connections and GUI interactions.
    """

    def __init__(self, root):
        """
        Initialize the client with GUI components.
        
        Args:
            root: The Tkinter root window
        """
        self.root = root
        self.root.title("SUquid Quiz Games - Client")
        self.root.geometry("550x550")
        self.root.resizable(True, True)
        
        # Client socket - will be initialized when Connect is clicked
        self.client_socket = None
        # Flag to track connection state
        self.is_connected = False
        
        # Phase 3: Variable to track selected answer (A, B, or C)
        self.selected_answer = tk.StringVar()
        
        # Build the GUI
        self._create_widgets()
    
    def _create_widgets(self):
        """
        Create and layout all GUI widgets.
        """
        # ===== Connection Configuration Frame =====
        config_frame = tk.Frame(self.root, padx=10, pady=10)
        config_frame.pack(fill=tk.X)
        
        # Server IP Label and Entry
        ip_label = tk.Label(config_frame, text="Server IP:")
        ip_label.pack(side=tk.LEFT)
        
        self.ip_entry = tk.Entry(config_frame, width=12)
        self.ip_entry.pack(side=tk.LEFT, padx=(5, 10))
        self.ip_entry.insert(0, "127.0.0.1")  # Default to localhost
        
        # Port Label and Entry
        port_label = tk.Label(config_frame, text="Port:")
        port_label.pack(side=tk.LEFT)
        
        self.port_entry = tk.Entry(config_frame, width=7)
        self.port_entry.pack(side=tk.LEFT, padx=(5, 10))
        self.port_entry.insert(0, "12345")  # Default port for convenience
        
        # Username Label and Entry (Phase 2)
        username_label = tk.Label(config_frame, text="Username:")
        username_label.pack(side=tk.LEFT)
        
        self.username_entry = tk.Entry(config_frame, width=12)
        self.username_entry.pack(side=tk.LEFT, padx=(5, 10))
        
        # Connect Button
        self.connect_button = tk.Button(
            config_frame, 
            text="Connect", 
            command=self._connect_to_server
        )
        self.connect_button.pack(side=tk.LEFT)
        
        # ===== Log Console Frame =====
        log_frame = tk.Frame(self.root, padx=10, pady=5)
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        # Log Label
        log_label = tk.Label(log_frame, text="Client Log:")
        log_label.pack(anchor=tk.W)
        
        # Scrollbar for the Listbox
        scrollbar = tk.Scrollbar(log_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Listbox for logging client activities
        self.log_listbox = tk.Listbox(
            log_frame, 
            height=10, 
            width=60,
            yscrollcommand=scrollbar.set
        )
        self.log_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Link scrollbar to listbox
        scrollbar.config(command=self.log_listbox.yview)
        
        # ===== Game Area Frame (Phase 3) =====
        self.game_frame = tk.LabelFrame(self.root, text="Game Area", padx=10, pady=10)
        self.game_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Question Label (large font)
        self.question_label = tk.Label(
            self.game_frame,
            text="Waiting for game to start...",
            font=("Arial", 12, "bold"),
            wraplength=500,
            justify=tk.LEFT
        )
        self.question_label.pack(anchor=tk.W, pady=(0, 10))
        
        # Options Frame for Radiobuttons
        options_frame = tk.Frame(self.game_frame)
        options_frame.pack(anchor=tk.W, fill=tk.X)
        
        # Option A Radiobutton
        self.option_a_radio = tk.Radiobutton(
            options_frame,
            text="A) Option A",
            variable=self.selected_answer,
            value="A",
            font=("Arial", 10),
            state=tk.DISABLED
        )
        self.option_a_radio.pack(anchor=tk.W, pady=2)
        
        # Option B Radiobutton
        self.option_b_radio = tk.Radiobutton(
            options_frame,
            text="B) Option B",
            variable=self.selected_answer,
            value="B",
            font=("Arial", 10),
            state=tk.DISABLED
        )
        self.option_b_radio.pack(anchor=tk.W, pady=2)
        
        # Option C Radiobutton
        self.option_c_radio = tk.Radiobutton(
            options_frame,
            text="C) Option C",
            variable=self.selected_answer,
            value="C",
            font=("Arial", 10),
            state=tk.DISABLED
        )
        self.option_c_radio.pack(anchor=tk.W, pady=2)
        
        # Submit Answer Button
        self.submit_button = tk.Button(
            self.game_frame,
            text="Submit Answer",
            command=self._submit_answer,
            state=tk.DISABLED
        )
        self.submit_button.pack(anchor=tk.W, pady=(10, 0))
        
        # Handle window close event
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
    
    def _log(self, message):
        """
        Add a message to the log listbox.
        Thread-safe: Can be called from any thread.
        
        Args:
            message: The string message to log
        """
        # Use 'after' to schedule the update on the main thread
        # This ensures thread-safety when logging from the connection thread
        self.root.after(0, lambda: self._append_log(message))
    
    def _append_log(self, message):
        """
        Actually append the message to the listbox.
        Must be called from the main thread.
        
        Args:
            message: The string message to append
        """
        self.log_listbox.insert(tk.END, message)
        # Auto-scroll to the latest message
        self.log_listbox.see(tk.END)
    
    def _show_error(self, title, message):
        """
        Show an error messagebox.
        Thread-safe: Can be called from any thread.
        
        Args:
            title: The title of the error dialog
            message: The error message to display
        """
        # Use 'after' to schedule the messagebox on the main thread
        self.root.after(0, lambda: messagebox.showerror(title, message))
    
    def _validate_ip(self, ip_string):
        """
        Validate the IP address format.
        
        Args:
            ip_string: The IP address string to validate
            
        Returns:
            bool: True if valid, False otherwise
        """
        # Basic validation - check for proper IPv4 format
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
        """
        Enable the game area widgets when the game starts.
        Must be called from the main thread (use root.after() from other threads).
        """
        self.option_a_radio.config(state=tk.NORMAL)
        self.option_b_radio.config(state=tk.NORMAL)
        self.option_c_radio.config(state=tk.NORMAL)
        self.submit_button.config(state=tk.NORMAL)
        self.question_label.config(text="Get ready! First question coming...")
        # Clear any previous selection
        self.selected_answer.set("")
    
    def _disable_game_area(self):
        """
        Disable the game area widgets and reset to initial state.
        Called after disconnection or game over.
        
        Phase 6: Full reset ensures client is ready for a new GAME_START
        if the server starts another game.
        
        Must be called from the main thread.
        """
        self.option_a_radio.config(state=tk.DISABLED)
        self.option_b_radio.config(state=tk.DISABLED)
        self.option_c_radio.config(state=tk.DISABLED)
        self.submit_button.config(state=tk.DISABLED)
        self.question_label.config(text="Waiting for game to start...")
        # Reset option texts
        self.option_a_radio.config(text="A) Option A")
        self.option_b_radio.config(text="B) Option B")
        self.option_c_radio.config(text="C) Option C")
        self.selected_answer.set("")
    
    def _update_question_ui(self, question, opt_a, opt_b, opt_c):
        """
        Update the game area with a new question and options.
        Must be called from the main thread.
        
        Args:
            question: The question text
            opt_a: Option A text
            opt_b: Option B text
            opt_c: Option C text
        """
        self.question_label.config(text=question)
        self.option_a_radio.config(text=f"A) {opt_a}", state=tk.NORMAL)
        self.option_b_radio.config(text=f"B) {opt_b}", state=tk.NORMAL)
        self.option_c_radio.config(text=f"C) {opt_c}", state=tk.NORMAL)
        self.submit_button.config(state=tk.NORMAL)
        # Clear any previous selection
        self.selected_answer.set("")
    
    def _disable_answer_ui(self):
        """
        Disable game controls after submitting an answer.
        Shows waiting message while other players answer.
        Must be called from the main thread.
        """
        self.option_a_radio.config(state=tk.DISABLED)
        self.option_b_radio.config(state=tk.DISABLED)
        self.option_c_radio.config(state=tk.DISABLED)
        self.submit_button.config(state=tk.DISABLED)
        self.question_label.config(text="Waiting for other players...")
    
    def _submit_answer(self):
        """
        Handle the Submit Answer button click.
        Sends the selected answer to the server and disables UI while waiting.
        """
        answer = self.selected_answer.get()
        
        if not answer:
            messagebox.showwarning("No Selection", "Please select an answer before submitting.")
            return
        
        # Send answer to server
        try:
            answer_message = f"ANS:{answer}"
            self.client_socket.send(answer_message.encode('utf-8'))
            self._log(f"Sent answer: {answer}")
        except socket.error as e:
            self._log(f"Error sending answer: {e}")
            return
        
        # Disable UI while waiting for other players (barrier synchronization)
        self._disable_answer_ui()
    
    def _connect_to_server(self):
        """
        Initiate connection to the server.
        Called when the 'Connect' button is clicked.
        """
        # Get the IP, port, and username from entry fields
        ip_str = self.ip_entry.get().strip()
        port_str = self.port_entry.get().strip()
        username = self.username_entry.get().strip()
        
        # Validate IP address
        if not self._validate_ip(ip_str):
            messagebox.showerror("Invalid IP", "Please enter a valid IP address (e.g., 127.0.0.1).")
            return
        
        # Validate port number
        try:
            port = int(port_str)
            if port < 1 or port > 65535:
                raise ValueError("Port out of range")
        except ValueError:
            messagebox.showerror("Invalid Port", "Please enter a valid port number (1-65535).")
            return
        
        # Validate username (Phase 2)
        if not username:
            messagebox.showerror("Invalid Username", "Please enter a username.")
            return
        
        # Disable the connect button and entry fields during connection
        self.connect_button.config(state=tk.DISABLED)
        self.ip_entry.config(state=tk.DISABLED)
        self.port_entry.config(state=tk.DISABLED)
        self.username_entry.config(state=tk.DISABLED)
        
        self._log(f"Connecting to {ip_str}:{port} as '{username}'...")
        
        # Start the connection thread
        # IMPORTANT: This is where threading prevents GUI freezing!
        # The connect() and recv() calls in _handle_connection() are blocking.
        # By running them in a separate thread, the main thread remains free
        # to handle GUI events (window movement, resizing, etc.)
        connection_thread = threading.Thread(
            target=self._handle_connection, 
            args=(ip_str, port, username),
            daemon=True
        )
        connection_thread.start()
    
    def _handle_connection(self, ip, port, username):
        """
        Handle the connection to the server, authenticate, and receive messages.
        
        This method runs in a separate thread because socket.connect() and
        socket.recv() are BLOCKING. If this ran in the main thread, the GUI
        would freeze completely during the connection attempt and while waiting
        for data. The Tkinter mainloop() wouldn't be able to process any events,
        making the window unresponsive (can't move, resize, or close the window).
        
        By running this in a daemon thread:
        1. The main thread continues running mainloop(), keeping the GUI responsive
        2. This thread independently handles the network operations
        3. When data is received or connection ends, we log to the GUI
        4. The daemon=True flag ensures this thread dies when the main window closes
        
        Args:
            ip: The server IP address
            port: The server port number
            username: The username to authenticate with
        """
        try:
            # Create the TCP socket
            # AF_INET = IPv4, SOCK_STREAM = TCP
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            
            # connect() BLOCKS here until connection is established or fails
            # This is one of the reasons we need a separate thread!
            self.client_socket.connect((ip, port))
            
            self._log(f"Connected to server at {ip}:{port}")
            
            # ===== Phase 2: Authentication Handshake =====
            # Send the username to the server immediately after connecting
            self._log(f"Sending username: '{username}'")
            self.client_socket.send(username.encode('utf-8'))
            
            # Wait for the server's authentication response
            # recv() BLOCKS here until data is received
            auth_response = self.client_socket.recv(1024).decode('utf-8')
            
            if auth_response == "REJECT":
                # Username was rejected (duplicate)
                self._log("Connection rejected: Username taken.")
                self._show_error("Authentication Failed", "Username is already taken. Please choose a different username.")
                # Close and exit - don't enter the main loop
                return
            
            elif auth_response == "OK":
                # Username accepted - successfully authenticated
                self._log("Successfully connected to the lobby.")
                self.is_connected = True
            
            else:
                # Unexpected response
                self._log(f"Unexpected server response: {auth_response}")
                return
            
            # ===== Main Message Loop =====
            # Receive data from the server (game messages)
            # recv() BLOCKS here until data is received or connection is closed
            # This is another reason we need a separate thread!
            while self.is_connected:
                data = self.client_socket.recv(1024)
                
                if data:
                    # Decode the received bytes to string
                    message = data.decode('utf-8')
                    
                    # ===== Phase 3: Handle GAME_START signal =====
                    if message == "GAME_START":
                        self._log("Game is starting!")
                        # Enable the game area on the main thread
                        self.root.after(0, self._enable_game_area)
                    
                    # ===== Phase 4: Handle QUES| question messages =====
                    elif message.startswith("QUES|"):
                        # Parse: QUES|Question|OptA|OptB|OptC
                        parts = message.split("|")
                        if len(parts) >= 5:
                            question = parts[1]
                            opt_a = parts[2]
                            opt_b = parts[3]
                            opt_c = parts[4]
                            
                            self._log(f"Question: {question}")
                            # Update UI on main thread (using lambda with default args to capture values)
                            self.root.after(0, lambda q=question, a=opt_a, b=opt_b, c=opt_c: 
                                           self._update_question_ui(q, a, b, c))
                        else:
                            self._log(f"Invalid question format: {message}")
                    
                    # ===== Phase 5: Handle SCORE| feedback messages =====
                    elif message.startswith("SCORE|"):
                        # Parse: SCORE|Result|PointsEarned|TotalScore|Scoreboard
                        parts = message.split("|")
                        if len(parts) >= 5:
                            result = parts[1]           # "Correct" or "Wrong"
                            points_earned = parts[2]    # Points this round
                            total_score = parts[3]      # Total score
                            scoreboard = parts[4]       # "1-Alice-10\n2-Bob-5..."
                            
                            # Display round results in log
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
                    
                    # ===== Phase 6: Handle DISCONNECT| notification =====
                    elif message.startswith("DISCONNECT|"):
                        # Parse: DISCONNECT|username
                        parts = message.split("|")
                        if len(parts) >= 2:
                            disconnected_user = parts[1]
                            self._log(f"Player '{disconnected_user}' has disconnected.")
                    
                    # ===== Phase 6: Handle GAME_OVER signal =====
                    elif message == "GAME_OVER":
                        self._log("=" * 30)
                        self._log("GAME OVER!")
                        self._log("=" * 30)
                        self._log("Waiting for next game...")
                        # Full UI reset on main thread - ready for new GAME_START
                        self.root.after(0, self._disable_game_area)
                    
                    else:
                        # Log other messages
                        self._log(f"Received: {message}")
                else:
                    # Empty data means the server closed the connection
                    # This is the graceful disconnect detection
                    self._log("Server closed the connection")
                    break
            
        except socket.error as e:
            self._log(f"Connection error: {e}")
        
        finally:
            # Cleanup: close socket and update state
            self.is_connected = False
            if self.client_socket:
                try:
                    self.client_socket.close()
                except socket.error:
                    pass
            
            self._log("Disconnected from server")
            self._log("-" * 40)  # Visual separator
            
            # Re-enable the connect button and entry fields on the main thread
            self.root.after(0, self._reset_ui)
    
    def _reset_ui(self):
        """
        Reset the UI elements after disconnection.
        Must be called from the main thread.
        """
        self.connect_button.config(state=tk.NORMAL)
        self.ip_entry.config(state=tk.NORMAL)
        self.port_entry.config(state=tk.NORMAL)
        self.username_entry.config(state=tk.NORMAL)
        # Phase 3: Also reset game area
        self._disable_game_area()
    
    def _on_closing(self):
        """
        Handle the window close event.
        Properly cleanup the socket before destroying the window.
        
        Phase 6: Graceful exit - closing the socket sends TCP FIN to the server,
        allowing immediate detection of client disconnection.
        """
        self.is_connected = False
        
        if self.client_socket:
            try:
                # socket.close() sends TCP FIN to server for clean disconnection
                self.client_socket.close()
            except socket.error:
                pass  # Ignore errors during cleanup
        
        self.root.destroy()


def main():
    """
    Application entry point.
    Creates the Tkinter root window and starts the client application.
    """
    root = tk.Tk()
    app = QuizClient(root)
    
    # Start the Tkinter main event loop
    # This runs in the main thread and handles all GUI events
    root.mainloop()


if __name__ == "__main__":
    main()
