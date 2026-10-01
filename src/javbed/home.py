"""Home dashboard widgets."""

from PySide6.QtCore import QThreadPool, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from .jobs import Job
from .artwork import cached_art

class HomePage(QWidget):
    def __init__(self, window, snapshot):
        super().__init__()
        self.window = window
        self.snapshot = snapshot
        self.pool = QThreadPool.globalInstance()
        self.refresh_job = None
        self.latest = None
        root = QVBoxLayout(self)
        root.setContentsMargins(36, 28, 36, 28)
        root.setSpacing(14)
        top = QHBoxLayout()
        title = QLabel("HOME")
        title.setObjectName("heroTitle")
        top.addWidget(title)
        top.addStretch()
        self.refresh_button = QPushButton("REFRESH")
        self.refresh_button.setObjectName("secondary")
        self.refresh_button.clicked.connect(self.refresh)
        top.addWidget(self.refresh_button)
        root.addLayout(top)
        self.summary = QLabel("JAVBED launcher overview")
        self.summary.setObjectName("small")
        root.addWidget(self.summary)

        featured = QHBoxLayout()
        account_frame = QFrame()
        account_frame.setObjectName("hero")
        account_layout = QVBoxLayout(account_frame)
        account_layout.addWidget(QLabel("ACTIVE ACCOUNT"))
        account_row = QHBoxLayout()
        self.account_avatar = QLabel()
        self.account_avatar.setFixedSize(48, 48)
        account_row.addWidget(self.account_avatar)
        self.account_label = QLabel("No Java account")
        self.account_label.setWordWrap(True)
        account_row.addWidget(self.account_label, 1)
        account_layout.addLayout(account_row)
        account_button = QPushButton("SWITCH / ADD ACCOUNT")
        account_button.setObjectName("secondary")
        account_button.clicked.connect(self.window.open_accounts)
        account_layout.addWidget(account_button)
        featured.addWidget(account_frame, 1)

        continue_frame = QFrame()
        continue_frame.setObjectName("hero")
        continue_layout = QVBoxLayout(continue_frame)
        continue_layout.addWidget(QLabel("CONTINUE PLAYING"))
        self.continue_icon = QLabel()
        self.continue_icon.setFixedSize(56, 56)
        continue_layout.addWidget(self.continue_icon)
        self.continue_label = QLabel("Play a game to start your history.")
        self.continue_label.setWordWrap(True)
        continue_layout.addWidget(self.continue_label, 1)
        self.continue_button = QPushButton("PLAY")
        self.continue_button.setObjectName("play")
        self.continue_button.setEnabled(False)
        self.continue_button.clicked.connect(self.continue_playing)
        continue_layout.addWidget(self.continue_button)
        featured.addWidget(continue_frame, 2)
        root.addLayout(featured)

        recent_frame = QFrame()
        recent_frame.setObjectName("hero")
        recent_layout = QVBoxLayout(recent_frame)
        recent_layout.addWidget(QLabel("RECENTLY PLAYED"))
        self.recent_label = QLabel("No sessions recorded yet.")
        recent_layout.addWidget(self.recent_label)
        self.recent_buttons = []
        recent_row = QHBoxLayout()
        for _ in range(4):
            button = QPushButton()
            button.setObjectName("secondary")
            button.hide()
            button.clicked.connect(lambda checked=False, widget=button: self.play_item(widget.property("history_item")))
            recent_row.addWidget(button)
            self.recent_buttons.append(button)
        recent_layout.addLayout(recent_row)
        root.addWidget(recent_frame)

        cards = QHBoxLayout()
        self.games_card = self.card("GAMES")
        self.engines_card = self.card("ENGINES")
        self.servers_card = self.card("SERVERS")
        for card in (self.games_card, self.engines_card, self.servers_card):
            cards.addWidget(card[0])
        root.addLayout(cards)
        quick=QFrame();quick.setObjectName("hero");q=QVBoxLayout(quick);qt=QLabel("QUICK LAUNCH");qt.setObjectName("game");q.addWidget(qt);row=QHBoxLayout()
        for label in ("Java","Bedrock","EDU","LCE","Dungeons","Dungeons 2","Legends","Story Mode"):
            b=QPushButton(label);b.setObjectName("secondary")
            b.clicked.connect(lambda checked=False,name=label:self.quick_launch(name));row.addWidget(b)
        q.addLayout(row);root.addWidget(quick)
        self.details=QPlainTextEdit();self.details.setReadOnly(True);self.details.setMaximumHeight(125);root.addWidget(self.details);root.addStretch();QTimer.singleShot(500,self.refresh)
    def card(self,title):
        frame=QFrame();frame.setObjectName("hero");layout=QVBoxLayout(frame);head=QLabel(title);head.setObjectName("small");value=QLabel("…");value.setObjectName("game");layout.addWidget(head);layout.addWidget(value);return frame,value
    def quick_launch(self,name):
        if name=="Story Mode":
            page=self.window.story_page
            if not page.detect() and page.detect(1-page.season.currentIndex()):
                page.season.setCurrentIndex(1-page.season.currentIndex())
            if page.detect():
                page.launch()
                return
        self.window.select_name(name)
    def continue_playing(self):
        self.play_item(self.latest)
    def play_item(self, item):
        if not item:
            return
        game = item["game"]
        instance = item.get("instance", "")
        if game == "Java" and instance:
            self.window.select_name("Java")
            self.window.java_page.run(["instance", "launch", instance], target=self.window.java_page.instance_output)
        elif game in ("Dungeons", "Dungeons 2", "Legends"):
            self.window.select_name(game)
            self.window.pages[("Home","Java","Bedrock","EDU","LCE","Dungeons","Dungeons 2","Legends","Story Mode","Servers","Updates","Settings").index(game)].launch()
        elif game.startswith("Story Mode"):
            page = self.window.story_page
            page.season.setCurrentIndex(1 if game.endswith("2") else 0)
            self.window.select_name("Story Mode")
            page.launch()
        elif game in ("Java", "Bedrock") and item.get("version"):
            self.window.select_name(game)
            page = self.window.pages[("Home", "Java", "Bedrock").index(game)]
            page.run([item.get("channel") or "release", item["version"]])
        elif game == "EDU" and item.get("version"):
            self.window.select_name(game)
            self.window.pages[3].run([item["version"]])
        elif game == "LCE":
            self.window.select_name(game)
            self.window.pages[4].lce()
        else:
            self.window.select_name(game)
    def refresh(self):
        if self.refresh_job:return
        self.refresh_button.setEnabled(False);self.summary.setText("Checking your games...")
        job=Job(self.snapshot);self.refresh_job=job
        def done(ok,result):
            self.refresh_job=None;self.refresh_button.setEnabled(True)
            if not ok:self.summary.setText("Could not refresh: "+str(result));return
            installed,statuses,server_count,running_count,server_text,account,avatar,played=result
            self.summary.setText("Your Minecraft games and editions")
            self.games_card[1].setText(f"{len(installed)}/9 detected")
            healthy=sum(1 for _,path,_ in statuses if path);self.engines_card[1].setText(f"{healthy}/{len(statuses)} ready")
            self.servers_card[1].setText(f"{running_count}/{server_count} running" if server_count is not None else "Unavailable")
            self.account_label.setText((account["username"] + "\nAlias: " + account["alias"]) if account else "No Java account")
            self.account_avatar.setPixmap(QPixmap(avatar).scaled(48,48) if avatar else QPixmap())
            self.window.update_account(account, avatar)
            self.latest = played[0] if played else None
            self.continue_button.setEnabled(bool(self.latest))
            art = cached_art(self.latest["game"] if self.latest else "")
            self.continue_icon.setPixmap(QPixmap(str(art)).scaled(56,56) if art else QPixmap())
            if self.latest:
                item = self.latest
                title = item["instance"] or item["game"]
                details = [item["game"], item.get("version", ""), item.get("loader", ""), item["last_played"][:16].replace("T", " "), f'{item["total_seconds"] // 60} min played']
                self.continue_label.setText(title + "\n" + " · ".join(value for value in details if value))
                self.recent_label.setText("")
            else:
                self.continue_label.setText("Play a game to start your history.")
                self.recent_label.setText("No sessions recorded yet.")
            for button, item in zip(self.recent_buttons, played[:4]):
                button.setProperty("history_item", item)
                button.setText((item["instance"] or item["game"]) + "\n" + item["last_played"][:10])
                art = cached_art(item["game"])
                button.setIcon(QIcon(str(art)) if art else QIcon())
                button.show()
            for button in self.recent_buttons[len(played[:4]):]:
                button.hide()
            engine_lines=[f"{label}: {path or 'not configured'}" for label,path,_ in statuses]
            self.details.setPlainText("Detected launch targets: "+(", ".join(installed) if installed else "none")+"\n\n"+server_text+"\n\n" + "\n".join(engine_lines))
        job.signals.done.connect(done);self.pool.start(job)

