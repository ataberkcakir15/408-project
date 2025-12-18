import socket
import threading
import tkinter as tk
from tkinter import messagebox, filedialog


class QuizServer:
    def __init__(self, root):
        self.root = root
        self.root.title("SUquid Quiz Games - Server")
        self.root.geometry("550x500")
        self.root.resizable(True, True)
        self.server_socket = None
        self.is_running = False
        self.connected_clients = {}
        self.clients_lock = threading.Lock()
        self.questions = []
        self.current_question_index = 0
        self.current_answers = {}
        self.game_in_progress = False
        self.num_questions_to_play = 0
        self.player_scores = {}
        self.answer_arrival_order = []
        self._create_widgets()

    def _create_widgets(self):
        config_frame = tk.Frame(self.root, padx=10, pady=10)
        config_frame.pack(fill=tk.X)
        port_label = tk.Label(config_frame, text="Port Number:")
        port_label.pack(side=tk.LEFT)
        self.port_entry = tk.Entry(config_frame, width=10)
        self.port_entry.pack(side=tk.LEFT, padx=(5, 10))
        self.port_entry.insert(0, "12345")
        self.start_button = tk.Button(
            config_frame,
            text="Start Server",
            command=self._start_server
        )
        self.start_button.pack(side=tk.LEFT)
        game_frame = tk.Frame(self.root, padx=10, pady=5)
        game_frame.pack(fill=tk.X)
        self.load_questions_button = tk.Button(
            game_frame,
            text="Load Questions File",
            command=self._load_questions
        )
        self.load_questions_button.pack(side=tk.LEFT)
        num_questions_label = tk.Label(game_frame, text="# Questions:")
        num_questions_label.pack(side=tk.LEFT, padx=(15, 0))
        self.num_questions_entry = tk.Entry(game_frame, width=5)
        self.num_questions_entry.pack(side=tk.LEFT, padx=(5, 15))
        self.num_questions_entry.insert(0, "5")
        self.start_game_button = tk.Button(
            game_frame,
            text="Start Game",
            command=self._start_game,
            state=tk.DISABLED
        )
        self.start_game_button.pack(side=tk.LEFT)
        log_frame = tk.Frame(self.root, padx=10, pady=10)
        log_frame.pack(fill=tk.BOTH, expand=True)
        log_label = tk.Label(log_frame, text="Server Log:")
        log_label.pack(anchor=tk.W)
        scrollbar = tk.Scrollbar(log_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_listbox = tk.Listbox(
            log_frame,
            height=15,
            width=60,
            yscrollcommand=scrollbar.set
        )
        self.log_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.log_listbox.yview)
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _log(self, message):
        self.root.after(0, lambda: self._append_log(message))

    def _append_log(self, message):
        self.log_listbox.insert(tk.END, message)
        self.log_listbox.see(tk.END)

    def _load_questions(self):
        file_path = filedialog.askopenfilename(
            title="Select Questions File",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if not file_path:
            return
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f.readlines() if line.strip()]
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
                    'q': lines[i],
                    'options': [
                        lines[i + 1],
                        lines[i + 2],
                        lines[i + 3]
                    ],
                    'ans': lines[i + 4].split(":")[-1].strip().upper()
                }
                self.questions.append(question_dict)
            self._log(f"Loaded {len(self.questions)} questions from file")
            self.num_questions_entry.delete(0, tk.END)
            self.num_questions_entry.insert(0, str(len(self.questions)))
            self._check_start_conditions()
        except Exception as e:
            self._log(f"Error loading questions: {e}")
            messagebox.showerror("Error", f"Failed to load questions file:\n{e}")

    def _check_start_conditions(self):
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

        self.root.after(0, update_button)

    def _start_game(self):
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
        with self.clients_lock:
            if len(self.connected_clients) < 2:
                messagebox.showerror(
                    "Not Enough Players",
                    "At least 2 players must be connected to start the game."
                )
                return
            self.current_question_index = 0
            self.current_answers = {}
            self.game_in_progress = True
            self.num_questions_to_play = num_questions
            self.player_scores = {username: 0 for username in self.connected_clients}
            self.answer_arrival_order = []
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
        self.start_game_button.config(state=tk.DISABLED)
        self.root.after(500, self._broadcast_current_question)

    def _broadcast_current_question(self):
        if self.current_question_index >= self.num_questions_to_play:
            return
        question = self.questions[self.current_question_index]
        q_num = self.current_question_index + 1
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
        with self.clients_lock:
            if not self.game_in_progress:
                return
            if username in self.current_answers:
                return
            self.current_answers[username] = answer
            self.answer_arrival_order.append(username)
            self._log(f"[{username}] answered: {answer}")
            if len(self.current_answers) == len(self.connected_clients):
                self._all_answers_received()

    def _generate_scoreboard(self):
        sorted_players = sorted(
            self.player_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )
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
        scoreboard = self._generate_scoreboard()
        self._log(f"Scoreboard:\n{scoreboard}")
        for username, client_socket in self.connected_clients.items():
            was_correct = self.current_answers.get(username) == correct_answer
            result = "Correct" if was_correct else "Wrong"
            points = points_this_round.get(username, 0)
            total = self.player_scores.get(username, 0)
            msg = f"SCORE|{result}|{points}|{total}|{scoreboard}"
            try:
                client_socket.send(msg.encode('utf-8'))
                self._log(f"Sent score to '{username}': {result}, +{points} pts, total: {total}")
            except socket.error as e:
                self._log(f"Error sending score to '{username}': {e}")

    def _broadcast_disconnect(self, disconnected_username):
        msg = f"DISCONNECT|{disconnected_username}"
        for username, client_socket in self.connected_clients.items():
            try:
                client_socket.send(msg.encode('utf-8'))
            except socket.error:
                pass
        self._log(f"Broadcasted disconnect of '{disconnected_username}' to all clients")

    def _all_answers_received(self):
        q_num = self.current_question_index + 1
        self._log(f"All answers received for Question {q_num}")
        correct_answer = self.questions[self.current_question_index]['ans']
        self._log(f"Answers: {self.current_answers}")
        self._log(f"Correct: {correct_answer}")
        self._log(f"Answer order: {self.answer_arrival_order}")
        points_this_round = {}
        for username, answer in self.current_answers.items():
            if answer == correct_answer:
                self.player_scores[username] += 1
                points_this_round[username] = 1
                self._log(f"{username}: +1 base point (correct)")
            else:
                points_this_round[username] = 0
                self._log(f"{username}: 0 points (wrong)")
        for username in self.answer_arrival_order:
            if self.current_answers.get(username) == correct_answer:
                bonus = len(self.connected_clients) - 1
                self.player_scores[username] += bonus
                points_this_round[username] += bonus
                self._log(f"Speed bonus: {username} gets +{bonus} points (answered first correctly)!")
                break
        self._broadcast_scores(points_this_round, correct_answer)
        self.current_answers.clear()
        self.answer_arrival_order.clear()
        self.current_question_index += 1
        if self.current_question_index < self.num_questions_to_play:
            self._log("-" * 30)
            self.root.after(2000, self._broadcast_current_question)
        else:
            self._end_game()

    def _end_game(self):
        self._log("=" * 40)
        self._log("GAME OVER!")
        self._log("Final Scores:")
        if self.player_scores:
            final_scoreboard = self._generate_scoreboard()
            for line in final_scoreboard.split("\n"):
                self._log(f"  {line}")
        else:
            self._log("  No scores recorded")
        self._log("=" * 40)
        for username, client_socket in self.connected_clients.items():
            try:
                client_socket.send("GAME_OVER".encode('utf-8'))
                self._log(f"Sent GAME_OVER to '{username}'")
            except socket.error as e:
                self._log(f"Error sending to '{username}': {e}")
        self.game_in_progress = False
        self.current_question_index = 0
        self.current_answers.clear()
        self.answer_arrival_order.clear()
        self.player_scores.clear()
        self.num_questions_to_play = 0
        self._log("Game state reset. Ready for new game.")
        self._check_start_conditions()

    def _start_server(self):
        port_str = self.port_entry.get().strip()
        try:
            port = int(port_str)
            if port < 1 or port > 65535:
                raise ValueError("Port out of range")
        except ValueError:
            messagebox.showerror("Invalid Port", "Please enter a valid port number (1-65535).")
            return
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('0.0.0.0', port))
            self.server_socket.listen(5)
            self._log(f"Server started on 0.0.0.0:{port}")
            self._log("Waiting for connections...")
            self.start_button.config(state=tk.DISABLED)
            self.port_entry.config(state=tk.DISABLED)
            self.is_running = True
            listener_thread = threading.Thread(target=self._listen_for_clients, daemon=True)
            listener_thread.start()
        except socket.error as e:
            self._log(f"Error starting server: {e}")
            messagebox.showerror("Socket Error", f"Failed to start server: {e}")

    def _listen_for_clients(self):
        while self.is_running:
            try:
                client_socket, client_address = self.server_socket.accept()
                client_ip = client_address[0]
                client_port = client_address[1]
                self._log(f"Client connected: {client_ip}:{client_port}")
                client_thread = threading.Thread(
                    target=self._handle_client,
                    args=(client_socket, client_address),
                    daemon=True
                )
                client_thread.start()
            except socket.error as e:
                if self.is_running:
                    self._log(f"Socket error: {e}")
                break

    def _handle_client(self, client_socket, client_address):
        client_ip = client_address[0]
        client_port = client_address[1]
        username = None
        try:
            username_data = client_socket.recv(1024)
            if not username_data:
                self._log(f"Client {client_ip}:{client_port} disconnected before authentication")
                client_socket.close()
                return
            username = username_data.decode('utf-8').strip()
            self._log(f"Received username: '{username}' from {client_ip}:{client_port}")
            with self.clients_lock:
                if username in self.connected_clients:
                    self._log(f"Username '{username}' is already taken. Rejecting connection.")
                    client_socket.send("REJECT".encode('utf-8'))
                    client_socket.close()
                    self._log(f"Connection closed with {client_ip}:{client_port}")
                    self._log("-" * 40)
                    return
                else:
                    self.connected_clients[username] = client_socket
                    self._log(f"Username '{username}' accepted. Client added to lobby.")
            client_socket.send("OK".encode('utf-8'))
            self._log(f"Sent 'OK' to {username}")
            self._log(f"Connected clients: {list(self.connected_clients.keys())}")
            self._check_start_conditions()
            while self.is_running:
                data = client_socket.recv(1024)
                if data:
                    message = data.decode('utf-8')
                    if message.startswith("ANS:"):
                        answer = message[4:].strip().upper()
                        self._process_answer(username, answer)
                    else:
                        self._log(f"[{username}]: {message}")
                else:
                    self._log(f"Client '{username}' disconnected")
                    break
        except socket.error as e:
            if self.is_running:
                self._log(f"Error with client {client_ip}:{client_port}: {e}")
        finally:
            if username:
                with self.clients_lock:
                    if username in self.connected_clients:
                        del self.connected_clients[username]
                        self._log(f"Removed '{username}' from connected clients")
                        self._log(f"Connected clients: {list(self.connected_clients.keys())}")
                        self._broadcast_disconnect(username)
                        if self.game_in_progress:
                            self._log(f"Player '{username}' left during active game!")
                            if username in self.player_scores:
                                del self.player_scores[username]
                                self._log(f"Removed '{username}' from scoreboard")
                            if username in self.current_answers:
                                del self.current_answers[username]
                                self._log(f"Removed '{username}' from current answers")
                            if username in self.answer_arrival_order:
                                self.answer_arrival_order.remove(username)
                            if len(self.connected_clients) < 2:
                                self._log("Not enough players remaining! Ending game...")
                                self._end_game()
                            else:
                                if len(self.current_answers) > 0 and len(self.current_answers) >= len(self.connected_clients):
                                    self._log("All remaining players have answered. Proceeding...")
                                    self._all_answers_received()
                self._check_start_conditions()
            try:
                client_socket.close()
            except socket.error:
                pass
            self._log("-" * 40)

    def _on_closing(self):
        self.is_running = False
        self.game_in_progress = False
        with self.clients_lock:
            for username, client_socket in self.connected_clients.items():
                try:
                    client_socket.close()
                except socket.error:
                    pass
            self.connected_clients.clear()
        if self.server_socket:
            try:
                self.server_socket.close()
            except socket.error:
                pass
        self.root.destroy()


def main():
    root = tk.Tk()
    app = QuizServer(root)
    root.mainloop()


if __name__ == "__main__":
    main()
