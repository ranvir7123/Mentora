import QtQuick
import Theme
import "../components"

// Your question and its answer, under the step. While the answer is coming it says so, but only once it
// has taken more than 200 ms, so a quick answer never flashes a waiting line. When no answer can come,
// a calm line in the quieter colour says what still works.
Card {
    id: root
    property var ask: ({ "state": "idle", "question": "", "answer": "" })

    readonly property bool thinking: ask.state === "thinking"
    property bool slow: false

    onThinkingChanged: {
        slow = false
        if (thinking)
            wait.restart()
    }
    Component.onCompleted: if (thinking) wait.restart()
    Timer { id: wait; interval: 200; onTriggered: root.slow = root.thinking }

    spacing: Theme.space8
    Accessible.role: Accessible.Grouping
    Accessible.name: "Your question"

    Text {
        width: parent.width
        text: root.ask.question
        wrapMode: Text.Wrap
        color: Theme.muted
        font.family: Theme.fontBody
        font.weight: Font.Bold
        font.pixelSize: Theme.size14
    }

    Text {
        visible: root.thinking ? root.slow : text !== ""
        width: parent.width
        text: root.thinking ? "Thinking about your question…" : root.ask.answer
        wrapMode: Text.Wrap
        color: root.thinking || root.ask.state === "error" ? Theme.muted : Theme.text
        font.family: Theme.fontBody
        font.pixelSize: Theme.size16
    }
}
