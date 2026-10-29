import QtQuick
import QtQuick.Window
import Theme

// Type a question about the step and press Enter (or Ask). The panel never takes the keyboard from the
// app, except while you are typing here: `typing(true)` asks for it as you press into the box, and
// `typing(false)` gives it back when you leave.
Item {
    id: root
    property bool busy: false           // a question is being answered
    signal ask(string question)
    signal typing(bool on)

    function send() {
        const question = input.text.trim()
        if (question === "" || busy)
            return
        root.ask(question)
        input.text = ""
    }

    implicitWidth: 328
    implicitHeight: 48

    Rectangle {
        id: field
        width: parent.width - button.width - Theme.space8
        height: parent.height
        radius: Theme.radiusMedium
        color: Theme.surface1
        border.width: 2
        border.color: input.activeFocus ? Theme.text : Theme.border

        TextInput {
            id: input
            x: Theme.space16
            width: parent.width - 2 * Theme.space16
            height: parent.height
            verticalAlignment: TextInput.AlignVCenter
            clip: true
            maximumLength: 300
            selectByMouse: true
            color: Theme.text
            selectionColor: Theme.border
            selectedTextColor: Theme.text
            font.family: Theme.fontBody
            font.pixelSize: Theme.size16
            Accessible.role: Accessible.EditableText
            Accessible.name: "Ask about this step"
            onAccepted: root.send()
            onActiveFocusChanged: root.typing(activeFocus)
        }

        Text {
            visible: input.text === "" && !input.activeFocus
            x: Theme.space16
            width: parent.width - 2 * Theme.space16
            anchors.verticalCenter: parent.verticalCenter
            text: "Ask about this step"
            elide: Text.ElideRight
            color: Theme.muted
            font.family: Theme.fontBody
            font.pixelSize: Theme.size16
        }

        // A press asks for the keyboard first, then goes on to the text so it lands the cursor.
        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.IBeamCursor
            onPressed: (mouse) => {
                root.typing(true)
                if (root.Window.window)
                    root.Window.window.requestActivate()
                input.forceActiveFocus()
                mouse.accepted = false
            }
        }
    }

    ChunkyButton {
        id: button
        anchors.right: parent.right
        width: 80
        height: parent.height
        kind: "quiet"
        text: "Ask"
        enabled: input.text.trim() !== "" && !root.busy
        onClicked: root.send()
    }
}
