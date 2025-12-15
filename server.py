"""
SUquid Quiz Games - Server Application (Phase 6)
CS408 Computer Networks Term Project

This module implements a TCP server with a Tkinter GUI.
Phase 6 adds robust disconnection handling - gracefully handles player dropouts
during active games, maintains barrier synchronization, broadcasts disconnect
notifications, and properly resets state for new games.

Threading Model:
----------------
The GUI runs in the main thread via Tkinter's mainloop(). The socket.accept() call
is blocking - it waits indefinitely until a client connects. If we ran accept() in
the main thread, the entire GUI would freeze and become unresponsive.

Solution: We spawn a separate daemon thread to handle the listening loop. This allows:
  - Main Thread: Handles all GUI events (button clicks, window updates, listbox logging)
  - Listener Thread: Runs the blocking accept() loop independently
  - Client Handler Threads: Each connected client gets its own thread for communication

The daemon threads automatically terminate when the main window is closed.
"""

import socket
import threading
import tkinter as tk
from tkinter import messagebox, filedialog


class QuizServer:
    """
    TCP Server class that manages socket connections and GUI interactions.
    """

    def __init__(self, root):
        """
        Initialize the server with GUI components.
        
        Args:
            root: The Tkinter root window
        """
        self.root = root
        self.root.title("SUquid Quiz Games - Server")
        self.root.geometry("550x500")
        self.root.resizable(True, True)
        
        # Server socket - will be initialized when Start Server is clicked
        self.server_socket = None
        # Flag to control the listener thread
        self.is_running = False
        
        # Phase 2: Track connected clients by username
        # Using a dictionary: {username: client_socket}
        self.connected_clients = {}
        # Lock for thread-safe access to connected_clients and game state
        self.clients_lock = threading.Lock()
        
        # Phase 3: Questions storage
        self.questions = []  # List of question dictionaries
        
        # Phase 4: Game state variables
        self.current_question_index = 0      # Index of current question being played
        self.current_answers = {}            # {username: answer} for current question
        self.game_in_progress = False        # Flag to track if game is active
        self.num_questions_to_play = 0       # Number of questions for this game session
        
        # Phase 5: Scoring variables (initialized in _start_game)
        self.player_scores = {}              # {username: score}
        self.answer_arrival_order = []       # Track order of answers for speed bonus
        
        # Build the GUI
        self._create_widgets()
    
    def _create_widgets(self):
        """
        Create and layout all GUI widgets.
        """
        # ===== Port Configuration Frame =====
        config_frame = tk.Frame(self.root, padx=10, pady=10)
        config_frame.pack(fill=tk.X)
        
        # Port Label
        port_label = tk.Label(config_frame, text="Port Number:")
        port_label.pack(side=tk.LEFT)
        
        # Port Entry Field
        self.port_entry = tk.Entry(config_frame, width=10)
        self.port_entry.pack(side=tk.LEFT, padx=(5, 10))
        self.port_entry.insert(0, "12345")  # Default port for convenience
        
        # Start Server Button
        self.start_button = tk.Button(
            config_frame, 
            text="Start Server", 
            command=self._start_server
        )
        self.start_button.pack(side=tk.LEFT)
        
        # ===== Game Controls Frame (Phase 3) =====
        game_frame = tk.Frame(self.root, padx=10, pady=5)
        game_frame.pack(fill=tk.X)
        
        # Load Questions Button
        self.load_questions_button = tk.Button(
            game_frame,
            text="Load Questions File",
            command=self._load_questions
        )
        self.load_questions_button.pack(side=tk.LEFT)
        
        # Number of Questions Label and Entry
        num_questions_label = tk.Label(game_frame, text="# Questions:")
        num_questions_label.pack(side=tk.LEFT, padx=(15, 0))
        
        self.num_questions_entry = tk.Entry(game_frame, width=5)
        self.num_questions_entry.pack(side=tk.LEFT, padx=(5, 15))
        self.num_questions_entry.insert(0, "5")  # Default number of questions
        
        # Start Game Button (initially disabled)
        self.start_game_button = tk.Button(
            game_frame,
            text="Start Game",
            command=self._start_game,
            state=tk.DISABLED
        )
        self.start_game_button.pack(side=tk.LEFT)
        
        # ===== Log Console Frame =====
        log_frame = tk.Frame(self.root, padx=10, pady=10)
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        # Log Label
        log_label = tk.Label(log_frame, text="Server Log:")
        log_label.pack(anchor=tk.W)
        
        # Scrollbar for the Listbox
        scrollbar = tk.Scrollbar(log_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Listbox for logging server activities
        self.log_listbox = tk.Listbox(
            log_frame, 
            height=15, 
            width=60,
            yscrollcommand=scrollbar.set
        )
        self.log_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Link scrollbar to listbox
        scrollbar.config(command=self.log_listbox.yview)
        
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
        # This ensures thread-safety when logging from the listener thread
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
    
    def _load_questions(self):
        """
        Load questions from a text file.
        
        File format: 5 lines per question block
          Line 1: Question text
          Line 2: Option A
          Line 3: Option B
          Line 4: Option C
          Line 5: Correct answer (A, B, or C)
        
        Questions are stored as list of dictionaries:
          [{'q': question, 'options': [A, B, C], 'ans': answer}, ...]
        """
        # Open file dialog to select the questions file
        file_path = filedialog.askopenfilename(
            title="Select Questions File",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        
        if not file_path:
            # User cancelled the dialog
            return
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f.readlines() if line.strip()]
            
            # Parse questions in 5-line blocks
            self.questions = []
            
            if len(lines) % 5 != 0:
                messagebox.showwarning(
                    "Invalid Format",
                    "File format error: Number of lines is not a multiple of 5.\n"
                    "Each question should have 5 lines:\n"
                    "Question, Option A, Option B, Option C, Answer"
                )
                return
            
            for i in range(0, len(lines), 5):
                question_dict = {
                    'q': lines[i],           # Question text
                    'options': [
                        lines[i + 1],        # Option A
                        lines[i + 2],        # Option B
                        lines[i + 3]         # Option C
                    ],
                    'ans': lines[i + 4].upper()  # Correct answer (A, B, or C)
                }
                self.questions.append(question_dict)
            
            self._log(f"Loaded {len(self.questions)} questions from file")
            
            # Update the default number of questions in the entry
            self.num_questions_entry.delete(0, tk.END)
            self.num_questions_entry.insert(0, str(len(self.questions)))
            
            # Check if we can enable the Start Game button
            self._check_start_conditions()
            
        except Exception as e:
            self._log(f"Error loading questions: {e}")
            messagebox.showerror("Error", f"Failed to load questions file:\n{e}")
    
    def _check_start_conditions(self):
        """
        Check if conditions are met to enable the Start Game button.
        
        Conditions:
        1. Questions are loaded (len(self.questions) > 0)
        2. At least 2 clients are connected
        3. Game is not already in progress
        
        This method is called:
        - After loading questions
        - When a client connects or disconnects
        """
        # Must be called from main thread or use after()
        def update_button():
            with self.clients_lock:
                num_clients = len(self.connected_clients)
            
            questions_loaded = len(self.questions) > 0
            enough_clients = num_clients >= 2
            game_not_running = not self.game_in_progress
            
            if questions_loaded and enough_clients and game_not_running:
                self.start_game_button.config(state=tk.NORMAL)
            else:
                self.start_game_button.config(state=tk.DISABLED)
        
        # Schedule the update on the main thread
        self.root.after(0, update_button)
    
    def _start_game(self):
        """
        Start the game by broadcasting GAME_START to all connected clients,
        then send the first question.
        
        Validates:
        - At least 2 clients connected
        - Questions are loaded
        - Number of questions is valid
        """
        # Validate number of questions
        try:
            num_questions = int(self.num_questions_entry.get().strip())
            if num_questions < 1:
                raise ValueError("Must be at least 1")
            if num_questions > len(self.questions):
                raise ValueError(f"Only {len(self.questions)} questions available")
        except ValueError as e:
            messagebox.showerror(
                "Invalid Number",
                f"Please enter a valid number of questions (1-{len(self.questions)}).\n{e}"
            )
            return
        
        # Validate number of clients
        with self.clients_lock:
            if len(self.connected_clients) < 2:
                messagebox.showerror(
                    "Not Enough Players",
                    "At least 2 players must be connected to start the game."
                )
                return
            
            # Phase 4: Initialize game state
            self.current_question_index = 0
            self.current_answers = {}
            self.game_in_progress = True
            self.num_questions_to_play = num_questions
            
            # Phase 5: Initialize scoring state
            self.player_scores = {username: 0 for username in self.connected_clients}
            self.answer_arrival_order = []
            
            # Broadcast GAME_START to all connected clients
            self._log("=" * 40)
            self._log("STARTING GAME!")
            self._log(f"Number of questions: {num_questions}")
            self._log(f"Players: {list(self.connected_clients.keys())}")
            
            for username, client_socket in self.connected_clients.items():
                try:
                    client_socket.send("GAME_START".encode('utf-8'))
                    self._log(f"Sent GAME_START to '{username}'")
                except socket.error as e:
                    self._log(f"Error sending to '{username}': {e}")
        
        self._log("Game Started!")
        self._log("=" * 40)
        
        # Disable the Start Game button to prevent multiple starts
        self.start_game_button.config(state=tk.DISABLED)
        
        # Phase 4: Send the first question after a short delay
        # (gives clients time to process GAME_START)
        self.root.after(500, self._broadcast_current_question)
    
    def _broadcast_current_question(self):
        """
        Broadcast the current question to all connected clients.
        
        Message format: QUES|Question Text|OptionA|OptionB|OptionC
        
        This method sends the question at current_question_index to all clients.
        """
        if self.current_question_index >= self.num_questions_to_play:
            # No more questions
            return
        
        question = self.questions[self.current_question_index]
        q_num = self.current_question_index + 1
        
        # Format: QUES|question|optionA|optionB|optionC
        msg = f"QUES|{question['q']}|{question['options'][0]}|{question['options'][1]}|{question['options'][2]}"
        
        self._log(f"--- Question {q_num}/{self.num_questions_to_play} ---")
        self._log(f"Q: {question['q']}")
        self._log(f"A) {question['options'][0]}")
        self._log(f"B) {question['options'][1]}")
        self._log(f"C) {question['options'][2]}")
        self._log(f"Correct answer: {question['ans']}")
        
        with self.clients_lock:
            for username, client_socket in self.connected_clients.items():
                try:
                    client_socket.send(msg.encode('utf-8'))
                    self._log(f"Sent question {q_num} to '{username}'")
                except socket.error as e:
                    self._log(f"Error sending to '{username}': {e}")
        
        self._log("Waiting for all answers...")
    
    def _process_answer(self, username, answer):
        """
        Process an answer received from a client.
        Thread-safe method that implements barrier synchronization.
        
        Phase 5: Also tracks the order in which answers arrive for speed bonus.
        
        Args:
            username: The username of the client who answered
            answer: The answer (A, B, or C)
        """
        with self.clients_lock:
            # Only process if game is in progress
            if not self.game_in_progress:
                return
            
            # Only process if this user hasn't already answered this question
            if username in self.current_answers:
                return
            
            # Store the answer
            self.current_answers[username] = answer
            
            # Phase 5: Track the order of answers for speed bonus
            self.answer_arrival_order.append(username)
            
            self._log(f"[{username}] answered: {answer}")
            
            # Barrier check: Have all connected clients answered?
            if len(self.current_answers) == len(self.connected_clients):
                # All clients have answered - proceed to scoring
                self._all_answers_received()
    
    def _generate_scoreboard(self):
        """
        Generate a ranked scoreboard string with tie handling.
        
        Tie handling: If scores are [10, 8, 8, 5], ranks are [1, 2, 2, 4]
        
        Returns:
            str: Scoreboard string with format "rank-username-score" per line
        """
        # Sort by score descending
        sorted_players = sorted(
            self.player_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        # Generate ranks with tie handling
        scoreboard_lines = []
        current_rank = 1
        prev_score = None
        
        for i, (username, score) in enumerate(sorted_players):
            if prev_score is not None and score < prev_score:
                current_rank = i + 1
            scoreboard_lines.append(f"{current_rank}-{username}-{score}")
            prev_score = score
        
        return "\n".join(scoreboard_lines)
    
    def _broadcast_scores(self, points_this_round, correct_answer):
        """
        Send personalized SCORE| message to each client.
        
        Format: SCORE|<Result>|<PointsEarned>|<TotalScore>|<Scoreboard>
        
        Args:
            points_this_round: Dictionary {username: points_earned_this_round}
            correct_answer: The correct answer for logging
        """
        scoreboard = self._generate_scoreboard()
        
        self._log(f"Scoreboard:\n{scoreboard}")
        
        for username, client_socket in self.connected_clients.items():
            # Determine if this player was correct
            was_correct = self.current_answers.get(username) == correct_answer
            result = "Correct" if was_correct else "Wrong"
            points = points_this_round.get(username, 0)
            total = self.player_scores.get(username, 0)
            
            # Format: SCORE|Result|PointsEarned|TotalScore|Scoreboard
            msg = f"SCORE|{result}|{points}|{total}|{scoreboard}"
            
            try:
                client_socket.send(msg.encode('utf-8'))
                self._log(f"Sent score to '{username}': {result}, +{points} pts, total: {total}")
            except socket.error as e:
                self._log(f"Error sending score to '{username}': {e}")
    
    def _broadcast_disconnect(self, disconnected_username):
        """
        Broadcast a disconnect notification to all remaining connected clients.
        
        Phase 6: Notifies other players when someone leaves the game.
        
        Args:
            disconnected_username: The username of the player who disconnected
        
        Note: This method should be called while holding clients_lock.
        """
        msg = f"DISCONNECT|{disconnected_username}"
        
        for username, client_socket in self.connected_clients.items():
            try:
                client_socket.send(msg.encode('utf-8'))
            except socket.error:
                pass  # Ignore errors - they might disconnect too
        
        self._log(f"Broadcasted disconnect of '{disconnected_username}' to all clients")
    
    def _all_answers_received(self):
        """
        Called when all clients have submitted their answers (barrier reached).
        Calculates scores, broadcasts results, and moves to next question or ends game.
        
        Phase 5 Scoring:
        - Base Points: +1 for correct answer
        - Speed Bonus: First correct answerer gets (num_players - 1) bonus points
        
        Note: This method is called while holding clients_lock.
        """
        q_num = self.current_question_index + 1
        self._log(f"All answers received for Question {q_num}")
        
        # Get correct answer for this question
        correct_answer = self.questions[self.current_question_index]['ans']
        self._log(f"Answers: {self.current_answers}")
        self._log(f"Correct: {correct_answer}")
        self._log(f"Answer order: {self.answer_arrival_order}")
        
        # ===== Phase 5: Scoring =====
        points_this_round = {}
        
        # Base points: +1 for correct answer
        for username, answer in self.current_answers.items():
            if answer == correct_answer:
                self.player_scores[username] += 1
                points_this_round[username] = 1
                self._log(f"{username}: +1 base point (correct)")
            else:
                points_this_round[username] = 0
                self._log(f"{username}: 0 points (wrong)")
        
        # Speed bonus: First correct answerer gets (n-1) bonus points
        for username in self.answer_arrival_order:
            if self.current_answers.get(username) == correct_answer:
                bonus = len(self.connected_clients) - 1
                self.player_scores[username] += bonus
                points_this_round[username] += bonus
                self._log(f"Speed bonus: {username} gets +{bonus} points (answered first correctly)!")
                break  # Only the first correct answerer gets the bonus
        
        # Broadcast scores to all clients
        self._broadcast_scores(points_this_round, correct_answer)
        
        # Clear answers and order for next question
        self.current_answers.clear()
        self.answer_arrival_order.clear()
        
        # Move to next question
        self.current_question_index += 1
        
        if self.current_question_index < self.num_questions_to_play:
            # More questions - broadcast next after a short delay
            self._log("-" * 30)
            # Schedule next question on main thread
            self.root.after(2000, self._broadcast_current_question)
        else:
            # No more questions - game over
            self._end_game()
    
    def _end_game(self):
        """
        End the game and notify all clients.
        Shows final scoreboard and resets all game state for potential new games.
        
        Phase 6: Full state reset to allow starting new games without restarting server.
        
        Note: This method is called while holding clients_lock.
        """
        self._log("=" * 40)
        self._log("GAME OVER!")
        self._log("Final Scores:")
        
        # Log final scoreboard (only if there are scores)
        if self.player_scores:
            final_scoreboard = self._generate_scoreboard()
            for line in final_scoreboard.split("\n"):
                self._log(f"  {line}")
        else:
            self._log("  No scores recorded")
        
        self._log("=" * 40)
        
        # Broadcast GAME_OVER to all clients
        for username, client_socket in self.connected_clients.items():
            try:
                client_socket.send("GAME_OVER".encode('utf-8'))
                self._log(f"Sent GAME_OVER to '{username}'")
            except socket.error as e:
                self._log(f"Error sending to '{username}': {e}")
        
        # Phase 6: Full state reset for new games
        self.game_in_progress = False
        self.current_question_index = 0
        self.current_answers.clear()
        self.answer_arrival_order.clear()
        self.player_scores.clear()
        self.num_questions_to_play = 0
        
        self._log("Game state reset. Ready for new game.")
        
        # Re-check start conditions (can start new game now)
        self._check_start_conditions()
    
    def _start_server(self):
        """
        Start the TCP server on the specified port.
        Called when the 'Start Server' button is clicked.
        """
        # Get the port number from the entry field
        port_str = self.port_entry.get().strip()
        
        # Validate port number
        try:
            port = int(port_str)
            if port < 1 or port > 65535:
                raise ValueError("Port out of range")
        except ValueError:
            messagebox.showerror("Invalid Port", "Please enter a valid port number (1-65535).")
            return
        
        try:
            # Create the TCP socket
            # AF_INET = IPv4, SOCK_STREAM = TCP
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            
            # Allow reuse of the address to enable quick server restarts
            # Without this, you might get "Address already in use" errors
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # Bind to all interfaces (0.0.0.0) on the specified port
            self.server_socket.bind(('0.0.0.0', port))
            
            # Start listening for incoming connections
            # The argument specifies the backlog (max queued connections)
            self.server_socket.listen(5)
            
            self._log(f"Server started on 0.0.0.0:{port}")
            self._log("Waiting for connections...")
            
            # Disable the start button and port entry to prevent multiple starts
            self.start_button.config(state=tk.DISABLED)
            self.port_entry.config(state=tk.DISABLED)
            
            # Set the running flag
            self.is_running = True
            
            # Start the listener thread
            # IMPORTANT: This is where threading prevents GUI freezing!
            # The accept() call in _listen_for_clients() is blocking.
            # By running it in a separate thread, the main thread remains free
            # to handle GUI events (button clicks, window updates, etc.)
            listener_thread = threading.Thread(target=self._listen_for_clients, daemon=True)
            listener_thread.start()
            
        except socket.error as e:
            self._log(f"Error starting server: {e}")
            messagebox.showerror("Socket Error", f"Failed to start server: {e}")
    
    def _listen_for_clients(self):
        """
        Listen for incoming client connections.
        
        This method runs in a separate thread because socket.accept() is BLOCKING.
        If this ran in the main thread, the GUI would freeze completely while
        waiting for a client to connect. The Tkinter mainloop() wouldn't be able
        to process any events, making the window unresponsive.
        
        By running this in a daemon thread:
        1. The main thread continues running mainloop(), keeping the GUI responsive
        2. This thread independently waits for connections
        3. When a client connects, we spawn a new thread to handle that client
        4. The daemon=True flag ensures this thread dies when the main window closes
        """
        while self.is_running:
            try:
                # accept() BLOCKS here until a client connects
                # This is why we need a separate thread!
                client_socket, client_address = self.server_socket.accept()
                
                # Extract client IP and port for logging
                client_ip = client_address[0]
                client_port = client_address[1]
                
                # Log the connection to the GUI
                self._log(f"Client connected: {client_ip}:{client_port}")
                
                # Phase 2: Spawn a new thread to handle this client
                # This allows multiple clients to connect simultaneously
                client_thread = threading.Thread(
                    target=self._handle_client,
                    args=(client_socket, client_address),
                    daemon=True
                )
                client_thread.start()
                
            except socket.error as e:
                # Only log if the server is still supposed to be running
                # (avoids error spam when shutting down)
                if self.is_running:
                    self._log(f"Socket error: {e}")
                break
    
    def _handle_client(self, client_socket, client_address):
        """
        Handle an individual client connection with authentication.
        
        This method runs in its own thread for each connected client.
        
        Phase 2 Authentication Flow:
        1. Wait to receive the username from the client
        2. Check if the username is already taken
        3. If taken: send "REJECT" and close connection
        4. If unique: send "OK" and keep connection open for future messages
        
        Phase 4 additions:
        - Handle "ANS:" prefixed messages for answer submission
        
        Args:
            client_socket: The socket object for this client
            client_address: Tuple of (IP, port) for this client
        """
        client_ip = client_address[0]
        client_port = client_address[1]
        username = None
        
        try:
            # ===== Phase 2: Authentication =====
            # Wait for the client to send their username
            # recv() BLOCKS until data is received
            username_data = client_socket.recv(1024)
            
            if not username_data:
                # Client disconnected before sending username
                self._log(f"Client {client_ip}:{client_port} disconnected before authentication")
                client_socket.close()
                return
            
            username = username_data.decode('utf-8').strip()
            self._log(f"Received username: '{username}' from {client_ip}:{client_port}")
            
            # Check if username is unique (thread-safe)
            with self.clients_lock:
                if username in self.connected_clients:
                    # Username is taken - reject the connection
                    self._log(f"Username '{username}' is already taken. Rejecting connection.")
                    client_socket.send("REJECT".encode('utf-8'))
                    client_socket.close()
                    self._log(f"Connection closed with {client_ip}:{client_port}")
                    self._log("-" * 40)
                    return
                else:
                    # Username is unique - accept the connection
                    self.connected_clients[username] = client_socket
                    self._log(f"Username '{username}' accepted. Client added to lobby.")
            
            # Send OK response to client
            client_socket.send("OK".encode('utf-8'))
            self._log(f"Sent 'OK' to {username}")
            self._log(f"Connected clients: {list(self.connected_clients.keys())}")
            
            # Phase 3: Check if we can enable Start Game button
            self._check_start_conditions()
            
            # ===== Main Client Loop =====
            # Keep connection open for future game messages
            while self.is_running:
                data = client_socket.recv(1024)
                
                if data:
                    message = data.decode('utf-8')
                    
                    # Phase 4: Handle answer messages
                    if message.startswith("ANS:"):
                        # Extract the answer (A, B, or C)
                        answer = message[4:].strip().upper()
                        self._process_answer(username, answer)
                    else:
                        # Log other messages
                        self._log(f"[{username}]: {message}")
                else:
                    # Client disconnected
                    self._log(f"Client '{username}' disconnected")
                    break
                    
        except socket.error as e:
            if self.is_running:
                self._log(f"Error with client {client_ip}:{client_port}: {e}")
        
        finally:
            # Cleanup: Remove client from connected list and close socket
            if username:
                with self.clients_lock:
                    if username in self.connected_clients:
                        del self.connected_clients[username]
                        self._log(f"Removed '{username}' from connected clients")
                        self._log(f"Connected clients: {list(self.connected_clients.keys())}")
                        
                        # Phase 6: Broadcast disconnect notification to remaining clients
                        self._broadcast_disconnect(username)
                        
                        # Phase 6: Handle mid-game disconnection
                        if self.game_in_progress:
                            self._log(f"Player '{username}' left during active game!")
                            
                            # Remove from scores if present
                            if username in self.player_scores:
                                del self.player_scores[username]
                                self._log(f"Removed '{username}' from scoreboard")
                            
                            # Remove from current answers if present
                            if username in self.current_answers:
                                del self.current_answers[username]
                                self._log(f"Removed '{username}' from current answers")
                            
                            # Remove from answer order if present
                            if username in self.answer_arrival_order:
                                self.answer_arrival_order.remove(username)
                            
                            # Check minimum players (need at least 2 to continue)
                            if len(self.connected_clients) < 2:
                                self._log("Not enough players remaining! Ending game...")
                                self._end_game()
                            else:
                                # Game continues - check if barrier is now met
                                # (disconnected player might have been the one we were waiting for)
                                if len(self.current_answers) > 0 and len(self.current_answers) >= len(self.connected_clients):
                                    self._log("All remaining players have answered. Proceeding...")
                                    self._all_answers_received()
                
                # Phase 3: Re-check start conditions after client disconnect
                self._check_start_conditions()
            
            try:
                client_socket.close()
            except socket.error:
                pass
            
            self._log("-" * 40)
    
    def _on_closing(self):
        """
        Handle the window close event.
        Properly cleanup all sockets before destroying the window.
        """
        self.is_running = False
        self.game_in_progress = False
        
        # Close all client connections
        with self.clients_lock:
            for username, client_socket in self.connected_clients.items():
                try:
                    client_socket.close()
                except socket.error:
                    pass
            self.connected_clients.clear()
        
        # Close the server socket
        if self.server_socket:
            try:
                self.server_socket.close()
            except socket.error:
                pass  # Ignore errors during cleanup
        
        self.root.destroy()


def main():
    """
    Application entry point.
    Creates the Tkinter root window and starts the server application.
    """
    root = tk.Tk()
    app = QuizServer(root)
    
    # Start the Tkinter main event loop
    # This runs in the main thread and handles all GUI events
    root.mainloop()


if __name__ == "__main__":
    main()
