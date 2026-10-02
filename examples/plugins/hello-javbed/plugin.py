from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from javbed_plugin_api import JavbedPlugin


class HelloPlugin(JavbedPlugin):
    def on_load(self, context):
        self.context = context
        context.logger.info("Hello JAVBED loaded")
        context.events.subscribe("javbed.started", self.on_started)
        context.commands.register(
            id="example.hello",
            title="Say Hello",
            description="Show a greeting from the example plugin",
            keywords=("example", "greeting"),
            callback=self.say_hello,
        )
        context.ui.register_page(
            id="example.hello-page", title="Hello", widget_factory=self.make_page
        )

    def on_started(self, **_data):
        self.context.logger.info("JAVBED started")

    def say_hello(self):
        count = int(self.context.settings.get("greetings", 0)) + 1
        self.context.settings.set("greetings", count)
        self.context.notifications.show(title="Hello JAVBED", message=f"Greeting #{count}")

    def make_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("Hello from a third-party JAVBED plugin."))
        button = QPushButton("SAY HELLO")
        button.setObjectName("play")
        button.clicked.connect(self.say_hello)
        layout.addWidget(button)
        layout.addStretch()
        return page


def create_plugin():
    return HelloPlugin()
